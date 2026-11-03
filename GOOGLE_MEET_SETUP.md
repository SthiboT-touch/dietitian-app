# Google Meet and Calendar setup

The integration is implemented, but real meeting creation requires your own
Google OAuth credentials and authorization from each dietitian. No API key or
Google connection is bundled with the app.

## Configure Google Cloud

1. Create/select a Google Cloud project and enable **Google Calendar API** and
   **Google Meet API**.
2. Configure the Google Auth Platform consent screen. For testing, add the
   dietitian's Google email as a test user. Production distribution may require
   Google's verification for the scopes requested.
3. Create an OAuth client of type **Web application**. Add this exact authorized
   redirect URI for local testing:
   `http://127.0.0.1:8001/api/v1/integrations/google/callback`.
   Production must use your HTTPS app origin with the same callback path.
4. Put these server-side variables in your ignored root `.env` file or hosting
   environment, preserving all existing settings:

```dotenv
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
GOOGLE_REDIRECT_URI=http://127.0.0.1:8001/api/v1/integrations/google/callback
GOOGLE_TOKEN_ENCRYPTION_KEY=
```

Generate the encryption key with:

```powershell
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Keep the key stable and backed up securely for PostgreSQL installations. Tokens
cannot be decrypted if the key is lost or replaced. In temporary in-memory mode,
an ephemeral key is generated automatically if this variable is blank; restarting
the server clears the connection. Never put client secrets or tokens in frontend
JavaScript, screenshots, commits, or chat.

Install the updated requirements. Existing PostgreSQL installations must manually
run `python back-end/migrations/apply_019_google_meet.py` after migrations 017 and
018, before starting this version. Fresh databases include the schema. The
deployment pipeline has not been modified.

## Use the integration

1. Restart the API after changing environment variables. Sign in as an approved
   dietitian, open **Settings → Google Meet & Calendar → Connect Google**, and
   authorize both requested permissions.
2. Choose **Calendar appointment with Google Meet** (default), or **Google Meet
   link only**. Existing meetings keep their original format.
3. The patient books a **Virtual consultation**. When the dietitian approves it,
   the app attempts to create the meeting. Failed meeting creation does not undo
   appointment confirmation.
4. A **Join Google Meet** link appears in the patient's Appointments screen and
   the dietitian's appointment calendar. The host may need to admit the patient.
5. For appointments confirmed before connection, the dietitian uses
   **Create / check Google Meet** on the confirmed appointment. Google sometimes
   prepares conference links asynchronously; use the same button to check again.

The Calendar event is created on the connected dietitian's primary calendar with
a generic title and the appointment's time/duration. The app does not upload
medical history or patient email, and does not send Calendar invitations. Patients
join from NutriCare. Calendar creation uses a deterministic event ID so retries
reuse the same event instead of creating duplicates.

Cancellation immediately hides the Join button. The app attempts to delete its
Google Calendar event, or end an active Meet-only conference. An already copied
Meet URL is governed by Google and is not guaranteed to become invalid when an
appointment is cancelled. Failed Google cleanup can be retried by the appointment
dietitian with `DELETE /api/v1/appointments/{appointment_id}/meeting` after local
cancellation. Disconnection revokes the OAuth grant; it does not delete already
created Calendar events.

OAuth state is single-use, expires after ten minutes, and is bound to the
initiating local session. Pending state and existing login sessions are currently
process-local; use one API worker or sticky routing during OAuth. State is cleared
on restart, so restart the connection flow if it was interrupted. Configure any
reverse proxy/access logs to omit callback query strings. The API strips these
parameters from its own response-time access log.

If a Meet-only creation request times out, the app does not automatically repeat
it because Google Meet's space-creation endpoint lacks an idempotency key. Check
the connected Google account before manual recovery. Calendar mode is the default
and supports safe repeated creation/check requests.

## Validation

`python -m pytest -q back-end/tests/test_google_meet.py` tests OAuth state/PKCE,
encrypted storage, role/participant access, token renewal, both Google APIs,
Calendar retries, cancellation, and provider outages using simulated Google
responses. No tests create real meetings. A real-account smoke test is required
after entering your credentials and before production use.

Official references: [Google OAuth web-server flow](https://developers.google.com/identity/protocols/oauth2/web-server),
[Calendar event creation](https://developers.google.com/workspace/calendar/api/v3/reference/events/insert),
[Meet space creation](https://developers.google.com/workspace/meet/api/reference/rest/v2/spaces/create).
