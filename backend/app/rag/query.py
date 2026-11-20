"""Query processing: normalisation, intent detection, complexity scoring, safety triage, expansion.

Rule-based on purpose: deterministic, inspectable and testable without an LLM.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

# Abbreviation expansion improves recall for lexical-poor queries (e.g. "HDL vs LDL")
ABBREVIATIONS = {
    "hdl": "high-density lipoprotein cholesterol", "ldl": "low-density lipoprotein cholesterol",
    "bp": "blood pressure", "bmi": "body mass index", "hba1c": "glycated haemoglobin HbA1c diabetes",
    "a1c": "glycated haemoglobin HbA1c", "egfr": "estimated glomerular filtration rate kidney",
    "cvd": "cardiovascular disease", "ckd": "chronic kidney disease", "t2d": "type 2 diabetes",
    "hb": "haemoglobin", "hgb": "haemoglobin", "mi": "myocardial infarction heart attack",
}

EMERGENCY_PATTERNS = [
    r"chest pain", r"can'?t breathe|cannot breathe|trouble breathing|shortness of breath",
    r"stroke symptoms|face (is )?droop\w*|droopy face|slurred (speech|words)|speech is slurred|slurring|sudden weakness", r"heart attack",
    r"suicid|kill myself|end my life|self[- ]harm", r"overdose", r"severe bleeding|bleeding (a lot|heavily)",
    r"unconscious|passed out|seizure", r"blood sugar .{0,20}(very|extremely) (high|low)|diabetic ketoacidosis",
    r"severe allergic reaction|anaphylaxis|throat (is )?(closing|swelling)|(lips|tongue|face) (is |are )?swelling",
    r"not breathing|stopped breathing|turning blue|blue lips", r"worst headache of my life|thunderclap",
    r"sudden (loss of vision|vision loss|confusion|numbness|trouble speaking)",
    r"(baby|infant|newborn).{0,40}(not (waking|feeding|breathing)|floppy|limp|hard to wake)",
]
# Not an emergency, but worth prompt medical advice: we add a gentle "please get advice soon" note.
URGENT_PATTERNS = [
    r"(baby|infant|newborn|toddler).{0,40}(fever|temperature)|(fever|temperature).{0,40}(baby|infant|newborn)",
    r"\bstiff neck\b", r"blood in (my |the )?(stool|urine|poo|pee)|coughing (up )?blood|vomiting blood",
    r"(fever|temperature).{0,40}(more than|over|for|since|lasting).{0,15}(3|three|4|four|5|five|week)",
    r"severe (headache|stomach pain|abdominal pain|pain)", r"pregnan\w*.{0,40}(bleed|pain|fever|headache|dizz)",
    r"(cough|headache|pain|tired|fever|dizz\w*).{0,30}(for|over|more than) (several |a few |\d+ )?(weeks|a month|months)",
    r"unexplained weight loss", r"\bconfus(ed|ion)\b",
]
# "Do I have diabetes?" asks for a diagnosis; "Why do I have a headache?" asks for an explanation, so it must not match.
DIAGNOSIS_PATTERNS = [r"(?<!why )(?<!how )(?<!what )\bdo i have\b", r"\bam i (diabetic|sick|dying|anaemic|anemic)\b", r"diagnose me",
                      r"what disease do i have", r"\bis it cancer\b", r"\bdo you think i have\b",
                      r"\bwhat (is|could be) wrong with me\b", r"\bwhat do i have\b", r"\bwhat'?s wrong with me\b"]
PRESCRIPTION_PATTERNS = [r"\bwhat (dose|dosage)\b", r"\bhow (much|many) (mg|pills|tablets)\b", r"\bprescribe\b",
                         r"\bwhich (medicine|medication|drug|pill)s? should i (take|use)\b", r"\bshould i (take|stop|increase|reduce) (my )?(medication|medicine|insulin|metformin|statin)",
                         r"\b(what|which) (can|should|could) i (take|use|give)\b",
                         r"\b(what|which) (medicine|medication|drug|pill|tablet|painkiller|antibiotic|cream|remedy|remedies)s? (can|should|could|do|would) i\b",
                         r"\bwhat (can|should) i do (to treat|for)\b.*\b(medicine|medication|drug)",
                         r"\b(medicine|medication|pill|tablet|drug|painkiller|antibiotic)s? (for|to treat)\b",
                         r"\bhow (much|many) .{0,25}(should|can) i (take|give)\b", r"\bis it (ok|okay|safe) to (take|mix)\b"]

INTENT_RULES = [
    ("comparison", r"\b(difference between|differ|vs\.?|versus|compare|compared to|better than)\b"),
    ("lab_interpretation", r"\b(normal range|reference range|my (result|level|value|report)|high (level|reading)|low (level|reading)|what does .* (level|result|value) mean)\b"),
    ("definition", r"\b(what (is|are|does)|define|meaning of|explain|stands? for|what does .{1,40} mean)\b"),
    ("risk_factors", r"\b(risk factors?|causes?|why (do|does|am)|who is at risk)\b"),
    ("prevention_lifestyle", r"\b(prevent|reduce|lower|diet|exercise|lifestyle|eat|physical activity)\b"),
    ("symptoms", r"\b(symptoms?|signs?)\b"),
    ("management", r"\b(treat|treatment|manage|management|therapy|guideline)\b"),
]


@dataclass
class QueryAnalysis:
    original: str
    normalised: str
    intent: str
    complexity: str                 # "simple" | "complex"
    complexity_score: float
    complexity_reasons: list[str] = field(default_factory=list)
    safety_flags: list[str] = field(default_factory=list)   # emergency | diagnosis_request | prescription_request
    sub_queries: list[str] = field(default_factory=list)


def normalise(q: str) -> str:
    q = re.sub(r"\s+", " ", q.strip())
    return q


def expand_abbreviations(q: str) -> str:
    def sub(m: re.Match) -> str:
        tok = m.group(0)
        exp = ABBREVIATIONS.get(tok.lower())
        return f"{tok} ({exp})" if exp else tok
    return re.sub(r"\b[A-Za-z0-9]{2,6}\b", sub, q)


def detect_safety(q: str) -> list[str]:
    ql = q.lower()
    flags = []
    if any(re.search(p, ql) for p in EMERGENCY_PATTERNS):
        flags.append("emergency")
    elif any(re.search(p, ql) for p in URGENT_PATTERNS):
        flags.append("urgent")
    if any(re.search(p, ql) for p in DIAGNOSIS_PATTERNS):
        flags.append("diagnosis_request")
    if any(re.search(p, ql) for p in PRESCRIPTION_PATTERNS):
        flags.append("prescription_request")
    return flags


def detect_intent(q: str) -> str:
    ql = q.lower()
    for name, pat in INTENT_RULES:
        if re.search(pat, ql):
            return name
    return "general_information"


def score_complexity(q: str, intent: str) -> tuple[float, list[str]]:
    ql = q.lower()
    words = re.findall(r"[a-z0-9\-]+", ql)
    score, reasons = 0.0, []
    if len(words) > 18:
        score += 0.35; reasons.append("long question")
    elif len(words) > 11:
        score += 0.15
    if intent == "comparison":
        score += 0.4; reasons.append("comparison between concepts")
    if len(re.findall(r"\band\b|\bor\b|,", ql)) >= 2:
        score += 0.25; reasons.append("multiple concepts")
    if q.count("?") > 1:
        score += 0.25; reasons.append("multiple questions")
    if intent in ("lab_interpretation", "management", "risk_factors") and len(words) > 8:
        score += 0.15; reasons.append(f"{intent.replace('_', ' ')} requires several evidence types")
    if re.search(r"\b(and|with|in patients with|in people with|while)\b.*\b(diabetes|hypertension|kidney|heart)\b", ql) and len(words) > 10:
        score += 0.2; reasons.append("condition interaction")
    return min(score, 1.0), reasons


def build_sub_queries(q: str, intent: str) -> list[str]:
    """Decomposes a complex query into focused retrieval queries (always includes the full question)."""
    subs = [q]
    if intent == "comparison":
        m = re.search(r"(?:difference between|compare|compared to)?\s*(.+?)\s+(?:and|vs\.?|versus|or)\s+(.+?)(?:\?|$)", q, re.I)
        if m:
            a = re.sub(r"^(what('s| is| are) the |the )?(difference between )?", "", m.group(1), flags=re.I).strip()
            b = m.group(2).strip(" ?.")
            subs += [f"What is {a}?", f"What is {b}?"]
    else:
        parts = [p.strip(" ?.") for p in re.split(r"\?|;|,\s*and\s+|\band\b", q) if len(p.split()) >= 3]
        subs += [p for p in parts if p.lower() != q.lower().strip(" ?.")][:3]
    seen, out = set(), []
    for s in subs:
        key = s.lower()
        if key not in seen:
            seen.add(key)
            out.append(s)
    return out[:4]


def analyse(q: str, complexity_threshold: float = 0.4) -> QueryAnalysis:
    nq = normalise(q)
    intent = detect_intent(nq)
    score, reasons = score_complexity(nq, intent)
    complexity = "complex" if score >= complexity_threshold else "simple"
    return QueryAnalysis(
        original=q, normalised=nq, intent=intent, complexity=complexity, complexity_score=round(score, 2),
        complexity_reasons=reasons, safety_flags=detect_safety(nq),
        sub_queries=build_sub_queries(nq, intent) if complexity == "complex" else [nq],
    )
