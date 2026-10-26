-- Lactation tracking (additive only: no existing table or column is changed)

CREATE TABLE IF NOT EXISTS lactation_status_log (
    log_id            VARCHAR(36) PRIMARY KEY,
    client_id         VARCHAR(36) NOT NULL REFERENCES client(client_id) ON DELETE CASCADE,
    feeding_status    VARCHAR(20) NOT NULL CHECK (feeding_status IN ('breastfeeding','formula_feeding','combo')),
    infant_age_months INT,
    infant_age_weeks  INT,
    infant_birth_date DATE,
    notes             TEXT,
    logged_at         TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS daily_feeding_log (
    log_id                 VARCHAR(36) PRIMARY KEY,
    client_id              VARCHAR(36) NOT NULL REFERENCES client(client_id) ON DELETE CASCADE,
    feed_date              DATE NOT NULL DEFAULT CURRENT_DATE,
    breastfeeding_sessions INT NOT NULL DEFAULT 0,
    pumping_sessions       INT NOT NULL DEFAULT 0,
    expressed_milk_ml      NUMERIC(7,1) NOT NULL DEFAULT 0,
    formula_ml             NUMERIC(7,1) NOT NULL DEFAULT 0,
    formula_feeds          INT NOT NULL DEFAULT 0,
    wet_diapers            INT,
    dirty_diapers          INT,
    notes                  TEXT,
    logged_at              TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS milk_supply_log (
    log_id           VARCHAR(36) PRIMARY KEY,
    client_id        VARCHAR(36) NOT NULL REFERENCES client(client_id) ON DELETE CASCADE,
    concern          VARCHAR(20) NOT NULL CHECK (concern IN ('low_supply','over_supply')),
    log_date         DATE NOT NULL DEFAULT CURRENT_DATE,
    pumped_ml_24h    NUMERIC(7,1),
    strategies_tried TEXT,
    notes            TEXT,
    logged_at        TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS weaning_plan_log (
    log_id                VARCHAR(36) PRIMARY KEY,
    client_id             VARCHAR(36) NOT NULL REFERENCES client(client_id) ON DELETE CASCADE,
    approach              VARCHAR(20) NOT NULL DEFAULT 'gradual' CHECK (approach IN ('gradual','partial','abrupt_medical')),
    start_date            DATE NOT NULL DEFAULT CURRENT_DATE,
    feeds_per_day_current INT NOT NULL,
    feeds_per_day_target  INT NOT NULL DEFAULT 0,
    notes                 TEXT,
    logged_at             TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS maternal_discomfort_log (
    log_id               VARCHAR(36) PRIMARY KEY,
    client_id            VARCHAR(36) NOT NULL REFERENCES client(client_id) ON DELETE CASCADE,
    symptom_type         VARCHAR(20) NOT NULL CHECK (symptom_type IN ('mastitis','clogged_duct','sore_nipples','cracked_nipples','engorgement','other')),
    severity             INT NOT NULL CHECK (severity BETWEEN 1 AND 10),
    breast_side          VARCHAR(5) CHECK (breast_side IN ('left','right','both')),
    has_fever            BOOLEAN NOT NULL DEFAULT FALSE,
    temperature_c        NUMERIC(4,1),
    flu_like_symptoms    BOOLEAN NOT NULL DEFAULT FALSE,
    redness_or_hard_lump BOOLEAN NOT NULL DEFAULT FALSE,
    log_date             DATE NOT NULL DEFAULT CURRENT_DATE,
    treatment_tried      TEXT,
    notes                TEXT,
    logged_at            TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS infant_sensitivity_log (
    log_id                           VARCHAR(36) PRIMARY KEY,
    client_id                        VARCHAR(36) NOT NULL REFERENCES client(client_id) ON DELETE CASCADE,
    category                         VARCHAR(20) NOT NULL CHECK (category IN ('food_reaction','allergy','excessive_gas','reflux','colic','other')),
    severity                         INT NOT NULL CHECK (severity BETWEEN 1 AND 10),
    suspected_trigger                VARCHAR(150),
    symptoms                         TEXT,
    log_date                         DATE NOT NULL DEFAULT CURRENT_DATE,
    duration_minutes                 INT,
    blood_in_stool                   BOOLEAN NOT NULL DEFAULT FALSE,
    breathing_difficulty_or_swelling BOOLEAN NOT NULL DEFAULT FALSE,
    notes                            TEXT,
    logged_at                        TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_lactation_status_client     ON lactation_status_log(client_id);
CREATE INDEX IF NOT EXISTS idx_daily_feeding_client        ON daily_feeding_log(client_id);
CREATE INDEX IF NOT EXISTS idx_milk_supply_client          ON milk_supply_log(client_id);
CREATE INDEX IF NOT EXISTS idx_weaning_plan_client         ON weaning_plan_log(client_id);
CREATE INDEX IF NOT EXISTS idx_maternal_discomfort_client  ON maternal_discomfort_log(client_id);
CREATE INDEX IF NOT EXISTS idx_infant_sensitivity_client   ON infant_sensitivity_log(client_id);
