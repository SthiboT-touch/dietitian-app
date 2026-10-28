-- NutriCare Security Milestone 02: additive schema (safe for existing rows).
-- Apply manually to an isolated LOCAL PostgreSQL database before enabling staff accounts.
-- Neither table replaces existing admin, dietitian, client or approval_log tables.

CREATE TABLE IF NOT EXISTS staff_account (
    staff_id       VARCHAR(36) PRIMARY KEY,
    full_name      VARCHAR(200) NOT NULL,
    email          VARCHAR(150) NOT NULL,
    password_hash  VARCHAR(255) NOT NULL,
    role           VARCHAR(32) NOT NULL CHECK (
        role IN ('reception', 'branch_manager', 'compliance_officer', 'executive', 'content_manager')
    ),
    branch_id      VARCHAR(36) REFERENCES branch(branch_id) ON DELETE RESTRICT,
    is_active      BOOLEAN NOT NULL DEFAULT TRUE,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT staff_branch_required CHECK (
        role NOT IN ('reception', 'branch_manager') OR branch_id IS NOT NULL
    )
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_staff_email_lower ON staff_account (LOWER(email));
CREATE INDEX IF NOT EXISTS idx_staff_branch ON staff_account (branch_id);

CREATE TABLE IF NOT EXISTS access_audit_event (
    event_id      VARCHAR(36) PRIMARY KEY,
    actor_id      VARCHAR(36),
    actor_role    VARCHAR(32) NOT NULL,
    http_method   VARCHAR(10) NOT NULL,
    resource_path TEXT NOT NULL,
    status_code   SMALLINT NOT NULL,
    occurred_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_access_audit_time ON access_audit_event (occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_access_audit_actor ON access_audit_event (actor_role, actor_id);
