-- Require identity and gender data for newly created client profiles.
-- Existing rows receive a deterministic placeholder ID and 'other' until reviewed.
ALTER TABLE client ADD COLUMN IF NOT EXISTS id_number VARCHAR(30);
ALTER TABLE client ADD COLUMN IF NOT EXISTS gender VARCHAR(20);

UPDATE client
SET id_number = 'legacy-' || client_id
WHERE id_number IS NULL OR BTRIM(id_number) = '';

UPDATE client
SET gender = 'other'
WHERE gender IS NULL OR BTRIM(gender) = '';

ALTER TABLE client ALTER COLUMN id_number SET NOT NULL;
ALTER TABLE client ALTER COLUMN gender SET NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS idx_client_id_number ON client(id_number);
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'client_gender_check'
    ) THEN
        ALTER TABLE client ADD CONSTRAINT client_gender_check CHECK (gender IN ('male','female','other'));
    END IF;
END $$;
