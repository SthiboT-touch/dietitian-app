# Resend email verification

The signup flow emails a six-digit one-time password (OTP) before creating a client or dietitian account. It sends mail through Resend's official Python SDK. The code is verified by the FastAPI backend, and the OTP and API key are never sent to the browser.

## Configure Resend

1. Create an API key in the Resend dashboard.
2. Verify a sending domain in Resend, then choose a sender address on that domain.
3. Add the following to the project-root `.env` file:

```text
RESEND_API_KEY=re_your_api_key
RESEND_FROM_EMAIL=NutriCare <noreply@your-verified-domain.com>
```

4. Install the dependencies in `back-end/requirements.txt`, then restart the API. Docker deployments should rebuild the API image.

## Configure the production deployment

The local `.env` file is not copied to the production server. In GitHub, open **Settings → Secrets and variables → Actions** and add repository secrets named `RESEND_API_KEY` and `RESEND_FROM_EMAIL`. Use an active Resend sending key and a sender address on a verified domain. The deployment workflow forwards these secrets to Docker Compose and stops before restarting services if either is missing.

The backend loads the API key from `RESEND_API_KEY`, assigns it to the SDK, and sends the message with `resend.Emails.send(...)`. Set `RESEND_FROM_EMAIL` to an address on a sending domain verified in your Resend account. See Resend's [Python SDK guide](https://resend.com/python) for the SDK setup and examples.

Keep the API key private and do not commit `.env`. OTPs expire after five minutes, allow five attempts, and can be resent once per minute. OTP challenge state is held in API process memory, so use a single API worker unless challenge storage is moved to shared storage.

If the Resend key or sender address is missing, the API blocks registration and explains that email verification needs to be configured.

The existing migration `back-end/migrations/011_stytch_email_verification.sql` adds `email_verified` and `stytch_user_id` columns used by the account tables. Resend does not require a Stytch user ID; the column stays empty for Resend-verified accounts.
