"""Extractive answers: the best-matching sentences quoted verbatim from the retrieved sources.

Used when no LLM is configured or the LLM call fails. Nothing is generated or paraphrased. Each line is a
sentence from a WHO / CDC / PubMed passage with its citation, so this mode cannot hallucinate. It can only
select imperfectly.
"""
from __future__ import annotations

import re

import numpy as np

from app.rag.retriever import Evidence, Retriever

_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9(])|\n+")
_JUNK = re.compile(r"^(##|- ?$|figure|table|copyright|©|doi:|http|source:|data from)", re.I)
# Captions and chart titles ("Hypertension prevalence among adults aged 18 and over: United States, 2017-2018")
# have no verb. A real explanatory sentence does, so we require one.
_VERB = re.compile(
    r"\b(is|are|was|were|be|been|can|could|may|might|will|would|should|must|has|have|had|does|do|means?|causes?|leads?|helps?|"
    r"increases?|reduces?|lowers?|raises?|occurs?|affects?|includes?|requires?|shows?|measures?|protects?|prevents?|builds?|"
    r"happens?|results?|damages?|carr(?:y|ies)|produces?|called|known|defined|diagnosed|recommended|needs?|contains?|refers?|"
    r"develops?|gets?|makes?|keeps?|lives?|stores?|turns?|breaks?|stops?|starts?|slows?|raise[sd]?)\b", re.I)


def _sentences(text: str) -> list[str]:
    out = []
    for s in _SENT_SPLIT.split(text):
        s = s.strip(" -•\t")
        s = re.sub(r"^#+\s*", "", s)
        # a sentence ending in ":" only introduces a list that is not part of the quote, so it would read as unfinished
        if 50 <= len(s) <= 420 and not _JUNK.match(s) and s[0].isalnum() and _VERB.search(s) and not s.endswith(":"):
            out.append(s)
    return out


def extractive_answer(question: str, evidence: list[Evidence], retriever: Retriever, max_sentences: int = 5,
                      min_similarity: float = 0.35) -> str | None:
    cands: list[tuple[int, str]] = []
    for i, e in enumerate(evidence, 1):
        cands += [(i, s) for s in _sentences(e.text)]
    if not cands:
        return None
    q = retriever.embed([question])[0]
    vecs = retriever.embed([s for _, s in cands])
    sims = vecs @ q
    chosen: list[int] = []
    for j in np.argsort(-sims):
        if sims[j] < min_similarity or len(chosen) == max_sentences:
            break
        # skip near-duplicates of an already chosen sentence
        if any(float(vecs[j] @ vecs[k]) > 0.88 for k in chosen):
            continue
        chosen.append(int(j))
    if not chosen:
        return None
    lines = [f"- {cands[j][1]} [{cands[j][0]}]" for j in chosen]
    return "Here is what trusted health sources say, word for word:\n\n" + "\n".join(lines)


# --------------------------------------------------------------------------- structured answer
_CAUSE = re.compile(r"\b(causes?d?|due to|results? from|common(ly)?|can be (a sign|caused)|may be (caused|due)|linked to|trigger\w*|reasons?)\b", re.I)
# advice-style wording only: a sentence that merely mentions "treatment" or "fluids" is not self-care advice
_SELF_CARE = re.compile(r"\b(you should|you may want to|try (to )?\w+|drink|rest\b|avoid|stay (hydrated|warm|cool|home)|wash your|apply|elevate|can help|helps? (to )?(relieve|ease|lower|reduce|prevent))\b", re.I)
_WARN = re.compile(r"\b(call|see (a|your|an) (doctor|health|provider|healthcare)|seek|get (medical|immediate|emergency)|emergency|911|urgent|medical (help|attention|care)|contact (a|your)|when to (see|call|get)|talk to (a|your)|let your)\b", re.I)
_DOSE = re.compile(r"\b\d+(\.\d+)?\s?(mg|mcg|µg|g|ml|iu|units?)\b|\btake \d", re.I)
# advice to take a medicine: left out whenever the user asked about medicines (we do not recommend them)
_TAKE_MEDICINE = re.compile(r"\b(take|taking|use|using|try|trying)\b.{0,60}\b(medicines?|medications?|pain relievers?|painkillers?|drugs?|tablets?|pills?|antibiotics?|over-the-counter|acetaminophen|ibuprofen|aspirin|naproxen)\b", re.I)
SAFETY_LINE = "Please speak to a doctor or pharmacist if it is severe, getting worse, or you are worried."


def structured_answer(question: str, evidence: list[Evidence], retriever: Retriever, plan=None, follow_ups: list[str] | None = None,
                      limited: bool = False, max_per_section: int = 3, avoid_medicine: bool = False) -> str | None:
    """Quoted sentences organised as: Short answer / What may explain it / What you can do / When to get medical help /
    Questions that could help. Every sentence is copied from a source and carries its citation.

    Selection rules that keep the answer on topic and safe:
      * explanations and advice are quoted only from the two best-ranked passages, so a loosely related page cannot
        add unrelated conditions; warning signs may come from any retrieved passage;
      * sentences are matched against the question AND its medical search terms (so "I feel cold" finds hypothermia);
      * sentences giving doses are never used, and when the user asked about medicines, neither are sentences
        advising to take one.
    Returns None when nothing usable is found."""
    primary_docs = {e.doc_id for e in evidence[:2]}
    cands: list[tuple[int, str, bool]] = []          # (citation number, sentence, from a top-ranked passage)
    for i, e in enumerate(evidence, 1):
        for sent in _sentences(e.text):
            if _DOSE.search(sent) or (avoid_medicine and _TAKE_MEDICINE.search(sent)):
                continue
            cands.append((i, sent, e.doc_id in primary_docs))
    if not cands:
        return None
    queries = [question] + (list(plan.primary[:2]) if plan is not None else []) + (plan.rewrites[:1] if plan is not None and plan.rewrites else [])
    qv = retriever.embed(queries)
    vecs = retriever.embed([c[1] for c in cands])
    rank_bonus = np.array([0.08 * (1 - (c[0] - 1) / max(len(evidence), 1)) for c in cands])
    sims = (vecs @ qv.T).max(axis=1) + rank_bonus
    order = list(np.argsort(-sims))
    used: list[int] = []

    def pick(pred, n: int, min_sim: float, only_primary: bool = True) -> list[int]:
        out: list[int] = []
        for j in order:
            if len(out) == n:
                break
            if j in used or sims[j] < min_sim or not pred(cands[j][1]) or (only_primary and not cands[j][2]):
                continue
            if any(float(vecs[j] @ vecs[k]) > 0.88 for k in used + out):
                continue
            out.append(int(j))
        used.extend(out)
        return out

    symptom = bool(plan is not None and plan.symptom_keys)
    # a definition gets up to two sentences; a symptom question gets one, so "What may explain it" keeps its own
    short = pick(lambda s: len(s) <= 260, 1 if symptom else 2, 0.30)      # short means short: no long asides
    if not short:
        return None
    explain = pick(lambda s: bool(_CAUSE.search(s)), max_per_section, 0.30) if symptom else pick(lambda s: True, max_per_section, 0.35)
    care = pick(lambda s: bool(_SELF_CARE.search(s)), max_per_section, 0.30) if (symptom or explain) else []
    warn = pick(lambda s: bool(_WARN.search(s)), max_per_section, 0.25, only_primary=False)

    def bullets(idx: list[int]) -> str:
        return "\n".join(f"- {cands[j][1]} [{cands[j][0]}]" for j in idx)

    parts = []
    if limited:
        parts.append("The sources I found only partly match your question, so please treat this as general information only.")
    parts.append("**Short answer**\n" + bullets(short))
    if explain:
        parts.append(("**What may explain it**\n" if symptom else "**More from the sources**\n") + bullets(explain))
    if care:
        parts.append("**What you can do**\n" + bullets(care))
    if warn or symptom:
        parts.append("**When to get medical help**\n" + (bullets(warn) + "\n" if warn else "") + SAFETY_LINE)
    if follow_ups:
        parts.append("**A few questions that could help**\n" + "\n".join(f"- {q}" for q in follow_ups))
    return "\n\n".join(parts)
