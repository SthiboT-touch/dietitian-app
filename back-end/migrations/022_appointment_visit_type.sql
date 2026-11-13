ALTER TABLE appointment
    ADD COLUMN IF NOT EXISTS visit_type VARCHAR(20) NOT NULL DEFAULT 'initial_visit'
    CHECK (visit_type IN ('initial_visit', 'follow_up'));
