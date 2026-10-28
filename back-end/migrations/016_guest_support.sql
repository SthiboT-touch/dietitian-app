ALTER TABLE support_ticket ADD COLUMN IF NOT EXISTS contact_email VARCHAR(150);
CREATE INDEX IF NOT EXISTS idx_support_contact_time ON support_ticket(contact_email, created_at);
