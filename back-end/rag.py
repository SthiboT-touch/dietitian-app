"""Bounded local knowledge retrieval with optional Ollama semantic reranking.

Only curated local .txt references are indexed. No patient data is stored.
Set NUTRICARE_RAG_SEMANTIC=1 and install/pull the embedding model in Ollama
before enabling semantic search. Keyword retrieval remains the safe fallback.
"""

import math
import json
import os
from pathlib import Path
import re
from functools import lru_cache

KNOWLEDGE_DIR = Path(__file__).resolve().parent / "knowledge"
STOPWORDS = {
    "about",
    "after",
    "also",
    "and",
    "are",
    "for",
    "from",
    "have",
    "into",
    "that",
    "the",
    "their",
    "this",
    "with",
    "your",
}


def _tokens(text):
    return {t for t in re.findall(r"[a-z0-9]{3,}", text.lower()) if t not in STOPWORDS}


def _documents():
    if not KNOWLEDGE_DIR.is_dir():
        return []
    # Explicit allowlist: unreviewed or revoked documents must never enter retrieval.
    manifest_path = KNOWLEDGE_DIR / "manifest.json"
    if not manifest_path.is_file():
        return []
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        entries = manifest.get("documents", [])
        allowed = {
            e["filename"]
            for e in entries
            if isinstance(e, dict)
            and e.get("approved") is True
            and all(
                isinstance(e.get(k), str) and e[k].strip()
                for k in ("filename", "title", "publisher", "source_url", "reviewer", "reviewed_on")
            )
            and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*\.txt", e.get("filename", ""))
        }
    except (OSError, ValueError, TypeError, KeyError):
        return []
    result = []
    for path in sorted(KNOWLEDGE_DIR.glob("*.txt"))[:100]:
        if path.name not in allowed:
            continue
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 250_000:
            continue
        for i, paragraph in enumerate(
            re.split(r"\n\s*\n", path.read_text(encoding="utf-8", errors="replace"))
        ):
            paragraph = paragraph.strip()
            for offset in range(0, len(paragraph), 900):
                chunk = paragraph[offset : offset + 900]
                if chunk:
                    result.append({"source": path.name, "paragraph": i + 1, "excerpt": chunk})
    return result


@lru_cache(maxsize=1)
def _embeddings():
    from langchain_ollama import OllamaEmbeddings

    return OllamaEmbeddings(
        model=os.getenv("NUTRICARE_EMBED_MODEL", "nomic-embed-text"),
        base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
    )


def _cosine(a, b):
    if len(a) != len(b) or not a:
        return 0.0
    denom = math.sqrt(sum(x * x for x in a) * sum(y * y for y in b))
    return sum(x * y for x, y in zip(a, b)) / denom if denom else 0.0


def retrieve_context(query: str, *, max_chunks: int = 3, max_chars: int = 2400) -> list[dict]:
    """Return source-labelled excerpts. Semantic search is opt-in, local-only.

    Failure of local embedding service falls back to keyword matching.
    Never use this output as medical advice without practitioner review.
    """
    if not isinstance(query, str) or not query.strip() or max_chunks <= 0 or max_chars <= 0:
        return []
    docs = _documents()
    terms = _tokens(query)
    if not docs or not terms:
        return []
    lexical = [len(terms & _tokens(d["excerpt"])) for d in docs]
    scores = [float(s) for s in lexical]
    if os.getenv("NUTRICARE_RAG_SEMANTIC", "0") == "1":
        try:
            embeddings = _embeddings()
            q_vector = embeddings.embed_query(query[:1000])
            # Keep indexing bounded to prevent large memory and latency spikes.
            vectors = embeddings.embed_documents([d["excerpt"] for d in docs[:500]])
            for i, vec in enumerate(vectors[:500]):
                scores[i] += max(0.0, _cosine(q_vector, vec)) * 3.0
        except Exception:
            # An unavailable local embedding model must not break the app.
            pass
    ranked = sorted(
        range(len(docs)), key=lambda i: (-scores[i], docs[i]["source"], docs[i]["paragraph"])
    )
    result, remaining = [], max_chars
    for i in ranked:
        if scores[i] <= 0 or len(result) >= max_chunks or remaining <= 0:
            break
        excerpt = docs[i]["excerpt"][:remaining]
        result.append({**docs[i], "excerpt": excerpt})
        remaining -= len(excerpt)
    return result
