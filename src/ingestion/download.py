"""Download the raw dataset once, record provenance + SHA-256. Raw files are never modified.

Usage:  python -m src.ingestion.download [--force]
"""
import argparse
import hashlib
import json
import logging
import urllib.request
from datetime import datetime, timezone

from src.config import DATA_RAW, DATASET

log = logging.getLogger("ingestion")


def sha256(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def download(force: bool = False):
    DATA_RAW.mkdir(parents=True, exist_ok=True)
    target = DATA_RAW / DATASET["filename"]
    meta_path = DATA_RAW / "PROVENANCE.json"
    if target.exists() and not force:
        log.info("Raw file exists: %s (use --force to re-download)", target)
        return target
    log.info("Downloading %s", DATASET["data_url"])
    req = urllib.request.Request(DATASET["data_url"], headers={"User-Agent": "MediCoreAI-pipeline/0.1"})
    with urllib.request.urlopen(req, timeout=120) as resp, open(target, "wb") as out:
        out.write(resp.read())
    provenance = {
        **{k: v for k, v in DATASET.items() if k != "filename"},
        "file": target.name,
        "sha256": sha256(target),
        "bytes": target.stat().st_size,
        "downloaded_at": datetime.now(timezone.utc).isoformat(),
    }
    meta_path.write_text(json.dumps(provenance, indent=2))
    log.info("Saved %s (%d bytes, sha256=%s)", target, provenance["bytes"], provenance["sha256"])
    return target


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    p = argparse.ArgumentParser()
    p.add_argument("--force", action="store_true")
    download(p.parse_args().force)
