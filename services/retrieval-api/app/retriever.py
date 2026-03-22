from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import numpy as np
from chromadb import PersistentClient
from chromadb.api.models.Collection import Collection
from chromadb.utils.embedding_functions import OpenAIEmbeddingFunction, SentenceTransformerEmbeddingFunction
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


def default_chunks_path() -> Path:
    env_path = os.getenv("CHUNKS_PATH")
    if env_path:
        return Path(env_path)

    resolved = Path(__file__).resolve()
    candidate_rel = []
    for depth in (2, 3):
        try:
            candidate_rel.append(resolved.parents[depth] / "data/knowledge/processed/chunks.jsonl")
        except IndexError:
            continue

    candidates = [
        Path("/app/data/knowledge/processed/chunks.jsonl"),
        *candidate_rel,
        Path.cwd() / "data/knowledge/processed/chunks.jsonl",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


CHUNKS_PATH = default_chunks_path()


@dataclass
class ChunkRecord:
    id: str
    bank_id: str
    bank_name: str
    topic: str
    url: str
    title: str
    text: str


class Retriever(Protocol):
    backend: str
    chunks: list[ChunkRecord]

    def search(self, query: str, topic: str, bank_id: str | None = None, top_k: int = 5) -> list[tuple[ChunkRecord, float]]:
        ...


def _load_chunks(path: Path) -> list[ChunkRecord]:
    if not path.exists():
        return []
    chunks: list[ChunkRecord] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            raw = json.loads(line)
            chunks.append(ChunkRecord(**raw))
    return chunks


class TfidfRetriever:
    backend = "tfidf"

    def __init__(self, chunks: list[ChunkRecord]):
        self.chunks = chunks
        self.vectorizer = TfidfVectorizer(
            analyzer="char_wb",
            ngram_range=(3, 5),
            min_df=1,
        )
        corpus = [f"{c.title} {c.text}" for c in chunks] or ["empty"]
        self.matrix = self.vectorizer.fit_transform(corpus)

    @classmethod
    def from_disk(cls, path: Path = CHUNKS_PATH) -> "TfidfRetriever":
        return cls(chunks=_load_chunks(path))

    def search(self, query: str, topic: str, bank_id: str | None = None, top_k: int = 5) -> list[tuple[ChunkRecord, float]]:
        if not self.chunks:
            return []

        idx = [
            i
            for i, chunk in enumerate(self.chunks)
            if chunk.topic == topic and (bank_id is None or chunk.bank_id == bank_id)
        ]
        if not idx:
            return []

        q_vec = self.vectorizer.transform([query])
        scores = cosine_similarity(q_vec, self.matrix[idx]).flatten()

        ranked = np.argsort(scores)[::-1][:top_k]
        results: list[tuple[ChunkRecord, float]] = []
        for ridx in ranked:
            score = float(scores[ridx])
            results.append((self.chunks[idx[int(ridx)]], score))
        return results


class ChromaRetriever:
    backend = "chroma"

    def __init__(self, chunks: list[ChunkRecord], collection: Collection):
        self.chunks = chunks
        self.collection = collection
        self.chunk_by_id = {c.id: c for c in chunks}

    @classmethod
    def from_disk(cls, path: Path = CHUNKS_PATH) -> "ChromaRetriever":
        chunks = _load_chunks(path)
        persist_dir = Path(os.getenv("CHROMA_PERSIST_DIR", "/app/data/chroma"))
        persist_dir.mkdir(parents=True, exist_ok=True)

        embedding_fn = None
        provider = os.getenv("EMBEDDING_PROVIDER", "hf").lower()

        if provider == "openai":
            openai_key = os.getenv("OPENAI_API_KEY")
            if openai_key:
                embedding_fn = OpenAIEmbeddingFunction(
                    api_key=openai_key,
                    model_name=os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small"),
                )
        elif provider == "hf":
            embedding_fn = SentenceTransformerEmbeddingFunction(
                model_name=os.getenv(
                    "HF_EMBEDDING_MODEL",
                    "Metric-AI/armenian-text-embeddings-2-large",
                ),
            )

        client = PersistentClient(path=str(persist_dir))
        collection_name = os.getenv("CHROMA_COLLECTION", "bank_chunks")
        # Deterministic startup behavior: rebuild the collection from the local source of truth.
        try:
            client.delete_collection(name=collection_name)
        except Exception:
            pass

        collection = client.get_or_create_collection(
            name=collection_name,
            embedding_function=embedding_fn,
            metadata={"hnsw:space": "cosine"},
        )
        if chunks:
            collection.add(
                ids=[c.id for c in chunks],
                documents=[c.text for c in chunks],
                metadatas=[
                    {
                        "bank_id": c.bank_id,
                        "bank_name": c.bank_name,
                        "topic": c.topic,
                        "url": c.url,
                        "title": c.title,
                    }
                    for c in chunks
                ],
            )

        retriever = cls(chunks=chunks, collection=collection)
        return retriever

    def search(self, query: str, topic: str, bank_id: str | None = None, top_k: int = 5) -> list[tuple[ChunkRecord, float]]:
        if not self.chunks:
            return []

        where = {"topic": topic}
        if bank_id is not None:
            where["bank_id"] = bank_id

        result = self.collection.query(
            query_texts=[query],
            n_results=top_k,
            where=where,
            include=["documents", "metadatas", "distances"],
        )

        ids = result.get("ids", [[]])[0]
        docs = result.get("documents", [[]])[0]
        metas = result.get("metadatas", [[]])[0]
        dists = result.get("distances", [[]])[0]

        out: list[tuple[ChunkRecord, float]] = []
        for idx, chunk_id in enumerate(ids):
            existing = self.chunk_by_id.get(chunk_id)
            if existing is not None:
                chunk = existing
            else:
                meta = metas[idx] if idx < len(metas) else {}
                text = docs[idx] if idx < len(docs) else ""
                chunk = ChunkRecord(
                    id=chunk_id,
                    bank_id=str(meta.get("bank_id", "")),
                    bank_name=str(meta.get("bank_name", "")),
                    topic=str(meta.get("topic", topic)),
                    url=str(meta.get("url", "")),
                    title=str(meta.get("title", "")),
                    text=text,
                )

            raw_dist = dists[idx] if idx < len(dists) else None
            dist = float(raw_dist) if raw_dist is not None else 1.0
            score = max(0.0, 1.0 - dist)
            out.append((chunk, score))
        return out


def build_retriever(path: Path = CHUNKS_PATH) -> Retriever:
    backend = os.getenv("RETRIEVER_BACKEND", "auto").lower()
    print(backend, 'backend')
    if backend == "tfidf":
        return TfidfRetriever.from_disk(path)

    if backend == "chroma":
        return ChromaRetriever.from_disk(path)

    # auto mode: prefer ChromaDB, then fallback to TF-IDF for robustness.
    try:
        return ChromaRetriever.from_disk(path)
    except Exception:
        return TfidfRetriever.from_disk(path)


