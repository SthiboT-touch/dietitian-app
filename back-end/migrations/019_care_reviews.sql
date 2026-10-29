-- Additive clinical review history; existing accounts and consultations remain unchanged.
CREATE TABLE IF NOT EXISTS care_review (
    review_id VARCHAR(36) PRIMARY KEY,
    client_id VARCHAR(36) NOT NULL REFERENCES client(client_id) ON DELETE CASCADE,
    dietitian_id VARCHAR(36) NOT NULL REFERENCES dietitian(dietitian_id),
    appointment_id VARCHAR(36) NOT NULL REFERENCES appointment(appointment_id),
    review_summary TEXT NOT NULL,
    monitoring_plan TEXT NOT NULL,
    decision VARCHAR(20) NOT NULL CHECK (decision IN ('CONTINUE_PLAN', 'ADJUST_PLAN', 'FOLLOW_UP')),
    next_review_date DATE,
    reviewed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_care_review_client_date ON care_review(client_id, reviewed_at DESC);
CREATE INDEX IF NOT EXISTS idx_care_review_dietitian ON care_review(dietitian_id);
