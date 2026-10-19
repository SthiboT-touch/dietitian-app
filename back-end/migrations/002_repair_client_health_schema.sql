CREATE TABLE IF NOT EXISTS pregnancy_profile (
    pregnancy_id VARCHAR(36) PRIMARY KEY DEFAULT gen_random_uuid()::VARCHAR,
    client_id VARCHAR(36) NOT NULL REFERENCES client(client_id) ON DELETE CASCADE,
    conception_date DATE,
    due_date DATE,
    pre_pregnancy_weight_kg NUMERIC(5,2),
    gestational_diabetes BOOLEAN NOT NULL DEFAULT FALSE,
    multiple_gestation BOOLEAN NOT NULL DEFAULT FALSE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS lactation_profile (
    lactation_id VARCHAR(36) PRIMARY KEY DEFAULT gen_random_uuid()::VARCHAR,
    client_id VARCHAR(36) NOT NULL REFERENCES client(client_id) ON DELETE CASCADE,
    start_date DATE NOT NULL,
    end_date DATE,
    exclusive BOOLEAN NOT NULL DEFAULT TRUE,
    notes TEXT,
    CHECK (end_date IS NULL OR end_date >= start_date)
);

ALTER TABLE lactation_profile
    ADD COLUMN IF NOT EXISTS end_date DATE;

CREATE TABLE IF NOT EXISTS medical_condition (
    condition_id VARCHAR(36) PRIMARY KEY DEFAULT gen_random_uuid()::VARCHAR,
    name VARCHAR(100) NOT NULL UNIQUE,
    category VARCHAR(50),
    icd_code VARCHAR(20)
);

CREATE TABLE IF NOT EXISTS client_medical_condition (
    client_id VARCHAR(36) NOT NULL REFERENCES client(client_id) ON DELETE CASCADE,
    condition_id VARCHAR(36) NOT NULL REFERENCES medical_condition(condition_id) ON DELETE RESTRICT,
    diagnosed_date DATE,
    severity VARCHAR(20) DEFAULT 'MODERATE'
        CHECK (severity IN ('MILD', 'MODERATE', 'SEVERE')),
    notes TEXT,
    PRIMARY KEY (client_id, condition_id)
);

CREATE TABLE IF NOT EXISTS allergen (
    allergen_id VARCHAR(36) PRIMARY KEY DEFAULT gen_random_uuid()::VARCHAR,
    name VARCHAR(100) NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS client_allergy (
    client_id VARCHAR(36) NOT NULL REFERENCES client(client_id) ON DELETE CASCADE,
    allergen_id VARCHAR(36) NOT NULL REFERENCES allergen(allergen_id) ON DELETE RESTRICT,
    severity VARCHAR(30) DEFAULT 'MODERATE'
        CHECK (severity IN ('MILD', 'MODERATE', 'SEVERE', 'ANAPHYLACTIC')),
    PRIMARY KEY (client_id, allergen_id)
);

CREATE TABLE IF NOT EXISTS metric_type (
    metric_type_id VARCHAR(36) PRIMARY KEY DEFAULT gen_random_uuid()::VARCHAR,
    name VARCHAR(100) NOT NULL UNIQUE,
    unit VARCHAR(20) NOT NULL
);

CREATE TABLE IF NOT EXISTS client_metric_log (
    metric_log_id VARCHAR(36) PRIMARY KEY DEFAULT gen_random_uuid()::VARCHAR,
    client_id VARCHAR(36) NOT NULL REFERENCES client(client_id) ON DELETE CASCADE,
    metric_type_id VARCHAR(36) NOT NULL REFERENCES metric_type(metric_type_id) ON DELETE RESTRICT,
    recorded_at TIMESTAMP NOT NULL DEFAULT NOW(),
    value NUMERIC(8,2) NOT NULL,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS progress_log (
    progress_log_id VARCHAR(36) PRIMARY KEY DEFAULT gen_random_uuid()::VARCHAR,
    client_id VARCHAR(36) NOT NULL REFERENCES client(client_id) ON DELETE CASCADE,
    log_date DATE NOT NULL,
    weight NUMERIC(5,2),
    body_fat_pct NUMERIC(4,2),
    waist_cm NUMERIC(5,2),
    calories_consumed INTEGER,
    calories_burned INTEGER,
    water_ml INTEGER,
    steps INTEGER,
    protein_g NUMERIC(5,1),
    carbs_g NUMERIC(5,1),
    fat_g NUMERIC(5,1),
    fiber_g NUMERIC(4,1),
    sugar_g NUMERIC(4,1),
    sleep_minutes INTEGER,
    resting_heart_rate INTEGER,
    notes TEXT,
    CONSTRAINT unique_client_date_log UNIQUE (client_id, log_date)
);
