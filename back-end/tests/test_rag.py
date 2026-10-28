import json
import rag


def test_retrieval_no_documents(tmp_path, monkeypatch):
    monkeypatch.setattr(rag, "KNOWLEDGE_DIR", tmp_path)
    assert rag.retrieve_context("diabetes nutrition") == []


def test_retrieval_source_and_relevance(tmp_path, monkeypatch):
    (tmp_path / "reviewed.txt").write_text(
        "Source: Example reviewed reference\n\nDiabetes nutrition education discusses food choices and meal timing."
    )
    (tmp_path / "ignored.md").write_text("Diabetes nutrition")
    (tmp_path / "manifest.json").write_text(
        json.dumps(
            {
                "documents": [
                    {
                        "filename": "reviewed.txt",
                        "title": "Test",
                        "publisher": "Test",
                        "source_url": "https://example.org",
                        "reviewer": "Tester",
                        "reviewed_on": "2026-10-22",
                        "approved": True,
                    }
                ]
            }
        )
    )
    monkeypatch.setattr(rag, "KNOWLEDGE_DIR", tmp_path)
    results = rag.retrieve_context("diabetes nutrition")
    assert results and results[0]["source"] == "reviewed.txt"
    assert "Diabetes" in results[0]["excerpt"]
    assert len(results) <= 3


def test_unapproved_reference_is_excluded(tmp_path, monkeypatch):
    (tmp_path / "unreviewed.txt").write_text("Diabetes nutrition guidance")
    (tmp_path / "manifest.json").write_text(
        json.dumps({"documents": [{"filename": "unreviewed.txt", "approved": False}]})
    )
    monkeypatch.setattr(rag, "KNOWLEDGE_DIR", tmp_path)
    assert rag.retrieve_context("diabetes nutrition") == []


def test_missing_manifest_fails_closed(tmp_path, monkeypatch):
    (tmp_path / "random.txt").write_text("Diabetes nutrition")
    monkeypatch.setattr(rag, "KNOWLEDGE_DIR", tmp_path)
    assert rag.retrieve_context("diabetes nutrition") == []
