"""Symptom-list questions: "I feel tired, very thirsty and I pee a lot".

A single-topic search answers one symptom at a time and loses the others. Here we
  1. split the message into the separate symptoms the person described,
  2. search for each symptom and for all of them together,
  3. rank health topics by how many of the symptoms their trusted source text mentions *in the same passage*,
  4. show the best matches as "may be linked to ...", each with a sentence quoted from the source.

This never says the person HAS something. It tells them which topics the trusted sources link to the same group of
symptoms, says clearly that it cannot tell which (if any) applies, and lists warning signs and next steps.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.rag import hybrid as H
from app.rag.extractive import _DOSE, _SELF_CARE, _WARN, SAFETY_LINE, _sentences
from app.rag.lexical import STOPWORDS, tokenize
from app.rag.retriever import Evidence, Retriever

# everyday wording -> (label shown to the person, words the sources are likely to use)
_SYNONYMS: list[tuple[str, str, list[str]]] = [
    (r"\b(pee|peeing|urinat\w*|wee|weeing|toilet)\b.*\b(lot|often|more|frequent\w*|night)\b|\bfrequent urination\b|\bkeep going to the toilet\b",
     "passing urine a lot", ["urination", "urinate", "urinating", "urine", "urinary"]),
    (r"\b(thirst\w*|always thirsty|dry mouth)\b", "feeling very thirsty", ["thirst", "thirsty", "dry mouth"]),
    (r"\b(tired|exhaust\w*|fatigue\w*|no energy|worn out|weak|weakness|sleepy|lethargic)\b", "feeling tired", ["fatigue", "tired", "tiredness", "weakness", "weak"]),
    (r"\b(blurr?y|blurred|fuzzy) vision\b|\bcan'?t see (clearly|properly)\b", "blurry vision", ["blurred vision", "blurry vision", "vision"]),
    (r"\b(body|muscle) ?(pain|ache|aches|aching)\b|\bachy\b|\baches\b", "aches and pains", ["aches", "body aches", "muscle aches", "muscle pain"]),
    (r"\bhead ?aches?\b|\bhead (hurts|is pounding)\b|\bmigraine\b", "headache", ["headache", "headaches"]),
    (r"\bfever\w*\b|\bhigh temperature\b|\bburning up\b", "fever", ["fever", "temperature"]),
    (r"\bchills?\b|\bshiver\w*\b|\bfeel(ing)? cold\b", "chills", ["chills", "shivering"]),
    (r"\bsore throat\b|\bthroat (hurts|pain|ache)\b|\bscratchy throat\b", "sore throat", ["sore throat", "throat"]),
    (r"\bcough\w*\b", "cough", ["cough", "coughing"]),
    (r"\b(runny|stuffy|blocked|congested) nose\b|\bsneez\w*\b|\bcongestion\b", "runny or blocked nose", ["runny nose", "stuffy nose", "nasal congestion", "sneezing"]),
    (r"\bnause\w*\b|\bfeel(ing)? sick\b|\bvomit\w*\b|\bthrow(ing)? up\b", "feeling sick", ["nausea", "vomiting", "vomit"]),
    (r"\bdiarrh\w*\b|\bloose (stools?|motions?)\b", "diarrhea", ["diarrhea", "diarrhoea", "loose stools"]),
    (r"\b(stomach|tummy|belly|abdominal) ?(ache|pain|cramps?|hurts)\b|\bstomach (hurts|is hurting)\b", "stomach pain", ["abdominal pain", "stomach pain", "stomach cramps", "belly pain"]),
    (r"\bdizz\w*\b|\blight ?headed\b|\bvertigo\b|\bfaint\w*\b", "feeling dizzy", ["dizziness", "dizzy", "lightheaded", "fainting"]),
    (r"\bchest (pain|tightness|pressure|hurts)\b", "chest pain", ["chest pain", "chest tightness"]),
    (r"\b(short(ness)? of breath|breathless\w*|hard to breathe|wheez\w*)\b", "trouble breathing", ["shortness of breath", "breathing", "wheezing"]),
    (r"\b(weight loss|losing weight|lost weight|lose weight)\b", "losing weight", ["weight loss", "losing weight", "lose weight"]),
    (r"\b(gaining weight|weight gain)\b", "gaining weight", ["weight gain"]),
    (r"\b(rash|itch\w*|hives|red spots?)\b", "skin rash or itching", ["rash", "itching", "itchy", "hives"]),
    (r"\b(can'?t sleep|trouble sleeping|insomnia|sleepless)\b", "trouble sleeping", ["insomnia", "sleep"]),
    (r"\b(anxious|anxiety|panic|stressed|worried)\b", "feeling anxious", ["anxiety", "anxious", "stress", "panic"]),
    (r"\bback ?(ache|pain|hurts)\b", "back pain", ["back pain"]),
    (r"\b(joint|knee|neck|shoulder) (pain|ache|hurts)\b|\bstiff joints?\b", "joint pain", ["joint pain", "joints", "arthritis"]),
    (r"\bswollen (feet|ankles|legs)\b|\bswelling\b", "swelling", ["swelling", "swollen"]),
    (r"\bpale\b|\bpale skin\b", "looking pale", ["pale", "paleness", "pallor"]),
    (r"\bhair (loss|falling)\b", "hair loss", ["hair loss"]),
    (r"\b(constipat\w*)\b", "constipation", ["constipation"]),
    (r"\b(low mood|sad|depress\w*|hopeless)\b", "low mood", ["depression", "low mood", "sadness"]),
    (r"\b(cold hands|cold feet)\b", "cold hands and feet", ["cold hands", "cold feet"]),
    (r"\bnumb\w*\b|\btingling\b|\bpins and needles\b", "numbness or tingling", ["numbness", "tingling"]),
    (r"\b(sweat\w*|night sweats)\b", "sweating", ["sweating", "night sweats"]),
]
_SYN_RE = [(re.compile(p, re.I), label, terms) for p, label, terms in _SYNONYMS]

_NARRATIVE = re.compile(
    r"\b(i am|i'?m|im|i feel|i have|i'?ve|ive|i got|i get|having|feeling|experiencing|suffering|my .{0,25} (hurts|aches)|since|symptoms?)\b", re.I)
_FRAME_START = re.compile(
    r"^(hi|hello|hey|please|so|ok|okay|doctor|dr)?[\s,]*"
    r"((i am|i'?m|im|i feel|i have|i'?ve|ive|i got|i get|i am having|i have been|i'?ve been|i been|been)\s+"
    r"(feeling|having|getting|experiencing|suffering from|suffering|noticing|been)?\s*)+", re.I)
_TAIL_QUESTION = re.compile(
    r"[,;.\s]*(what (could|might|may|can) (it|this|that) be|what (is|could be) (wrong|happening|going on)|what do i have|what (might|could) i have|"
    r"what (am i|is) (going through|happening)|is (it|this) serious|should i (be )?worr(y|ied)|please help|any idea|what should i do|"
    r"can you (tell|help)|what does (this|it) mean|why\b.*)\s*\??$", re.I)
_DURATION = re.compile(r"\b(for|since|from|over|past|last)\s+(the\s+)?(last\s+|past\s+)?(a |an |one |two |three |four |five |\d+\s*)?(day|days|week|weeks|month|months|year|years|yesterday|morning|night|hours?)\b", re.I)
_SPLIT = re.compile(r"\s*(?:,|;|\band\b|\bwith\b|\balso\b|\bplus\b|\balong with\b|\bas well as\b|\bthen\b|&|\+)\s*", re.I)
_NOISE = frozenset("very really so quite bit little lot lots always sometimes often constantly keep keeps getting getting. been being a an the some too much more".split())


@dataclass
class Symptom:
    label: str
    terms: list[str]                                  # words/phrases the sources may use
    stems: list[frozenset[str]] = field(default_factory=list)  # each term as a set of stems (all must be present)


def _make(label: str, terms: list[str]) -> Symptom:
    stems = [frozenset(tokenize(t)) for t in dict.fromkeys([label, *terms])]
    return Symptom(label, terms, [s for s in stems if s])


def parse_symptoms(question: str) -> list[Symptom]:
    """The separate symptoms in a message, or [] when it is not a list of at least two symptoms."""
    q = re.sub(r"\s+", " ", question.strip())
    if not q or len(q) > 400 or not _NARRATIVE.search(q):
        return []
    if re.match(r"^(what|why|how|who|when|where|which|define|explain|tell me about)\b", q, re.I) and not re.search(r"\bi (feel|have|am|got)\b|\bmy\b|\bsymptoms\b", q, re.I):
        return []
    body = _TAIL_QUESTION.sub("", q)
    body = _DURATION.sub(" ", body)
    body = _FRAME_START.sub("", body).strip(" ,.;?!")
    found: list[Symptom] = []
    seen: set[str] = set()
    # known symptoms first (whole message): handles "pee a lot" style phrases that a comma split would cut apart
    for rx, label, terms in _SYN_RE:
        if rx.search(body) and label not in seen:
            seen.add(label)
            found.append(_make(label, terms))
    # unknown parts: keep their own content words, so a symptom we have no synonym for still takes part in the search
    for part in _SPLIT.split(body):
        part = part.strip(" ,.;?!")
        if not part or any(rx.search(part) for rx, _, _ in _SYN_RE):
            continue
        words = [w for w in re.findall(r"[A-Za-z][A-Za-z'-]+", part.lower()) if w not in _NOISE and w not in STOPWORDS
                 and w not in {"i", "my", "me", "have", "feel", "feeling", "am", "is", "are", "been", "got", "get", "pain", "hurts", "hurt"}]
        if 1 <= len(words) <= 4 and " ".join(words) not in seen:
            label = " ".join(words)
            seen.add(label)
            found.append(_make(label, [label]))
    return found if len(found) >= 2 else []


# --------------------------------------------------------------------------- matching
@dataclass
class TopicMatch:
    doc_id: str
    title: str
    covered: list[int]                # indexes into the symptom list, mentioned together in the best passage
    covered_any: list[int]            # mentioned anywhere in the page
    best: Evidence                    # the passage that mentions the most symptoms
    score: float
    quote: str | None = None
    covered_sentence: int = 0         # symptoms named inside the quoted sentence itself


def _mentions(stems: set[str], symptom: Symptom) -> bool:
    return any(t <= stems for t in symptom.stems)


def _doc_chunks(r: Retriever) -> dict[str, list[int]]:
    m = getattr(r, "_doc_chunks", None)
    if m is None:
        m = {}
        for i, c in enumerate(r.chunks):
            m.setdefault(c["doc_id"], []).append(i)
        r._doc_chunks = m
    return m


def _evidence(r: Retriever, idx: int, sim: float) -> Evidence:
    ch = r.chunks[idx]
    e = Evidence(ch["chunk_id"], ch["doc_id"], ch["title"], ch["source"], ch["doc_type"], ch["url"], ch.get("published"), ch["text"], sim)
    e.reliability = r._reliability(e)
    e.recency = r._recency(e)
    return e


def find_topics(r: Retriever, symptoms: list[Symptom], question: str, limit: int = 5) -> list[TopicMatch]:
    queries = [", ".join(s.label for s in symptoms) + " symptoms", question]
    queries += [f"{s.terms[0] if s.terms else s.label} symptoms causes" for s in symptoms]
    # pairs help the pages that connect two symptoms rise even when neither is the page's main topic
    for i in range(len(symptoms)):
        for j in range(i + 1, min(len(symptoms), i + 3)):
            queries.append(f"{symptoms[i].label} and {symptoms[j].label}")
    pool: dict[int, H.Cand] = {}
    H.search_candidates(r, list(dict.fromkeys(queries))[:10], None, pool)
    by_doc = _doc_chunks(r)
    docs = {r.chunks[i]["doc_id"] for i in pool}
    matches: list[TopicMatch] = []
    for doc_id in docs:
        best_idx, best_cov = None, []
        any_cov: set[int] = set()
        for ci in by_doc[doc_id]:
            ch = r.chunks[ci]
            stems = set(tokenize(ch["title"] + " " + " ".join(ch.get("also_called") or []) + " " + ch["text"]))
            cov = [k for k, s in enumerate(symptoms) if _mentions(stems, s)]
            any_cov.update(cov)
            sim = pool[ci].dense if ci in pool else 0.0
            key = (len(cov), sim)
            if best_idx is None or key > (len(best_cov), pool[best_idx].dense if best_idx in pool else 0.0):
                best_idx, best_cov = ci, cov
        if not best_cov:
            continue
        sim = pool[best_idx].dense if best_idx in pool else 0.0
        ev = _evidence(r, best_idx, sim)
        # more symptoms together in one passage is the strongest signal; similarity and source quality refine it
        score = len(best_cov) / len(symptoms) * 1.0 + 0.25 * len(any_cov) / len(symptoms) + 0.5 * sim + 0.1 * ev.reliability
        title = re.sub(r"^[A-Za-z ]+: ", "", ev.title)
        matches.append(TopicMatch(doc_id, title, best_cov, sorted(any_cov), ev, score))
    matches.sort(key=lambda m: m.score, reverse=True)
    # one topic per name (several sources can describe the same condition), keep the best-scoring
    seen, out = set(), []
    for m in matches:
        key = m.title.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(m)
        if len(out) == limit:
            break
    return out


# sentences about spreading, preventing or vaccinating are not descriptions of symptoms, even when they say "cough"
_NOT_SYMPTOM_TALK = re.compile(r"\b(catch|spread|spreads|prevent\w*|protect\w*|vaccin\w*|shots?|immuni[sz]\w*|cover(ing)?|wash\w*|avoid\w*|"
                               r"transmi\w*|outbreaks?|residents|staff|exposed|exposure)\b", re.I)
_LOW_VALUE_TITLE = re.compile(r"\b(vaccin\w*|outbreaks?|surveillance|key facts|report|shelter|guidance|recommendations?|schedule)\b", re.I)
_LIFESTYLE = re.compile(r"\b(healthy (diet|eating|weight)|balanced diet|exercise|physical activity|get (enough )?sleep|enough sleep|limit(ing)? (alcohol|salt|sugar|caffeine)|"
                        r"quit smoking|stop smoking|reduce stress|manage stress|stay hydrated|drink (plenty|enough|water|fluids)|eat (more|fewer|a healthy))\b", re.I)
_MONITOR = re.compile(r"\b(monitor\w*|keep (track|a record|a diary|a log)|track(ing)? your|check your (blood|weight|temperature|symptoms)|write down|"
                      r"pay attention to|watch for|keep an eye)\b", re.I)
_NOT_SYMPTOM_TALK_SOFT = re.compile(r"\b(vaccin\w*|outbreaks?|residents|staff|transmi\w*)\b", re.I)
_MEDICINE_ADVICE = re.compile(r"\b(take|taking|use|using|try|trying)\b.{0,60}\b(medicines?|medications?|pain relievers?|painkillers?|drugs?|tablets?|pills?|antibiotics?|over-the-counter|acetaminophen|ibuprofen|aspirin|naproxen)\b", re.I)
_SPLIT_SENT = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9(])|\n+")


def _quote_candidates(text: str) -> list[str]:
    """Sentences usable as a quote. Source lists such as 'Symptoms include: feeling thirsty, blurred vision' are fine here,
    so unlike the general answer we do not insist on a verb."""
    out = []
    for s in _SPLIT_SENT.split(text):
        s = re.sub(r"^#+\s*", "", s.strip(" -•\t"))
        if 25 <= len(s) <= 420 and s[0].isalnum() and not s.endswith(":") and not re.match(r"^(figure|table|copyright|©|doi:|http|source:)", s, re.I) \
                and not _DOSE.search(s):
            out.append(s)
    return out


def _best_sentence(r: Retriever, m: TopicMatch, symptoms: list[Symptom]) -> tuple[str, int] | None:
    """The sentence in the topic's best passage that mentions the most of the person's symptoms (and how many)."""
    sents = [s for s in _quote_candidates(m.best.text) if not _NOT_SYMPTOM_TALK.search(s)]
    if not sents:
        return None
    qv = r.embed([", ".join(x.label for x in symptoms)])[0]
    sims = r.embed(sents) @ qv
    best, best_key = None, (0, -1.0)
    for s, sim in zip(sents, sims):
        stems = set(tokenize(s))
        n = sum(1 for sym in symptoms if _mentions(stems, sym))
        if (n, float(sim)) > best_key:
            best, best_key = s, (n, float(sim))
    return (best, best_key[0]) if best and best_key[0] >= 1 else None


def rerank(r: Retriever, matches: list[TopicMatch], symptoms: list[Symptom], top: int = 10) -> list[TopicMatch]:
    """Looks at the actual sentences: a topic whose quoted sentence names several of the symptoms goes first."""
    scored = []
    for m in matches[:top]:
        if _LOW_VALUE_TITLE.search(m.title):
            continue                       # outbreak reports, vaccine pages and guidance describe events, not what symptoms mean
        q = _best_sentence(r, m, symptoms)
        if q:
            m.quote = q[0]
            m.score += 2.0 * q[1] / len(symptoms)
            m.covered_sentence = q[1]
        if _LOW_VALUE_TITLE.search(m.title):
            m.score -= 0.8                     # news-style pages and vaccine pages describe events, not symptoms
        scored.append(m)
    scored.sort(key=lambda m: (m.quote is not None, m.score), reverse=True)
    return scored


def level_for(matches: list[TopicMatch], symptoms: list[Symptom]) -> str:
    """strong: a page mentions at least two of the symptoms together (or all of them, if only two were listed)."""
    quoted = [m for m in matches if m.quote]
    if not quoted:
        return "none"
    top = max(len(m.covered) for m in quoted)
    if top >= 2:
        return "strong"
    return "limited" if top == 1 else "none"


def symptom_answer(r: Retriever, symptoms: list[Symptom], matches: list[TopicMatch], follow_ups: list[str],
                   limited: bool = False, avoid_medicine: bool = False) -> tuple[str, list[Evidence]]:
    """Quoted answer in the same plain structure as the rest of the assistant. Returns the text and the evidence that is
    cited, in citation order."""
    evidence: list[Evidence] = []

    def cite(e: Evidence) -> int:
        for i, x in enumerate(evidence, 1):
            if x.chunk_id == e.chunk_id:
                return i
        evidence.append(e)
        return len(evidence)

    names = [s.label for s in symptoms]
    listed = ", ".join(names[:-1]) + " and " + names[-1] if len(names) > 1 else names[0]
    parts = []
    if limited:
        parts.append("The sources I found only partly match what you described, so please treat this as general information only.")
    lines = []
    shown, seen_quotes = [], set()
    for m in matches:
        if m.covered and m.quote and m.quote.lower() not in seen_quotes:     # two pages often share the same symptom list
            seen_quotes.add(m.quote.lower())
            shown.append(m)
        if len(shown) == 4:
            break
    for m in shown:
        q = m.quote
        n = cite(m.best)
        got = [symptoms[k].label for k in m.covered]
        match_txt = f"mentions {len(got)} of your {len(symptoms)} symptoms" if len(symptoms) > 2 or len(got) < len(symptoms) \
            else "mentions both of your symptoms"
        lines.append(f"- **{m.title}** ({match_txt}: {', '.join(got)}). “{q}” [{n}]")
    if not lines:
        return "", []
    topic_names = [m.title for m in shown]
    topics_txt = ", ".join(topic_names[:-1]) + " and " + topic_names[-1] if len(topic_names) > 1 else topic_names[0]
    parts.append(f"**In short**\nYou told me about {listed}. In the trusted sources, these symptoms are most often discussed together under: "
                 f"{topics_txt}. I cannot tell which of these, if any, applies to you. A doctor can ask questions, examine you "
                 "and narrow it down.")
    parts.append("**What these symptoms may be linked to**\nI cannot tell which of these, if any, is behind your symptoms, because that "
                 "needs a doctor to ask questions and examine you. These are the health topics whose trusted sources talk about "
                 "several of the symptoms you listed together:\n" + "\n".join(lines))

    # practical steps and warning signs: from the best-matching passages only
    care_lines, warn_lines = [], []
    pool_ev = [m.best for m in shown]
    for e in pool_ev:
        for s in _sentences(e.text):
            if _DOSE.search(s):
                continue
            if _WARN.search(s) and len(warn_lines) < 3 and all(s not in x for x in warn_lines):
                warn_lines.append(f"- {s} [{cite(e)}]")
            elif _SELF_CARE.search(s) and not (avoid_medicine and re.search(r"\b(take|use|try)\b.{0,50}\b(medicine|medication|drug|pill|tablet)", s, re.I)) \
                    and len(care_lines) < 3 and all(s not in x for x in care_lines):
                care_lines.append(f"- {s} [{cite(e)}]")
    # lifestyle and monitoring tips come from the whole page of each shown topic, not only the best passage
    life_lines, watch_lines = [], []
    by_doc = _doc_chunks(r)
    for m in shown[:3]:
        for ci in by_doc.get(m.doc_id, []):
            e = _evidence(r, ci, 0.0)
            for sent in _sentences(e.text):
                if _DOSE.search(sent) or _NOT_SYMPTOM_TALK_SOFT.search(sent) or any(sent in x for x in care_lines + warn_lines + life_lines + watch_lines):
                    continue
                if avoid_medicine and _MEDICINE_ADVICE.search(sent):
                    continue
                if _MONITOR.search(sent) and len(watch_lines) < 2:
                    watch_lines.append(f"- {sent} [{cite(e)}]")
                elif _LIFESTYLE.search(sent) and len(life_lines) < 2:
                    life_lines.append(f"- {sent} [{cite(e)}]")
    if care_lines:
        parts.append("**What you can do**\n" + "\n".join(care_lines))
    if life_lines:
        parts.append("**Everyday habits that may help**\n" + "\n".join(life_lines))
    if watch_lines:
        parts.append("**What to keep an eye on**\n" + "\n".join(watch_lines))
    parts.append("**When to get medical help**\n" + ("\n".join(warn_lines) + "\n" if warn_lines else "") + SAFETY_LINE)
    if follow_ups:
        parts.append("**A few questions that could help**\n" + "\n".join(f"- {q}" for q in follow_ups))
    return "\n\n".join(parts), evidence


def symptom_follow_ups(symptoms: list[Symptom]) -> list[str]:
    return ["How long have you had these symptoms, and are they getting better, the same or worse?",
            "Did they start together, or one after another?",
            "Do you have any health conditions, take regular medicines, or could you be pregnant?"]


SYMPTOM_PROMPT_NOTE = (
    "\nThe user listed SEVERAL symptoms: {symptoms}. Use the CONTEXT to say which health topics are linked to several of these "
    "symptoms together, naming each topic and how many of the symptoms it mentions. Always say 'may be linked to', never 'you have', "
    "and say clearly that you cannot tell which one applies. Begin with **In short**: two or three plain sentences "
    "summarising the symptoms and the topics they may be linked to. Then use the headings **What these symptoms may be linked to**, "
    "**What you can do**, **Everyday habits that may help**, **What to keep an eye on**, **When to get medical help** and "
    "**A few questions that could help**, leaving out any heading the CONTEXT cannot support. No medicine names or doses."
)
