-- Apply to DEVELOPMENT PostgreSQL only, after a database backup.
-- Does not alter existing production meal_plan records.
CREATE TABLE IF NOT EXISTS meal_plan_review (
    plan_id TEXT PRIMARY KEY,
    client_id TEXT NOT NULL,
    dietitian_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'PENDING_REVIEW' CHECK (status IN ('PENDING_REVIEW','APPROVED','MODIFIED','REJECTED')),
    draft_json JSONB NOT NULL,
    approved_json JSONB,
    review_note TEXT,
    reviewed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT reviewed_plan_consistency CHECK (
      (status='PENDING_REVIEW' AND reviewed_at IS NULL AND approved_json IS NULL) OR
      (status='REJECTED' AND reviewed_at IS NOT NULL AND approved_json IS NULL) OR
      (status IN ('APPROVED','MODIFIED') AND reviewed_at IS NOT NULL AND approved_json IS NOT NULL)
    )
);
CREATE INDEX IF NOT EXISTS idx_meal_plan_review_client ON meal_plan_review(client_id,status);
CREATE INDEX IF NOT EXISTS idx_meal_plan_review_dietitian ON meal_plan_review(dietitian_id,status);
