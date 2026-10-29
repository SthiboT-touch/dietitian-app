-- Run once on your LOCAL PostgreSQL database after migration 013.
-- Existing QR credentials are deliberately invalidated: old codes were not
-- linked to an appointment, so they must not be usable after this change.
ALTER TABLE client_checkin_credential
    ADD COLUMN IF NOT EXISTS appointment_id VARCHAR(36) REFERENCES appointment(appointment_id) ON DELETE CASCADE;
ALTER TABLE client_checkin_event
    ADD COLUMN IF NOT EXISTS appointment_id VARCHAR(36) REFERENCES appointment(appointment_id) ON DELETE RESTRICT;
CREATE UNIQUE INDEX IF NOT EXISTS uq_client_checkin_event_appointment
    ON client_checkin_event (appointment_id) WHERE appointment_id IS NOT NULL;
DELETE FROM client_checkin_credential WHERE appointment_id IS NULL;
