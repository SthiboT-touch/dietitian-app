CREATE TABLE IF NOT EXISTS client_medical_document (
    document_id         VARCHAR(36) PRIMARY KEY DEFAULT gen_random_uuid()::VARCHAR,
    client_id           VARCHAR(36) NOT NULL REFERENCES client(client_id) ON DELETE CASCADE,
    file_name           VARCHAR(255) NOT NULL,
    content_type        VARCHAR(100) NOT NULL,
    file_data           BYTEA NOT NULL,
    condition_name      VARCHAR(150),
    doctor_name         VARCHAR(150),
    doctor_information  TEXT,
    uploaded_at         TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS meal_log (
    meal_log_id   VARCHAR(36) PRIMARY KEY DEFAULT gen_random_uuid()::VARCHAR,
    client_id     VARCHAR(36) NOT NULL REFERENCES client(client_id) ON DELETE CASCADE,
    log_date      DATE NOT NULL DEFAULT CURRENT_DATE,
    meal_time     VARCHAR(10),
    meal_type     VARCHAR(20) NOT NULL CHECK (meal_type IN ('breakfast','lunch','dinner','snack','other')),
    description   TEXT NOT NULL,
    calories      INTEGER CHECK (calories IS NULL OR calories >= 0),
    notes         TEXT,
    created_at    TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_client_medical_document_client ON client_medical_document(client_id);
CREATE INDEX IF NOT EXISTS idx_meal_log_client_date ON meal_log(client_id, log_date);
