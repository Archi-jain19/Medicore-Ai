"""Additional trusted sources: MedlinePlus, NHS (official API) and locally licensed content (e.g. Mayo Clinic).

Access policy (checked against each provider, Nov 2026):
  * MedlinePlus  - NIH/NLM publishes a daily XML feed of every health topic for reuse. Fully integrated.
  * NHS          - official "NHS website content" API. Needs a free subscription key (NHS_API_KEY); without it
                   the API answers 401, so this adapter is skipped. Not verified against the live API during development.
  * Mayo Clinic  - no public API, and the site returns 403 to automated clients (even robots.txt). We do NOT scrape
                   it. If you hold a content licence, drop JSON files in data/external/licensed/mayo_clinic/ and
                   they are indexed with the same metadata as every other source.
"""
from __future__ import annotations

import html
import json
import logging
import os
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

import httpx
from bs4 import BeautifulSoup

from src.config import DATA_RAW, ROOT
from src.rag_ingestion.sources import RawDoc, UA, _clean_ws, _get, _html_to_text

log = logging.getLogger("rag.sources.more")
LICENSED_DIR = ROOT / "data" / "external" / "licensed"


# --------------------------------------------------------------------------- MedlinePlus
def _latest_mplus_url(c: httpx.Client) -> str | None:
    r = _get(c, "https://medlineplus.gov/xml.html")
    if r is None:
        return None
    dates = sorted(set(re.findall(r"mplus_topics_(\d{4}-\d{2}-\d{2})\.xml", r.text)))
    return f"https://medlineplus.gov/xml/mplus_topics_{dates[-1]}.xml" if dates else None


def parse_medlineplus(xml_bytes: bytes, max_topics: int | None = None) -> list[RawDoc]:
    """Parses MedlinePlus' health-topics feed. `published` is the feed's generation date (the content is current as of
    then); the topic's original creation date is kept as metadata."""
    root = ET.fromstring(xml_bytes)
    gen = root.get("date-generated", "")[:10]
    try:
        feed_date = datetime.strptime(gen, "%m/%d/%Y").date().isoformat()
    except ValueError:
        feed_date = None
    docs = []
    for t in root.iter("health-topic"):
        if t.get("language", "English") != "English":
            continue
        title = (t.get("title") or "").strip()
        url = t.get("url") or ""
        summary = (t.findtext("full-summary") or "").strip()
        if not title or not url or len(summary) < 80:
            continue
        body = _html_to_text(BeautifulSoup(html.unescape(summary), "html.parser"))
        also = [a.text.strip() for a in t.findall("also-called") if a.text]
        head = f"{title}\n" + (f"Also called: {', '.join(also)}\n" if also else "")
        meta_desc = (t.get("meta-desc") or "").strip()
        created = None
        try:
            created = datetime.strptime(t.get("date-created", ""), "%m/%d/%Y").date().isoformat()
        except ValueError:
            pass
        docs.append(RawDoc(
            f"medlineplus:{t.get('id')}", f"MedlinePlus: {title}", "MedlinePlus", "health_topic", url, feed_date,
            _clean_ws(head + (meta_desc + "\n" if meta_desc and meta_desc not in body else "") + body),
            extra={"also_called": also, "created": created, "medlineplus_id": t.get("id")},
        ))
        if max_topics and len(docs) >= max_topics:
            break
    return docs


def fetch_medlineplus(max_topics: int | None = None) -> list[RawDoc]:
    cache = DATA_RAW / "rag" / "mplus_topics.xml"
    with httpx.Client(headers={"User-Agent": UA}, timeout=180, follow_redirects=True) as c:
        url = _latest_mplus_url(c)
        if url is None:
            log.warning("MedlinePlus: could not find the topics feed; skipping")
            return []
        log.info("MedlinePlus feed: %s", url)
        r = _get(c, url, retries=2)
        if r is None:
            return []
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_bytes(r.content)
    docs = parse_medlineplus(cache.read_bytes(), max_topics)
    log.info("MedlinePlus: %d documents", len(docs))
    return docs


# --------------------------------------------------------------------------- NHS (official API, key required)
NHS_API = "https://api.service.nhs.uk/nhs-website-content"


def _collect_text(node, out: list[str]) -> None:
    """The NHS API returns schema.org-style JSON; gather readable text from known text-bearing keys."""
    if isinstance(node, dict):
        for k in ("headline", "description", "text"):
            v = node.get(k)
            if isinstance(v, str) and v.strip():
                out.append(("## " + v.strip()) if k == "headline" else v)
        for k, v in node.items():
            if k not in ("headline", "description", "text"):
                _collect_text(v, out)
    elif isinstance(node, list):
        for v in node:
            _collect_text(v, out)


def parse_nhs_page(js: dict, slug: str) -> RawDoc | None:
    parts: list[str] = []
    _collect_text(js.get("mainEntityOfPage", js.get("hasPart", [])), parts)
    desc = js.get("description") if isinstance(js.get("description"), str) else ""
    body = _clean_ws("\n".join(BeautifulSoup(p, "html.parser").get_text(" ", strip=True) if "<" in p else p for p in ([desc] if desc else []) + parts))
    if len(body) < 200:
        return None
    name = js.get("name") or slug.replace("-", " ").title()
    published = (js.get("lastReviewed") or js.get("dateModified") or js.get("datePublished") or "")[:10] or None
    return RawDoc(f"nhs:{slug}", f"NHS: {name}", "NHS", "health_page", js.get("url") or f"https://www.nhs.uk/conditions/{slug}/",
                  published, f"{name}\n{body}", extra={"nhs_slug": slug})


def fetch_nhs(api_key: str | None = None, max_pages: int = 150, delay: float = 0.4, client: httpx.Client | None = None) -> list[RawDoc]:
    key = api_key or os.environ.get("NHS_API_KEY")
    if not key:
        log.warning("NHS: NHS_API_KEY is not set (free key: https://developer.api.nhs.uk). Skipping NHS.")
        return []
    own = client is None
    c = client or httpx.Client(headers={"User-Agent": UA, "subscription-key": key, "accept": "application/json"}, timeout=60)
    docs: list[RawDoc] = []
    try:
        r = _get(c, f"{NHS_API}/conditions/")
        if r is None:
            log.warning("NHS: could not read the conditions index; skipping")
            return []
        links = r.json().get("significantLink", [])
        for link in links[:max_pages]:
            slug = (link.get("url") or "").rstrip("/").rsplit("/", 1)[-1]
            if not slug:
                continue
            page = _get(c, f"{NHS_API}/conditions/{slug}")
            if page is not None:
                d = parse_nhs_page(page.json(), slug)
                if d:
                    docs.append(d)
            time.sleep(delay)
    finally:
        if own:
            c.close()
    log.info("NHS: %d documents", len(docs))
    return docs


# --------------------------------------------------------------------------- locally licensed content
def load_licensed(base: Path = LICENSED_DIR) -> list[RawDoc]:
    """Indexes JSON files you have the right to use: data/external/licensed/<source_name>/<anything>.json with
    {"title","url","text","published"?,"doc_type"?}. The directory name becomes the source name (underscores -> spaces)."""
    docs: list[RawDoc] = []
    if not base.exists():
        return docs
    for src_dir in sorted(p for p in base.iterdir() if p.is_dir()):
        source = src_dir.name.replace("_", " ").title()
        for f in sorted(src_dir.glob("*.json")):
            try:
                js = json.loads(f.read_text(encoding="utf-8"))
                items = js if isinstance(js, list) else [js]
                for it in items:
                    if not (it.get("title") and it.get("url") and len(it.get("text", "")) >= 200):
                        log.warning("Licensed file %s: item missing title/url/text; skipped", f.name)
                        continue
                    docs.append(RawDoc(f"{src_dir.name}:{f.stem}:{abs(hash(it['url'])) % 10**8}", f"{source}: {it['title']}", source,
                                       it.get("doc_type", "health_page"), it["url"], it.get("published"), _clean_ws(it["text"]),
                                       extra={"licensed": True}))
            except (json.JSONDecodeError, OSError) as exc:
                log.warning("Could not read %s: %s", f, exc)
    log.info("Licensed content: %d documents from %s", len(docs), base)
    return docs
