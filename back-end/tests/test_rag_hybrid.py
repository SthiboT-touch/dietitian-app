import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import rag
import json

def approve_test_document(tmp_path):
    (tmp_path / "manifest.json").write_text(json.dumps({"documents": [{"filename": "reviewed.txt", "title": "Test", "publisher": "Test", "source_url": "https://example.org", "reviewer": "Tester", "reviewed_on": "2026-10-22", "approved": True}]}))

def test_keyword_retrieval(tmp_path, monkeypatch):
    (tmp_path / "reviewed.txt").write_text("Hypertension dietary sodium guidance.", encoding="utf-8")
    approve_test_document(tmp_path)
    monkeypatch.setattr(rag, "KNOWLEDGE_DIR", tmp_path)
    monkeypatch.delenv("NUTRICARE_RAG_SEMANTIC", raising=False)
    result = rag.retrieve_context("hypertension sodium")
    assert result and result[0]["source"] == "reviewed.txt"

def test_empty_and_unmatched(tmp_path, monkeypatch):
    (tmp_path / "reviewed.txt").write_text("Calcium guidance.", encoding="utf-8")
    approve_test_document(tmp_path)
    monkeypatch.setattr(rag, "KNOWLEDGE_DIR", tmp_path)
    monkeypatch.delenv("NUTRICARE_RAG_SEMANTIC", raising=False)
    assert rag.retrieve_context("") == []
    assert rag.retrieve_context("hypertension") == []

def test_semantic_fallback(tmp_path, monkeypatch):
    (tmp_path / "reviewed.txt").write_text("Hypertension guidance.", encoding="utf-8")
    approve_test_document(tmp_path)
    monkeypatch.setattr(rag, "KNOWLEDGE_DIR", tmp_path)
    monkeypatch.setenv("NUTRICARE_RAG_SEMANTIC", "1")
    class Broken:
        def embed_query(self, query): raise ConnectionError("offline")
    monkeypatch.setattr(rag, "_embeddings", lambda: Broken())
    assert rag.retrieve_context("hypertension")[0]["source"] == "reviewed.txt"
