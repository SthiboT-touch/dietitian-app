ALTER TABLE appointment ADD COLUMN IF NOT EXISTS branch_id VARCHAR(50);
ALTER TABLE appointment ADD COLUMN IF NOT EXISTS consultation_type VARCHAR(20) NOT NULL DEFAULT 'INITIAL';
CREATE TABLE IF NOT EXISTS client_care_event (
    event_id VARCHAR(50) PRIMARY KEY,
    client_id VARCHAR(50) NOT NULL REFERENCES client(client_id),
    kind VARCHAR(30) NOT NULL,
    author_id VARCHAR(50) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    payload JSONB NOT NULL
);
CREATE INDEX IF NOT EXISTS client_care_event_client_idx ON client_care_event(client_id, created_at);
