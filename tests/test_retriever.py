import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1] / "services/retrieval-api"))

from app.retriever import ChunkRecord, TfidfRetriever, build_retriever


def test_retriever_filters_by_topic_and_bank():
    chunks = [
        ChunkRecord(
            id="1",
            bank_id="acba",
            bank_name="ACBA",
            topic="credits",
            url="https://example.com/loans",
            title="Loans",
            text="ACBA offers mortgage and consumer loans.",
        ),
        ChunkRecord(
            id="2",
            bank_id="acba",
            bank_name="ACBA",
            topic="deposits",
            url="https://example.com/deposits",
            title="Deposits",
            text="Term deposits are available for 12 months.",
        ),
    ]

    retriever = TfidfRetriever(chunks)
    results = retriever.search(query="consumer loan", topic="credits", bank_id="acba", top_k=3)
    assert len(results) == 1
    assert results[0][0].topic == "credits"


def test_from_disk_missing_file_returns_empty(tmp_path):
    missing = tmp_path / "does-not-exist.jsonl"
    retriever = TfidfRetriever.from_disk(path=missing)
    assert retriever.chunks == []


def test_factory_can_force_tfidf(tmp_path, monkeypatch):
    missing = tmp_path / "does-not-exist.jsonl"
    monkeypatch.setenv("RETRIEVER_BACKEND", "tfidf")
    retriever = build_retriever(path=missing)
    assert retriever.backend == "tfidf"


