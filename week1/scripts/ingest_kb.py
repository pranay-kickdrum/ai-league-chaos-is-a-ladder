#!/usr/bin/env python3
"""Run knowledge-base ingestion.

Usage (from the backend/ directory):
    python -m scripts.ingest_kb              # ingest everything found in ../data/
    python -m scripts.ingest_kb --liar       # ingest LIAR dataset only
    python -m scripts.ingest_kb --wiki       # ingest Wikipedia articles only
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

# Ensure the backend package is on sys.path
_backend_dir = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(_backend_dir))

from app.knowledge_base.ingest import (
    ingest_documents,
    load_liar_dataset,
    load_wiki_articles,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest knowledge base")
    parser.add_argument("--liar", action="store_true", help="Ingest LIAR dataset")
    parser.add_argument("--wiki", action="store_true", help="Ingest Wikipedia articles")
    parser.add_argument("--all", action="store_true", help="Ingest everything available")
    args = parser.parse_args()

    # Default: ingest all
    do_all = args.all or (not args.liar and not args.wiki)
    total = 0

    # --- LIAR dataset ---
    if do_all or args.liar:
        liar_dir = DATA_DIR / "liar_dataset"
        for tsv in sorted(liar_dir.glob("*.tsv")) if liar_dir.exists() else []:
            logger.info("Ingesting LIAR file: %s", tsv.name)
            docs = load_liar_dataset(tsv)
            total += ingest_documents(docs, source_label=f"liar:{tsv.stem}")

    # --- Wikipedia ---
    if do_all or args.wiki:
        wiki_dir = DATA_DIR / "wiki_articles"
        if wiki_dir.exists():
            docs = load_wiki_articles(wiki_dir)
            total += ingest_documents(docs, source_label="wikipedia")

    logger.info("=== Ingestion complete: %d total chunks ===", total)


if __name__ == "__main__":
    main()
