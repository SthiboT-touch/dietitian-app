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
