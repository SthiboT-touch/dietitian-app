-- FR-1.7: store only SHA256 of random check-in credential; never ID numbers.
CREATE TABLE IF NOT EXISTS client_checkin_credential (
    client_id VARCHAR(36) PRIMARY KEY REFERENCES client(client_id) ON DELETE CASCADE,
    token_hash VARCHAR(64) UNIQUE NOT NULL,
    rotated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL DEFAULT (NOW() + INTERVAL '10 minutes')
);
CREATE TABLE IF NOT EXISTS client_checkin_event (
    checkin_id VARCHAR(36) PRIMARY KEY,
    client_id VARCHAR(36) NOT NULL REFERENCES client(client_id) ON DELETE RESTRICT,
    staff_id VARCHAR(36) NOT NULL REFERENCES staff_account(staff_id) ON DELETE RESTRICT,
    branch_id VARCHAR(36) NOT NULL REFERENCES branch(branch_id) ON DELETE RESTRICT,
    checked_in_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_client_checkin_event_client ON client_checkin_event(client_id, checked_in_at DESC);
