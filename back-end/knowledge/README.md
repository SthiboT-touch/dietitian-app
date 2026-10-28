# Curated NutriCare knowledge base

The retrieval engine **fails closed**: no document is retrieved unless it is explicitly listed in `manifest.json` with `approved: true` and complete metadata. The manifest initially has an empty `documents` array.

A qualified dietitian or designated academic supervisor should first review each document for clinical accuracy, currency, intended population, licensing and relevance to South African practice. Do not add private patient data. Store a permitted plain-text excerpt in this folder as `filename.txt`.

Then add an entry to `manifest.json`, for example (illustrative metadata only, NOT a real clinical source):

```json
{
  "documents": [
    {
      "filename": "approved-reference.txt",
      "title": "Reviewed document title",
      "publisher": "Publisher name",
      "source_url": "https://example.org/source",
      "reviewer": "Qualified reviewer",
      "reviewed_on": "2026-10-22",
      "approved": true
    }
  ]
}
```

Only set `approved` to true after a genuine review. Remove approval to immediately exclude a document. Keep the full original source and permissions record separately. The system still requires clinician approval of generated recommendations.

Semantic reranking remains optional and requires Ollama. This update does not provide verified clinical sources or certify POPIA/HPCSA compliance.
