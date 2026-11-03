CREATE TABLE IF NOT EXISTS dietitian_google_connection (
    dietitian_id VARCHAR(36) PRIMARY KEY REFERENCES dietitian(dietitian_id),
    encrypted_tokens TEXT NOT NULL,
    meeting_mode VARCHAR(16) NOT NULL DEFAULT 'calendar' CHECK (meeting_mode IN ('calendar','meet')),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS appointment_meeting (
    appointment_id VARCHAR(36) PRIMARY KEY REFERENCES appointment(appointment_id),
    dietitian_id VARCHAR(36) NOT NULL REFERENCES dietitian(dietitian_id),
    meeting_mode VARCHAR(16) NOT NULL CHECK (meeting_mode IN ('calendar','meet')),
    meeting_url TEXT,
    google_event_id TEXT,
    google_space_name TEXT,
    status VARCHAR(24) NOT NULL,
    message VARCHAR(300),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
