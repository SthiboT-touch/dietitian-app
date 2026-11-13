-- Additive care workflow; compatible with the existing appointment fields.
ALTER TABLE appointment
    ADD COLUMN IF NOT EXISTS appointment_type VARCHAR(20)
    NOT NULL DEFAULT 'IN_PERSON';

ALTER TABLE appointment
    ADD COLUMN IF NOT EXISTS meeting_link TEXT;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'appointment_type_check'
          AND conrelid = 'appointment'::regclass
    ) THEN
        ALTER TABLE appointment
            ADD CONSTRAINT appointment_type_check
            CHECK (appointment_type IN ('IN_PERSON', 'VIRTUAL'));
    END IF;
END
$$;

ALTER TABLE appointment ADD COLUMN IF NOT EXISTS branch_id VARCHAR(50);
ALTER TABLE appointment ADD COLUMN IF NOT EXISTS consultation_type VARCHAR(20) NOT NULL DEFAULT 'INITIAL';
CREATE TABLE IF NOT EXISTS client_care_event (
    event_id VARCHAR(50) PRIMARY KEY,
    client_id VARCHAR(50) NOT NULL REFERENCES client(client_id),
    kind VARCHAR(30) NOT NULL,
    author_id VARCHAR(50) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    payload JSONB NOT NULL
);
CREATE INDEX IF NOT EXISTS client_care_event_client_idx ON client_care_event(client_id, created_at);

ALTER TABLE nutrition_goal ADD COLUMN IF NOT EXISTS appointment_id VARCHAR(36) REFERENCES appointment(appointment_id);
ALTER TABLE client_checkin_credential ADD COLUMN IF NOT EXISTS appointment_id VARCHAR(36) REFERENCES appointment(appointment_id);
ALTER TABLE client_checkin_event ADD COLUMN IF NOT EXISTS appointment_id VARCHAR(36) REFERENCES appointment(appointment_id);
CREATE INDEX IF NOT EXISTS nutrition_goal_appointment_idx ON nutrition_goal(appointment_id);
CREATE INDEX IF NOT EXISTS client_checkin_event_appointment_idx ON client_checkin_event(appointment_id);
