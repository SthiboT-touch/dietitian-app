# Resend email verification

The signup flow emails a six-digit one-time password (OTP) before creating a client or dietitian account. It sends mail through the Resend Email API. The code is verified by the FastAPI backend, and the OTP and API key are never sent to the browser.

## Configure Resend

1. Create an API key in the Resend dashboard.
2. Verify a sending domain in Resend, then choose a sender address on that domain.
3. Add the following to the project-root `.env` file:

```text
RESEND_API_KEY=re_your_api_key
RESEND_FROM_EMAIL=NutriCare <noreply@your-verified-domain.com>
```

4. Restart the API.

The backend sends a `POST` request to Resend's `/emails` endpoint using the API key as a Bearer token. Set `RESEND_FROM_EMAIL` to an address authorized for your Resend account. See the [Resend Email API](https://resend.com/features/email-api) for the request format and sender examples.

Keep the API key private and do not commit `.env`. OTPs expire after five minutes, allow five attempts, and can be resent once per minute. OTP challenge state is held in API process memory, so use a single API worker unless challenge storage is moved to shared storage.

If the Resend key or sender address is missing, the API blocks registration and explains that email verification needs to be configured.

The existing migration `back-end/migrations/011_stytch_email_verification.sql` adds `email_verified` and `stytch_user_id` columns used by the account tables. Resend does not require a Stytch user ID; the column stays empty for Resend-verified accounts.
