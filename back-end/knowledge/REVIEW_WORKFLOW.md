# Nutrition reference intake — academic development

This is an intake queue, **not an approved clinical knowledge base**. The five rows in `reference_review_queue.csv` are research topics, not verified references. No clinical content has been inserted.

1. Identify an authoritative and current publication relevant to South African dietetic practice.
2. Confirm that copying/extracting the chosen passage into a local file is permitted by its license or by written permission. Prefer short, appropriately attributed summaries written by your team rather than copying copyrighted text.
3. Have a qualified dietitian or designated academic supervisor verify accuracy, population, contraindications, date and applicability. Record actual reviewer name, date, URL and permission evidence.
4. Place a reviewed, permitted UTF-8 `.txt` file in this folder. Never include patient-identifiable data.
5. Add its matching metadata to `manifest.json` and set `approved: true` **only after real approval**.
6. Run `python audit_references.py` from this folder, then test retrieval and the practitioner review UI locally.

A valid manifest record does not prove clinical correctness, licensing or regulatory compliance. Keep approval evidence separately.
