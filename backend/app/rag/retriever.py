"""FAISS retrieval + evidence-aware reranking + adaptive strategy.

Strategies (compared in the evaluation module):
  hybrid    (default in the app) FAISS + BM25, query rewriting, fallback across sources: see hybrid.py
  basic     vector top-k only
  reranked  vector top-N candidates, reranked by the transparent evidence score
  adaptive  complexity-based: simple -> reranked small k; complex -> decomposed queries, merged, reranked,
            plus evidence-coverage checks
"""
from __future__ import annotations

import json
import logging
import re
import threading
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import numpy as np

from app.rag import query as Q
from app.rag.config import DEFAULT_RANKING, RankingConfig

log = logging.getLogger("medicore.rag")
_STOP = set("a an the of in on for to and or is are what does do how why with my me i it its this that be can your you".split())


@dataclass
class Evidence:
    chunk_id: str
    doc_id: str
    title: str
    source: str
    doc_type: str
    url: str
    published: str | None
    text: str
    similarity: float
    reliability: float = 0.0
    recency: float = 0.0
    clinical_relevance: float = 0.0
    lexical: float = 0.0          # BM25 score, normalised to the best candidate
    title_match: float = 0.0      # how well the document title matches the topic of the question
    score: float = 0.0

    def public(self, rank: int, snippet_chars: int = 600) -> dict:
        return {
            "rank": rank, "chunk_id": self.chunk_id, "doc_id": self.doc_id, "title": self.title,
            "source": self.source, "doc_type": self.doc_type, "url": self.url, "published": self.published,
            "snippet": self.text[:snippet_chars] + ("…" if len(self.text) > snippet_chars else ""),
            "relevance": round(self.score, 3),
            "score_breakdown": {"similarity": round(self.similarity, 3), "source_reliability": round(self.reliability, 3),
                                "recency": round(self.recency, 3), "clinical_relevance": round(self.clinical_relevance, 3),
                                "keyword_match": round(self.lexical, 3), "title_match": round(self.title_match, 3)},
        }


@dataclass
class RetrievalResult:
    strategy: str
    analysis: Q.QueryAnalysis
    evidence: list[Evidence]
    sufficient: bool
    notes: list[str] = field(default_factory=list)
    queries_used: list[str] = field(default_factory=list)
    level: str = ""                                   # hybrid only: "strong" | "limited" | "none"
    stages: list[dict] = field(default_factory=list)  # hybrid only: what each search stage found
    plan: object | None = None                        # hybrid only: the QueryPlan (rewrites, topics, typo repair)


def _terms(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-z][a-z\-]{2,}", text.lower()) if t not in _STOP}


class Retriever:
    def __init__(self, index_dir: Path, embedding_model: str, config: RankingConfig = DEFAULT_RANKING):
        import faiss  # noqa: PLC0415 - heavy import deferred
        self.config = config
        self.index_dir = index_dir
        self.index = faiss.read_index(str(index_dir / "index.faiss"))
        self.chunks = [json.loads(l) for l in (index_dir / "chunks.jsonl").read_text(encoding="utf-8").split("\n") if l]
        if self.index.ntotal != len(self.chunks):
            raise RuntimeError("FAISS index and chunk metadata are out of sync; rebuild the index")
        self.manifest = json.loads((index_dir / "manifest.json").read_text(encoding="utf-8"))
        self._model_name = embedding_model
        self._model = None
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ embeddings
    def _embedder(self):
        if self._model is None:
            with self._lock:
                if self._model is None:
                    from sentence_transformers import SentenceTransformer  # noqa: PLC0415
                    self._model = SentenceTransformer(self._model_name)
        return self._model

    def embed(self, texts: list[str]) -> np.ndarray:
        return self._embedder().encode(texts, normalize_embeddings=True, show_progress_bar=False).astype("float32")

    # ------------------------------------------------------------------ search
    def vector_search(self, q: str, k: int) -> list[Evidence]:
        qv = self.embed([Q.expand_abbreviations(q)])
        sims, ids = self.index.search(qv, k)
        out = []
        for s, i in zip(sims[0], ids[0]):
            if i < 0:
                continue
            c = self.chunks[i]
            out.append(Evidence(c["chunk_id"], c["doc_id"], c["title"], c["source"], c["doc_type"], c["url"],
                                c.get("published"), c["text"], float(s)))
        return out

    # ------------------------------------------------------------------ scoring components
    def _reliability(self, e: Evidence) -> float:
        cfg = self.config
        return cfg.reliability.get(f"{e.source}:{e.doc_type}", cfg.reliability.get(e.source, cfg.default_reliability))

    def _recency(self, e: Evidence) -> float:
        if not e.published:
            return self.config.unknown_date_recency
        try:
            years = max(0.0, (date.today() - date.fromisoformat(e.published[:10])).days / 365.25)
        except ValueError:
            return self.config.unknown_date_recency
        return 0.5 ** (years / self.config.recency_half_life_years)

    @staticmethod
    def _clinical_relevance(e: Evidence, q_terms: set[str]) -> float:
        """Share of the question's content terms found in the passage/title (lexical grounding),
        so semantically-close but off-topic passages are down-weighted."""
        if not q_terms:
            return 0.0
        hay = _terms(e.title + " " + e.text)
        return len(q_terms & hay) / len(q_terms)

    def score(self, ev: list[Evidence], query: str) -> list[Evidence]:
        cfg = self.config
        total = cfg.weights_sum() or 1.0
        qt = _terms(Q.expand_abbreviations(query))
        for e in ev:
            e.reliability = self._reliability(e)
            e.recency = self._recency(e)
            e.clinical_relevance = self._clinical_relevance(e, qt)
            e.score = (cfg.w_similarity * e.similarity + cfg.w_reliability * e.reliability
                       + cfg.w_recency * e.recency + cfg.w_clinical * e.clinical_relevance) / total
        return sorted(ev, key=lambda x: x.score, reverse=True)

    def _diversify(self, ev: list[Evidence], k: int) -> list[Evidence]:
        per_doc: dict[str, int] = {}
        out = []
        for e in ev:
            if per_doc.get(e.doc_id, 0) >= self.config.max_chunks_per_doc:
                continue
            per_doc[e.doc_id] = per_doc.get(e.doc_id, 0) + 1
            out.append(e)
            if len(out) == k:
                break
        return out

    # ------------------------------------------------------------------ strategies
    def retrieve(self, question: str, strategy: str = "hybrid", llm=None) -> RetrievalResult:
        if strategy == "hybrid":
            from app.rag.hybrid import retrieve_hybrid  # noqa: PLC0415 - avoids a circular import

            return retrieve_hybrid(self, question, llm)
        cfg = self.config
        analysis = Q.analyse(question)
        notes: list[str] = []
        if strategy == "basic":
            ev = self.vector_search(question, cfg.simple_k)
            queries = [question]
        elif strategy == "reranked":
            pool = self.vector_search(question, cfg.candidate_pool)
            ev = self._diversify(self.score(pool, question), cfg.simple_k)
            queries = [question]
        elif strategy == "adaptive":
            if analysis.complexity == "simple":
                pool = self.vector_search(question, cfg.candidate_pool)
                ev = self._diversify(self.score(pool, question), cfg.simple_k)
                queries = [question]
            else:
                queries = analysis.sub_queries
                merged: dict[str, Evidence] = {}
                for sq in queries:
                    for e in self.score(self.vector_search(sq, cfg.complex_k_per_query * 2), sq)[: cfg.complex_k_per_query]:
                        if e.chunk_id not in merged or e.similarity > merged[e.chunk_id].similarity:
                            merged[e.chunk_id] = e
                ev = self._diversify(self.score(list(merged.values()), question), cfg.complex_final_k)
                notes.append("Your question has several parts, so we looked for sources in a few different ways.")
                # additional evidence check: at least two independent documents
                if len({e.doc_id for e in ev}) < 2:
                    notes.append("Only one source covers this, so please treat the answer with extra care.")
        else:
            raise ValueError(f"Unknown strategy {strategy!r}")

        # filter irrelevant passages (basic strategy still filters, to keep comparison fair on evidence use)
        kept = [e for e in ev if e.similarity >= cfg.min_similarity]
        dropped = len(ev) - len(kept)
        # (low-similarity passages are dropped silently: this is an internal detail, not something users need)
        best = max((e.similarity for e in kept), default=0.0)
        sufficient = bool(kept) and best >= cfg.min_best_similarity
        if not sufficient:
            notes.append("No reliable source was found for this question.")
        if strategy == "basic":
            self.score(kept, question)       # fills score components in place; keeps the pure vector order
        return RetrievalResult(strategy, analysis, kept, sufficient, notes, queries)


_retriever: Retriever | None = None
_lock = threading.Lock()


def get_retriever() -> Retriever | None:
    """Returns None when no index has been built, so callers can report 'knowledge base not built'."""
    global _retriever
    from app.core.config import get_settings
    s = get_settings()
    d = s.models_dir / "rag"
    if _retriever is None and (d / "index.faiss").exists():
        with _lock:
            if _retriever is None:
                _retriever = Retriever(d, s.embedding_model)
                log.info("RAG index loaded: %d chunks", _retriever.index.ntotal)
    return _retriever


def reset_retriever() -> None:
    global _retriever
    _retriever = None

