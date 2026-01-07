# file: backend/ingest.py
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import List

import numpy as np
from dotenv import load_dotenv

from rag_index import ingest_folder, IngestedChunk
from embed_backends import build_embedder


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def write_jsonl_index(chunks: List[IngestedChunk], vectors: np.ndarray, index_path: Path) -> None:
    """Write one JSON object per line: metadata + vector list."""
    ensure_parent(index_path)
    with index_path.open("w", encoding="utf-8") as f:
        for ch, vec in zip(chunks, vectors):
            rec = {
                "id": ch.id,
                "doc_id": ch.doc_id,
                "doc_title": ch.doc_title,
                "kind": ch.kind,
                "path": ch.path,
                "text": ch.text,
                "vector": vec.tolist(),
            }
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def main() -> None:
    # Load env from ./backend/.env
    here = Path(__file__).resolve().parent
    load_dotenv(here / ".env")

    parser = argparse.ArgumentParser(description="Ingest PDFs/DOCX → JSONL index with embeddings.")
    parser.add_argument("--docs-dir", default=os.getenv("DOCS_DIR", "./docs"), help="Folder with source PDFs/DOCX.")
    parser.add_argument("--index-path", default=os.getenv("INDEX_PATH", "./data/index.jsonl"), help="Output JSONL index.")
    parser.add_argument("--target-tokens", type=int, default=1000, help="Approx tokens per chunk.")
    parser.add_argument("--overlap-tokens", type=int, default=120, help="Approx overlap tokens between chunks.")
    parser.add_argument("--batch", type=int, default=256, help="Embedding batch size.")
    args = parser.parse_args()

    docs_dir = Path(args.docs_dir).resolve()
    index_path = Path(args.index_path).resolve()

    docs_dir.mkdir(parents=True, exist_ok=True)
    print(f"[ingest] docs_dir = {docs_dir}")
    print(f"[ingest] index_path = {index_path}")

    print("[ingest] Scanning & parsing documents …")
    chunks = ingest_folder(
        docs_dir=docs_dir,
        target_tokens=args.target_tokens,
        overlap_tokens=args.overlap_tokens,
    )
    if not chunks:
        print("[ingest] No chunks produced (no docs found?). You can still start the API; retrieval will be empty.")
        ensure_parent(index_path)
        index_path.write_text("", encoding="utf-8")
        return

    print(f"[ingest] Parsed {len(chunks)} chunk(s) from {len({c.doc_id for c in chunks})} document(s).")

    print("[ingest] Building embeddings …")
    embedder = build_embedder()

    texts = [c.text for c in chunks]
    # Simple batching to keep memory modest for larger corpora
    vecs: List[np.ndarray] = []
    for i in range(0, len(texts), args.batch):
        batch = texts[i : i + args.batch]
        v = embedder.embed(batch)
        if not isinstance(v, np.ndarray):
            v = np.asarray(v, dtype=np.float32)
        vecs.append(v.astype(np.float32))
        print(f"[ingest] Embedded {min(i + len(batch), len(texts))}/{len(texts)}")

    vectors = np.vstack(vecs).astype(np.float32)
    assert vectors.shape[0] == len(chunks), "vector count != chunk count"

    print(f"[ingest] Writing index → {index_path} (records: {len(chunks)}, dim: {vectors.shape[1]})")
    write_jsonl_index(chunks, vectors, index_path)
    print("[ingest] Done.")


if __name__ == "__main__":
    main()
