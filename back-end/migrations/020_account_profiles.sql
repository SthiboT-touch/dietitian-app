-- NutriCare: additive, self-service account profiles for all eight roles.
-- Apply locally only, after earlier schema migrations. No existing table is modified.
CREATE TABLE IF NOT EXISTS account_profile (
    account_role VARCHAR(30) NOT NULL CHECK (account_role IN (
        'client', 'dietitian', 'admin', 'reception', 'branch_manager',
        'compliance_officer', 'executive', 'content_manager'
    )),
    account_id VARCHAR(36) NOT NULL,
    phone_number VARCHAR(30),
    address VARCHAR(240),
    emergency_contact VARCHAR(120),
    bio VARCHAR(500),
    preferred_contact VARCHAR(10) NOT NULL DEFAULT 'email'
        CHECK (preferred_contact IN ('email', 'phone')),
    email_notifications BOOLEAN NOT NULL DEFAULT TRUE,
    appointment_reminders BOOLEAN NOT NULL DEFAULT TRUE,
    photo_data BYTEA,
    photo_content_type VARCHAR(30),
    photo_hidden BOOLEAN NOT NULL DEFAULT FALSE,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY(account_role, account_id)
);
-- account_id may reference one of several role tables; ownership is enforced
-- by bearer session and identity-bound queries in the API.
