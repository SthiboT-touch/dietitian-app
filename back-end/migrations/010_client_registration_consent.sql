-- FR-1.3: additive consent audit record for new patient registrations.
-- Existing accounts stay intact; their historical consent is NOT fabricated.
CREATE TABLE IF NOT EXISTS client_registration_consent (
    client_id VARCHAR(36) PRIMARY KEY REFERENCES client(client_id) ON DELETE RESTRICT,
    privacy_notice_version VARCHAR(40) NOT NULL,
    consented_at TIMESTAMPTZ NOT NULL,
    ip_address VARCHAR(45) NOT NULL
);
