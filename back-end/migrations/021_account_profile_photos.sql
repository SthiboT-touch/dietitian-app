CREATE TABLE IF NOT EXISTS account_profile_photo (
    account_type VARCHAR(30) NOT NULL CHECK (
        account_type IN (
            'client', 'dietitian', 'admin', 'reception',
            'branch_manager', 'compliance_officer', 'executive', 'content_manager'
        )
    ),
    account_id VARCHAR(36) NOT NULL,
    file_name VARCHAR(120) NOT NULL,
    content_type VARCHAR(30) NOT NULL CHECK (content_type IN ('image/jpeg', 'image/png')),
    file_data BYTEA NOT NULL,
    uploaded_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (account_type, account_id)
);

INSERT INTO account_profile_photo (account_type, account_id, file_name, content_type, file_data, uploaded_at)
SELECT 'client', client_id, file_name, content_type, file_data, uploaded_at
FROM client_profile_photo
ON CONFLICT (account_type, account_id) DO NOTHING;
