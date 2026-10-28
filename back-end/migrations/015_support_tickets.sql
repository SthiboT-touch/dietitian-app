CREATE TABLE IF NOT EXISTS support_ticket (
    ticket_id VARCHAR(36) PRIMARY KEY,
    owner_role VARCHAR(32) NOT NULL,
    owner_id VARCHAR(36) NOT NULL,
    subject VARCHAR(160) NOT NULL,
    status VARCHAR(16) NOT NULL DEFAULT 'OPEN' CHECK (status IN ('OPEN','IN_PROGRESS','RESOLVED')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_support_ticket_owner ON support_ticket(owner_role, owner_id, updated_at DESC);
CREATE TABLE IF NOT EXISTS support_message (
    message_id VARCHAR(36) PRIMARY KEY,
    ticket_id VARCHAR(36) NOT NULL REFERENCES support_ticket(ticket_id) ON DELETE CASCADE,
    author_role VARCHAR(32) NOT NULL,
    author_id VARCHAR(36) NOT NULL,
    body TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_support_message_ticket ON support_message(ticket_id, created_at);
