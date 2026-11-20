"""End-to-end RAG: understand -> hybrid retrieve (with fallback) -> judge evidence -> answer -> verify -> package.

How the evidence level decides the answer
  strong   the sources clearly cover the question  -> a full, cited answer (Gemini if available, else quoted sentences)
  limited  the sources only partly cover it         -> a cautious answer that says so (Gemini may add a clearly labelled
                                                       "general background" section; without Gemini, quoted sentences)
  none     nothing relevant after rewriting and searching every source -> an honest "I could not find this", plus
                                                       safety advice and follow-up questions for symptoms
Safety is layered on top of all of these: emergency alert, "get advice soon" for urgent patterns, and a clear
statement when someone asks for a diagnosis or a medicine.
"""
from __future__ import annotations

import logging

from app.core.errors import ServiceUnavailableError
from app.rag import rewrite as RW
from app.rag import symptoms as SY
from app.rag.extractive import extractive_answer, structured_answer
from app.rag.generator import LLM, SYSTEM_PROMPT, build_prompt
from app.rag.retriever import Retriever
from app.rag.verifier import verify_answer

log = logging.getLogger("medicore.rag.pipeline")

EMERGENCY_NOTICE = (
    "**If this is an emergency, or you feel unsafe, call your local emergency number now** "
    "(for example 911 in the US, 112 in Europe, 999 in the UK) or go to the nearest emergency room. "
    "This assistant cannot help in an emergency."
)
URGENT_PREFACE = ("**This may need prompt medical advice.** Please contact a doctor, a nurse line or an urgent care service "
                  "soon, rather than waiting.")
DIAGNOSIS_PREFACE = ("I cannot tell you what is causing your symptoms or whether you have a condition. What follows is general "
                     "information, and a doctor can examine you and give you a proper answer.")
MEDICINE_PREFACE = ("I cannot recommend medicines or doses. What follows is general information, and a doctor or pharmacist can "
                    "tell you what is safe for you.")
DISCLAIMER = "This is general health information, not medical advice, a diagnosis or a prescription."
NO_EVIDENCE = (
    "I could not find a reliable answer to this in the sources I use (WHO, CDC, MedlinePlus, NHS and PubMed), so I won't guess. "
    "Try asking in different words, or ask a doctor or pharmacist."
)
NO_EVIDENCE_SYMPTOM = ("If you have symptoms that are severe, getting worse, or worrying you, please speak to a doctor or "
                       "pharmacist.")
NO_LLM = (
    "I found some related sources, shown below, but I could not pull out a clear answer from them. Please read the "
    "sources, or ask a doctor or pharmacist."
)
CLARIFY = ("I am happy to help. Which medical term or health topic would you like explained? For example, you could type "
           "“What does haemoglobin mean?” or “What is dehydration?”.")
LIMITED_NOTE = "The sources only partly match your question, so this is general information and may be incomplete."
KB_MISSING = "The health library is not available right now. Please try again later."
KB_MISSING_OPERATOR_HINT = "RAG knowledge base missing. Run: python -m src.rag_ingestion.build_index"


def _preface(flags: list[str]) -> list[str]:
    out = []
    if "urgent" in flags:
        out.append(URGENT_PREFACE)
    if "diagnosis_request" in flags:
        out.append(DIAGNOSIS_PREFACE)
    if "prescription_request" in flags:
        out.append(MEDICINE_PREFACE)
    return out


def _compose(preface: list[str], body: str) -> str:
    return "\n\n".join([*preface, body]) if preface else body


SYMPTOM_PREFACE = ("I cannot diagnose you, but I can show what trusted health sources say these symptoms may be linked to. "
                   "Please treat it as a starting point for a conversation with a doctor.")
SYMPTOM_PREFACE_DIAGNOSIS = ("I cannot tell you what is causing your symptoms or whether you have a condition, but I can show what "
                             "trusted health sources say these symptoms may be linked to. A doctor can examine you and give you a proper answer.")


def _symptom_flow(out: dict, question: str, symptoms, plan, retriever, llm, flags: list[str], verify: bool) -> bool:
    """Answers a list of symptoms. Returns False when the sources link none of them to anything (the normal flow then runs)."""
    matches = SY.rerank(retriever, SY.find_topics(retriever, symptoms, plan.corrected, limit=12), symptoms)
    level = SY.level_for(matches, symptoms)
    out["analysis"]["symptoms"] = [s.label for s in symptoms]
    if level == "none":
        return False
    limited = level == "limited"
    preface = _preface([f for f in flags if f != "diagnosis_request"]) + [SYMPTOM_PREFACE_DIAGNOSIS if "diagnosis_request" in flags else SYMPTOM_PREFACE]
    follow_ups = SY.symptom_follow_ups(symptoms)
    avoid = "prescription_request" in flags
    text, evidence = SY.symptom_answer(retriever, symptoms, matches, follow_ups, limited, avoid)
    if not text:
        return False
    out["evidence_level"] = level
    out["analysis"]["evidence_level"] = level
    ok_status = "limited_evidence" if limited else None
    if limited:
        out["notes"].append(LIMITED_NOTE)

    def quoted(reason: str) -> bool:
        out.update(status=ok_status or "extractive", answer=_compose(preface, text), mode="extractive",
                   sources=[e.public(i) for i, e in enumerate(evidence, 1)])
        out["notes"].append(reason)
        return True

    if llm is None:
        return quoted("These sentences are copied word for word from trusted health sources.")
    ev = [m.best for m in matches if m.covered][:6]
    try:
        gen = llm.generate(SYSTEM_PROMPT, build_prompt(question, ev, flags, limited, follow_ups, plan.interpreted_as,
                                                       symptom_labels=[s.label for s in symptoms]))
    except ServiceUnavailableError as exc:
        log.warning("LLM unavailable (%s); answering extractively", exc.code)
        return quoted("Our writing assistant is busy right now, so these sentences are copied word for word from trusted health sources.")
    out.update(answer=_compose(preface, gen), generated=True, model=getattr(llm, "name", "unknown"), mode="generated",
               status=ok_status or "ok", sources=[e.public(i) for i, e in enumerate(ev, 1)])
    if verify:
        v = verify_answer(gen, ev, retriever)
        out["verification"] = v
        if v["flagged"]:
            out["notes"].append("Some statements in this answer could not be matched to a source. They are marked below, so please double-check them.")
    return True


def answer_question(question: str, retriever: Retriever | None, llm: LLM | None, strategy: str = "hybrid",
                    verify: bool = True) -> dict:
    out: dict = {"question": question, "strategy": strategy, "disclaimer": DISCLAIMER, "emergency_notice": None,
                 "answer": None, "generated": False, "status": "ok", "sources": [], "verification": None,
                 "analysis": None, "notes": [], "evidence_level": None, "mode": None}
    if retriever is None:
        log.error(KB_MISSING_OPERATOR_HINT)
        out.update(status="knowledge_base_missing", answer=KB_MISSING)
        return out

    res = retriever.retrieve(question, strategy, llm=llm) if strategy == "hybrid" else retriever.retrieve(question, strategy)
    a, plan = res.analysis, getattr(res, "plan", None)
    level = res.level or ("strong" if res.sufficient else "none")
    flags = list(a.safety_flags)
    out["evidence_level"] = level
    out["analysis"] = {
        "intent": a.intent, "complexity": a.complexity, "complexity_score": a.complexity_score,
        "complexity_reasons": a.complexity_reasons, "safety_flags": flags, "queries": res.queries_used,
        "evidence_level": level, "stages": res.stages,
        "interpreted_as": plan.interpreted_as if plan else None, "topics": plan.topics if plan else [],
    }
    out["notes"] = list(res.notes)
    out["sources"] = [e.public(i) for i, e in enumerate(res.evidence, 1)]
    if "emergency" in flags:
        out["emergency_notice"] = EMERGENCY_NOTICE
    preface = _preface(flags)

    # Questions with no topic ("What does this medical term mean?"): ask what they mean instead of searching blindly.
    if plan is not None and plan.needs_clarification:
        out.update(status="needs_more_info", answer=CLARIFY, sources=[])
        return out

    # Several symptoms in one message ("I feel tired, very thirsty and pee a lot"): look for the topics the sources link to
    # the whole group, instead of answering about only one of them.
    if plan is not None and strategy == "hybrid":
        symptoms = SY.parse_symptoms(plan.corrected)
        if symptoms:
            done = _symptom_flow(out, question, symptoms, plan, retriever, llm, flags, verify)
            if done:
                return out

    follow_ups: list[str] = []
    if plan is not None and plan.symptom_keys and (len(question.split()) <= 12 or level != "strong"):
        follow_ups = RW.follow_up_questions(plan)

    if level == "none":
        body = NO_EVIDENCE
        if plan is not None and plan.symptom_keys:
            body += "\n\n" + NO_EVIDENCE_SYMPTOM
        if follow_ups:
            body += "\n\n**A few questions that could help**\n" + "\n".join(f"- {q}" for q in follow_ups)
        out.update(status="insufficient_evidence", answer=_compose(preface, body), sources=[])
        return out

    limited = level == "limited"
    if limited:
        out["notes"].append(LIMITED_NOTE)
    ok_status = "limited_evidence" if limited else None

    def extractive(reason: str) -> dict:
        text = structured_answer(question, res.evidence, retriever, plan, follow_ups, limited,
                                 avoid_medicine="prescription_request" in flags) if strategy == "hybrid" \
            else extractive_answer(question, res.evidence, retriever)
        if text is None:
            out.update(status="generation_unavailable", answer=_compose(preface, NO_LLM))
            return out
        out.update(status=ok_status or "extractive", answer=_compose(preface, text), mode="extractive")
        out["notes"].append(reason)
        if verify:
            out["verification"] = verify_answer(text, res.evidence, retriever)
        return out

    if llm is None:
        return extractive("These sentences are copied word for word from trusted health sources.")
    try:
        text = llm.generate(SYSTEM_PROMPT, build_prompt(question, res.evidence, flags, limited, follow_ups,
                                                         plan.interpreted_as if plan else None))
    except ServiceUnavailableError as exc:
        log.warning("LLM unavailable (%s); answering extractively", exc.code)
        return extractive("Our writing assistant is busy right now, so these sentences are copied word for word from "
                          "trusted health sources.")
    out.update(answer=_compose(preface, text), generated=True, model=getattr(llm, "name", "unknown"), mode="generated",
               status=ok_status or "ok")
    if verify:
        v = verify_answer(text, res.evidence, retriever)
        out["verification"] = v
        if v["flagged"]:
            out["notes"].append("Some statements in this answer could not be matched to a source. They are marked "
                                "below, so please double-check them.")
        if v.get("general_background_not_checked"):
            out["notes"].append("The part marked “General background” is general knowledge that our sources do not "
                                "confirm, so it is less certain.")
    return out
