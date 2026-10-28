ALTER TABLE dietitian ADD COLUMN IF NOT EXISTS email_verified BOOLEAN NOT NULL DEFAULT TRUE;
ALTER TABLE dietitian ADD COLUMN IF NOT EXISTS stytch_user_id VARCHAR(80);
ALTER TABLE client ADD COLUMN IF NOT EXISTS email_verified BOOLEAN NOT NULL DEFAULT TRUE;
ALTER TABLE client ADD COLUMN IF NOT EXISTS stytch_user_id VARCHAR(80);

CREATE INDEX IF NOT EXISTS idx_dietitian_stytch_user ON dietitian(stytch_user_id);
CREATE INDEX IF NOT EXISTS idx_client_stytch_user ON client(stytch_user_id);
