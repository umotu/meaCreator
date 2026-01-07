# file: backend/rag_index.py
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple, Iterable, Any

import fitz  # PyMuPDF
import docx  # python-docx

# Heuristic: ~4 chars ≈ 1 token for English prose
CHARS_PER_TOKEN = 4


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_pdf(path: Path) -> Tuple[str, Dict[str, Any]]:
    """
    Returns full extracted text and metadata.
    why: page-wise extraction ensures reasonable ordering without layout noise.
    """
    try:
        data = path.read_bytes()
        doc = fitz.open(stream=data, filetype="pdf")
    except Exception as e:
        raise RuntimeError(f"Failed to open PDF '{path.name}': {e}") from e

    parts: List[str] = []
    for page in doc:
        # 'text' preserves reading order better than raw
        parts.append(page.get_text("text"))
    text = "\n".join(parts).strip()
    meta = {"pages": len(doc), "sha256": sha256_bytes(data)}
    return text, meta


def read_docx(path: Path) -> Tuple[str, Dict[str, Any]]:
    """
    DOCX paragraphs joined by newlines. Inline images/objects are ignored.
    """
    try:
        data = path.read_bytes()
        d = docx.Document(path.as_posix())
    except Exception as e:
        raise RuntimeError(f"Failed to open DOCX '{path.name}': {e}") from e

    paras = [p.text.strip() for p in d.paragraphs if p.text and p.text.strip()]
    text = "\n".join(paras).strip()
    meta = {"sha256": sha256_bytes(data)}
    return text, meta


def split_paragraphs(text: str) -> List[str]:
    """
    Lightweight paragraph splitter.
    why: chunking along semantic-ish breaks improves retrieval quality.
    """
    # Collapse multiple blank lines; keep non-empty lines
    lines = [ln.rstrip() for ln in text.splitlines()]
    parts: List[str] = []
    buf: List[str] = []
    for ln in lines:
        if ln.strip():
            buf.append(ln)
        else:
            if buf:
                parts.append(" ".join(buf).strip())
                buf = []
    if buf:
        parts.append(" ".join(buf).strip())
    return [p for p in parts if p]


def pack_chunks(
    parts: List[str],
    target_tokens: int = 1000,
    overlap_tokens: int = 120,
) -> List[str]:
    """
    Packs paragraphs into ~target_tokens windows with ~overlap_tokens back-carry.
    why: overlap preserves cross-boundary context for ranking & synthesis.
    """
    target_chars = max(200, target_tokens * CHARS_PER_TOKEN)
    overlap_chars = max(0, overlap_tokens * CHARS_PER_TOKEN)

    chunks: List[str] = []
    cur: List[str] = []
    cur_len = 0

    for p in parts:
        p_len = len(p)
        if cur and cur_len + p_len + 1 > target_chars:
            chunks.append("\n".join(cur))
            # carry tail overlap forward
            carry: List[str] = []
            carry_len = 0
            for seg in reversed(cur):
                carry.append(seg)
                carry_len += len(seg) + 1
                if carry_len >= overlap_chars:
                    break
            cur = list(reversed(carry))
            cur_len = sum(len(x) + 1 for x in cur)

        cur.append(p)
        cur_len += p_len + 1

    if cur:
        chunks.append("\n".join(cur))

    # Guard: avoid empty artifacts
    return [c.strip() for c in chunks if c.strip()]


@dataclass
class IngestedChunk:
    id: str          # stable chunk id (sha256)
    doc_id: str      # stable doc id (sha256)
    doc_title: str   # filename stem
    kind: str        # 'pdf' | 'docx'
    path: str        # absolute or project-relative path
    text: str        # chunk contents


def walk_docs(docs_dir: Path) -> List[Tuple[Path, str]]:
    allowed = {".pdf", ".docx"}
    items: List[Tuple[Path, str]] = []
    for p in docs_dir.rglob("*"):
        if p.is_file() and p.suffix.lower() in allowed:
            items.append((p, p.suffix.lower()))
    return items


def parse_doc(path: Path, ext: str) -> Tuple[str, Dict[str, Any]]:
    if ext == ".pdf":
        return read_pdf(path)
    if ext == ".docx":
        return read_docx(path)
    raise ValueError(f"Unsupported extension: {ext}")


def _doc_stable_id(path: Path, file_sha256: str) -> str:
    return sha256_bytes((str(path.resolve()) + "|" + file_sha256).encode("utf-8"))


def ingest_folder(
    docs_dir: Path,
    target_tokens: int = 1000,
    overlap_tokens: int = 120,
) -> List[IngestedChunk]:
    """
    Parse and chunk all PDFs/DOCX in a folder. Embeddings are handled elsewhere.
    """
    chunks: List[IngestedChunk] = []
    for path, ext in walk_docs(docs_dir):
        try:
            full_text, meta = parse_doc(path, ext)
        except Exception as e:
            # Surface which file failed; continue others
            print(f"[ingest] Skipping {path.name}: {e}")
            continue

        title = path.stem
        doc_id = _doc_stable_id(path, meta.get("sha256", ""))

        parts = split_paragraphs(full_text)
        packed = pack_chunks(parts, target_tokens=target_tokens, overlap_tokens=overlap_tokens)

        for i, chunk_text in enumerate(packed):
            chunk_id = sha256_bytes(f"{doc_id}:{i}".encode("utf-8"))
            chunks.append(
                IngestedChunk(
                    id=chunk_id,
                    doc_id=doc_id,
                    doc_title=title,
                    kind=ext.lstrip("."),
                    path=str(path),
                    text=chunk_text,
                )
            )

    return chunks
