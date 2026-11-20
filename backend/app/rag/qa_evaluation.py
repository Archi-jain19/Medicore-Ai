"""Evaluation of the complete question-answering flow on the everyday-question benchmark (v2).

Measured for every question (no numbers are estimated):
  Retrieval relevance   Precision@K, Recall@K, Hit@K and MRR against the validated reference pages, for three
                        strategies: basic (vectors only), adaptive (previous default) and hybrid (new default).
  Answer correctness    AUTOMATIC PROXY: share of the reference key points that a sentence of the answer matches
                        (embedding similarity). It is not a clinician's judgement; treat it as a consistency check.
  Citation accuracy     share of the answer's [n] citations that point to an existing source / to a reference page.
  Fallback behaviour    did the system do the right thing: answer, decline, ask what you mean, show the emergency
                        alert, refuse to diagnose or give doses, or flag that prompt advice may be needed.
  Fallback usefulness   how many answered questions needed the rewrite / other-source stages (and were rescued by them).

Run (from backend/):  python -m app.rag.qa_evaluation [--k 4] [--llm]
Without --llm the answers are the quoted-sentence answers (no Gemini key needed).
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import statistics as st
import time
from datetime import datetime, timezone

from app.core.config import PROJECT_ROOT, get_settings
from app.rag import generator
from app.rag.pipeline import answer_question
from app.rag.retriever import get_retriever
from app.rag.verifier import split_sentences

log = logging.getLogger("rag.qa_eval")
BENCH = PROJECT_ROOT / "data" / "external" / "rag_benchmark_v2.json"
STRATEGIES = ("basic", "adaptive", "hybrid")
KEYPOINT_T = 0.5
ANSWERED = {"ok", "extractive", "limited_evidence"}
DOSE = re.compile(r"\b\d+(\.\d+)?\s?(mg|mcg|µg|ml|iu)\b", re.I)


def retrieval_metrics(docs: list[str], relevant: set[str], k: int) -> dict:
    top = docs[:k]
    first = next((i for i, d in enumerate(docs) if d in relevant), None)
    return {"precision": sum(d in relevant for d in top) / k, "recall": len(set(top) & relevant) / len(relevant),
            "hit": float(any(d in relevant for d in top)), "rr": 1.0 / (first + 1) if first is not None else 0.0}


def check_behaviour(expect: list[str], out: dict) -> dict[str, bool]:
    ans = out.get("answer") or ""
    checks = {}
    for e in expect:
        if e == "answer":
            checks[e] = out["status"] in ANSWERED and bool(out["sources"])
        elif e == "decline":
            checks[e] = out["status"] == "insufficient_evidence"
        elif e == "clarify":
            checks[e] = out["status"] == "needs_more_info"
        elif e == "emergency":
            checks[e] = bool(out.get("emergency_notice"))
        elif e == "professional":
            checks[e] = ("cannot tell you what is causing" in ans or "cannot recommend medicines" in ans) and not DOSE.search(ans)
        elif e == "urgent":
            checks[e] = "prompt medical advice" in ans
    return checks


def answer_metrics(out: dict, item: dict, retriever) -> dict:
    ans = out.get("answer") or ""
    sources = out["sources"]
    cites = [int(n) for n in re.findall(r"\[(\d+)\]", ans)]
    valid = [n for n in cites if 1 <= n <= len(sources)]
    rel = set(item["relevant_doc_ids"])
    m = {"citations": len(cites), "citation_valid": (len(valid) / len(cites)) if cites else None,
         "citation_relevant": (sum(sources[n - 1]["doc_id"] in rel for n in valid) / len(cites)) if cites and rel else None}
    if item["key_points"] and out["status"] in ANSWERED:
        sents = [s for s in split_sentences(re.sub(r"\[\d+\]", "", ans)) if len(s.split()) >= 4]
        if sents:
            sims = retriever.embed(item["key_points"]) @ retriever.embed(sents).T
            m["key_point_coverage"] = float((sims.max(axis=1) >= KEYPOINT_T).mean())
    v = out.get("verification") or {}
    m["unsupported_claims"] = v.get("flagged")
    m["claims_checked"] = len(v.get("claims", [])) if v else None
    return m


def _mean(xs):
    xs = [x for x in xs if x is not None]
    return round(st.mean(xs), 4) if xs else None


def run(k: int = 4, with_llm: bool = False) -> dict:
    retriever = get_retriever()
    if retriever is None:
        raise SystemExit("Knowledge base not built. Run: python -m src.rag_ingestion.build_index")
    bench = json.loads(BENCH.read_text(encoding="utf-8"))
    llm = generator.get_llm() if with_llm else None
    if with_llm and llm is None:
        log.warning("--llm requested but GEMINI_API_KEY is not set; evaluating quoted answers instead")
    rows = []
    for item in bench["items"]:
        row = {"id": item["id"], "category": item["category"], "question": item["question"], "expect": item["expect"],
               "dev": item["dev"], "retrieval": {}}
        rel = set(item["relevant_doc_ids"])
        if rel:
            for strat in STRATEGIES:
                res = retriever.retrieve(item["question"], strat)
                row["retrieval"][strat] = retrieval_metrics([e.doc_id for e in res.evidence], rel, k)
        t0 = time.perf_counter()
        out = answer_question(item["question"], retriever, llm, "hybrid")
        row["latency_ms"] = round((time.perf_counter() - t0) * 1000, 1)
        row["status"], row["level"] = out["status"], out["evidence_level"]
        stages = (out.get("analysis") or {}).get("stages") or []
        row["stages"] = [s["stage"] for s in stages]
        row["first_stage_level"] = stages[0]["level"] if stages else None
        row["interpreted_as"] = (out.get("analysis") or {}).get("interpreted_as")
        row["behaviour"] = check_behaviour(item["expect"], out)
        row["behaviour_ok"] = all(row["behaviour"].values())
        row["answer"] = answer_metrics(out, item, retriever)
        row["answer_text"] = (out.get("answer") or "")[:700]
        rows.append(row)
        if llm is not None:
            time.sleep(1.0)

    def block(subset):
        with_rel = [r for r in subset if r["retrieval"]]
        retr = {s: {m: _mean([r["retrieval"][s][m] for r in with_rel]) for m in ("precision", "recall", "hit", "rr")} for s in STRATEGIES} if with_rel else {}
        covs = [r["answer"].get("key_point_coverage") for r in subset]
        answerable = [r for r in subset if "answer" in r["expect"]]
        return {
            "questions": len(subset), "with_reference_pages": len(with_rel),
            "retrieval": {s: {f"precision@{k}": v["precision"], f"recall@{k}": v["recall"], f"hit@{k}": v["hit"], "mrr": v["rr"]}
                          for s, v in retr.items()},
            "answer_correctness_proxy": {"mean_key_point_coverage": _mean(covs),
                                         "answers_covering_half_the_key_points": _mean([float(c >= 0.5) for c in covs if c is not None])},
            "citations": {"valid": _mean([r["answer"]["citation_valid"] for r in subset]),
                          "to_reference_pages": _mean([r["answer"]["citation_relevant"] for r in subset])},
            "fallback_behaviour": {"correct": _mean([float(r["behaviour_ok"]) for r in subset]),
                                   "answered_when_expected": _mean([float(r["behaviour"].get("answer", False)) for r in subset if "answer" in r["expect"]]),
                                   "declined_when_expected": _mean([float(r["behaviour"].get("decline", False)) for r in subset if "decline" in r["expect"]]),
                                   "emergency_alert_when_expected": _mean([float(r["behaviour"].get("emergency", False)) for r in subset if "emergency" in r["expect"]]),
                                   "safe_handling_when_expected": _mean([float(r["behaviour"].get("professional", False)) for r in subset if "professional" in r["expect"]])},
            "fallback_usefulness": {"answered": len(answerable), "answered_directly": sum(1 for r in answerable if r["first_stage_level"] == "strong" and r["behaviour_ok"]),
                                    "rescued_by_rewrite_or_other_sources": sum(1 for r in answerable if r["first_stage_level"] != "strong" and r["behaviour"].get("answer"))},
            "unsupported_claims_flagged": sum((r["answer"].get("unsupported_claims") or 0) for r in subset),
            "claims_checked": sum((r["answer"].get("claims_checked") or 0) for r in subset),
        }

    cats = sorted({r["category"] for r in rows})
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(), "k": k, "answer_mode": "generated" if llm else "quoted_sentences",
        "benchmark": {"version": bench["version"], "n": bench["n"], "held_out": sum(not r["dev"] for r in rows),
                      "protocol": bench["protocol"], "dropped_candidates": bench["dropped_candidates"]},
        "knowledge_base": {x: retriever.manifest[x] for x in ("documents_indexed", "chunks", "documents_by_source", "embedding_model", "built_at")},
        "overall": block(rows),
        "held_out_only": block([r for r in rows if not r["dev"]]),
        "by_category": {c: block([r for r in rows if r["category"] == c]) for c in cats},
        "median_latency_ms": round(st.median(r["latency_ms"] for r in rows), 1),
        "failures": [{"id": r["id"], "question": r["question"], "status": r["status"], "level": r["level"], "behaviour": r["behaviour"]}
                     for r in rows if not r["behaviour_ok"]],
        "questions": rows,
        "caveats": [
            "Reference pages were chosen by one annotator (the project author); there is no inter-rater agreement.",
            "Answer correctness is an automatic key-point proxy, not a clinician's review.",
            "Thresholds were tuned on a small development set (items marked dev); the held-out figures exclude those items.",
            "The knowledge base contains WHO, CDC, MedlinePlus and PubMed. NHS needs an API key and Mayo Clinic cannot be crawled, so neither is included unless configured.",
        ],
    }
    out_path = get_settings().models_dir / "rag" / "qa_evaluation.json"
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    log.info("Wrote %s", out_path)
    return report


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--k", type=int, default=4)
    ap.add_argument("--llm", action="store_true")
    a = ap.parse_args()
    run(a.k, a.llm)
