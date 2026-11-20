"""Hybrid retrieval (FAISS vectors + BM25 keywords) with query rewriting and a staged fallback.

Pipeline for one question
  0. understand  - repair spelling, map everyday phrasing to medical terms, optional LLM rewrites (rewrite.py)
  1. direct      - hybrid search on the (spelling-corrected) question
  2. rewritten   - if the evidence is not strong, search the rewrites too
  3. per-source  - if still not strong, search every trusted source on its own, so one source with a different
                   vocabulary (e.g. NHS vs. WHO) can fill the gap
  4. rank        - fuse vector and keyword results (reciprocal rank fusion), rerank by relevance, authority and freshness
  5. select      - remove near-duplicates, cap chunks per document and per source (source-aware context)
  6. judge       - label the evidence "strong", "limited" or "none"; the pipeline decides how to answer from that

A high similarity score is not proof of medical correctness; it only tells us the text is about the same topic.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from datetime import date

import numpy as np

from app.rag import rewrite as RW
from app.rag.lexical import tokenize
from app.rag.retriever import Evidence, RetrievalResult, Retriever

RRF_K = 60
DENSE_POOL = 40
LEX_POOL = 40
NEAR_DUPLICATE = 0.92
STRONG_DENSE = 0.45
STRONG_DENSE_WITH_TITLE = 0.38
LIMITED_DENSE = 0.30

# Meaning (dense similarity) leads; keywords, authority, freshness and title agreement refine it.
W = {"dense": 0.50, "lexical": 0.10, "reliability": 0.12, "recency": 0.06, "coverage": 0.08, "title": 0.07}


@dataclass
class Cand:
    idx: int
    dense: float = 0.0
    bm25: float = 0.0
    rrf: float = 0.0
    queries: set = field(default_factory=set)


@dataclass
class Assets:
    vectors: np.ndarray
    bm25: object
    vocab: frozenset
    sources: list[str]
    doc_ids: np.ndarray


def assets(r: Retriever) -> Assets:
    """Built once per retriever: the BM25 index, the in-memory vectors (for per-source search and de-duplication),
    and the spelling vocabulary."""
    a = getattr(r, "_hybrid_assets", None)
    if a is None:
        from collections import Counter

        from app.rag.lexical import BM25Index

        n = r.index.ntotal
        vectors = np.vstack([r.index.reconstruct(i) for i in range(n)]).astype("float32") if n else np.zeros((0, 1), "float32")
        texts = [f"{c['title']} {c['title']} {' '.join(c.get('also_called') or [])} {c['text']}" for c in r.chunks]
        words = Counter(w for t in texts for w in re.findall(r"[a-z]{4,}", t.lower()))
        vocab = frozenset(w for w, c in words.items() if c >= 2)
        a = Assets(vectors, BM25Index(texts), vocab, sorted({c["source"] for c in r.chunks}),
                   np.array([c["doc_id"] for c in r.chunks]))
        r._hybrid_assets = a
    return a


def _normalise_query(q: str) -> str:
    from app.rag import query as Q
    return Q.expand_abbreviations(q)


def search_candidates(r: Retriever, queries: list[str], source: str | None, pool: dict[int, Cand]) -> None:
    """Adds dense + keyword hits for every query into `pool` (a dict shared across stages)."""
    a = assets(r)
    src_mask = None
    if source is not None:
        src_mask = np.array([c["source"] == source for c in r.chunks])
    for q in queries:
        qv = r.embed([_normalise_query(q)])
        if src_mask is None:
            sims, ids = r.index.search(qv, min(DENSE_POOL, r.index.ntotal))
            dense = [(int(i), float(s)) for s, i in zip(sims[0], ids[0]) if i >= 0]
        else:
            s_all = a.vectors @ qv[0]
            s_all = np.where(src_mask, s_all, -1.0)
            top = np.argsort(-s_all)[:DENSE_POOL]
            dense = [(int(i), float(s_all[i])) for i in top if s_all[i] > -1.0]
        lex = a.bm25.search(q, LEX_POOL)
        if src_mask is not None:
            lex = [(i, s) for i, s in lex if src_mask[i]]
        for rank, (i, s) in enumerate(dense):
            c = pool.setdefault(i, Cand(i))
            c.dense = max(c.dense, s)
            c.rrf += 1.0 / (RRF_K + rank + 1)
            c.queries.add(q)
        for rank, (i, s) in enumerate(lex):
            c = pool.setdefault(i, Cand(i))
            c.bm25 = max(c.bm25, s)
            c.rrf += 1.0 / (RRF_K + rank + 1)
            c.queries.add(q)
        # dense similarity for lexical-only hits (so every candidate has a comparable semantic score)
        missing = [i for i, _ in lex if pool[i].dense == 0.0]
        if missing:
            sims = a.vectors[missing] @ qv[0]
            for i, s in zip(missing, sims):
                pool[i].dense = max(pool[i].dense, float(s))


def _topic_terms(plan: RW.QueryPlan) -> set[str]:
    """Stemmed words of the question and its first rewrites (so 'bruise' meets 'bruises')."""
    terms: set[str] = set()
    for w in [plan.keywords, *plan.rewrites[:3]]:
        terms |= set(tokenize(w))
    return terms


def rank(r: Retriever, pool: dict[int, Cand], plan: RW.QueryPlan) -> list[Evidence]:
    if not pool:
        return []
    cfg = r.config
    max_bm = max((c.bm25 for c in pool.values()), default=0.0) or 1.0
    q_terms = set(tokenize(plan.keywords)) or _topic_terms(plan)
    topic_terms = _topic_terms(plan)
    rule_stems = set(tokenize(" ".join(plan.rule_terms)))
    out = []
    for c in pool.values():
        ch = r.chunks[c.idx]
        e = Evidence(ch["chunk_id"], ch["doc_id"], ch["title"], ch["source"], ch["doc_type"], ch["url"],
                     ch.get("published"), ch["text"], c.dense)
        title_words = set(tokenize(re.sub(r"^[A-Za-z ]+: ", "", ch["title"]) + " " + " ".join(ch.get("also_called") or [])))
        e.title_match = (len(topic_terms & title_words) / len(title_words)) if title_words else 0.0
        hay = set(tokenize(ch["title"] + " " + " ".join(ch.get("also_called") or []) + " " + ch["text"]))
        cov = len(q_terms & hay) / len(q_terms) if q_terms else 0.0
        if rule_stems and hay & rule_stems:
            cov = max(cov, 0.7)                     # an everyday phrase matched its medical term in this passage
        e.clinical_relevance = cov
        e.lexical = c.bm25 / max_bm
        e.reliability = r._reliability(e)
        e.recency = r._recency(e)
        rrf_bonus = c.rrf / (2.0 / (RRF_K + 1))          # 1.0 when ranked first by both retrievers
        e.score = (W["dense"] * e.similarity + W["lexical"] * e.lexical + W["reliability"] * e.reliability
                   + W["recency"] * e.recency + W["coverage"] * e.clinical_relevance + W["title"] * e.title_match
                   + 0.05 * min(1.0, rrf_bonus))
        out.append(e)
    return sorted(out, key=lambda x: x.score, reverse=True)


def select(r: Retriever, ranked: list[Evidence], k: int) -> list[Evidence]:
    """Top-K with near-duplicates removed, at most N chunks per document, and no single source dominating."""
    a = assets(r)
    id_to_idx = {c["chunk_id"]: i for i, c in enumerate(r.chunks)}
    n_sources = len({e.source for e in ranked[: k * 4]})
    source_cap = max(2, math.ceil(k * 0.6)) if n_sources > 1 else k
    chosen: list[Evidence] = []
    per_doc: dict[str, int] = {}
    per_src: dict[str, int] = {}

    def duplicate(e: Evidence) -> bool:
        v = a.vectors[id_to_idx[e.chunk_id]]
        return any(float(v @ a.vectors[id_to_idx[x.chunk_id]]) >= NEAR_DUPLICATE for x in chosen)

    for relaxed in (False, True):
        for e in ranked:
            if len(chosen) == k:
                break
            if e in chosen or duplicate(e):
                continue
            if per_doc.get(e.doc_id, 0) >= r.config.max_chunks_per_doc:
                continue
            if not relaxed and per_src.get(e.source, 0) >= source_cap:
                continue
            chosen.append(e)
            per_doc[e.doc_id] = per_doc.get(e.doc_id, 0) + 1
            per_src[e.source] = per_src.get(e.source, 0) + 1
    return chosen


def judge(sel: list[Evidence]) -> str:
    """strong: clearly on topic.  limited: partly on topic, answer cautiously.  none: nothing relevant found.

    A big library makes unrelated text look vaguely similar (cosine ~0.3 is common by chance), so similarity alone is not
    enough: the question's own words (or their medical synonyms) must also show up in the evidence."""
    if not sel:
        return "none"
    def shares_a_word(e: Evidence) -> bool:    # at least one of the question's words (or their medical terms) is in the passage
        return e.clinical_relevance > 0 or e.title_match >= 0.5

    def on_topic(e: Evidence) -> bool:         # a stricter test, used for the weaker tiers
        return e.clinical_relevance >= 0.34 or e.title_match >= 0.5

    if any(e.similarity >= STRONG_DENSE and shares_a_word(e) for e in sel):
        return "strong"
    if any(e.similarity >= STRONG_DENSE_WITH_TITLE and (e.title_match >= 0.5 or e.clinical_relevance >= 0.6) for e in sel):
        return "strong"
    if any(e.similarity >= LIMITED_DENSE and on_topic(e) for e in sel) or any(e.title_match >= 0.5 and e.similarity >= 0.25 for e in sel):
        return "limited"
    return "none"


_LEVEL_ORDER = {"none": 0, "limited": 1, "strong": 2}


def retrieve_hybrid(r: Retriever, question: str, llm=None, k: int = 6) -> RetrievalResult:
    from app.rag import query as Q

    a = assets(r)
    plan = RW.build_plan(question, a.vocab)
    analysis = Q.analyse(plan.corrected)
    analysis.original = question
    notes: list[str] = []
    stages: list[dict] = []
    pool: dict[int, Cand] = {}

    def run(name: str, queries: list[str], source: str | None = None):
        search_candidates(r, queries, source, pool)
        sel = select(r, rank(r, pool, plan), k)
        level = judge(sel)
        stages.append({"stage": name, "source": source, "queries": queries[:6],
                       "candidates": len(pool), "best_similarity": round(max((e.similarity for e in sel), default=0.0), 3),
                       "level": level})
        return sel, level

    if plan.needs_clarification:
        return RetrievalResult("hybrid", analysis, [], False, notes, [plan.corrected], level="none", stages=stages, plan=plan)

    base = list(plan.primary) or [plan.corrected]
    sel, level = run("direct", base)
    if level != "strong" and (plan.rewrites or llm is not None):
        plan.llm_rewrites = RW.llm_rewrites(llm, plan.corrected) if llm is not None else []
        sel, level = run("rewritten", base + plan.rewrites + plan.llm_rewrites)
    if level != "strong":
        queries = (base + plan.rewrites[:3] + plan.llm_rewrites)[:5]
        for src in a.sources:
            sel, level = run("other_sources", queries, source=src)
            if level == "strong":
                break
    queries_used = [q for s in stages for q in s["queries"]]
    if plan.was_corrected and level != "none":
        notes.append(f"We read your question as: “{plan.corrected}”.")
    if len(stages) > 1 and level != "none":
        notes.append("Your question needed a wider search, so we also looked for it in other trusted sources.")
    if level != "none" and len({e.doc_id for e in sel}) < 2:
        notes.append("Only one source covers this, so please treat the answer with extra care.")
    return RetrievalResult("hybrid", analysis, sel, level != "none", notes, list(dict.fromkeys(queries_used)),
                           level=level, stages=stages, plan=plan)
