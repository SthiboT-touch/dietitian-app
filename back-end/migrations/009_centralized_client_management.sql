CREATE TABLE IF NOT EXISTS ehr_note (
    note_id VARCHAR(36) PRIMARY KEY,
    client_id VARCHAR(36) NOT NULL REFERENCES client(client_id) ON DELETE CASCADE,
    author_id VARCHAR(36) NOT NULL,
    note_type VARCHAR(30) NOT NULL CHECK (note_type IN ('consultation','assessment','follow_up','general')),
    content TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS nutrition_plan_version (
    plan_id VARCHAR(36) PRIMARY KEY,
    client_id VARCHAR(36) NOT NULL REFERENCES client(client_id) ON DELETE CASCADE,
    author_id VARCHAR(36) NOT NULL,
    title VARCHAR(200) NOT NULL,
    content TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    status VARCHAR(20) NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','active','archived')),
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS client_attachment (
    attachment_id VARCHAR(36) PRIMARY KEY,
    client_id VARCHAR(36) NOT NULL REFERENCES client(client_id) ON DELETE CASCADE,
    uploaded_by VARCHAR(36) NOT NULL,
    file_name VARCHAR(255) NOT NULL,
    content_type VARCHAR(100) NOT NULL,
    file_data BYTEA NOT NULL,
    category VARCHAR(50) NOT NULL DEFAULT 'medical',
    version INTEGER NOT NULL DEFAULT 1,
    previous_attachment_id VARCHAR(36) REFERENCES client_attachment(attachment_id) ON DELETE SET NULL,
    uploaded_at TIMESTAMP NOT NULL DEFAULT NOW(),
    retention_until DATE NOT NULL,
    sha256 VARCHAR(64) NOT NULL
);

CREATE TABLE IF NOT EXISTS client_access_audit (
    audit_id VARCHAR(36) PRIMARY KEY,
    client_id VARCHAR(36) NOT NULL REFERENCES client(client_id) ON DELETE CASCADE,
    actor_id VARCHAR(36) NOT NULL,
    action VARCHAR(80) NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    accessed_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_ehr_note_client ON ehr_note(client_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_nutrition_plan_client ON nutrition_plan_version(client_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_client_attachment_client ON client_attachment(client_id, uploaded_at DESC);
CREATE INDEX IF NOT EXISTS idx_client_access_audit_client ON client_access_audit(client_id, accessed_at DESC);
