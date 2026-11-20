"""Answer generation with Google Gemini, constrained to retrieved evidence."""
from __future__ import annotations

import logging
from typing import Protocol

from app.core.config import get_settings
from app.core.errors import ServiceUnavailableError
from app.rag.retriever import Evidence

log = logging.getLogger("medicore.rag.gen")

SYSTEM_PROMPT = """You are the MediCore AI healthcare information assistant. You explain health information for education only.

STRICT RULES
1. Use ONLY the numbered CONTEXT passages below for facts. Do not add facts from outside knowledge, even if you are sure of them.
2. After every factual sentence, cite the supporting passage(s) like [1] or [2][3]. Never cite a passage number that is not in the context, and never invent a source.
3. If the context does not cover part of the question, say so plainly ("The sources I found do not cover ...") instead of guessing.
4. Mention uncertainty, differences between sources, or the age of a source when it matters.
5. Do NOT diagnose the user and do not say or imply they have a particular condition. Describe what is common or possible in general ("Common causes include ...", "It can be linked to ..."). Do NOT recommend medicines, doses, or changes to treatment. If asked, explain that you cannot, and suggest speaking to a doctor or pharmacist.
6. Write for an ordinary adult with no medical training, at about an 8th-grade reading level: short sentences, everyday words, and medical terms explained in brackets the first time. The user may write casually, with typos or fragments. Answer what they most likely mean.
7. Do not invent statistics, thresholds, dates, or source names.
8. Do not add a generic disclaimer (the application adds one), and do not list the sources (the application shows them).

ANSWER FORMAT. Use these exact bold headings, and only the ones that apply:
**Short answer**    one or two sentences that answer the question directly.
**What may explain it**    (only for symptoms) bullet points of common possible reasons found in the context. Never say the user has them.
**What you can do**    practical, general self-care or next steps found in the context. No medicines or doses.
**When to get medical help**    warning signs found in the context. Always finish this section with: Please speak to a doctor or pharmacist if it is severe, getting worse, or you are worried.
**A few questions that could help**    2 or 3 short questions, only when the user described symptoms without enough detail."""

LIMITED_EVIDENCE_PROMPT = """
EVIDENCE IS LIMITED for this question: the passages below only partly cover it.
- Start with one sentence saying the sources only partly cover the question.
- Then give only what the passages support, with [n] citations, using the format above.
- You may add a final section titled exactly **General background (not from the sources above)** with a few sentences of well-established, general information. Begin it by saying it is less certain. No citations, no numbers or doses, nothing about the user's own condition.
- End with advice to speak to a doctor or pharmacist."""

GENERAL_BACKGROUND_MARKER = "General background (not from the sources above)"


class LLM(Protocol):
    name: str

    def generate(self, system: str, prompt: str) -> str: ...


def format_context(evidence: list[Evidence]) -> str:
    blocks = []
    for i, e in enumerate(evidence, 1):
        date = f", {e.published}" if e.published else ""
        blocks.append(f"[{i}] {e.title} ({e.source}{date})\n{e.text}")
    return "\n\n".join(blocks)


def build_prompt(question: str, evidence: list[Evidence], safety_flags: list[str], limited: bool = False,
                 follow_ups: list[str] | None = None, interpreted_as: str | None = None,
                 symptom_labels: list[str] | None = None) -> str:
    extra = ""
    if symptom_labels:
        from app.rag.symptoms import SYMPTOM_PROMPT_NOTE  # noqa: PLC0415
        extra += SYMPTOM_PROMPT_NOTE.format(symptoms=", ".join(symptom_labels))
    if "diagnosis_request" in safety_flags:
        extra += "\nNote: the user seems to ask for a personal diagnosis. Decline that part and explain general information only."
    if "prescription_request" in safety_flags:
        extra += "\nNote: the user seems to ask about medicines or doses. Decline that part; give no doses and no advice to start or stop a medicine."
    if "urgent" in safety_flags:
        extra += "\nNote: what the user describes may need prompt medical advice. Say so clearly in the 'When to get medical help' section."
    if follow_ups:
        extra += "\nSuggested follow-up questions (use them if the symptoms are unclear): " + " | ".join(follow_ups)
    if interpreted_as:
        extra += f"\nNote: the question was spell-corrected. It most likely means: {interpreted_as}"
    mode = LIMITED_EVIDENCE_PROMPT if limited else ""
    return f"CONTEXT\n{format_context(evidence)}\n{mode}\nQUESTION\n{question}{extra}\n\nANSWER:"


class GeminiLLM:
    def __init__(self, api_key: str, model: str):
        from google import genai  # noqa: PLC0415
        self._client = genai.Client(api_key=api_key)
        self._model = model
        self.name = model

    def generate(self, system: str, prompt: str) -> str:
        from google.genai import types  # noqa: PLC0415
        try:
            resp = self._client.models.generate_content(
                model=self._model, contents=prompt,
                config=types.GenerateContentConfig(system_instruction=system, temperature=0.2, max_output_tokens=1200),
            )
        except Exception as exc:  # SDK raises several error types; surface one clean error
            log.exception("Gemini request failed")
            raise ServiceUnavailableError("The writing assistant could not answer right now. Please try again in a moment.",
                                          code="llm_error") from exc
        text = (resp.text or "").strip()
        if not text:
            raise ServiceUnavailableError("The writing assistant could not answer right now. Please try again in a moment.", code="llm_error")
        return text


_llm: LLM | None = None


def get_llm() -> LLM | None:
    """None when GEMINI_API_KEY is not configured (callers must say so; no fake answers)."""
    global _llm
    s = get_settings()
    if _llm is None and s.gemini_api_key:
        _llm = GeminiLLM(s.gemini_api_key, s.gemini_model)
    return _llm
