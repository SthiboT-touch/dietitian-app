ALTER TABLE dietitian_document
    ADD COLUMN IF NOT EXISTS branch_id VARCHAR(36) REFERENCES branch(branch_id) ON DELETE RESTRICT;

UPDATE dietitian_document dd
SET branch_id = d.branch_id
FROM dietitian d
WHERE dd.dietitian_id = d.dietitian_id
  AND dd.branch_id IS NULL;

ALTER TABLE dietitian_document
    ALTER COLUMN branch_id SET NOT NULL;

CREATE INDEX IF NOT EXISTS idx_dietitian_document_branch
    ON dietitian_document(branch_id);
