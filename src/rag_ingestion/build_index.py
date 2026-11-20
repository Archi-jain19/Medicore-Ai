"""Build the RAG knowledge base: fetch -> clean -> deduplicate -> chunk -> embed -> FAISS.

Outputs (models/rag/):
  index.faiss      FAISS IndexFlatIP over L2-normalised embeddings (cosine similarity)
  chunks.jsonl     one JSON object per chunk with metadata
  manifest.json    sources, counts, embedding model, build time
Raw fetched documents are saved (read-only afterwards) to data/raw/rag/documents.jsonl.

Usage: python -m src.rag_ingestion.build_index [--skip-fetch] [--sources who,cdc,pubmed,medlineplus,nhs,licensed]
"""
import argparse
import hashlib
import json
import logging
import re
from dataclasses import asdict
from datetime import datetime, timezone

import faiss
import numpy as np
from langchain_text_splitters import RecursiveCharacterTextSplitter
from sentence_transformers import SentenceTransformer

from src.config import DATA_RAW, MODELS_DIR
from src.rag_ingestion import sources as S
from src.rag_ingestion import sources_more as M

log = logging.getLogger("rag.build")
EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
CHUNK_SIZE, CHUNK_OVERLAP, MIN_CHUNK = 900, 150, 200
RAW_DIR = DATA_RAW / "rag"
OUT_DIR = MODELS_DIR / "rag"


def normalise(text: str) -> str:
    text = re.sub(r"https?://\S+", "", text)                # inline URLs add noise to embeddings
    text = re.sub(r"\[\d+(?:[,–-]\s*\d+)*\]", "", text)  # [1], [2,3] citation markers
    text = re.sub(r"\s+\n", "\n", text)
    return re.sub(r"[ \t]{2,}", " ", text).strip()


def dedupe(docs: list[S.RawDoc]) -> list[S.RawDoc]:
    """Drop exact-duplicate bodies and same-URL repeats (keeps the first, i.e. highest-priority source)."""
    seen_hash, seen_url, out = set(), set(), []
    for d in docs:
        h = hashlib.sha256(re.sub(r"\W+", " ", d.text.lower()).encode()).hexdigest()
        if h in seen_hash or d.url in seen_url:
            log.info("Duplicate removed: %s", d.doc_id)
            continue
        seen_hash.add(h)
        seen_url.add(d.url)
        out.append(d)
    return out


def chunk_documents(docs: list[S.RawDoc]) -> list[dict]:
    splitter = RecursiveCharacterTextSplitter(chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP,
                                              separators=["\n## ", "\n\n", "\n", ". ", " "])
    chunks, seen = [], set()
    for d in docs:
        pieces = [p for p in splitter.split_text(normalise(d.text)) if len(p) >= MIN_CHUNK]
        for i, p in enumerate(pieces):
            h = hashlib.sha1(p.encode()).hexdigest()
            if h in seen:        # near-boilerplate repeated across pages
                continue
            seen.add(h)
            chunks.append({
                "chunk_id": f"{d.doc_id}#{i}", "doc_id": d.doc_id, "title": d.title, "source": d.source,
                "doc_type": d.doc_type, "url": d.url, "published": d.published, "retrieved_at": d.retrieved_at,
                "chunk_index": i, "text": p, **({"journal": d.extra.get("journal")} if d.extra.get("journal") else {}),
                **({"also_called": d.extra["also_called"]} if d.extra.get("also_called") else {}),
            })
    return chunks


def embed(texts: list[str], model_name: str = EMBEDDING_MODEL) -> np.ndarray:
    model = SentenceTransformer(model_name)
    return model.encode(texts, batch_size=64, show_progress_bar=False, normalize_embeddings=True).astype("float32")


def load_raw(path) -> list[S.RawDoc]:
    # split on "\n" only: str.splitlines() would also split on U+2028 inside document text
    return [S.RawDoc(**json.loads(line)) for line in path.read_text(encoding="utf-8").split("\n") if line]


ALL_SOURCES = ("who", "cdc", "pubmed", "medlineplus", "nhs", "licensed")


def run(skip_fetch: bool = False, sources: tuple[str, ...] = ALL_SOURCES):
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    raw_path = RAW_DIR / "documents.jsonl"
    if skip_fetch and raw_path.exists():
        docs = load_raw(raw_path)
    else:
        # re-fetch only the requested sources; keep previously fetched documents from the others
        names = {"who": "WHO", "cdc": "CDC", "pubmed": "PubMed", "medlineplus": "MedlinePlus", "nhs": "NHS"}
        keep = {names[k] for k in names if k not in sources}
        if "licensed" not in sources:   # licensed documents carry their own source names; keep them unless refreshed
            keep |= {d.source for d in (load_raw(raw_path) if raw_path.exists() else []) if d.extra.get("licensed")}
        docs = [d for d in load_raw(raw_path) if d.source in keep] if keep and raw_path.exists() else []
        if "who" in sources:
            docs += S.fetch_who()
        if "cdc" in sources:
            docs += S.fetch_cdc()
        if "pubmed" in sources:
            docs += S.fetch_pubmed()
        if "medlineplus" in sources:
            docs += M.fetch_medlineplus()
        if "nhs" in sources:
            docs += M.fetch_nhs()
        if "licensed" in sources:
            docs += M.load_licensed()
        raw_path.write_text("\n".join(json.dumps(asdict(d)) for d in docs), encoding="utf-8")
    if not docs:
        raise SystemExit("No documents fetched; check network access.")
    n_raw = len(docs)
    docs = dedupe(docs)
    chunks = chunk_documents(docs)
    log.info("%d raw docs -> %d after dedupe -> %d chunks", n_raw, len(docs), len(chunks))
    vectors = embed([c["text"] for c in chunks])
    index = faiss.IndexFlatIP(vectors.shape[1])
    index.add(vectors)
    faiss.write_index(index, str(OUT_DIR / "index.faiss"))
    (OUT_DIR / "chunks.jsonl").write_text("\n".join(json.dumps(c) for c in chunks), encoding="utf-8")
    by_source = {s: sum(1 for d in docs if d.source == s) for s in {d.source for d in docs}}
    manifest = {
        "built_at": datetime.now(timezone.utc).isoformat(), "embedding_model": EMBEDDING_MODEL,
        "dimension": int(vectors.shape[1]), "index": "faiss.IndexFlatIP (cosine on normalised vectors)",
        "chunking": {"splitter": "RecursiveCharacterTextSplitter", "size": CHUNK_SIZE, "overlap": CHUNK_OVERLAP, "min_chars": MIN_CHUNK},
        "documents_fetched": n_raw, "documents_indexed": len(docs), "chunks": len(chunks),
        "documents_by_source": by_source,
        "documents": [{"doc_id": d.doc_id, "title": d.title, "source": d.source, "type": d.doc_type, "url": d.url,
                       "published": d.published} for d in docs],
    }
    (OUT_DIR / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    log.info("Index built: %s", {k: manifest[k] for k in ("documents_indexed", "chunks", "documents_by_source")})
    return manifest


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-fetch", action="store_true")
    ap.add_argument("--sources", default=",".join(ALL_SOURCES))
    a = ap.parse_args()
    run(a.skip_fetch, tuple(a.sources.split(",")))
