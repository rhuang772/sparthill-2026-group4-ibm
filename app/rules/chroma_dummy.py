"""
app/rules/chroma_dummy.py — local Chroma-backed rules store.

RulesStore   — protocol / interface (swap this for a real corpus later)
DummyRulesStore — builds or loads collection "faa_rules_dummy" from seed_rules.json

Usage:
    store = DummyRulesStore()
    results = store.query("controlled airspace authorization", tags=["laanc"], k=4)

Run as a script to seed (or re-seed) the collection:
    python -m app.rules.chroma_dummy
"""
from __future__ import annotations

import json
from typing import Any, Protocol, runtime_checkable

import chromadb
from chromadb.config import Settings as ChromaSettings

from app.config import settings


# ---------------------------------------------------------------------------
# Protocol (interface)
# ---------------------------------------------------------------------------

@runtime_checkable
class RulesStore(Protocol):
    def query(self, query_text: str, tags: list[str] = [], k: int = 4) -> list[dict[str, Any]]:
        ...

    def ensure_seeded(self) -> None:
        ...


# ---------------------------------------------------------------------------
# DummyRulesStore
# ---------------------------------------------------------------------------

class DummyRulesStore:
    """Local persistent Chroma collection backed by seed_rules.json."""

    def __init__(self) -> None:
        self._client = chromadb.PersistentClient(
            path=settings.CHROMA_PATH,
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        self._col = self._client.get_or_create_collection(
            settings.CHROMA_COLLECTION,
            metadata={"hnsw:space": "cosine"},
        )

    def ensure_seeded(self) -> None:
        """Seed the collection from seed_rules.json if it is empty."""
        if self._col.count() == 0:
            self._seed()

    def _seed(self) -> None:
        rules: list[dict] = json.loads(settings.SEED_RULES_PATH.read_text())
        ids, documents, metadatas = [], [], []
        for rule in rules:
            ids.append(rule["rule_id"])
            documents.append(rule["text"])
            # Chroma metadata values must be str/int/float/bool — no lists.
            # Encode tags as a comma-separated string for storage; decode on retrieval.
            meta = {
                "rule_id": rule["rule_id"],
                "tags": ",".join(rule.get("tags", [])),
                "applies_to": ",".join(rule.get("applies_to", [])),
                "citation": rule.get("citation", ""),
                "source_url": rule.get("source_url", ""),
                "retrieved_date": rule.get("retrieved_date", ""),
                "dummy": rule.get("dummy", True),
            }
            if "status" in rule:
                meta["status"] = rule["status"]
            metadatas.append(meta)

        self._col.add(ids=ids, documents=documents, metadatas=metadatas)
        print(f"Seeded {len(ids)} rule chunks into '{settings.CHROMA_COLLECTION}'.")

    def query(
        self,
        query_text: str,
        tags: list[str] | None = None,
        k: int = 4,
    ) -> list[dict[str, Any]]:
        """Semantic search with optional tag filter.

        IMPORTANT: Never embed coordinates in query_text — pass only semantic
        terms (e.g. "controlled airspace authorization"), not lat/lon values.

        Tags are stored as a comma-separated string in metadata (Chroma requires
        scalar metadata values). Tag filtering is applied in Python after retrieval:
        fetch more candidates than needed (all docs), filter by tag match, re-rank
        by distance, and cap at k.
        """
        # Fetch all docs (small corpus) so Python-side tag filtering has full coverage
        n = self._col.count()
        result = self._col.query(query_texts=[query_text], n_results=max(1, n))
        all_chunks = self._format(result)

        if not tags:
            return all_chunks[:k]

        tag_set = set(tags)
        filtered = [
            c for c in all_chunks
            if tag_set & set(c["metadata"].get("tags", []))
        ]
        return filtered[:k]

    @staticmethod
    def _format(result: dict) -> list[dict[str, Any]]:
        chunks = []
        ids = result.get("ids", [[]])[0]
        docs = result.get("documents", [[]])[0]
        metas = result.get("metadatas", [[]])[0]
        distances = result.get("distances", [[]])[0]
        for i, doc_id in enumerate(ids):
            meta = dict(metas[i])
            # Decode comma-encoded tags back to lists
            meta["tags"] = [t for t in meta.get("tags", "").split(",") if t]
            meta["applies_to"] = [a for a in meta.get("applies_to", "").split(",") if a]
            chunks.append({
                "rule_id": doc_id,
                "text": docs[i],
                "metadata": meta,
                "distance": distances[i] if i < len(distances) else None,
            })
        return chunks


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------
_store: DummyRulesStore | None = None


def get_store() -> DummyRulesStore:
    global _store
    if _store is None:
        _store = DummyRulesStore()
    return _store


# ---------------------------------------------------------------------------
# Script entry-point: `python -m app.rules.chroma_dummy`
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    store = DummyRulesStore()
    store.ensure_seeded()
    count = store._col.count()
    print(f"Collection '{settings.CHROMA_COLLECTION}' now has {count} documents.")
