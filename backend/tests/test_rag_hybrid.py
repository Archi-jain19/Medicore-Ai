"""Hybrid retrieval, query rewriting, fallback control flow, structured answers and safety handling.

A small synthetic library is indexed with the real embedding model. Only the LLM is a test double.
"""
import json

import pytest

faiss = pytest.importorskip("faiss")
pytest.importorskip("sentence_transformers")

from app.rag import hybrid, pipeline, rewrite as RW  # noqa: E402
from app.rag.extractive import _sentences, structured_answer  # noqa: E402
from app.rag.lexical import BM25Index, tokenize  # noqa: E402
from app.rag.retriever import Retriever  # noqa: E402
from app.rag.verifier import verify_answer  # noqa: E402

MODEL = "sentence-transformers/all-MiniLM-L6-v2"
FEVER = ("A fever is a body temperature that is higher than normal. It is usually a sign that your body is fighting an infection. "
         "Infections are the most common cause of a fever. Rest and drink plenty of fluids to help your body recover. "
         "Call your doctor if a fever lasts more than three days or is very high. Seek emergency care if you have a stiff neck or trouble breathing.")
HEADACHE = ("A headache is pain in any part of the head. Most headaches are caused by tight muscles, stress or lack of sleep. "
            "Headaches can also be triggered by dehydration or skipping meals. "
            "Resting in a quiet room and drinking water can help a headache. Take 400 mg of ibuprofen every six hours for a headache. "
            "See a doctor right away if a headache is sudden and severe, or comes with a stiff neck.")
PASSAGES = [
    ("medlineplus:headache", "MedlinePlus: Headache", "MedlinePus".replace("us", "Plus"), "health_topic", "https://medlineplus.gov/headache.html", HEADACHE),
    ("medlineplus:fever", "MedlinePlus: Fever", "MedlinePlus", "health_topic", "https://medlineplus.gov/fever.html", FEVER),
    ("cdc:fever", "CDC: Fever", "CDC", "web_page", "https://www.cdc.gov/fever.html", FEVER),      # near-duplicate text from another source
    ("medlineplus:hypothermia", "MedlinePlus: Hypothermia", "MedlinePlus", "health_topic", "https://medlineplus.gov/hypothermia.html",
     "Hypothermia is a dangerously low body temperature. Shivering, chills and feeling very cold are early signs. "
     "Get medical help right away if someone has confusion or slurred speech after being in the cold."),
    ("medlineplus:cold", "MedlinePlus: Common Cold", "MedlinePlus", "health_topic", "https://medlineplus.gov/commoncold.html",
     "The common cold is a viral infection of the nose and throat. Symptoms include a runny nose, sneezing and a sore throat. "
     "Washing your hands often helps prevent a cold."),
    ("medlineplus:dehydration", "MedlinePlus: Dehydration", "MedlinePlus", "health_topic", "https://medlineplus.gov/dehydration.html",
     "Dehydration means your body does not have enough fluid. It happens when you lose more fluid than you take in. "
     "Drinking enough fluids prevents dehydration. Get medical help if you cannot keep fluids down."),
    ("who:anaemia", "WHO fact sheet: Anaemia", "WHO", "fact_sheet", "https://www.who.int/anaemia",
     "Anaemia is a condition in which the number of red blood cells is too low. Haemoglobin is the protein in red blood cells that carries oxygen."),
    ("medlineplus:abdominal", "MedlinePlus: Abdominal Pain", "MedlinePlus", "health_topic", "https://medlineplus.gov/abdominalpain.html",
     "Abdominal pain is pain in the stomach area, often called a stomach ache. Many things can cause abdominal pain, such as gas, indigestion or an infection. "
     "Call your doctor if the pain is severe or does not go away."),
    ("pubmed:vitd", "Vitamin D deficiency review", "PubMed", "review", "https://pubmed.ncbi.nlm.nih.gov/1/",
     "Vitamin D deficiency is common. The marker used to measure vitamin D status is serum 25-hydroxyvitamin D."),
]


@pytest.fixture(scope="module")
def retriever(tmp_path_factory):
    from sentence_transformers import SentenceTransformer

    d = tmp_path_factory.mktemp("hyb")
    chunks = [{"chunk_id": f"{p[0]}#0", "doc_id": p[0], "title": p[1], "source": p[2], "doc_type": p[3], "url": p[4], "published": "2026-01-01",
               "retrieved_at": "t", "chunk_index": 0, "text": p[5]} for p in PASSAGES]
    vec = SentenceTransformer(MODEL).encode([c["text"] for c in chunks], normalize_embeddings=True).astype("float32")
    idx = faiss.IndexFlatIP(vec.shape[1])
    idx.add(vec)
    faiss.write_index(idx, str(d / "index.faiss"))
    (d / "chunks.jsonl").write_text("\n".join(json.dumps(c) for c in chunks), encoding="utf-8")
    (d / "manifest.json").write_text(json.dumps({"documents_by_source": {}}))
    return Retriever(d, MODEL)


class FakeLLM:
    name = "fake"

    def __init__(self, text="Fever is a higher than normal body temperature [1]."):
        self.text, self.prompt, self.calls = text, "", 0

    def generate(self, system, prompt):
        self.calls += 1
        self.prompt = prompt
        return self.text


# ------------------------------------------------------------------ lexical search
def test_bm25_finds_exact_terms_and_handles_plurals():
    idx = BM25Index(["Headaches are common.", "25-hydroxyvitamin D measures vitamin D status.", "Cough and colds."])
    assert idx.search("headache")[0][0] == 0
    assert idx.search("25-hydroxyvitamin")[0][0] == 1
    assert idx.search("coughing")[0][0] == 2
    toks = tokenize("The bruises really bruise easily")
    assert len(toks) == 2 and toks[0] == toks[1]                                     # singular and plural meet; filler words are ignored
    assert tokenize("headache") == tokenize("headaches")


# ------------------------------------------------------------------ understanding the question
def test_typos_are_repaired_but_known_words_are_not():
    vocab = frozenset({"fever", "headache", "dehydration", "what", "tummy"})
    assert RW.correct_typos("wat is feever", vocab) == ("wat is fever", True)
    assert RW.correct_typos("headake why", vocab)[0] == "headache why"
    assert RW.correct_typos("dehydratoin symptoms", vocab)[0].startswith("dehydration")
    assert RW.correct_typos("what is a fever", vocab) == ("what is a fever", False)


def test_everyday_phrases_map_to_medical_terms():
    p = RW.build_plan("I am feeling cold.")
    assert p.topics == ["feeling_cold"] and "feeling_cold" in p.symptom_keys
    assert p.primary[0].startswith("chills") and "hypothermia" in " ".join(p.rewrites)      # raw "cold" would find the common cold
    assert "common_cold" in RW.build_plan("I have a runny nose and a cold").topics
    assert RW.build_plan("my tummy hurts after I eat").topics == ["stomach_pain"]
    assert "hemoglobin" in " ".join(RW.build_plan("What does haemoglobin mean?").rewrites)


def test_questions_without_a_topic_ask_for_clarification():
    assert RW.build_plan("What does this medical term mean?").needs_clarification
    assert RW.build_plan("what does it mean").needs_clarification
    assert not RW.build_plan("what does haemoglobin mean").needs_clarification


def test_follow_up_questions_are_symptom_specific():
    q = RW.follow_up_questions(RW.build_plan("Why do I have a headache?"))
    assert len(q) == 3 and any("fever" in x.lower() for x in q)
    assert RW.follow_up_questions(RW.build_plan("What is dehydration?")) == []            # not a symptom statement


def test_llm_rewrites_are_best_effort():
    assert RW.llm_rewrites(FakeLLM('["tummy ache causes", "abdominal pain"]'), "tummy ache") == ["tummy ache causes", "abdominal pain"]
    assert RW.llm_rewrites(FakeLLM("not json"), "x") == []

    class Boom:
        def generate(self, *a):
            raise RuntimeError("down")

    assert RW.llm_rewrites(Boom(), "x") == [] and RW.llm_rewrites(None, "x") == []


# ------------------------------------------------------------------ hybrid retrieval
def test_feeling_cold_finds_the_right_sense_not_the_common_cold(retriever):
    r = retriever.retrieve("I am feeling cold.", "hybrid")
    assert r.evidence[0].doc_id in ("medlineplus:hypothermia", "medlineplus:fever") and r.level == "strong"


def test_misspelled_question_is_understood_and_reported(retriever):
    r = retriever.retrieve("wat is feever", "hybrid")
    assert r.plan.interpreted_as == "wat is fever" and r.evidence[0].doc_id.endswith("fever")
    assert any("We read your question as" in n for n in r.notes)


def test_both_retrievers_contribute(retriever):
    pool = {}
    hybrid.search_candidates(retriever, ["25-hydroxyvitamin"], None, pool)
    c = next(c for c in pool.values() if retriever.chunks[c.idx]["doc_id"] == "pubmed:vitd")
    assert c.bm25 > 0 and c.dense > 0                          # keyword hit AND a dense score for the same chunk


def test_near_duplicate_text_from_two_sources_is_removed(retriever):
    r = retriever.retrieve("What is a fever?", "hybrid")
    fever_docs = [e.doc_id for e in r.evidence if e.doc_id in ("medlineplus:fever", "cdc:fever")]
    assert len(fever_docs) == 1


def test_off_topic_questions_are_judged_as_no_evidence_after_every_stage(retriever):
    r = retriever.retrieve("How do I fix a flat bicycle tyre?", "hybrid")
    assert r.level == "none" and [s["stage"] for s in r.stages][:2] == ["direct", "rewritten"]
    assert any(s["stage"] == "other_sources" for s in r.stages)            # every source was tried before giving up


def test_fallback_stages_run_in_order_until_the_evidence_is_strong(retriever, monkeypatch):
    seq = iter(["none", "limited", "strong"])
    monkeypatch.setattr(hybrid, "judge", lambda sel: next(seq))
    r = retriever.retrieve("tummy ache", "hybrid")
    assert [s["stage"] for s in r.stages] == ["direct", "rewritten", "other_sources"] and r.level == "strong"
    assert r.stages[2]["source"] in retriever._hybrid_assets.sources


# ------------------------------------------------------------------ answers
def test_strong_evidence_with_llm_gets_a_structured_prompt_and_verification(retriever):
    llm = FakeLLM("**Short answer**\nA fever is a body temperature higher than normal [1].\n\n**When to get medical help**\nCall your doctor if a fever lasts more than three days [1]. "
                  "Please speak to a doctor or pharmacist if it is severe, getting worse, or you are worried.")
    out = pipeline.answer_question("What is a fever?", retriever, llm)
    assert out["status"] == "ok" and out["generated"] and out["evidence_level"] == "strong" and llm.calls == 1
    assert "CONTEXT" in llm.prompt and "EVIDENCE IS LIMITED" not in llm.prompt
    assert out["verification"]["flagged"] == 0 and out["verification"]["claims"]


def test_limited_evidence_gets_a_cautious_prompt_and_a_clear_label(retriever, monkeypatch):
    monkeypatch.setattr(hybrid, "judge", lambda sel: "limited")
    llm = FakeLLM("The sources only partly cover this [1].\n\n**General background (not from the sources above)**\nThis is less certain, but many things can cause tiredness.")
    out = pipeline.answer_question("I feel tired", retriever, llm)
    assert out["status"] == "limited_evidence" and "EVIDENCE IS LIMITED" in llm.prompt
    assert out["verification"]["general_background_not_checked"] is True                # not marked "unsupported"
    assert any("General background" in n for n in out["notes"]) and any("partly match" in n for n in out["notes"])


def test_limited_evidence_without_llm_still_helps_but_says_so(retriever, monkeypatch):
    monkeypatch.setattr(hybrid, "judge", lambda sel: "limited")
    out = pipeline.answer_question("Why do I have a headache?", retriever, None)
    assert out["status"] == "limited_evidence" and out["answer"].startswith("The sources I found only partly match")


def test_no_evidence_declines_honestly_and_never_calls_the_llm(retriever):
    llm = FakeLLM("never used")
    out = pipeline.answer_question("Which football team won the cup?", retriever, llm)
    # the LLM may be asked for search rewrites while looking, but it never writes an answer without evidence
    assert out["status"] == "insufficient_evidence" and "CONTEXT" not in llm.prompt and out["sources"] == [] and not out["generated"]
    assert "could not find a reliable answer" in out["answer"]


def test_unclear_symptoms_get_follow_up_questions_in_the_answer(retriever):
    out = pipeline.answer_question("Why do I have a headache?", retriever, None)
    assert "**A few questions that could help**" in out["answer"] and "fever" in out["answer"].lower()


def test_a_question_with_no_topic_asks_what_the_user_means(retriever):
    out = pipeline.answer_question("What does this medical term mean?", retriever, FakeLLM("never"))
    assert out["status"] == "needs_more_info" and out["sources"] == [] and "Which medical term" in out["answer"]


def test_structured_quoted_answer_has_sections_citations_and_no_doses(retriever):
    out = pipeline.answer_question("Why do I have a headache?", retriever, None)
    text = out["answer"]
    for heading in ("**Short answer**", "**What may explain it**", "**What you can do**", "**When to get medical help**"):
        assert heading in text
    assert "400 mg" not in text and "ibuprofen" not in text                          # sentences with doses are never quoted
    quoted = [l[2:].rsplit(" [", 1) for l in text.splitlines() if l.startswith("- ") and l.rstrip().endswith("]")]
    corpus = " ".join(p[5] for p in PASSAGES)
    assert quoted and all(s in corpus and 1 <= int(c.rstrip("]")) <= len(out["sources"]) for s, c in quoted)
    assert out["verification"]["flagged"] == 0                                        # headings are not treated as claims


# ------------------------------------------------------------------ safety
def test_an_explanation_question_is_not_mistaken_for_a_diagnosis_request(retriever):
    out = pipeline.answer_question("Why do I have a headache?", retriever, None)
    assert "diagnosis_request" not in out["analysis"]["safety_flags"] and "I cannot tell you" not in out["answer"]


def test_medicine_and_diagnosis_requests_are_declined_politely(retriever):
    out = pipeline.answer_question("What medicine can I take for a headache?", retriever, None)
    assert out["answer"].startswith("I cannot recommend medicines or doses") and "mg" not in out["answer"]
    out = pipeline.answer_question("Do I have a fever?", retriever, None)
    assert "I cannot tell you what is causing your symptoms" in out["answer"]


def test_urgent_and_emergency_situations_are_flagged(retriever):
    assert "prompt medical advice" in pipeline.answer_question("My baby has a fever", retriever, None)["answer"]
    out = pipeline.answer_question("My face is drooping and my speech is slurred", retriever, None)
    assert out["emergency_notice"] and "emergency number" in out["emergency_notice"]


def test_structured_answer_skips_unrelated_text(retriever):
    assert structured_answer("fix a tyre", [], retriever) is None
    assert _sentences("Take 400 mg of ibuprofen every six hours for a headache is common.")  # selection of dose sentences happens later


def test_verifier_ignores_headings_and_labelled_general_background(retriever):
    ev = retriever.retrieve("What is a fever?", "hybrid").evidence
    v = verify_answer("**Short answer**\nA fever is a body temperature that is higher than normal [1].\n\n**General background (not from the sources above)**\n"
                      "Totally unrelated claim about the moon being made of cheese.", ev, retriever)
    assert v["flagged"] == 0 and v["general_background_not_checked"] and len(v["claims"]) == 1


# ------------------------------------------------------------------ several symptoms in one message
def test_a_list_of_symptoms_is_split_into_separate_symptoms():
    from app.rag import symptoms as SY

    labels = [s.label for s in SY.parse_symptoms("I am feeling tired, thirsty and I pee a lot")]
    assert set(labels) == {"feeling tired", "feeling very thirsty", "passing urine a lot"}
    assert {s.label for s in SY.parse_symptoms("I have a headache, fever and a stiff neck since two days")} == {"fever", "headache", "stiff neck"}


def test_single_symptoms_and_plain_questions_are_not_treated_as_a_list():
    from app.rag import symptoms as SY

    for q in ["I have a headache", "What is a fever?", "Why do I have a headache?", "What does haemoglobin mean?", "HDL vs LDL"]:
        assert SY.parse_symptoms(q) == [], q


def test_symptom_list_answer_shows_linked_topics_without_diagnosing(retriever):
    out = pipeline.answer_question("I have a fever and a headache and a stiff neck", retriever, None)
    ans = out["answer"]
    assert out["status"] == "extractive" and out["mode"] == "extractive"
    assert "In short" in ans and "What these symptoms may be linked to" in ans
    assert "cannot diagnose" in ans and "I cannot tell which of these" in ans
    assert "you have" not in ans.lower().replace("if you have", "").replace("do you have", "")
    assert set(out["analysis"]["symptoms"]) == {"fever", "headache", "stiff neck"}
    # every citation number used in the answer exists in the sources shown
    import re
    used = {int(n) for n in re.findall(r"\[(\d+)\]", ans)}
    assert used and used <= {s["rank"] for s in out["sources"]}
    assert "ibuprofen" not in ans and "400 mg" not in ans          # no medicine advice or doses
    assert "stiff neck" in ans.lower()                              # warning signs from the sources are kept


def test_symptom_list_with_an_llm_gets_a_symptom_aware_prompt(retriever):
    llm = FakeLLM("Fever and headache may be linked to infections [1].")
    out = pipeline.answer_question("I have a fever and a headache", retriever, llm)
    assert out["mode"] == "generated" and llm.calls >= 1
    assert "SEVERAL symptoms" in llm.prompt and "may be linked to" in llm.prompt


def test_symptom_list_with_an_emergency_sign_still_shows_the_alert(retriever):
    out = pipeline.answer_question("I have chest pain, I feel dizzy and I am sweating", retriever, None)
    assert out["emergency_notice"]
