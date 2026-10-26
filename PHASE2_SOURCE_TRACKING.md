# Phase 2 — RAG source tracking (development only)

AI recommendation records now retain the retrieved source excerpts used when a draft was generated. The PostgreSQL path stores these inside the existing `recommendation_text` JSON; the in-memory path stores them in the recommendation object. `decode_recommendation` returns the source excerpts to authorized dietitian review API callers. No database migration is required.

**Limitations:** This is keyword retrieval, not embeddings/vector RAG. The knowledge folder is not populated with approved clinical documents. Retrieved excerpts are not proof that an AI claim is supported; dietitians must verify citations and all generated advice. The frontend does not yet display these excerpts. Docker, end-to-end, and clinical safety tests remain outstanding. Do not deploy to production.
