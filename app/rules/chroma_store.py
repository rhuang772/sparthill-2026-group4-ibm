"""
app/rules/chroma_store.py — local Chroma collection of FAA Remote Pilot study guide chunks.

RulesStore      — protocol / interface
StudyGuideStore — builds or loads the collection from app/rules/corpus/ (see study_guide.py)

Usage:
    store = get_store()
    store.ensure_seeded()
    results = store.query("controlled airspace authorization", tags=["laanc"], k=4)

The collection stores a fingerprint of the parsed corpus; ensure_seeded() rebuilds it
whenever a chapter file or the parser changes.

Run as a script to (re)build the collection:
    python -m app.rules.chroma_store [--rebuild]
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Optional, Protocol, runtime_checkable

import chromadb
from chromadb.config import Settings as ChromaSettings

from app.config import settings
from app.rules.study_guide import corpus_fingerprint, load_chunks


@runtime_checkable
class RulesStore(Protocol):
    def query(self, query_text: str, tags: Optional[list[str]] = None, k: int = 4) -> list[dict[str, Any]]:
        ...

    def ensure_seeded(self) -> None:
        ...


class StudyGuideStore:
    """Persistent Chroma collection built from the study guide chapter files."""

    def __init__(
        self,
        path: Optional[str] = None,
        collection: Optional[str] = None,
        corpus_dir: Optional[Path] = None,
    ) -> None:
        self._client = chromadb.PersistentClient(
            path=path or settings.CHROMA_PATH,
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        self._name = collection or settings.CHROMA_COLLECTION
        self._corpus_dir = corpus_dir or settings.RULES_CORPUS_DIR
        self._col = self._client.get_or_create_collection(self._name, metadata={"hnsw:space": "cosine"})

    def count(self) -> int:
        return self._col.count()

    def ensure_seeded(self) -> None:
        """Build the collection if it is empty or was built from a different corpus."""
        chunks = load_chunks(self._corpus_dir)
        fingerprint = corpus_fingerprint(chunks)
        if self._col.count() != len(chunks) or (self._col.metadata or {}).get("corpus_hash") != fingerprint:
            self._build(chunks, fingerprint)

    def rebuild(self) -> None:
        chunks = load_chunks(self._corpus_dir)
        self._build(chunks, corpus_fingerprint(chunks))

    def _build(self, chunks: list[dict], fingerprint: str) -> None:
        self._client.delete_collection(self._name)
        self._col = self._client.create_collection(
            self._name, metadata={"hnsw:space": "cosine", "corpus_hash": fingerprint},
        )
        # Chroma metadata values must be scalars, so tags are stored comma-separated.
        self._col.add(
            ids=[c["rule_id"] for c in chunks],
            documents=[c["text"] for c in chunks],
            metadatas=[{**c["metadata"], "rule_id": c["rule_id"], "tags": ",".join(c["metadata"]["tags"])}
                       for c in chunks],
        )
        print(f"Built '{self._name}' with {len(chunks)} study guide chunks.")

    def query(
        self,
        query_text: str,
        tags: Optional[list[str]] = None,
        k: int = 4,
    ) -> list[dict[str, Any]]:
        """Semantic search, optionally restricted to chunks carrying any of `tags`.

        Never put coordinates in query_text — only semantic terms. Tag filtering runs in
        Python over the whole (small) collection; if no chunk carries any requested tag,
        the unfiltered ranking is returned instead of nothing.
        """
        n = self._col.count()
        if n == 0:
            return []
        chunks = self._format(self._col.query(query_texts=[query_text], n_results=n))
        if tags:
            wanted = set(tags)
            filtered = [c for c in chunks if wanted & set(c["metadata"]["tags"])]
            chunks = filtered or chunks
        return chunks[:k]

    @staticmethod
    def _format(result: dict) -> list[dict[str, Any]]:
        ids = result.get("ids", [[]])[0]
        docs = result.get("documents", [[]])[0]
        metas = result.get("metadatas", [[]])[0]
        distances = result.get("distances", [[]])[0]
        chunks = []
        for i, doc_id in enumerate(ids):
            meta = dict(metas[i])
            meta["tags"] = [t for t in meta.get("tags", "").split(",") if t]
            chunks.append({
                "rule_id": doc_id,
                "text": docs[i],
                "metadata": meta,
                "distance": distances[i] if i < len(distances) else None,
            })
        return chunks


_store: Optional[StudyGuideStore] = None


def get_store() -> StudyGuideStore:
    global _store
    if _store is None:
        _store = StudyGuideStore()
    return _store


if __name__ == "__main__":
    store = StudyGuideStore()
    store.rebuild() if "--rebuild" in sys.argv else store.ensure_seeded()
    print(f"Collection '{settings.CHROMA_COLLECTION}' has {store.count()} documents.")
