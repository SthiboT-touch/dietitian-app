# Stytch email verification

The app uses Stytch B2C Email OTP to verify client and dietitian email addresses during registration.

1. Create a Stytch B2C project and copy its Project ID and Secret from the Stytch Dashboard.
2. Put them in the project-root `.env` file using the names in `.env.example`:

```text
STYTCH_PROJECT_ID=your-project-id
STYTCH_SECRET=your-secret
STYTCH_ENABLED=1
```

3. Restart the API. New client and dietitian registrations will receive a one-time code by email before they are signed in.
4. Keep the secret only in the backend environment. It is never placed in the browser code.

If the values are blank, the app remains usable in local development and email verification is reported as disabled.

The database migration `back-end/migrations/011_stytch_email_verification.sql` adds `email_verified` and `stytch_user_id` to client and dietitian records. The deployment workflow applies it automatically.
