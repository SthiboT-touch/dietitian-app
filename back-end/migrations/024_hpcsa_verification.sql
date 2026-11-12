-- Existing approvals require a fresh, evidenced HPCSA review before clinical access.
ALTER TABLE dietitian ADD COLUMN IF NOT EXISTS hpcsa_verified_until DATE;
ALTER TABLE dietitian_document ADD COLUMN IF NOT EXISTS practising_card_expires_at DATE;
ALTER TABLE approval_log ADD COLUMN IF NOT EXISTS practising_card_document_id VARCHAR(36);
ALTER TABLE approval_log ADD COLUMN IF NOT EXISTS hpcsa_verified_until DATE;
ALTER TABLE approval_log ADD COLUMN IF NOT EXISTS hpcsa_register_checked BOOLEAN NOT NULL DEFAULT FALSE;

-- Refuse conflicting legacy data rather than silently choosing an account.
CREATE UNIQUE INDEX IF NOT EXISTS dietitian_hpcsa_number_normalized_unique
ON dietitian (upper(regexp_replace(registration_number, '\s+', '', 'g')));
