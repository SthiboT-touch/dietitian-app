-- BRS FR-1.2: add normalized contact number for new client registrations.
-- Safe for existing records: no rows are deleted or modified.
-- Older records may have NULL until the client updates their contact details.
ALTER TABLE client ADD COLUMN IF NOT EXISTS phone VARCHAR(16);
