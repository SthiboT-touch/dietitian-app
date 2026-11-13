-- Retain administrator attribution and allow branch-manager decisions.
ALTER TABLE approval_log ALTER COLUMN admin_id DROP NOT NULL;
ALTER TABLE approval_log ADD COLUMN IF NOT EXISTS staff_id VARCHAR(36)
    REFERENCES staff_account(staff_id) ON DELETE RESTRICT;
