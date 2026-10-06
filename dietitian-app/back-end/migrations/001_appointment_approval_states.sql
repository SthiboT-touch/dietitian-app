ALTER TABLE appointment
    DROP CONSTRAINT IF EXISTS appointment_status_check;

ALTER TABLE appointment
    ADD CONSTRAINT appointment_status_check
    CHECK (status IN ('PENDING', 'CONFIRMED', 'REJECTED', 'SCHEDULED', 'COMPLETED', 'CANCELLED', 'NO_SHOW'));

ALTER TABLE appointment
    ALTER COLUMN status SET DEFAULT 'PENDING';
