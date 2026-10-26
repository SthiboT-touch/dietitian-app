# Phase 2: RAG source visibility

Adds a collapsible list of retrieved reference excerpts to the dietitian review queue and the draft-generation result. Each item shows the source filename, paragraph number, and escaped excerpt. If no references exist, the interface warns the practitioner. No production configuration, schema, credentials, or server deployment was changed.

## Verification
- JavaScript syntax: `node --check front-end/app.js`
- Python compilation: `python -m compileall -q back-end`
- Still required: Docker/API integration, browser UI verification, clinical source curation, approval-flow tests, and production-grade RAG retrieval.

## Known limitations
The current knowledge directory has no reviewed clinical content, so the UI normally shows the no-sources warning. The underlying retrieval remains keyword-based. Source excerpts must not be treated as verified medical evidence.
