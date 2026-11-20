"""Medical query understanding: spelling repair, everyday-phrase mapping, expansion and follow-up questions.

Rule-based and deterministic, so it can be tested and explained. An LLM may add extra rewrites when one is available
(`llm_rewrites`), but nothing here depends on it.

The mappings below only connect how people *talk* ("tummy ache", "feeling cold") to the standard terms the trusted
sources use ("abdominal pain", "chills"). They are search aids; they never state a cause or diagnosis.
"""
from __future__ import annotations

import difflib
import json
import re
from dataclasses import dataclass, field

from app.rag.lexical import STOPWORDS, content_words

# key, pattern on the lower-cased question, search terms, is_symptom
_RULES: list[tuple[str, str, list[str], bool]] = [
    ("feeling_cold", r"\b(feel(ing)?|am|i'?m|being)\s+(so\s+|very\s+|really\s+)?cold\b|\bfreezing\b|\bshiver|\bchills?\b|\bcold (hands|feet)\b",
     ["chills fever shivering", "low body temperature hypothermia", "cold intolerance", "chills"], True),
    ("common_cold", r"\b(common cold|runny nose|stuffy nose|blocked nose|sneez\w*|have a cold|got a cold|catch(ing)? a cold|cold symptoms)\b",
     ["common cold", "common cold symptoms", "runny nose"], True),
    ("headache", r"\bhead ?aches?\b|\bhead (hurts|is (pounding|throbbing|aching))\b|\bmigraines?\b|\bhead pain\b",
     ["headache", "headache causes", "headache when to see a doctor", "migraine"], True),
    ("fever", r"\bfever\w*\b|\bhigh temperature\b|\btemperature\b|\bpyrexia\b|\bburning up\b",
     ["fever", "fever causes", "fever when to see a doctor"], True),
    ("cough", r"\bcough\w*\b|\bcoughing\b",
     ["cough", "cough causes", "persistent cough"], True),
    ("sore_throat", r"\b(sore|scratchy|painful) throat\b|\bthroat (hurts|pain|ache)\b",
     ["sore throat", "sore throat causes"], True),
    ("stomach_pain", r"\b(stomach|tummy|belly|abdominal|abdomen) ?(ache|pain|hurts|cramps?)\b|\bstomach (hurts|is hurting)\b|\bbellyache\b",
     ["abdominal pain", "stomach pain causes", "stomach ache"], True),
    ("nausea", r"\bnausea\w*\b|\bnauseous\b|\bfeel(ing)? sick\b|\bvomit\w*\b|\bthrow(ing)? up\b",
     ["nausea and vomiting", "nausea", "vomiting causes"], True),
    ("diarrhea", r"\bdiarrh\w*\b|\bloose (stools?|motions?)\b|\brunny tummy\b", ["diarrhea", "diarrhea causes"], True),
    ("constipation", r"\bconstipat\w*\b|\bcan'?t (poo|poop|go to the toilet)\b", ["constipation", "constipation causes"], True),
    ("dizziness", r"\bdizz\w*\b|\blight ?headed\b|\bvertigo\b|\bspinning\b|\bfaint\w*\b", ["dizziness", "dizziness and vertigo", "fainting"], True),
    ("fatigue", r"\b(tired|exhausted|fatigue\w*|no energy|worn out|always sleepy|lethargic)\b", ["fatigue", "tiredness causes"], True),
    ("chest_pain", r"\bchest (pain|tightness|pressure|hurts)\b", ["chest pain", "chest pain when to get help"], True),
    ("breathless", r"\bshort(ness)? of breath\b|\bbreathless\w*\b|\bhard to breathe\b|\bcan'?t breathe\b", ["shortness of breath", "breathing problems"], True),
    ("back_pain", r"\bback ?(ache|pain|hurts)\b", ["back pain", "back pain causes"], True),
    ("rash", r"\brash(es)?\b|\bitch\w*\b|\bhives\b|\bred spots?\b", ["rash", "skin rash causes", "itching"], True),
    ("sleep", r"\b(can'?t|cannot|trouble|difficulty) (sleep|fall asleep)\b|\binsomnia\b|\bsleepless\b", ["insomnia", "sleep problems"], True),
    ("anxiety", r"\banxi\w*\b|\bpanic\b|\bstress(ed)?\b|\bworr(y|ied)\b", ["anxiety", "stress", "anxiety disorders"], True),
    ("uti", r"\bburning (when|while) (i )?(pee|urinat\w*)\b|\bpainful urination\b|\burinary tract infection\b|\buti\b", ["urinary tract infection", "painful urination"], True),
    ("dehydration", r"\bdehydrat\w*\b|\bdry mouth\b|\bvery thirsty\b|\bnot drinking enough\b", ["dehydration", "dehydration signs and symptoms"], False),
    ("blood_pressure", r"\bblood pressure\b|\bbp\b|\bhypertension\b|\bhigh bp\b", ["blood pressure", "high blood pressure", "blood pressure readings"], False),
    ("low_bp", r"\blow blood pressure\b|\bhypotension\b|\blow bp\b", ["low blood pressure", "hypotension"], False),
    ("hemoglobin", r"\bh(a)?emoglobin\b|\bhb\b|\bhgb\b|\bhaemoglobin\b", ["hemoglobin", "hemoglobin test", "anemia"], False),
    ("anemia", r"\ban(a)?emi\w*\b|\blow iron\b|\biron deficiency\b", ["anemia", "iron deficiency anemia"], False),
    ("vitamin_d", r"\bvit(amin)?\.? ?d\b|\b25[- ]?(oh|hydroxy)\b", ["vitamin D", "vitamin D deficiency", "vitamin D test"], False),
    ("cholesterol", r"\bcholesterol\b|\bldl\b|\bhdl\b|\blipid\w*\b|\btriglycerides?\b", ["cholesterol", "cholesterol levels", "HDL and LDL cholesterol"], False),
    ("diabetes", r"\bdiabet\w*\b|\bblood (sugar|glucose)\b|\bhba1c\b|\ba1c\b|\bglucose\b", ["diabetes", "blood sugar", "A1C test"], False),
    ("thyroid", r"\bthyroid\b|\btsh\b", ["thyroid", "thyroid tests", "TSH test"], False),
    ("kidney", r"\bkidney\w*\b|\bcreatinine\b|\begfr\b", ["kidney disease", "creatinine test", "kidney function tests"], False),
    ("allergy", r"\ballerg\w*\b|\bhay fever\b", ["allergy", "allergic reactions"], False),
    ("asthma", r"\basthma\w*\b|\bwheez\w*\b", ["asthma", "wheezing"], True),
    ("flu", r"\bflu\b|\binfluenza\b", ["influenza", "flu symptoms"], True),
    ("weight", r"\blos(e|ing) weight\b|\bweight loss\b|\bgain(ing)? weight\b|\bunexplained weight\b", ["weight loss", "weight gain"], True),
]
_RULES_RE = [(k, re.compile(p, re.I), terms, sym) for k, p, terms, sym in _RULES]

# Generic words that carry no topic: if nothing else is left, we must ask what the user means.
_GENERIC = frozenset("medical term terms word meaning mean means definition define explain explanation thing something this that it".split())
_FILLER = re.compile(
    r"^(please |pls |hey |hi |hello |ok |okay |so |can you |could you |would you |will you |tell me |explain |i want to know |i wanna know |"
    r"i would like to know |i need to know |what do you know about |do you know )+", re.I)
_TOPIC_FRAME = re.compile(
    r"^(what('?s| is| are| does| do)|whats|define|meaning of|why (do|am|does|is|are) (i|my|me)|why do i have|why am i|how (do|can|to)|"
    r"i (am|have|feel|got|get)|i'?m|my|is it normal|should i)\b\s*", re.I)

# Rules whose raw wording misleads a keyword search (the word "cold" finds the Common Cold page, which is a different
# thing from feeling cold). For these, the rule's search terms REPLACE the raw question in the first search, and the
# ambiguous word is ignored when matching titles.
_REPLACE_RAW = {"feeling_cold": {"cold"}}

COMMON_OK = frozenset("tummy bp uti hb hgb flu vit nhs pcr icu ecg ekg mri ct".split())


@dataclass
class QueryPlan:
    original: str
    corrected: str
    was_corrected: bool
    topics: list[str] = field(default_factory=list)          # canonical topic keys matched (e.g. "headache")
    symptom_keys: list[str] = field(default_factory=list)    # subset that are symptoms
    rewrites: list[str] = field(default_factory=list)        # alternative search strings, best first
    primary: list[str] = field(default_factory=list)         # queries for the first search (the corrected question unless replaced)
    keywords: str = ""                                        # content words only (for BM25 / term coverage)
    rule_terms: list[str] = field(default_factory=list)       # canonical medical words for matched everyday phrases
    needs_clarification: bool = False
    llm_rewrites: list[str] = field(default_factory=list)

    @property
    def interpreted_as(self) -> str | None:
        return self.corrected if self.was_corrected else None


def correct_typos(text: str, vocab: frozenset[str] | set[str], cutoff: float = 0.8) -> tuple[str, bool]:
    """Replaces words that are not in the corpus vocabulary with their closest corpus word (e.g. 'feever' -> 'fever').
    Short words, known words and anything without a confident match are left alone."""
    if not vocab:
        return text, False
    by_first: dict[str, list[str]] = {}
    changed = False
    out = []
    for tok in re.findall(r"[A-Za-z']+|[^A-Za-z']+", text):
        low = tok.lower()
        if not re.fullmatch(r"[a-z]{4,}", low) or low in vocab or low in STOPWORDS or low in COMMON_OK:
            out.append(tok)
            continue
        if low not in by_first:
            by_first[low] = [w for w in vocab if abs(len(w) - len(low)) <= 2 and w[0] == low[0]] or \
                            [w for w in vocab if abs(len(w) - len(low)) <= 2]
        match = difflib.get_close_matches(low, by_first[low], n=1, cutoff=cutoff)
        if match:
            changed = True
            out.append(match[0].capitalize() if tok[0].isupper() else match[0])
        else:
            out.append(tok)
    return "".join(out), changed


def _strip_frame(q: str) -> str:
    q = re.sub(r"[?!.]+$", "", q.strip())
    q = _FILLER.sub("", q).strip()
    q = _TOPIC_FRAME.sub("", q).strip()
    q = re.sub(r"^(a|an|the|some|any)\s+", "", q, flags=re.I)
    return q


def build_plan(question: str, vocab: frozenset[str] | set[str] | None = None) -> QueryPlan:
    q0 = re.sub(r"\s+", " ", question.strip())
    corrected, changed = correct_typos(q0, vocab or frozenset())
    low = corrected.lower()
    topics: list[str] = []
    symptoms: list[str] = []
    rewrites: list[str] = []
    replace_terms: list[str] = []
    canon: list[str] = []
    drop: set[str] = set()
    for key, rx, terms, is_sym in _RULES_RE:
        if rx.search(low):
            topics.append(key)
            if is_sym:
                symptoms.append(key)
            rewrites += terms
            canon += content_words(" ".join(terms[:2]))
            if key in _REPLACE_RAW and "common_cold" not in topics:
                replace_terms += terms[:3]
                drop |= _REPLACE_RAW[key]
    # "common cold" should win over the ambiguous "cold" sense when someone says they have a cold with a runny nose
    core = _strip_frame(_FILLER.sub("", corrected))
    words = [w for w in content_words(core) if w not in _GENERIC and w not in drop]
    keywords = " ".join(words)
    needs_clarification = not words and not topics
    if words and not topics:
        base = " ".join(words)
        # No health-specific words are added here: tacking "causes symptoms" onto an unrelated question would make
        # it look medical and pull in random topics.
        rewrites += [base, f"what is {base}"]
    elif words and topics:
        rewrites.append(" ".join(words))
    seen, uniq = set(), []
    for r in rewrites:
        k = r.lower().strip()
        if k and k not in seen and k != low.strip(" ?!."):
            seen.add(k)
            uniq.append(r)
    return QueryPlan(original=q0, corrected=corrected, was_corrected=changed, topics=topics, symptom_keys=symptoms,
                     rewrites=uniq[:7], primary=replace_terms[:3] or [corrected], keywords=keywords,
                     rule_terms=sorted(set(canon)), needs_clarification=needs_clarification)


def llm_rewrites(llm, question: str, n: int = 3) -> list[str]:
    """Optional: ask the LLM for alternative search phrases. Any failure just means no extra rewrites."""
    if llm is None:
        return []
    prompt = (
        "Rewrite this health question as short search queries that would match pages on trusted medical websites "
        "(use standard medical terms and common synonyms). Fix spelling. Do not answer the question. "
        f'Return only a JSON list of at most {n} strings.\n\nQuestion: {question}'
    )
    try:
        raw = llm.generate("You turn everyday health questions into search queries.", prompt)
        m = re.search(r"\[.*\]", raw, re.S)
        items = json.loads(m.group(0)) if m else []
        return [str(x).strip() for x in items if isinstance(x, str) and 2 < len(x.strip()) < 120][:n]
    except Exception:  # noqa: BLE001 - rewriting is best-effort
        return []


# --------------------------------------------------------------------------- follow-up questions
_FOLLOW_UPS: dict[str, list[str]] = {
    "headache": ["How long have you had the headache, and is it getting worse?", "Is the pain on one side or all over?",
                 "Do you also have a fever, a stiff neck, vision changes, or did you recently hurt your head?"],
    "fever": ["How high is the temperature, and for how long has it lasted?", "Is this for an adult, a child or a baby?",
              "Do you have a rash, trouble breathing, a stiff neck or severe pain?"],
    "cough": ["How long have you had the cough?", "Is it dry, or do you bring up phlegm?",
              "Do you also have a fever, shortness of breath or chest pain?"],
    "feeling_cold": ["Do you also have a fever, shivering or aches?", "Does it happen all the time, or only in some situations (for example in cold rooms)?",
                     "Have you noticed tiredness, weight change or dry skin?"],
    "common_cold": ["How many days have you had symptoms?", "Do you have a high fever or trouble breathing?"],
    "sore_throat": ["How long has your throat been sore?", "Is it hard to swallow or breathe, or do you have a fever?"],
    "stomach_pain": ["Where exactly is the pain, and how long has it lasted?", "Do you have vomiting, diarrhea, fever, or blood in your stool?"],
    "nausea": ["How long have you felt sick?", "Can you keep fluids down, and do you have a fever or stomach pain?"],
    "diarrhea": ["How many days has it lasted?", "Do you have a fever, blood in the stool, or signs of dehydration?"],
    "dizziness": ["Does the room feel like it is spinning, or do you feel faint?", "Did it start suddenly, and do you have chest pain, weakness or trouble speaking?"],
    "fatigue": ["How long have you felt this tired?", "Any change in sleep, mood, weight or appetite?"],
    "chest_pain": ["Is the pain severe, spreading to your arm or jaw, or with trouble breathing?"],
    "breathless": ["Did it start suddenly, and are you able to speak in full sentences?"],
    "back_pain": ["How long have you had it, and did it start after an injury or lifting?", "Do you have numbness, weakness or trouble passing urine?"],
    "rash": ["Where is the rash, and when did it start?", "Is it itchy or painful, and do you have a fever?"],
    "sleep": ["How long have you had trouble sleeping?", "Is stress, caffeine or pain affecting your sleep?"],
    "anxiety": ["How long have you felt this way, and is it affecting daily life?"],
    "uti": ["Do you have a fever, back pain or blood in your urine?"],
    "flu": ["When did the symptoms start, and do you have a high fever or trouble breathing?"],
    "asthma": ["How often do you wheeze, and is it getting worse?"],
    "weight": ["How much weight, over how long, and was it intended?"],
}
_GENERIC_FOLLOW_UP = ["How long have you had this?", "Is it getting better, staying the same or getting worse?",
                      "Do you have any other symptoms?"]


def follow_up_questions(plan: QueryPlan, limit: int = 3) -> list[str]:
    for key in plan.symptom_keys:
        if key in _FOLLOW_UPS:
            return _FOLLOW_UPS[key][:limit]
    return _GENERIC_FOLLOW_UP[:limit] if plan.symptom_keys else []
