-- FR-1.8: distinguish staff-assisted consent capture; the staff IP is not the client's.
ALTER TABLE client_registration_consent
    ADD COLUMN IF NOT EXISTS registration_mode VARCHAR(12) NOT NULL DEFAULT 'SELF'
        CHECK (registration_mode IN ('SELF','ASSISTED'));
ALTER TABLE client_registration_consent
    ADD COLUMN IF NOT EXISTS registered_by_staff_id VARCHAR(36)
        REFERENCES staff_account(staff_id) ON DELETE SET NULL;
