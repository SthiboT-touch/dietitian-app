"""Desktop/mobile virtual appointment UI with synthetic API responses only."""
from datetime import datetime, timedelta, timezone
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / "qa/artifacts"
ARTIFACTS.mkdir(exist_ok=True)
FUTURE = datetime.now(timezone(timedelta(hours=2))) + timedelta(days=2)
ROOM = "https://meet.jit.si/NutriCare-" + "a" * 64
MANUAL = "https://meet.google.com/abc-defg-hij"


with sync_playwright() as playwright:
    browser = playwright.chromium.launch(channel="chrome", headless=True)
    for width in (1440, 390):
        page = browser.new_page(viewport={"width": width, "height": 960},
                                timezone_id="Africa/Johannesburg", reduced_motion="reduce")
        errors, requests, external, dialogs = [], [], [], []
        visits = [dict(appointment_id=key, client_id="c", dietitian_id="d",
                       client_name="Synthetic Patient", appointment_date=FUTURE.isoformat(),
                       appointment_type="VIRTUAL", consultation_type="FOLLOW_UP", branch_id="b",
                       status="CONFIRMED" if key == "legacy" else "PENDING", meeting_link=None)
                  for key in ("automatic", "manual", "legacy")]
        visits.append({**visits[0], "appointment_id": "in-person", "appointment_type": "IN_PERSON"})
        page.on("pageerror", lambda error: errors.append(str(error)))
        def dialog_handler(dialog):
            dialogs.append(dialog.type)
            dialog.dismiss()
        page.on("dialog", dialog_handler)

        def handle(route):
            request = route.request
            if not request.url.startswith("http://nutricare.test/"):
                # Existing theme fonts/photos are blocked too, but aren't meeting requests.
                if not request.url.startswith(("https://fonts.googleapis.com/", "https://images.unsplash.com/")):
                    external.append(request.url)
                route.abort()
                return
            path = request.url.split("nutricare.test", 1)[1].split("?", 1)[0]
            if path.startswith("/static/"):
                route.fulfill(path=str(ROOT / "front-end" / path.removeprefix("/static/")))
                return
            if not path.startswith("/api/") and path != "/health":
                route.fulfill(path=str(ROOT / "front-end/index.html"))
                return
            result = []
            if request.method in ("PATCH", "POST"):
                body = request.post_data_json if request.post_data else {}
                requests.append((request.method, path, body))
                if path.startswith("/api/v1/appointments/"):
                    key = path.split("/")[4]
                    visit = next(v for v in visits if v["appointment_id"] == key)
                    if path.endswith("/meeting"):
                        visit["meeting_link"] = visit["meeting_link"] or ROOM + key
                    elif body["action"] == "APPROVED":
                        visit["status"] = "CONFIRMED"
                        visit["meeting_link"] = body.get("meeting_link") or ROOM + key
                    else:
                        visit["status"] = body["action"]
                        visit["meeting_link"] = None
                    result = {"appointment": visit, "meeting_link": visit["meeting_link"]}
            elif path in ("/api/v1/appointments", "/api/v1/appointments/calendar"):
                result = visits
            elif path == "/api/v1/dietitians":
                result = [{"id": "d", "full_name": "Demo Dietitian", "branch_id": "b", "branch_name": "Main Branch"}]
            elif path == "/health":
                result = {"status": "online", "database": "in_memory"}
            elif path.endswith("setup-status"):
                result = {"available": False}
            route.fulfill(json=result)

        page.route("**/*", handle)
        page.goto("http://nutricare.test/")
        page.wait_for_function("typeof appointmentMeetingMarkup === 'function' && typeof showWorkspace === 'function'")
        page.evaluate("""() => {
            currentUser={id:'d', type:'dietitian', full_name:'Demo Dietitian'};
            sessionStorage.setItem(dietitianTokenKey, 'synthetic-doctor');
            showWorkspace(currentUser, 'dietitian-settings');
        }""")
        expect(page.get_by_role("heading", name="Settings.", exact=True)).to_be_visible()
        page.evaluate("date => renderAppointmentRequests(date)", FUTURE.isoformat())
        auto = page.locator('[data-appointment-id="automatic"]')
        expect(auto.locator('[data-meeting-mode]')).to_have_value("manual")
        expect(auto.locator('[data-manual-meeting-link]')).to_be_visible()
        expect(auto.locator('[data-jitsi-note]')).to_be_hidden()
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1"), "Pending meeting options overflow"
        page.screenshot(path=str(ARTIFACTS / f"virtual-pending-{width}.png"), full_page=True)
        auto.locator('[data-meeting-mode]').select_option("jitsi")
        expect(auto.locator('[data-jitsi-note]')).to_be_visible()
        expect(auto.locator('[data-manual-meeting-link]')).to_be_hidden()
        auto.locator('[data-appointment-decision="APPROVED"]').click()
        expect(page.locator('[data-appointment-id="automatic"] [data-join-appointment-meeting]')).to_have_attribute("href", ROOM + "automatic")
        assert requests[-1] == ("PATCH", "/api/v1/appointments/automatic", {"action": "APPROVED"})
        # The selected future calendar date survives approval.
        expect(page.locator('[data-appointment-id="manual"]')).to_be_visible()
        manual = page.locator('[data-appointment-id="manual"]')
        expect(manual.locator('[data-manual-meeting-link]')).to_be_visible()
        manual.locator('[data-manual-meeting-link]').fill("javascript:alert(1)")
        before = len(requests)
        manual.locator('[data-appointment-decision="APPROVED"]').click()
        expect(page.locator('[data-message]')).to_contain_text("valid HTTPS")
        assert len(requests) == before
        manual.locator('[data-manual-meeting-link]').fill(MANUAL)
        manual.locator('[data-appointment-decision="APPROVED"]').click()
        expect(page.locator('[data-appointment-id="manual"] [data-join-appointment-meeting]')).to_have_attribute("href", MANUAL)
        assert requests[-1][2]["meeting_link"] == MANUAL
        page.locator('[data-create-appointment-meeting="legacy"]').click()
        expect(page.locator('[data-appointment-id="legacy"] [data-join-appointment-meeting]')).to_have_attribute("href", ROOM + "legacy")
        expect(page.locator('[data-appointment-id="in-person"] [data-meeting-mode]')).to_have_count(0)
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1"), "Doctor meeting cards overflow"
        page.screenshot(path=str(ARTIFACTS / f"virtual-doctor-{width}.png"), full_page=True)

        page.evaluate("""() => {
            currentUser={id:'c', type:'client', full_name:'Synthetic Patient'};
            sessionStorage.removeItem(dietitianTokenKey);
            sessionStorage.setItem(clientTokenKey,'synthetic-patient');
            showWorkspace(currentUser, 'client-settings');
        }""")
        expect(page.get_by_role("heading", name="Your account.", exact=True)).to_be_visible()
        page.evaluate("renderClientAppointments('c')")
        expect(page.get_by_role("link", name="Join virtual appointment")).to_have_count(3)
        assert page.locator('[data-create-appointment-meeting]').count() == 0
        for link in page.locator('[data-join-appointment-meeting]').all():
            expect(link).to_have_attribute("target", "_blank")
            expect(link).to_have_attribute("rel", "noopener noreferrer")
        page.locator('[data-cancel-appointment="automatic"]').click()
        expect(page.locator(f'a[href="{ROOM}automatic"]')).to_have_count(0)
        # A virtual visit that just started remains in Upcoming for its scheduled day.
        visits[1]["appointment_date"] = (datetime.now(timezone(timedelta(hours=2))) - timedelta(minutes=5)).isoformat()
        page.locator('[data-refresh-appointments]').click()
        expect(page.locator(f'a[href="{MANUAL}"]')).to_be_visible()
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1"), "Patient meeting cards overflow"
        page.screenshot(path=str(ARTIFACTS / f"virtual-patient-{width}.png"), full_page=True)
        page.evaluate("renderClientAppointments('c', 'book')")
        page.locator('#appointmentType').select_option("VIRTUAL")
        expect(page.locator('[data-virtual-booking-note]')).to_be_visible()
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1"), "Horizontal overflow"
        assert not errors, errors
        assert not dialogs, dialogs
        assert not external, external
        print(f"PASS: automatic/manual approval, legacy links, patient join/cancel, ongoing visits, no provider requests at {width}px")
        page.close()
    browser.close()
