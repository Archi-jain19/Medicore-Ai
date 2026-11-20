"""RAG tests: query analysis, ranking, retrieval, verification, pipeline gating, chat API.

A small real FAISS index is built with the real embedding model from a handful of passages. The only test
double is the LLM (so tests are offline and deterministic); the pipeline has no fallback fake answers.
"""
import json
from datetime import date

import pytest

faiss = pytest.importorskip("faiss")
pytest.importorskip("sentence_transformers")

from app.rag import pipeline, query as Q  # noqa: E402
from app.rag.config import RankingConfig  # noqa: E402
from app.rag.retriever import Evidence, Retriever  # noqa: E402
from app.rag.verifier import verify_answer  # noqa: E402

MODEL = "sentence-transformers/all-MiniLM-L6-v2"
PASSAGES = [
    ("who:diabetes", "WHO fact sheet: Diabetes", "WHO", "fact_sheet", "2024-11-14",
     "Diabetes is a chronic disease that occurs when the pancreas does not produce enough insulin or when the body cannot "
     "effectively use the insulin it produces. Insulin is a hormone that regulates blood glucose. Over time diabetes can "
     "damage the heart, blood vessels, eyes, kidneys and nerves."),
    ("who:hypertension", "WHO fact sheet: Hypertension", "WHO", "fact_sheet", "2023-03-16",
     "Hypertension is diagnosed if, when measured on two different days, the systolic blood pressure readings on both days "
     "is greater than or equal to 140 mmHg and the diastolic blood pressure readings are greater than or equal to 90 mmHg."),
    ("cdc:cholesterol", "CDC: About Cholesterol", "CDC", "web_page", "2024-05-15",
     "LDL cholesterol is often called bad cholesterol because high levels can build up in the walls of arteries. HDL "
     "cholesterol is called good cholesterol because it helps remove other forms of cholesterol from your bloodstream."),
    ("pubmed:111", "Vitamin D deficiency review", "PubMed", "review", "2012-01-01",
     "Vitamin D deficiency is common worldwide and is associated with reduced bone density. Serum 25-hydroxyvitamin D is "
     "the usual laboratory marker used to assess vitamin D status in adults."),
    ("who:anaemia", "WHO fact sheet: Anaemia", "WHO", "fact_sheet", "2023-05-01",
     "Anaemia is a condition in which the number of red blood cells or their oxygen-carrying capacity is insufficient. "
     "Haemoglobin concentration thresholds used to define anaemia vary by age, sex and pregnancy status."),
]


@pytest.fixture(scope="module")
def retriever(tmp_path_factory):
    from sentence_transformers import SentenceTransformer

    d = tmp_path_factory.mktemp("rag")
    chunks = [{"chunk_id": f"{p[0]}#0", "doc_id": p[0], "title": p[1], "source": p[2], "doc_type": p[3],
               "url": f"https://example.org/{p[0]}", "published": p[4], "retrieved_at": "t", "chunk_index": 0, "text": p[5]}
              for p in PASSAGES]
    vec = SentenceTransformer(MODEL).encode([c["text"] for c in chunks], normalize_embeddings=True).astype("float32")
    idx = faiss.IndexFlatIP(vec.shape[1])
    idx.add(vec)
    faiss.write_index(idx, str(d / "index.faiss"))
    (d / "chunks.jsonl").write_text("\n".join(json.dumps(c) for c in chunks), encoding="utf-8")
    (d / "manifest.json").write_text(json.dumps({"documents_by_source": {"WHO": 3}}))
    return Retriever(d, MODEL)


class FakeLLM:  # the only test double
    name = "fake-llm"

    def __init__(self, text):
        self.text, self.calls = text, 0

    def generate(self, system, prompt):
        self.calls += 1
        self.prompt = prompt
        return self.text


# ------------------------------------------------------------------ query analysis
def test_intent_and_complexity():
    a = Q.analyse("What is cholesterol?")
    assert a.intent == "definition" and a.complexity == "simple"
    b = Q.analyse("What is the difference between HDL and LDL cholesterol?")
    assert b.intent == "comparison" and b.complexity == "complex"
    assert any("HDL" in s for s in b.sub_queries) and len(b.sub_queries) >= 2


def test_safety_flags():
    assert "emergency" in Q.detect_safety("I have chest pain and can't breathe")
    assert "diagnosis_request" in Q.detect_safety("Do I have diabetes?")
    assert "prescription_request" in Q.detect_safety("What dose of metformin should I take?")
    assert Q.detect_safety("What is hypertension?") == []


def test_abbreviation_expansion():
    assert "low-density lipoprotein" in Q.expand_abbreviations("what is LDL")


# ------------------------------------------------------------------ ranking
def test_ranking_components_are_transparent_and_configurable(retriever):
    ev = retriever.vector_search("normal blood pressure for hypertension diagnosis", 5)
    ranked = retriever.score(ev, "hypertension blood pressure diagnosis")
    top = ranked[0]
    assert top.doc_id == "who:hypertension"
    assert all(0 <= x <= 1 for x in (top.similarity, top.reliability, top.recency, top.clinical_relevance, top.score))
    # old PubMed review gets a lower recency and reliability than a recent WHO fact sheet
    by_id = {e.doc_id: e for e in retriever.score(retriever.vector_search("vitamin D", 5), "vitamin D")}
    assert by_id["pubmed:111"].recency < by_id["who:diabetes"].recency
    assert by_id["pubmed:111"].reliability < by_id["who:diabetes"].reliability
    # re-weighting changes the final score
    heavy = Retriever.__new__(Retriever)
    heavy.__dict__.update(retriever.__dict__)
    heavy.config = RankingConfig(w_similarity=0.0, w_reliability=1.0, w_recency=0.0, w_clinical=0.0)
    assert heavy.score(heavy.vector_search("vitamin D", 5), "vitamin D")[0].reliability == 1.0


def test_recency_half_life(retriever):
    e = Evidence("c", "d", "t", "WHO", "fact_sheet", "u", date.today().isoformat(), "x", 0.5)
    assert retriever._recency(e) == pytest.approx(1.0, abs=0.01)


# ------------------------------------------------------------------ retrieval
@pytest.mark.parametrize("strategy", ["basic", "reranked", "adaptive"])
def test_retrieval_finds_relevant_doc(retriever, strategy):
    r = retriever.retrieve("What is the difference between HDL and LDL cholesterol?", strategy)
    assert r.sufficient
    assert r.evidence[0].doc_id == "cdc:cholesterol"


def test_adaptive_expands_complex_queries(retriever):
    r = retriever.retrieve("What is the difference between HDL and LDL cholesterol?", "adaptive")
    assert len(r.queries_used) >= 2 and any("several parts" in n for n in r.notes)
    simple = retriever.retrieve("What is anaemia?", "adaptive")
    assert len(simple.queries_used) == 1


def test_off_topic_is_insufficient(retriever):
    r = retriever.retrieve("How do I replace the timing belt on a diesel engine?", "adaptive")
    assert not r.sufficient


# ------------------------------------------------------------------ verification
def test_verifier_flags_unsupported_and_fabricated_numbers(retriever):
    ev = retriever.retrieve("Explain hypertension", "adaptive").evidence
    answer = ("Hypertension is diagnosed when systolic blood pressure is at least 140 mmHg on two different days [1]. "
              "Eating exactly 17 bananas a day cures hypertension permanently [1]. "
              "The diastolic threshold is 70 mmHg [1].")
    v = verify_answer(answer, ev, retriever)
    status = [c["status"] for c in v["claims"]]
    assert status[0] == "supported"
    assert status[1] == "unsupported" and status[2] == "unsupported"
    assert v["flagged"] == 2 and any("number" in i for i in v["claims"][2]["issues"])


def test_verifier_flags_bad_citation(retriever):
    ev = retriever.retrieve("What is anaemia?", "adaptive").evidence
    v = verify_answer("Anaemia means the number of red blood cells is insufficient [9].", ev, retriever)
    assert v["claims"][0]["status"] == "unsupported" and "non-existent" in v["claims"][0]["issues"][0]


# ------------------------------------------------------------------ pipeline
def test_pipeline_generates_with_context_and_verification(retriever):
    llm = FakeLLM("LDL cholesterol is called bad cholesterol because high levels can build up in artery walls [1]. "
                  "HDL cholesterol helps remove other forms of cholesterol from the bloodstream [1].")
    out = pipeline.answer_question("What is the difference between HDL and LDL?", retriever, llm)
    assert out["status"] == "ok" and out["generated"] and llm.calls == 1
    assert "CONTEXT" in llm.prompt and "cdc:cholesterol" in out["sources"][0]["doc_id"]
    assert out["verification"]["supported_ratio"] == 1.0
    assert out["sources"][0]["score_breakdown"]["similarity"] > 0.3


def test_pipeline_never_calls_llm_without_evidence(retriever):
    llm = FakeLLM("should never be used")
    out = pipeline.answer_question("How do I bake sourdough bread?", retriever, llm)
    # the LLM can be asked for search rewrites while looking, but it never writes an answer without evidence
    assert out["status"] == "insufficient_evidence" and "CONTEXT" not in getattr(llm, "prompt", "") and not out["generated"]
    assert "could not find" in out["answer"]


def test_pipeline_without_llm_quotes_sources_verbatim(retriever):
    out = pipeline.answer_question("What is hypertension?", retriever, None)
    assert out["status"] == "extractive" and not out["generated"] and out["mode"] == "extractive"
    lines = [l[2:] for l in out["answer"].splitlines() if l.startswith("- ")]
    assert lines
    corpus = " ".join(p[5] for p in PASSAGES)
    for line in lines:
        sentence, cite = line.rsplit(" [", 1)
        assert sentence in corpus                         # verbatim quote, nothing generated
        assert 1 <= int(cite.rstrip("]")) <= len(out["sources"])
    assert out["verification"]["flagged"] == 0


def test_pipeline_falls_back_to_quotes_when_llm_fails(retriever):
    from app.core.errors import ServiceUnavailableError

    class DownLLM:
        name = "down"

        def generate(self, system, prompt):
            raise ServiceUnavailableError("quota", code="llm_error")

    out = pipeline.answer_question("What is hypertension?", retriever, DownLLM())
    assert out["status"] == "extractive" and any("busy right now" in n for n in out["notes"])


def test_pipeline_emergency_notice(retriever):
    out = pipeline.answer_question("I have chest pain, what is a heart attack?", retriever, None)
    assert out["emergency_notice"] and "emergency number" in out["emergency_notice"]


def test_pipeline_kb_missing():
    out = pipeline.answer_question("What is diabetes?", None, FakeLLM("x"))
    assert out["status"] == "knowledge_base_missing"


# ------------------------------------------------------------------ chat API
@pytest.fixture()
def chat_env(monkeypatch, retriever):
    from app.api import chat as chat_mod

    llm = FakeLLM("Diabetes is a chronic disease where the pancreas does not produce enough insulin [1].")
    monkeypatch.setattr(chat_mod, "get_retriever", lambda: retriever)
    monkeypatch.setattr(chat_mod.generator, "get_llm", lambda: llm)
    return llm


def test_chat_flow_history_and_privacy(client, auth_headers, chat_env):
    a, b = auth_headers("a@example.com"), auth_headers("b@example.com")
    r = client.post("/api/chat", json={"message": "What is diabetes?"}, headers=a)
    assert r.status_code == 200, r.text
    body = r.json()
    cid = body["conversation_id"]
    assert body["status"] == "ok" and body["reply"]["sources"][0]["doc_id"] == "who:diabetes"
    assert body["reply"]["verification"]["claims"]
    # follow-up in the same conversation
    r2 = client.post("/api/chat", json={"message": "What is hypertension?", "conversation_id": cid}, headers=a)
    assert r2.json()["conversation_id"] == cid
    detail = client.get(f"/api/chat/{cid}", headers=a).json()
    assert [m["role"] for m in detail["messages"]] == ["user", "assistant", "user", "assistant"]
    hist = client.get("/api/chat/history", headers=a).json()
    assert hist[0]["id"] == cid and hist[0]["message_count"] == 4
    # another user cannot read, continue or delete it
    assert client.get(f"/api/chat/{cid}", headers=b).status_code == 404
    assert client.post("/api/chat", json={"message": "hello there", "conversation_id": cid}, headers=b).status_code == 404
    assert client.delete(f"/api/chat/{cid}", headers=b).status_code == 404
    assert client.delete(f"/api/chat/{cid}", headers=a).status_code == 204
    assert client.get("/api/chat/history", headers=a).json() == []


def test_chat_validation_and_auth(client, auth_headers, chat_env):
    assert client.post("/api/chat", json={"message": "hi"}).status_code == 401
    h = auth_headers()
    assert client.post("/api/chat", json={"message": "x"}, headers=h).status_code == 422
    assert client.post("/api/chat", json={"message": "y" * 2001}, headers=h).status_code == 422


def test_chat_without_llm_reports_unavailable(client, auth_headers, monkeypatch, retriever):
    from app.api import chat as chat_mod

    monkeypatch.setattr(chat_mod, "get_retriever", lambda: retriever)
    monkeypatch.setattr(chat_mod.generator, "get_llm", lambda: None)
    r = client.post("/api/chat", json={"message": "What is anaemia?"}, headers=auth_headers())
    assert r.json()["status"] == "extractive" and "**Short answer**" in r.json()["reply"]["content"]
    assert r.json()["reply"]["sources"]


# ------------------------------------------------------------------ report "learn more" grounding
def test_report_learn_more_requires_the_analyte_in_the_passage(monkeypatch, retriever):
    from app.rag import retriever as retriever_mod
    from app.services import report_service

    monkeypatch.setattr(retriever_mod, "get_retriever", lambda: retriever)
    report_service._learn_more.cache_clear()
    try:
        hb = report_service._learn_more("Hemoglobin")
        assert hb is not None and hb["title"] == "WHO fact sheet: Anaemia"   # mentions haemoglobin
        assert report_service._learn_more("TSH") is None                      # nothing in the index mentions TSH
    finally:
        report_service._learn_more.cache_clear()


def test_extractive_skips_captions_and_chart_titles():
    from app.rag.extractive import _sentences

    text = ("Hypertension prevalence among adults aged 18 and over: United States, 2017–2018 . "
            "Hypertension is when the pressure in your blood vessels is too high. "
            "This elevated pressure and reduced blood flow can cause:\n"
            "Figure 2. Prevalence of high blood pressure by age group in the survey sample. "
            "Source: National Health and Nutrition Examination Survey, 2017–2018 data tables.")
    assert _sentences(text) == ["Hypertension is when the pressure in your blood vessels is too high."]
