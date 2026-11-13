# Virtual appointments

Virtual appointments use the existing appointment type and meeting link fields.
Use a meeting link created by the dietitian's own provider account by default.
The app also offers a public Jitsi room, but the live service requires the host
to sign in as a moderator before a patient can join. Initial and follow-up
consultation choices remain available.

## How to use it

1. Patient: open **Appointments → Book Appointment**, select a branch, dietitian,
   consultation type, **Virtual**, and date/time. Send the request.
2. Dietitian: create a meeting using a provider account (for example, Google
   Meet or Zoom). Open **Appointment Requests**, select the appointment's date,
   keep **Use my own meeting link (recommended)** selected, paste the HTTPS
   meeting link, and approve the request.
3. Dietitian: click **Start virtual appointment** to open the provider meeting
   in a new tab.
4. Patient: open **Appointments → Upcoming**, refresh if necessary, and click
   **Join virtual appointment**.
5. Allow camera and microphone on the meeting provider's HTTPS page. The external
   page allows this flow to work when NutriCare itself is running locally or on an
   HTTP origin. It does not add HTTPS to the NutriCare application.
6. For older confirmed virtual appointments without links, the appointment's
   dietitian can click **Create meeting link**. Repeated requests reuse the same
   Jitsi link. The dietitian must sign in to Jitsi as moderator to start that
   room. Existing provider links are retained.
7. Once the consultation is finished, the dietitian marks it completed from the
   patient's care record and continues the existing goals, plans and review flow.

Pending, rejected, cancelled and completed appointments do not expose join links
through the app. Only the appointment's patient and dietitian can read its meeting
endpoint, and only that dietitian can generate a missing link. Cancellation clears
the stored link. It cannot revoke a Jitsi URL someone already copied or end a call
on the external service; the host controls that room on Jitsi.

NutriCare does not send patient names, record IDs, email addresses or clinical
history in generated room URLs, and does not automatically open a provider page.
Participants share audio/video with the provider when they choose to join.

## Public service limits

The meet.jit.si service has usage limits and no availability guarantee. Its
moderator sign-in requirement was confirmed in a live browser check: an
unauthenticated host is held in the lobby and cannot start the meeting. Jitsi is
an optional fallback, not the default. Review its current limits and terms before
using it for clinical appointments. NutriCare does not activate provider billing
or subscribe to a paid service.

- [Jitsi's free service FAQ](https://jitsi.org/user-faq/)
- [Host authentication and joining](https://jitsi.github.io/handbook/docs/user-guide/user-guide-join-jitsi-meeting/)
- [Usage limits and terms](https://jitsi.org/meet-jit-si-terms-of-service/)
- [Provider privacy policy](https://jitsi.org/meet-jit-si-privacy/)

## Deployment and validation

No new database migration, dependency, environment variable, Google Cloud setup,
Docker service or deployment-workflow change is required for these meeting links.
The existing care workflow schema must already be present, including the current
`appointment_type` and `meeting_link` fields. Existing deployment migrations
continue to run as before. Deploy the backend and frontend together.

```bash
python -m pytest -q back-end/tests
python qa/verify_virtual_browser.py
python qa/verify_care_browser.py
```

The tests check appointment approval, access restrictions, idempotent link
generation, cancellation, manual links, and desktop/mobile UI behaviour without
creating real Jitsi meetings. Before using real appointments, perform a two-person
call: host starts the room and signs in, guest joins the same URL, verify both
audio/video directions, then complete the consultation. Automated tests do not
verify real device permissions or the provider's live availability.
