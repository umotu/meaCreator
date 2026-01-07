# file: backend/retriever.py
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import List, Tuple

import numpy as np

from embed_backends import Embedder  # why: keep retriever backend-agnostic


@dataclass
class IndexRecord:
    id: str
    doc_id: str
    doc_title: str
    kind: str
    path: str
    text: str
    vector: np.ndarray


class SimpleIndex:
    """RAM-loaded cosine index. Suitable for small/medium corpora."""

    def __init__(self, records: List[IndexRecord]):
        self.records = records
        if records:
            mat = np.stack([r.vector for r in records], axis=0).astype(np.float32)
            norms = np.linalg.norm(mat, axis=1, keepdims=True) + 1e-8
            self.mat = mat / norms  # cosine-ready
        else:
            self.mat = np.zeros((0, 1), dtype=np.float32)

    @classmethod
    def from_jsonl(cls, path: Path) -> "SimpleIndex":
        if not path.exists():
            return cls([])
        recs: List[IndexRecord] = []
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                obj = json.loads(line)
                vec = np.asarray(obj["vector"], dtype=np.float32)
                recs.append(
                    IndexRecord(
                        id=obj["id"],
                        doc_id=obj["doc_id"],
                        doc_title=obj["doc_title"],
                        kind=obj["kind"],
                        path=obj["path"],
                        text=obj["text"],
                        vector=vec,
                    )
                )
        return cls(recs)

    def size(self) -> int:
        return len(self.records)

    def search(self, query: str, embedder: Embedder, top_k: int = 8) -> List[IndexRecord]:
        """Return top-k records by cosine similarity."""
        results, _ = self.search_with_scores(query, embedder, top_k)
        return results

    def search_with_scores(
        self, query: str, embedder: Embedder, top_k: int = 8
    ) -> Tuple[List[IndexRecord], np.ndarray]:
        """Return (records, scores). Helpful for debugging retrieval."""
        if self.mat.shape[0] == 0:
            return [], np.array([], dtype=np.float32)
        q = embedder.embed_query(query).astype(np.float32)
        q = q / (np.linalg.norm(q) + 1e-8)
        sims = self.mat @ q  # cosine similarity
        k = min(top_k, sims.shape[0])
        idx = np.argpartition(-sims, k - 1)[:k]
        idx = idx[np.argsort(-sims[idx])]
        return [self.records[i] for i in idx], sims[idx]
