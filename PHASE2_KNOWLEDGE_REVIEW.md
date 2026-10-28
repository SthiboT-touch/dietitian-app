# Phase 2 — Curated knowledge gating

Added a manifest-based allowlist so only explicitly reviewed nutrition documents can enter RAG retrieval. No clinical documents are bundled; the default knowledge base is empty. See `back-end/knowledge/README.md`.

## Remaining work
- Obtain and license reliable source documents; have them reviewed by a qualified practitioner.
- Verify source attribution and retrieval quality using representative questions.
- Test the AI approval workflow and Docker integration.
- Add persistent embedding index only if performance warrants it.

No production systems or passwords were modified.
