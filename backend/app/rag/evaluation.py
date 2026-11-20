"""RAG evaluation: basic vs reranked vs adaptive on the labelled benchmark.

Retrieval (always measured, document-level relevance labels):
  Precision@K   share of the top-K passages that come from a relevant document
  Recall@K      share of a question's relevant documents that appear in the top-K passages
  Hit@K         share of questions with at least one relevant passage in the top-K ("retrieval relevance")
  MRR           mean reciprocal rank of the first relevant passage
  Abstention    unanswerable questions correctly reported as "insufficient evidence";
                answerable questions wrongly refused (false abstention)

Generation (measured only when an LLM is configured; otherwise reported as not measured):
  Faithfulness         share of answer claims the verifier marks "supported" by the retrieved passages
  Answer relevance     key-point coverage: share of reference key points semantically matched by an answer sentence
  Citation correctness share of [n] citations that point to an existing passage from a labelled relevant document
  Context utilisation  share of provided passages that the answer cites at least once

Usage (from backend/):  python -m app.rag.evaluation [--k 4] [--no-generation]
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import statistics as st
import time
from datetime import datetime, timezone

import numpy as np

from app.core.config import PROJECT_ROOT, get_settings
from app.rag import generator
from app.rag.pipeline import answer_question
from app.rag.retriever import get_retriever
from app.rag.verifier import split_sentences

log = logging.getLogger("rag.eval")
STRATEGIES = ("basic", "reranked", "adaptive")
BENCH = PROJECT_ROOT / "data" / "external" / "rag_benchmark.json"
KEYPOINT_T = 0.5


def retrieval_metrics(evidence_docs: list[str], relevant: set[str], k: int) -> dict:
    top = evidence_docs[:k]
    hits = [d in relevant for d in top]
    first = next((i for i, h in enumerate(evidence_docs) if h in relevant), None)
    return {
        "precision": sum(hits) / k,
        "recall": len(set(top) & relevant) / len(relevant),
        "hit": float(any(hits)),
        "rr": 1.0 / (first + 1) if first is not None else 0.0,
        "returned": len(evidence_docs),
        "precision_returned": (sum(d in relevant for d in evidence_docs) / len(evidence_docs)) if evidence_docs else 0.0,
        "recall_returned": len(set(evidence_docs) & relevant) / len(relevant),
    }


def generation_metrics(out: dict, item: dict, retriever) -> dict:
    ans = out.get("answer") or ""
    sources = out["sources"]
    v = out.get("verification") or {}
    cites = [int(n) for n in re.findall(r"\[(\d+)\]", ans)]
    rel = set(item["relevant_doc_ids"])
    valid = [n for n in cites if 1 <= n <= len(sources)]
    cite_ok = [sources[n - 1]["doc_id"] in rel for n in valid]
    sents = [s for s in split_sentences(re.sub(r"\[\d+\]", "", ans)) if len(s.split()) >= 4]
    coverage = None
    if item["key_points"] and sents:
        sims = retriever.embed(item["key_points"]) @ retriever.embed(sents).T
        coverage = float((sims.max(axis=1) >= KEYPOINT_T).mean())
    return {
        "faithfulness": v.get("supported_ratio"),
        "unsupported_claims": v.get("flagged"),
        "answer_relevance": coverage,
        "citation_correctness": (sum(cite_ok) / len(cites)) if cites else 0.0,
        "invalid_citations": len(cites) - len(valid),
        "context_utilisation": (len(set(valid)) / len(sources)) if sources else 0.0,
    }


def _mean(xs):
    xs = [x for x in xs if x is not None]
    return round(st.mean(xs), 4) if xs else None


def run(k: int = 4, with_generation: bool = True) -> dict:
    retriever = get_retriever()
    if retriever is None:
        raise SystemExit("Knowledge base not built. Run: python -m src.rag_ingestion.build_index")
    bench = json.loads(BENCH.read_text(encoding="utf-8"))
    llm = generator.get_llm() if with_generation else None
    results: dict = {}
    for strat in STRATEGIES:
        rows = []
        for item in bench["items"]:
            t0 = time.perf_counter()
            res = retriever.retrieve(item["question"], strat)
            latency = (time.perf_counter() - t0) * 1000
            docs = [e.doc_id for e in res.evidence]
            row = {"id": item["id"], "type": item["type"], "answerable": item["answerable"],
                   "sufficient": res.sufficient, "latency_ms": round(latency, 1), "retrieved_docs": docs,
                   "complexity": res.analysis.complexity}
            if item["answerable"]:
                row.update(retrieval_metrics(docs, set(item["relevant_doc_ids"]), k))
            if llm is not None and item["answerable"] and res.sufficient:
                out = answer_question(item["question"], retriever, llm, strat)
                row["generation"] = generation_metrics(out, item, retriever)
                time.sleep(1.0)  # stay within free-tier rate limits
            rows.append(row)
        ans = [r for r in rows if r["answerable"]]
        una = [r for r in rows if not r["answerable"]]
        gen = [r["generation"] for r in ans if "generation" in r]
        results[strat] = {
            "retrieval": {
                f"precision@{k}": _mean([r["precision"] for r in ans]),
                f"recall@{k}": _mean([r["recall"] for r in ans]),
                f"hit@{k}": _mean([r["hit"] for r in ans]),
                "mrr": _mean([r["rr"] for r in ans]),
                "avg_passages_returned": _mean([r["returned"] for r in ans]),
                "precision@returned": _mean([r["precision_returned"] for r in ans]),
                "recall@returned": _mean([r["recall_returned"] for r in ans]),
                "abstention_accuracy_unanswerable": _mean([float(not r["sufficient"]) for r in una]),
                "false_abstention_rate_answerable": _mean([float(not r["sufficient"]) for r in ans]),
                "median_latency_ms": round(float(np.median([r["latency_ms"] for r in rows])), 1),
            },
            "generation": ({
                "measured": True, "n": len(gen), "model": getattr(llm, "name", None),
                "faithfulness": _mean([g["faithfulness"] for g in gen]),
                "answer_relevance": _mean([g["answer_relevance"] for g in gen]),
                "citation_correctness": _mean([g["citation_correctness"] for g in gen]),
                "context_utilisation": _mean([g["context_utilisation"] for g in gen]),
                "invalid_citations_total": sum(g["invalid_citations"] for g in gen),
            } if gen else {"measured": False,
                           "reason": "No LLM configured (GEMINI_API_KEY unset) - generation metrics were not computed."}),
            "by_type": {t: _mean([r[f"recall"] for r in ans if r["type"] == t]) for t in sorted({r["type"] for r in ans})},
            "questions": rows,
        }
        log.info("%-9s %s", strat, results[strat]["retrieval"])
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "k": k,
        "benchmark": {"n": bench["n"], "answerable": sum(i["answerable"] for i in bench["items"]),
                      "unanswerable": sum(not i["answerable"] for i in bench["items"]),
                      "labelling_protocol": bench["labelling_protocol"]},
        "knowledge_base": {k2: retriever.manifest[k2] for k2 in ("documents_indexed", "chunks", "documents_by_source",
                                                                  "embedding_model", "built_at")},
        "ranking_config": retriever.config.as_dict(),
        "strategies": results,
        "caveats": [
            "Relevance labels are document-level and were assigned by the project author; a single annotator, no inter-rater agreement.",
            "The benchmark is small (30 answerable + 5 unanswerable questions); differences of a few points are within noise.",
            "Faithfulness uses the same heuristic verifier as the app; it measures resemblance to sources, not medical correctness.",
            "No hallucination rate is claimed beyond what these measurements show.",
        ],
    }
    out = get_settings().models_dir / "rag" / "evaluation.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    log.info("Wrote %s", out)
    return report


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--k", type=int, default=4)
    ap.add_argument("--no-generation", action="store_true")
    a = ap.parse_args()
    run(a.k, not a.no_generation)
