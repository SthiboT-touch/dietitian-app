-- ============================================

-- EXTENSIONS (needed for gen_random_uuid())

-- ============================================

CREATE EXTENSION IF NOT EXISTS pgcrypto;



-- ============================================

-- 1. BUSINESS & ORGANIZATIONAL STRUCTURE

-- ============================================



CREATE TABLE business (

    business_id          VARCHAR(36) PRIMARY KEY DEFAULT gen_random_uuid()::VARCHAR,

    name                 VARCHAR(150) NOT NULL,

    registration_number  VARCHAR(50) UNIQUE NOT NULL,

    contact_email        VARCHAR(150)

);



CREATE TABLE branch (

    branch_id    VARCHAR(36) PRIMARY KEY DEFAULT gen_random_uuid()::VARCHAR,

    business_id  VARCHAR(36) NOT NULL REFERENCES business(business_id) ON DELETE CASCADE,

    name         VARCHAR(150) NOT NULL,

    address      VARCHAR(255)

);



-- ============================================

-- 2. ADMIN & AUDIT LOGGING

-- ============================================



CREATE TABLE admin (

    admin_id    VARCHAR(36) PRIMARY KEY DEFAULT gen_random_uuid()::VARCHAR,

    first_name  VARCHAR(100) NOT NULL,

    last_name   VARCHAR(100) NOT NULL,

    email       VARCHAR(150) UNIQUE NOT NULL,

    password    VARCHAR(255) NOT NULL,

    role        VARCHAR(30) NOT NULL DEFAULT 'admin'

        CHECK (role IN ('admin','reception_staff','branch_manager','compliance','executive','content_manager'))

);



CREATE TABLE approval_log (

    approval_log_id  VARCHAR(36) PRIMARY KEY DEFAULT gen_random_uuid()::VARCHAR,

    admin_id         VARCHAR(36) NOT NULL REFERENCES admin(admin_id) ON DELETE CASCADE,

    entity_type      VARCHAR(50) NOT NULL,   -- e.g. 'DIETITIAN', 'BRANCH'

    entity_id        VARCHAR(36) NOT NULL,

    action           VARCHAR(50) NOT NULL,   -- e.g. 'APPROVE', 'REJECT'

    comments         TEXT,

    action_date      TIMESTAMP NOT NULL DEFAULT NOW()

);



-- ============================================

-- 3. DIETITIAN PRACTICE

-- ============================================



CREATE TABLE dietitian (

    dietitian_id          VARCHAR(36) PRIMARY KEY DEFAULT gen_random_uuid()::VARCHAR,

    branch_id             VARCHAR(36) NOT NULL REFERENCES branch(branch_id) ON DELETE CASCADE,

    first_name            VARCHAR(100) NOT NULL,

    last_name             VARCHAR(100) NOT NULL,

    email                 VARCHAR(150) UNIQUE NOT NULL,

    password              VARCHAR(255) NOT NULL,

    email_verified       BOOLEAN NOT NULL DEFAULT TRUE,

    stytch_user_id       VARCHAR(80),

    registration_number   VARCHAR(50) UNIQUE NOT NULL,

    specialisation        VARCHAR(150),

    status                VARCHAR(20) NOT NULL DEFAULT 'PENDING'

        CHECK (status IN ('PENDING','APPROVED','REJECTED','SUSPENDED'))

);



-- ============================================

-- 4. LOOKUP: LIFE STAGE / POPULATION GROUP

-- ============================================

-- Generic, extensible tag for which population group a client falls

-- into beyond a fixed diagnosis (child, elderly, athlete, etc.)



CREATE TABLE dietitian_document (
    document_id    VARCHAR(36) PRIMARY KEY DEFAULT gen_random_uuid()::VARCHAR,
    dietitian_id   VARCHAR(36) NOT NULL REFERENCES dietitian(dietitian_id) ON DELETE CASCADE,
    branch_id      VARCHAR(36) NOT NULL REFERENCES branch(branch_id) ON DELETE RESTRICT,
    file_name      VARCHAR(255) NOT NULL,
    content_type   VARCHAR(100) NOT NULL,
    file_data      BYTEA NOT NULL,
    uploaded_at    TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_dietitian_document_dietitian ON dietitian_document(dietitian_id);
CREATE INDEX idx_dietitian_document_branch ON dietitian_document(branch_id);

CREATE TABLE life_stage (

    life_stage_id  VARCHAR(36) PRIMARY KEY DEFAULT gen_random_uuid()::VARCHAR,

    name           VARCHAR(50) NOT NULL UNIQUE

);



-- ============================================

-- 5. CLIENT / PATIENT PROFILE

-- ============================================



CREATE TABLE client (

    client_id            VARCHAR(36) PRIMARY KEY DEFAULT gen_random_uuid()::VARCHAR,

    dietitian_id         VARCHAR(36) REFERENCES dietitian(dietitian_id) ON DELETE SET NULL,

    life_stage_id        VARCHAR(36) REFERENCES life_stage(life_stage_id) ON DELETE SET NULL,

    name                 VARCHAR(150) NOT NULL,

    email                VARCHAR(150) UNIQUE NOT NULL,

    password              VARCHAR(255) NOT NULL,

    email_verified       BOOLEAN NOT NULL DEFAULT TRUE,

    stytch_user_id       VARCHAR(80),

    id_number            VARCHAR(30) UNIQUE NOT NULL,

    phone                VARCHAR(16),   -- normalized +27; nullable for existing patients

    date_of_birth        DATE NOT NULL,

    gender               VARCHAR(20) NOT NULL CHECK (gender IN ('male','female','other')),

    phone_number         VARCHAR(30),

    consent_accepted     BOOLEAN NOT NULL DEFAULT FALSE,

    consent_at           TIMESTAMP,

    consent_ip           VARCHAR(45),

    privacy_notice_acknowledged BOOLEAN NOT NULL DEFAULT FALSE,

    consent_location     VARCHAR(150),

    consent_date         DATE,

    consent_signatory_name VARCHAR(150),

    consent_signature    VARCHAR(150),

    height               NUMERIC(5,2),   -- cm

    activity_level       VARCHAR(30),

    dietary_preferences  TEXT,

    status               VARCHAR(20) NOT NULL DEFAULT 'ACTIVE'

        CHECK (status IN ('ACTIVE','INACTIVE','SUSPENDED'))

);



-- ============================================

-- FR-1.3: immutable evidence of patient registration privacy consent.
-- Timestamp and IP are supplied by the API, not the browser.
CREATE TABLE client_registration_consent (
    client_id VARCHAR(36) PRIMARY KEY REFERENCES client(client_id) ON DELETE RESTRICT,
    privacy_notice_version VARCHAR(40) NOT NULL,
    consented_at TIMESTAMPTZ NOT NULL,
    ip_address VARCHAR(45) NOT NULL,
    registration_mode VARCHAR(12) NOT NULL DEFAULT 'SELF' CHECK (registration_mode IN ('SELF','ASSISTED')),
    registered_by_staff_id VARCHAR(36)
);

-- 6. PREGNANCY & LACTATION TRACKING

-- ============================================

-- Time-bound states with their own clinical fields, not a permanent

-- attribute on client. A client can move in/out over time.



CREATE TABLE pregnancy_profile (

    pregnancy_id             VARCHAR(36) PRIMARY KEY DEFAULT gen_random_uuid()::VARCHAR,

    client_id                VARCHAR(36) NOT NULL REFERENCES client(client_id) ON DELETE CASCADE,

    conception_date          DATE,

    due_date                 DATE,

    pre_pregnancy_weight_kg  NUMERIC(5,2),

    gestational_diabetes     BOOLEAN NOT NULL DEFAULT FALSE,

    multiple_gestation       BOOLEAN NOT NULL DEFAULT FALSE,

    is_active                BOOLEAN NOT NULL DEFAULT TRUE,

    notes                    TEXT

);



CREATE TABLE lactation_profile (

    lactation_id  VARCHAR(36) PRIMARY KEY DEFAULT gen_random_uuid()::VARCHAR,

    client_id     VARCHAR(36) NOT NULL REFERENCES client(client_id) ON DELETE CASCADE,

    start_date    DATE NOT NULL,

    end_date      DATE,

    exclusive     BOOLEAN NOT NULL DEFAULT TRUE,

    notes         TEXT,

    CHECK (end_date IS NULL OR end_date >= start_date)

);



-- ============================================

-- 7. CLINICAL HISTORY & ALLERGEN MANAGEMENT

-- ============================================



CREATE TABLE medical_condition (

    condition_id  VARCHAR(36) PRIMARY KEY DEFAULT gen_random_uuid()::VARCHAR,

    name          VARCHAR(100) NOT NULL UNIQUE,

    category      VARCHAR(50),   -- METABOLIC, CARDIOVASCULAR, RENAL, GASTROINTESTINAL, ENDOCRINE, etc.

    icd_code      VARCHAR(20)

);



CREATE TABLE client_medical_condition (

    client_id        VARCHAR(36) NOT NULL REFERENCES client(client_id) ON DELETE CASCADE,

    condition_id     VARCHAR(36) NOT NULL REFERENCES medical_condition(condition_id) ON DELETE RESTRICT,

    diagnosed_date   DATE,

    severity         VARCHAR(20) DEFAULT 'MODERATE'

        CHECK (severity IN ('MILD','MODERATE','SEVERE')),

    notes            TEXT,

    PRIMARY KEY (client_id, condition_id)

);



CREATE TABLE allergen (

    allergen_id  VARCHAR(36) PRIMARY KEY DEFAULT gen_random_uuid()::VARCHAR,

    name         VARCHAR(100) NOT NULL UNIQUE

);



CREATE TABLE client_allergy (

    client_id     VARCHAR(36) NOT NULL REFERENCES client(client_id) ON DELETE CASCADE,

    allergen_id   VARCHAR(36) NOT NULL REFERENCES allergen(allergen_id) ON DELETE RESTRICT,

    severity      VARCHAR(30) DEFAULT 'MODERATE'

        CHECK (severity IN ('MILD','MODERATE','SEVERE','ANAPHYLACTIC')),

    PRIMARY KEY (client_id, allergen_id)

);



-- ============================================

-- 8. CLINICAL METRICS / LAB TRACKING

-- ============================================

-- Generic time-series log so any measurable metric (blood glucose,

-- HbA1c, blood pressure, cholesterol...) can be tracked without

-- adding a new column per condition.



CREATE TABLE metric_type (

    metric_type_id  VARCHAR(36) PRIMARY KEY DEFAULT gen_random_uuid()::VARCHAR,

    name            VARCHAR(100) NOT NULL UNIQUE,  -- BLOOD_GLUCOSE_FASTING, HBA1C, BLOOD_PRESSURE_SYSTOLIC...

    unit            VARCHAR(20) NOT NULL           -- mg/dL, %, mmHg...

);



CREATE TABLE client_metric_log (

    metric_log_id   VARCHAR(36) PRIMARY KEY DEFAULT gen_random_uuid()::VARCHAR,

    client_id       VARCHAR(36) NOT NULL REFERENCES client(client_id) ON DELETE CASCADE,

    metric_type_id  VARCHAR(36) NOT NULL REFERENCES metric_type(metric_type_id) ON DELETE RESTRICT,

    recorded_at     TIMESTAMP NOT NULL DEFAULT NOW(),

    value           NUMERIC(8,2) NOT NULL,

    notes           TEXT

);



-- ============================================

-- 9. APPOINTMENTS & GOAL / PROGRESS TRACKING

-- ============================================



CREATE TABLE appointment (

    appointment_id  VARCHAR(36) PRIMARY KEY DEFAULT gen_random_uuid()::VARCHAR,

    client_id       VARCHAR(36) NOT NULL REFERENCES client(client_id) ON DELETE CASCADE,

    dietitian_id    VARCHAR(36) NOT NULL REFERENCES dietitian(dietitian_id) ON DELETE CASCADE,

    date_time       TIMESTAMP NOT NULL,

    duration        INTEGER NOT NULL,   -- minutes

    status          VARCHAR(20) NOT NULL DEFAULT 'PENDING'

        CHECK (status IN ('PENDING','CONFIRMED','REJECTED','SCHEDULED','COMPLETED','CANCELLED','NO_SHOW')),

    notes           TEXT

);



CREATE TABLE nutrition_goal (

    goal_id        VARCHAR(36) PRIMARY KEY DEFAULT gen_random_uuid()::VARCHAR,

    client_id      VARCHAR(36) NOT NULL REFERENCES client(client_id) ON DELETE CASCADE,

    goal_type      VARCHAR(100) NOT NULL,

    current_value  NUMERIC(6,2),

    target_value   NUMERIC(6,2),

    target_date    DATE

);



CREATE TABLE progress_log (

    progress_log_id  VARCHAR(36) PRIMARY KEY DEFAULT gen_random_uuid()::VARCHAR,

    client_id        VARCHAR(36) NOT NULL REFERENCES client(client_id) ON DELETE CASCADE,

    log_date         DATE NOT NULL,

   

    -- Body Changes

    weight NUMERIC(5,2),          -- kg (HealthKit: HKQuantityTypeIdentifierBodyMass)

    body_fat_pct NUMERIC(4,2),    -- %  (HealthKit: HKQuantityTypeIdentifierBodyFatPercentage)

    waist_cm NUMERIC(5,2),        -- cm (HealthKit: HKQuantityTypeIdentifierWaistCircumference)



    -- Energy Balance & Habits

    calories_consumed INTEGER,     -- kcal (HealthKit: HKQuantityTypeIdentifierDietaryEnergyConsumed)

    calories_burned INTEGER,       -- kcal (HealthKit: HKQuantityTypeIdentifierActiveEnergyBurned)

    water_ml INTEGER,              -- ml   (HealthKit: HKQuantityTypeIdentifierDietaryWater)

    steps INTEGER,                 -- count(HealthKit: HKQuantityTypeIdentifierStepCount)



    -- Macronutrients (Grams)

    protein_g NUMERIC(5,1),        -- g (HealthKit: HKQuantityTypeIdentifierDietaryProtein)

    carbs_g NUMERIC(5,1),          -- g (HealthKit: HKQuantityTypeIdentifierDietaryCarbohydrates)

    fat_g NUMERIC(5,1),            -- g (HealthKit: HKQuantityTypeIdentifierDietaryFatTotal)

    fiber_g NUMERIC(4,1),          -- g (HealthKit: HKQuantityTypeIdentifierDietaryFiber)

    sugar_g NUMERIC(4,1),          -- g (HealthKit: HKQuantityTypeIdentifierDietarySugar)



    -- Lifestyle & Recovery

    sleep_minutes INTEGER,         -- min (HealthKit: HKCategoryTypeIdentifierSleepAnalysis)

    resting_heart_rate INTEGER,    -- bpm (HealthKit: HKQuantityTypeIdentifierRestingHeartRate)

    notes            TEXT,



    CONSTRAINT unique_client_date_log UNIQUE (client_id, log_date)

);

CREATE TABLE client_medical_document (
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

CREATE TABLE meal_log (
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

CREATE INDEX idx_client_medical_document_client ON client_medical_document(client_id);
CREATE INDEX idx_meal_log_client_date ON meal_log(client_id, log_date);



-- ============================================

-- 10. FOOD ITEMS, RECIPES & ALLERGEN MAPPING

-- ============================================



CREATE TABLE food_item (

    food_item_id    VARCHAR(36) PRIMARY KEY DEFAULT gen_random_uuid()::VARCHAR,

    name            VARCHAR(150) NOT NULL,

    calories        NUMERIC(6,2) NOT NULL,

    protein         NUMERIC(6,2) DEFAULT 0,

    carbs           NUMERIC(6,2) DEFAULT 0,

    fat             NUMERIC(6,2) DEFAULT 0,

    fiber_g         NUMERIC(6,2) DEFAULT 0,

    sugar_g         NUMERIC(6,2) DEFAULT 0,

    sodium_mg       NUMERIC(6,2) DEFAULT 0,

    potassium_mg    NUMERIC(6,2) DEFAULT 0,

    saturated_fat   NUMERIC(6,2) DEFAULT 0,

    glycemic_index  INTEGER   -- useful for diabetic meal planning

);



CREATE TABLE food_allergen (

    food_item_id  VARCHAR(36) NOT NULL REFERENCES food_item(food_item_id) ON DELETE CASCADE,

    allergen_id   VARCHAR(36) NOT NULL REFERENCES allergen(allergen_id) ON DELETE RESTRICT,

    PRIMARY KEY (food_item_id, allergen_id)

);



CREATE TABLE recipe (

    recipe_id      VARCHAR(36) PRIMARY KEY DEFAULT gen_random_uuid()::VARCHAR,

    name           VARCHAR(150) NOT NULL,

    instructions   TEXT NOT NULL,

    prep_time_min  INTEGER

);



CREATE TABLE recipe_ingredient (

    recipe_id     VARCHAR(36) NOT NULL REFERENCES recipe(recipe_id) ON DELETE CASCADE,

    food_item_id  VARCHAR(36) NOT NULL REFERENCES food_item(food_item_id) ON DELETE RESTRICT,

    amount_g      NUMERIC(6,2) NOT NULL,

    PRIMARY KEY (recipe_id, food_item_id)

);



-- ============================================

-- 11. DIET TYPE (clinical / lifestyle diet templates)

-- ============================================

-- Lets a meal plan be tagged with the clinical diet it follows, e.g.

-- DIABETIC, RENAL, LOW_SODIUM, GLUTEN_FREE, PRENATAL.



CREATE TABLE diet_type (

    diet_type_id  VARCHAR(36) PRIMARY KEY DEFAULT gen_random_uuid()::VARCHAR,

    name          VARCHAR(50) NOT NULL UNIQUE,

    description   TEXT

);



-- ============================================

-- 12. MEAL PLANNING & STRUCTURED ROTATION

-- ============================================



CREATE TABLE meal_plan (

    meal_plan_id     VARCHAR(36) PRIMARY KEY DEFAULT gen_random_uuid()::VARCHAR,

    client_id        VARCHAR(36) NOT NULL REFERENCES client(client_id) ON DELETE CASCADE,

    dietitian_id     VARCHAR(36) NOT NULL REFERENCES dietitian(dietitian_id) ON DELETE CASCADE,

    diet_type_id     VARCHAR(36) REFERENCES diet_type(diet_type_id) ON DELETE SET NULL,

    target_calories  INTEGER,

    start_date       DATE NOT NULL,

    end_date         DATE,

    CHECK (end_date IS NULL OR end_date >= start_date)

);



CREATE TABLE meal_plan_day (

    meal_plan_day_id  VARCHAR(36) PRIMARY KEY DEFAULT gen_random_uuid()::VARCHAR,

    meal_plan_id      VARCHAR(36) NOT NULL REFERENCES meal_plan(meal_plan_id) ON DELETE CASCADE,

    day_number        INTEGER NOT NULL,   -- e.g. Day 1 to Day 7

    notes             TEXT,

    UNIQUE (meal_plan_id, day_number)

);



CREATE TABLE meal_plan_item (

    meal_plan_item_id  VARCHAR(36) PRIMARY KEY DEFAULT gen_random_uuid()::VARCHAR,

    meal_plan_day_id   VARCHAR(36) NOT NULL REFERENCES meal_plan_day(meal_plan_day_id) ON DELETE CASCADE,

    food_item_id       VARCHAR(36) REFERENCES food_item(food_item_id) ON DELETE RESTRICT,

    recipe_id          VARCHAR(36) REFERENCES recipe(recipe_id) ON DELETE SET NULL,

    meal_type          VARCHAR(20) NOT NULL

        CHECK (meal_type IN ('BREAKFAST','LUNCH','DINNER','SNACK')),

    portion            NUMERIC(6,2) NOT NULL,   -- grams or serving multiplier

    CHECK (food_item_id IS NOT NULL OR recipe_id IS NOT NULL)

);



-- ============================================

-- 13. AI ENGINE & HUMAN-IN-THE-LOOP WORKFLOW

-- ============================================



CREATE TABLE ai_model_log (

    model_log_id       VARCHAR(36) PRIMARY KEY DEFAULT gen_random_uuid()::VARCHAR,

    model_version      VARCHAR(50) NOT NULL,

    prompt_tokens      INTEGER,

    completion_tokens  INTEGER,

    created_at         TIMESTAMP DEFAULT NOW()

);



CREATE TABLE ai_recommendation (

    recommendation_id    VARCHAR(36) PRIMARY KEY DEFAULT gen_random_uuid()::VARCHAR,

    client_id            VARCHAR(36) NOT NULL REFERENCES client(client_id) ON DELETE CASCADE,

    dietitian_id         VARCHAR(36) REFERENCES dietitian(dietitian_id) ON DELETE SET NULL,

    model_log_id         VARCHAR(36) REFERENCES ai_model_log(model_log_id) ON DELETE SET NULL,

    generated_plan_id    VARCHAR(36) REFERENCES meal_plan(meal_plan_id) ON DELETE SET NULL,

    recommendation_text  TEXT NOT NULL,

    client_feedback      TEXT,

    status               VARCHAR(20) NOT NULL DEFAULT 'PENDING_REVIEW'

        CHECK (status IN ('PENDING_REVIEW','APPROVED','MODIFIED','REJECTED')),

    generated_date        TIMESTAMP NOT NULL DEFAULT NOW()

);



-- ============================================

-- 14. INDEXES FOR PERFORMANCE

-- ============================================



CREATE INDEX idx_branch_business ON branch(business_id);

CREATE INDEX idx_dietitian_branch ON dietitian(branch_id);

CREATE INDEX idx_client_dietitian ON client(dietitian_id);

CREATE INDEX idx_client_life_stage ON client(life_stage_id);

CREATE INDEX idx_pregnancy_client ON pregnancy_profile(client_id);

CREATE INDEX idx_lactation_client ON lactation_profile(client_id);

CREATE INDEX idx_appointment_client ON appointment(client_id);

CREATE INDEX idx_appointment_dietitian ON appointment(dietitian_id);

CREATE INDEX idx_nutrition_goal_client ON nutrition_goal(client_id);

CREATE INDEX idx_progress_log_client ON progress_log(client_id);

CREATE INDEX idx_client_metric_client ON client_metric_log(client_id);

CREATE INDEX idx_client_metric_type ON client_metric_log(metric_type_id);

CREATE INDEX idx_meal_plan_client ON meal_plan(client_id);

CREATE INDEX idx_meal_plan_dietitian ON meal_plan(dietitian_id);

CREATE INDEX idx_meal_plan_diet_type ON meal_plan(diet_type_id);

CREATE INDEX idx_meal_plan_day_plan ON meal_plan_day(meal_plan_id);

CREATE INDEX idx_meal_plan_item_day ON meal_plan_item(meal_plan_day_id);

CREATE INDEX idx_ai_recommendation_client ON ai_recommendation(client_id);

CREATE INDEX idx_ai_recommendation_dietitian ON ai_recommendation(dietitian_id);

CREATE INDEX idx_client_allergy_client ON client_allergy(client_id);

CREATE INDEX idx_client_medical_client ON client_medical_condition(client_id);



-- ============================================

-- 15. SEED DATA: common life stages, conditions, diet types, metrics

-- ============================================



INSERT INTO life_stage (name) VALUES

    ('INFANT'), ('CHILD'), ('ADOLESCENT'), ('ADULT'),

    ('PREGNANT'), ('LACTATING'), ('ELDERLY'), ('ATHLETE');



INSERT INTO medical_condition (name, category) VALUES

    ('Type 1 Diabetes', 'METABOLIC'),

    ('Type 2 Diabetes', 'METABOLIC'),

    ('Gestational Diabetes', 'METABOLIC'),

    ('Hypertension', 'CARDIOVASCULAR'),

    ('Chronic Kidney Disease', 'RENAL'),

    ('Celiac Disease', 'GASTROINTESTINAL'),

    ('Irritable Bowel Syndrome', 'GASTROINTESTINAL'),

    ('Hypothyroidism', 'ENDOCRINE'),

    ('Obesity', 'METABOLIC'),

    ('Anemia', 'HEMATOLOGIC');



INSERT INTO diet_type (name, description) VALUES

    ('DIABETIC', 'Controlled carbohydrate / glycemic-index diet'),

    ('RENAL', 'Restricted sodium, potassium, and phosphorus'),

    ('LOW_SODIUM', 'Reduced sodium for cardiovascular conditions'),

    ('GLUTEN_FREE', 'Excludes gluten-containing grains'),

    ('PRENATAL', 'Increased folate, iron, and calcium for pregnancy'),

    ('LACTATION', 'Increased calories and hydration for breastfeeding'),

    ('HIGH_PROTEIN', 'Elevated protein for athletes or recovery');



INSERT INTO metric_type (name, unit) VALUES

    ('BLOOD_GLUCOSE_FASTING', 'mg/dL'),

    ('BLOOD_GLUCOSE_POSTPRANDIAL', 'mg/dL'),

    ('HBA1C', '%'),

    ('BLOOD_PRESSURE_SYSTOLIC', 'mmHg'),

    ('BLOOD_PRESSURE_DIASTOLIC', 'mmHg'),

    ('LDL_CHOLESTEROL', 'mg/dL'),

    ('HDL_CHOLESTEROL', 'mg/dL'),

    ('TRIGLYCERIDES', 'mg/dL'); 
	
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

-- Security milestone 02: staff roles and access event audit.
-- Kept in sync with migrations/008_staff_roles_and_access_audit.sql for NEW installs.
CREATE TABLE IF NOT EXISTS staff_account (
    staff_id VARCHAR(36) PRIMARY KEY,
    full_name VARCHAR(200) NOT NULL,
    email VARCHAR(150) NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    role VARCHAR(32) NOT NULL CHECK (role IN (
        'reception', 'branch_manager', 'compliance_officer', 'executive', 'content_manager'
    )),
    branch_id VARCHAR(36) REFERENCES branch(branch_id) ON DELETE RESTRICT,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT staff_branch_required CHECK (
        role NOT IN ('reception', 'branch_manager') OR branch_id IS NOT NULL
    )
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_staff_email_lower ON staff_account (LOWER(email));
CREATE INDEX IF NOT EXISTS idx_staff_branch ON staff_account (branch_id);

CREATE TABLE IF NOT EXISTS access_audit_event (
    event_id VARCHAR(36) PRIMARY KEY,
    actor_id VARCHAR(36),
    actor_role VARCHAR(32) NOT NULL,
    http_method VARCHAR(10) NOT NULL,
    resource_path TEXT NOT NULL,
    status_code SMALLINT NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_access_audit_time ON access_audit_event (occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_access_audit_actor ON access_audit_event (actor_role, actor_id);


-- Onboarding: 011_registration_welcome_outbox.sql
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


-- Onboarding: 012_registration_uploads.sql
-- FR-1.6: uploaded portrait kept separately from medical documents.
CREATE TABLE IF NOT EXISTS client_profile_photo (
    client_id VARCHAR(36) PRIMARY KEY REFERENCES client(client_id) ON DELETE CASCADE,
    file_name VARCHAR(120) NOT NULL,
    content_type VARCHAR(30) NOT NULL,
    file_data BYTEA NOT NULL,
    uploaded_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);


-- Onboarding: 013_client_qr_checkin.sql
-- FR-1.7: store only SHA256 of random check-in credential; never ID numbers.
CREATE TABLE IF NOT EXISTS client_checkin_credential (
    client_id VARCHAR(36) PRIMARY KEY REFERENCES client(client_id) ON DELETE CASCADE,
    token_hash VARCHAR(64) UNIQUE NOT NULL,
    rotated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL DEFAULT (NOW() + INTERVAL '10 minutes')
);
CREATE TABLE IF NOT EXISTS client_checkin_event (
    checkin_id VARCHAR(36) PRIMARY KEY,
    client_id VARCHAR(36) NOT NULL REFERENCES client(client_id) ON DELETE RESTRICT,
    staff_id VARCHAR(36) NOT NULL REFERENCES staff_account(staff_id) ON DELETE RESTRICT,
    branch_id VARCHAR(36) NOT NULL REFERENCES branch(branch_id) ON DELETE RESTRICT,
    checked_in_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_client_checkin_event_client ON client_checkin_event(client_id, checked_in_at DESC);

ALTER TABLE client_registration_consent ADD CONSTRAINT fk_registration_staff FOREIGN KEY (registered_by_staff_id) REFERENCES staff_account(staff_id) ON DELETE SET NULL;

-- User support tickets and conversations
CREATE TABLE IF NOT EXISTS support_ticket (
    ticket_id VARCHAR(36) PRIMARY KEY,
    owner_role VARCHAR(32) NOT NULL,
    owner_id VARCHAR(36) NOT NULL,
    contact_email VARCHAR(150),
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

CREATE INDEX IF NOT EXISTS idx_support_contact_time ON support_ticket(contact_email, created_at);

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
    metadata JSON NOT NULL DEFAULT '{}',
    accessed_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_ehr_note_client ON ehr_note(client_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_nutrition_plan_client ON nutrition_plan_version(client_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_client_attachment_client ON client_attachment(client_id, uploaded_at DESC);
CREATE INDEX IF NOT EXISTS idx_client_access_audit_client ON client_access_audit(client_id, accessed_at DESC);
