-- Additive migration: existing appointments remain IN_PERSON, existing data preserved.
ALTER TABLE appointment
    ADD COLUMN IF NOT EXISTS consultation_type VARCHAR(12) NOT NULL DEFAULT 'IN_PERSON';
ALTER TABLE appointment
    ADD COLUMN IF NOT EXISTS virtual_room_id VARCHAR(96);

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='appointment_consultation_type_check') THEN
        ALTER TABLE appointment ADD CONSTRAINT appointment_consultation_type_check
            CHECK (consultation_type IN ('IN_PERSON', 'VIRTUAL'));
    END IF;
END $$;
