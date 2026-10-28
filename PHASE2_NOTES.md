# Phase 2 — RAG development baseline

Added `back-end/rag.py` local keyword-based retrieval, a knowledge-base folder, and tests. AI chat and draft plan prompts now include matching local reference excerpts when available. The knowledge folder intentionally contains no clinical source material: a qualified reviewer must supply licensed, current references.

**Not complete:** vector embeddings, ingestion for PDF/HTML, source validation, citation display in the frontend, retrieval quality evaluation, automated tests in the target Docker environment, and full security assessment. AI drafts still require human approval. This is a development artifact only; do not deploy to production.
