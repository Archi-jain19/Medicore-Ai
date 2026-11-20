"""Fetchers for trusted public medical sources. Each returns a list of RawDoc.

* WHO fact sheets  - public HTML pages (https://www.who.int/news-room/fact-sheets)
* CDC              - official content syndication API (https://tools.cdc.gov/api/v2/resources/media)
* PubMed           - NCBI E-utilities (abstracts of guidelines / reviews, with PMID links)

Requests are throttled and identify the client. No browser spoofing: if a site refuses automated access
it is skipped rather than bypassed.
"""
from __future__ import annotations

import logging
import re
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime, timezone

import httpx
from bs4 import BeautifulSoup

log = logging.getLogger("rag.sources")
UA = "MediCoreAI-research/0.1 (educational project)"

# Topics are chosen to match the platform's scope (lab values, cardiometabolic health, common questions)
TOPIC_KEYWORDS = (
    "diabet", "cholesterol", "lipid", "hypertension", "blood pressure", "heart disease", "heart attack",
    "stroke", "obesity", "overweight", "body mass", "anemia", "anaemia", "vitamin", "kidney", "physical activity",
    "healthy eating", "nutrition", "glucose", "a1c", "prediabetes", "cardiovascular", "sodium", "salt",
    # everyday symptoms and common conditions
    "fever", "cough", "headache", "dehydrat", "common cold", "influenza", "flu ", "sore throat", "nausea",
    "dizziness", "fatigue", "allerg", "asthma", "chest pain", "diarrh",
)

WHO_SLUGS = [
    "diabetes", "hypertension", "dyslipidaemia", "cardiovascular-diseases-(cvds)", "obesity-and-overweight",
    "anaemia", "healthy-diet", "physical-activity", "kidney-disease", "heart-attack", "noncommunicable-diseases",
    "malnutrition", "depression", "oral-health", "pre-eclampsia", "ageing-and-health",
]

PUBMED_QUERIES = {
    "diabetes": '(diabetes mellitus[Title]) AND (screening OR diagnosis OR "glycated hemoglobin")',
    "hypertension": "(hypertension[Title]) AND (management OR guideline OR blood pressure)",
    "cholesterol": "(cholesterol[Title] OR dyslipidemia[Title] OR LDL[Title] OR HDL[Title])",
    "obesity": "(obesity[Title] OR overweight[Title]) AND (adults OR management)",
    "anemia": "(anemia[Title] OR hemoglobin[Title]) AND (diagnosis OR iron)",
    "kidney": '(chronic kidney disease[Title] OR creatinine[Title] OR "glomerular filtration rate"[Title])',
    "vitamin_d": '("vitamin D"[Title]) AND (deficiency OR supplementation OR serum)',
    "cardiovascular": "(cardiovascular risk[Title]) AND (prevention OR guideline)",
}


@dataclass
class RawDoc:
    doc_id: str
    title: str
    source: str            # WHO | CDC | PubMed
    doc_type: str          # fact_sheet | web_page | guideline | systematic_review | review | article
    url: str
    published: str | None  # ISO date as published by the source, never invented
    text: str
    retrieved_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    extra: dict = field(default_factory=dict)


def _client() -> httpx.Client:
    return httpx.Client(headers={"User-Agent": UA}, timeout=60, follow_redirects=True)


def _get(c: httpx.Client, url: str, retries: int = 3, **kw) -> httpx.Response | None:
    for i in range(retries):
        try:
            r = c.get(url, **kw)
            if r.status_code == 200:
                return r
            if r.status_code in (403, 401):
                log.warning("Access refused (%s) for %s - skipping, not bypassing", r.status_code, url)
                return None
            log.warning("HTTP %s for %s", r.status_code, url)
        except httpx.HTTPError as exc:
            log.warning("Request error %s (%s), attempt %d", url, exc, i + 1)
        time.sleep(1.5 * (i + 1))
    return None


def _clean_ws(t: str) -> str:
    t = t.replace("\xa0", " ")
    t = re.sub(r"[ \t]+", " ", t)
    t = re.sub(r"\n\s*\n+", "\n\n", t)
    return t.strip()


def _html_to_text(node) -> str:
    for bad in node.select("script, style, nav, footer, form, aside, .sf-social-share, .sf-related-list, figure, button"):
        bad.decompose()
    lines = []
    for el in node.find_all(["h1", "h2", "h3", "h4", "p", "li", "td", "th"]):
        txt = el.get_text(" ", strip=True)
        if not txt:
            continue
        if el.name in ("h1", "h2", "h3", "h4"):
            lines.append(f"\n## {txt}")
        elif el.name == "li":
            lines.append(f"- {txt}")
        else:
            lines.append(txt)
    return _clean_ws("\n".join(lines))


# --------------------------------------------------------------------------- WHO
_MONTHS = "January|February|March|April|May|June|July|August|September|October|November|December"


def fetch_who(slugs=WHO_SLUGS, delay: float = 1.0) -> list[RawDoc]:
    docs = []
    with _client() as c:
        for slug in slugs:
            url = f"https://www.who.int/news-room/fact-sheets/detail/{slug}"
            r = _get(c, url)
            if r is None:
                continue
            soup = BeautifulSoup(r.text, "html.parser")
            body = soup.select_one("article") or soup.select_one("[role=main]")
            if body is None:
                continue
            title = (soup.find("meta", property="og:title") or {}).get("content") or soup.title.get_text(strip=True)
            m = re.search(rf"(\d{{1,2}}) ({_MONTHS}) (\d{{4}})", soup.get_text(" ")[:6000])
            published = None
            if m:
                published = datetime.strptime(" ".join(m.groups()), "%d %B %Y").date().isoformat()
            text = _html_to_text(body)
            if len(text) < 500:
                continue
            docs.append(RawDoc(f"who:{slug}", f"WHO fact sheet: {title}", "WHO", "fact_sheet", url, published, text))
            time.sleep(delay)
    log.info("WHO: %d documents", len(docs))
    return docs


# --------------------------------------------------------------------------- CDC
def fetch_cdc(max_docs: int = 60, delay: float = 0.5) -> list[RawDoc]:
    """Pages through CDC's syndication catalogue (English HTML), keeps topic-relevant items, fetches content."""
    api = "https://tools.cdc.gov/api/v2/resources/media"
    cand = []
    with _client() as c:
        page = 1
        while True:
            r = _get(c, api, params={"max": 100, "mediatype": "html", "pagenum": page, "language": "english"})
            if r is None:
                break
            js = r.json()
            for it in js["results"]:
                hay = " ".join([it["name"], it.get("description") or "",
                                " ".join(t["name"] for t in it.get("tags", []))]).lower()
                if any(k in hay for k in TOPIC_KEYWORDS) and it.get("sourceUrl", "").startswith("https://www.cdc.gov"):
                    cand.append(it)
            if page >= js["meta"]["pagination"]["totalPages"]:
                break
            page += 1
            time.sleep(0.2)
        log.info("CDC: %d topic-relevant catalogue items", len(cand))
        docs = []
        for it in cand:
            if len(docs) >= max_docs:
                break
            r = _get(c, it["contentUrl"])
            if r is None:
                continue
            soup = BeautifulSoup(r.text, "html.parser")
            text = _html_to_text(soup)
            if len(text) < 600:
                continue
            published = (it.get("dateContentReviewed") or it.get("dateContentUpdated") or it.get("dateContentAuthored") or "")[:10] or None
            title = re.sub(r"<[^>]+>", "", it["name"])
            docs.append(RawDoc(f"cdc:{it['id']}", f"CDC: {title}", "CDC", "web_page", it["sourceUrl"], published, text))
            time.sleep(delay)
    log.info("CDC: %d documents", len(docs))
    return docs


# --------------------------------------------------------------------------- PubMed
EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
_PUBTYPE_MAP = [("Practice Guideline", "guideline"), ("Guideline", "guideline"), ("Meta-Analysis", "systematic_review"),
                ("Systematic Review", "systematic_review"), ("Review", "review")]


def _pubmed_date(art) -> str | None:
    for path in (".//ArticleDate", ".//PubDate", ".//DateCompleted"):
        n = art.find(path)
        if n is not None and n.findtext("Year"):
            y, m, d = n.findtext("Year"), n.findtext("Month") or "01", n.findtext("Day") or "01"
            try:
                return datetime.strptime(f"{y}-{m}-{d}", "%Y-%b-%d" if m.isalpha() else "%Y-%m-%d").date().isoformat()
            except ValueError:
                return f"{y}-01-01"
    return None


def fetch_pubmed(per_topic: int = 8, delay: float = 0.4) -> list[RawDoc]:
    docs, seen = [], set()
    with _client() as c:
        for topic, q in PUBMED_QUERIES.items():
            term = f"({q}) AND (hasabstract) AND (\"Practice Guideline\"[pt] OR Guideline[pt] OR \"Systematic Review\"[pt] OR Meta-Analysis[pt] OR Review[pt]) AND (\"2019\"[dp] : \"3000\"[dp]) AND English[lang] AND humans[mh]"
            r = _get(c, f"{EUTILS}/esearch.fcgi", params={"db": "pubmed", "term": term, "retmax": per_topic, "retmode": "json", "sort": "relevance"})
            if r is None:
                continue
            ids = [i for i in r.json()["esearchresult"]["idlist"] if i not in seen]
            seen.update(ids)
            time.sleep(delay)
            if not ids:
                continue
            r = _get(c, f"{EUTILS}/efetch.fcgi", params={"db": "pubmed", "id": ",".join(ids), "retmode": "xml"})
            if r is None:
                continue
            for art in ET.fromstring(r.text).findall(".//PubmedArticle"):
                pmid = art.findtext(".//PMID")
                title = "".join(art.find(".//ArticleTitle").itertext()).strip()
                parts = []
                for ab in art.findall(".//Abstract/AbstractText"):
                    label = ab.get("Label")
                    t = "".join(ab.itertext()).strip()
                    parts.append(f"{label}: {t}" if label else t)
                abstract = "\n".join(parts)
                if len(abstract) < 300:
                    continue
                ptypes = [p.text for p in art.findall(".//PublicationType")]
                dtype = next((v for k, v in _PUBTYPE_MAP if k in ptypes), "article")
                journal = art.findtext(".//Journal/Title") or ""
                docs.append(RawDoc(f"pubmed:{pmid}", title, "PubMed", dtype, f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                                   _pubmed_date(art), f"{title}\n\n{abstract}",
                                   extra={"journal": journal, "pmid": pmid, "topic": topic, "publication_types": ptypes}))
            time.sleep(delay)
    log.info("PubMed: %d documents", len(docs))
    return docs
