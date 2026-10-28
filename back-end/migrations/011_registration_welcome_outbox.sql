-- FR-1.5: durable email queue; no email is sent if SMTP is not configured.
CREATE TABLE IF NOT EXISTS registration_welcome_outbox (
    message_id VARCHAR(36) PRIMARY KEY,
    client_id VARCHAR(36) NOT NULL UNIQUE REFERENCES client(client_id) ON DELETE CASCADE,
    recipient_email VARCHAR(150) NOT NULL,
    recipient_name VARCHAR(150) NOT NULL,
    state VARCHAR(16) NOT NULL DEFAULT 'PENDING' CHECK (state IN ('PENDING','SENDING','SENT','RETRY')),
    attempts INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    sent_at TIMESTAMPTZ,
    next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_welcome_outbox_due ON registration_welcome_outbox(state, next_attempt_at);
