ALTER TABLE nutrition_goal ADD COLUMN IF NOT EXISTS appointment_id VARCHAR(36) REFERENCES appointment(appointment_id);
ALTER TABLE client_checkin_credential ADD COLUMN IF NOT EXISTS appointment_id VARCHAR(36) REFERENCES appointment(appointment_id);
ALTER TABLE client_checkin_event ADD COLUMN IF NOT EXISTS appointment_id VARCHAR(36) REFERENCES appointment(appointment_id);
CREATE INDEX IF NOT EXISTS nutrition_goal_appointment_idx ON nutrition_goal(appointment_id);
CREATE INDEX IF NOT EXISTS client_checkin_event_appointment_idx ON client_checkin_event(appointment_id);
