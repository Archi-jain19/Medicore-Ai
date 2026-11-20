"""Source adapters: MedlinePlus feed, NHS API (mocked), locally licensed content. No network is used."""
import json
from html import escape

import httpx

from src.rag_ingestion import sources_more as M

BODY = ("<p>A headache is pain in any part of the head. Most headaches are not serious and many are caused by tension in "
        "the muscles of the neck and scalp. See a doctor if a headache is sudden and severe or comes with a stiff neck.</p>"
        "<h3>What causes a headache?</h3><p>Common causes include stress, lack of sleep, dehydration and infections.</p>")


def feed(topics: str) -> bytes:
    return (f'<?xml version="1.0"?><health-topics total="2" date-generated="11/12/2026 02:30:39">{topics}</health-topics>').encode()


def topic(tid, title, summary, lang="English", also=("Head pain",)):
    also_xml = "".join(f"<also-called>{a}</also-called>" for a in also)
    return (f'<health-topic meta-desc="About {title}." title="{title}" url="https://medlineplus.gov/{title.lower()}.html" id="{tid}" '
            f'language="{lang}" date-created="01/27/1999">{also_xml}<full-summary>{escape(summary)}</full-summary></health-topic>')


def test_medlineplus_feed_is_parsed_with_full_metadata():
    docs = M.parse_medlineplus(feed(topic(273, "Headache", BODY) + topic(9, "Dolor", BODY, lang="Spanish") + topic(5, "Tiny", "<p>x</p>")))
    assert len(docs) == 1                                     # Spanish and near-empty topics are skipped
    d = docs[0]
    assert (d.doc_id, d.source, d.doc_type) == ("medlineplus:273", "MedlinePlus", "health_topic")
    assert d.url == "https://medlineplus.gov/headache.html" and d.title == "MedlinePlus: Headache"
    assert d.published == "2026-11-12"                        # feed date: the content is current as of then
    assert d.extra["created"] == "1999-01-27" and d.extra["also_called"] == ["Head pain"]
    assert "Also called: Head pain" in d.text and "<p>" not in d.text and "## What causes a headache?" in d.text


def test_nhs_adapter_is_skipped_without_a_key(monkeypatch):
    monkeypatch.delenv("NHS_API_KEY", raising=False)
    assert M.fetch_nhs() == []


def test_nhs_adapter_with_key_reads_index_and_pages():
    page = {"name": "Headaches", "url": "https://www.nhs.uk/conditions/headaches/", "lastReviewed": "2025-03-21T00:00:00+00:00",
            "description": "Headaches are very common and not usually serious.",
            "mainEntityOfPage": [{"headline": "Causes of headaches", "text": "<p>Headaches can be caused by stress, tiredness, dehydration "
                                  "and infections such as colds and flu. Most headaches get better on their own.</p>"},
                                 {"headline": "When to get medical help", "text": "Call 999 if you have a sudden severe headache or a stiff neck."}]}

    def handler(request: httpx.Request):
        assert request.headers["subscription-key"] == "k"
        if request.url.path.endswith("/conditions/"):
            return httpx.Response(200, json={"significantLink": [{"name": "Headaches", "url": "https://www.nhs.uk/conditions/headaches/"}]})
        return httpx.Response(200, json=page)

    c = httpx.Client(transport=httpx.MockTransport(handler), headers={"subscription-key": "k"})
    docs = M.fetch_nhs("k", client=c, delay=0)
    assert len(docs) == 1
    d = docs[0]
    assert (d.doc_id, d.source, d.published) == ("nhs:headaches", "NHS", "2025-03-21")
    assert "Call 999" in d.text and "<p>" not in d.text and d.url == "https://www.nhs.uk/conditions/headaches/"


def test_licensed_content_is_indexed_under_its_own_source_name(tmp_path):
    d = tmp_path / "mayo_clinic"
    d.mkdir()
    (d / "dehydration.json").write_text(json.dumps({"title": "Dehydration", "url": "https://example.org/licensed/dehydration",
                                                    "published": "2025-01-10", "text": "Dehydration occurs when you use or lose more fluid than you take in. " * 6}))
    (d / "bad.json").write_text(json.dumps({"title": "No text", "url": "https://example.org/x"}))
    docs = M.load_licensed(tmp_path)
    assert len(docs) == 1 and docs[0].source == "Mayo Clinic" and docs[0].title == "Mayo Clinic: Dehydration"
    assert docs[0].published == "2025-01-10" and docs[0].extra["licensed"] is True
    assert M.load_licensed(tmp_path / "missing") == []
