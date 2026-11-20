"""Post-generation verification: is each important claim supported by the retrieved context?

Deterministic and inspectable (no second LLM call):
  1. Split the answer into sentences; skip non-claims (questions, hedges/advice, very short text).
  2. For each claim, find the best-matching *sentence* in the retrieved passages (embedding cosine).
  3. Numbers/percentages in the claim must appear in the context.
  4. Citation markers [n] must refer to existing passages, and the cited passage should support the claim.

Thresholds are heuristics, not clinical truth. They are documented in the evaluation results and can be
tuned. The verifier flags unsupported claims; it does not prove that supported claims are correct.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

import numpy as np

from app.rag.retriever import Evidence, Retriever

SUPPORTED_T = 0.55
WEAK_T = 0.42
_NON_CLAIM = re.compile(
    r"^(please|consult|talk to|speak (with|to)|see a|contact|seek|note that|keep in mind|i (can('|no)t|am not)|"
    r"the retrieved sources do not|the (provided |retrieved )?(sources|context) (do|does) not|"
    r"this (information )?is (for|not)|in summary|in short|here('s| is| are))", re.I)
_NUM = re.compile(r"\d+(?:[.,]\d+)?\s*%?")


@dataclass
class ClaimCheck:
    text: str
    status: str                  # supported | weak | unsupported
    similarity: float
    best_chunk_id: str | None
    cited: list[int]
    issues: list[str]

    def as_dict(self) -> dict:
        return {"text": self.text, "status": self.status, "similarity": round(self.similarity, 3),
                "best_chunk_id": self.best_chunk_id, "cited": self.cited, "issues": self.issues}


def split_sentences(text: str) -> list[str]:
    text = re.sub(r"\n[-*•]\s+", "\n", text)
    text = re.sub(r"[#*_`>]", "", text)
    parts = re.split(r"(?<=[.!?])(?:\s*\[\d+\])*\s+|\n+", text)
    return [p.strip() for p in parts if p and len(p.strip()) > 0]


def _sentences_of(chunk: str) -> list[str]:
    return [s for s in re.split(r"(?<=[.!?])\s+|\n+", chunk) if len(s.strip()) > 25]


GENERAL_MARKER = "General background (not from the sources above)"


def verify_answer(answer: str, evidence: list[Evidence], retriever: Retriever) -> dict:
    """Checks the sourced part of an answer. A section the answer itself labels as general background (not from the
    sources) is not checked against them. It is reported separately so the UI can say it is less certain."""
    has_general = GENERAL_MARKER.lower() in answer.lower()
    if has_general:
        answer = re.split(re.escape(GENERAL_MARKER), answer, maxsplit=1, flags=re.I)[0]
    # bold-only lines are section headings ("When to get medical help"), not claims
    answer = re.sub(r"^\s*\*\*[^*\n]+\*\*:?\s*$", "", answer, flags=re.M)
    sentences = split_sentences(answer)
    claims: list[tuple[str, list[int]]] = []
    for s in sentences:
        cited = sorted({int(n) for n in re.findall(r"\[(\d+)\]", s)})
        clean = re.sub(r"\s*\[\d+\]", "", s).strip(" -:")
        if len(clean.split()) < 5 or clean.endswith("?") or _NON_CLAIM.match(clean):
            continue
        claims.append((clean, cited))
    if not claims or not evidence:
        return {"claims": [], "supported_ratio": None, "flagged": 0, "method": "embedding+numeric",
                "note": "No verifiable factual claims were found in the answer."}

    # sentence-level index of the context
    ctx_sents, owners = [], []
    for ci, e in enumerate(evidence):
        for s in _sentences_of(e.text):
            ctx_sents.append(s)
            owners.append(ci)
    if not ctx_sents:
        ctx_sents, owners = [e.text for e in evidence], list(range(len(evidence)))
    ctx_vec = retriever.embed(ctx_sents)
    claim_vec = retriever.embed([c for c, _ in claims])
    sims = claim_vec @ ctx_vec.T
    ctx_text_all = " ".join(e.text for e in evidence).replace(",", "")
    owners_arr = np.array(owners)

    results: list[ClaimCheck] = []
    for (claim, cited), row in zip(claims, sims):
        j = int(np.argmax(row))
        best, best_chunk = float(row[j]), evidence[owners[j]].chunk_id
        issues: list[str] = []
        status = "supported" if best >= SUPPORTED_T else "weak" if best >= WEAK_T else "unsupported"
        missing_nums = [n for n in _NUM.findall(claim) if n.replace(",", "").strip() not in ctx_text_all]
        if missing_nums:
            issues.append(f"number(s) not found in sources: {', '.join(m.strip() for m in missing_nums)}")
            status = "unsupported"
        bad = [n for n in cited if n < 1 or n > len(evidence)]
        if bad:
            issues.append(f"cites non-existent source(s): {bad}")
            status = "unsupported" if status == "supported" else status
        valid = [n for n in cited if 1 <= n <= len(evidence)]
        if valid:
            mask = np.isin(owners_arr, [n - 1 for n in valid])
            cited_best = float(row[mask].max()) if mask.any() else 0.0
            if cited_best < WEAK_T and status != "unsupported":
                issues.append("the cited source does not appear to support this claim")
                status = "weak"
        elif status == "supported":
            issues.append("no citation given")
        results.append(ClaimCheck(claim, status, best, best_chunk, cited, issues))

    n_sup = sum(r.status == "supported" for r in results)
    flagged = sum(r.status == "unsupported" for r in results)
    return {
        "claims": [r.as_dict() for r in results],
        "supported_ratio": round(n_sup / len(results), 3),
        "flagged": flagged,
        "weak": sum(r.status == "weak" for r in results),
        "method": "embedding+numeric",
        "general_background_not_checked": has_general,
        "thresholds": {"supported": SUPPORTED_T, "weak": WEAK_T},
        "note": "We compare each sentence with the sources. 'Matched' means it is close to what a source says. It does not prove the source is right.",
    }
