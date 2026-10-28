-- FR-1.6: uploaded portrait kept separately from medical documents.
CREATE TABLE IF NOT EXISTS client_profile_photo (
    client_id VARCHAR(36) PRIMARY KEY REFERENCES client(client_id) ON DELETE CASCADE,
    file_name VARCHAR(120) NOT NULL,
    content_type VARCHAR(30) NOT NULL,
    file_data BYTEA NOT NULL,
    uploaded_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
