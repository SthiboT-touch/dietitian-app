"""Desktop/mobile workflow UI checks against synthetic API responses only."""
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / "qa" / "artifacts"
ARTIFACTS.mkdir(exist_ok=True)


with sync_playwright() as playwright:
    browser = playwright.chromium.launch(channel="chrome", headless=True)
    for width in (1440, 390):
        page = browser.new_page(viewport={"width": width, "height": 960})
        errors, posts, events = [], [], []
        appointments = []
        google_status = {"configured": True, "connected": True, "mode": "calendar"}
        virtual_links = {}
        progress = [{"log_date": "2026-11-02", "weight_kg": 70, "sleep_hours": 8}]
        page.on("pageerror", lambda error: errors.append(str(error)))

        def route(request_route):
            request = request_route.request
            path = request.url.split("nutricare.test")[-1].split("?")[0]
            if path.startswith("/static/"):
                file = ROOT / "front-end" / path.removeprefix("/static/")
                request_route.fulfill(path=str(file))
                return
            if not path.startswith("/api/") and path != "/health":
                if request.url.startswith("http://nutricare.test"):
                    request_route.fulfill(path=str(ROOT / "front-end" / "index.html"))
                else:
                    request_route.abort()
                return
            result = []
            if request.method == "POST":
                body = request.post_data_json
                posts.append((path, body))
                kind = {"history": "HISTORY", "recommendations": "RECOMMENDATION", "progress-reviews": "PROGRESS_REVIEW"}.get(path.rsplit("/", 1)[-1])
                if kind:
                    payload = dict(body)
                    if kind == "PROGRESS_REVIEW":
                        payload["snapshot"] = dict(progress[0])
                    events.append({"event_id": str(len(events)), "kind": kind, "payload": payload, "created_at": "2026-11-02T10:00:00Z"})
                result = {"message": "Saved"}
                if path.endswith('/complete'):
                    appointment_id = path.split('/')[-2]
                    next(a for a in appointments if a['appointment_id'] == appointment_id)['status'] = 'COMPLETED'
                if path.endswith('/checkin-code'):
                    result = {"qr_svg": '<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20"><rect width="20" height="20"/></svg>'}
                if path == '/api/v1/ai/generate-plan':
                    result = {"recommendation": {"recommendation_id": "rec-test", "generated_plan": ["Reviewed draft"], "appointment_id": body['appointment_id']}}
                if path.endswith('/meeting'):
                    virtual_links[path] = {"status": "READY", "meeting_url": "https://meet.google.com/abc-defg-hij"}
                    result = virtual_links[path]
                if path.endswith('/google/disconnect'):
                    google_status['connected'] = False
            elif path.endswith("/care"):
                result = events
            elif path == "/api/v1/goals":
                result = [body for posted_path, body in posts if posted_path == "/api/v1/goals"]
            elif path == "/api/v1/appointments":
                result = appointments
            elif path == '/api/v1/appointments/calendar':
                result = appointments
            elif path == '/api/v1/integrations/google':
                if request.method == 'PATCH':
                    google_status['mode'] = request.post_data_json['mode']
                result = google_status
            elif path.endswith('/meeting'):
                result = virtual_links.get(path, {"status": "NOT_CREATED"})
            elif path == '/api/v1/clients':
                result = [{"id": "c", "name": "Sample Patient"}]
            elif path == '/api/v1/recipes':
                result = [{"recipe_id": "r", "title": "Reviewed recipe", "ingredients": ["rice"]}]
            elif path == '/api/v1/meal-plans/approved':
                result = [{"plan_id": "plan-test", "status": "APPROVED", "plan": {"appointment_id": "visit-a", "days": 1, "schedule": [{"day": 1, "candidate_recipe": {"title": "Reviewed recipe"}}]}}]
            elif path.endswith("/progress"):
                result = progress
            elif path.endswith("/profile"):
                result = {"allergies": [], "conditions": [], "metrics": [], "progress": progress}
            elif path == "/api/v1/dietitians":
                result = [{"id": "d1", "full_name": "Dietitian One", "branch_id": "b1", "branch_name": "Central"},
                          {"id": "d2", "full_name": "Dietitian Two", "branch_id": "b2", "branch_name": "North"}]
            elif path == "/health":
                result = {"database": "in_memory"}
            elif path.endswith("setup-status"):
                result = {"available": False}
            request_route.fulfill(json=result)

        page.route("**/*", route)
        page.goto("http://nutricare.test/")
        page.wait_for_function("typeof mountCarePanel === 'function'")
        page.evaluate("""() => {
            currentUser = {id:'c', type:'client', full_name:'Sample Patient'};
            sessionStorage.setItem(clientTokenKey,'synthetic-patient-token');
            authScreen.hidden = true; workspace.hidden = false;
        }""")
        page.evaluate("showWorkspace(currentUser, 'client-settings')")
        views = page.locator('.side-nav .nav-item:visible').evaluate_all('(items) => items.map(item => item.dataset.view)')
        assert views == ['overview', 'client-appointments', 'client-progress', 'client-goals', 'ai-workspace', 'client-settings'], views
        menu_labels = page.locator('.side-nav .nav-item:visible').evaluate_all('(items) => items.map(item => item.textContent.replace(item.querySelector(".nav-glyph").textContent, "").trim())')
        assert menu_labels == ['Dashboard', 'Appointments', 'Progress', 'Goals', 'Nutrition Coach', 'Settings'], menu_labels
        expect(page.locator('[data-go="my-profile"]')).to_be_visible()
        expect(page.locator('[data-go="support"]')).to_be_visible()
        page.locator('.side-nav [data-view="overview"]').click()
        expect(page.locator('[data-go="client-checkin"]')).to_be_visible()
        expect(page.locator('[data-go="health-allergies"]')).to_be_visible()
        expect(page.locator('[data-go="client-recommendations"]')).to_be_visible()
        page.evaluate("renderClientAppointments('c','book')")
        page.locator("#appointmentBranch").select_option("b1")
        assert page.locator('#appointmentDietitian option[value="d2"]').is_disabled()
        page.locator("#appointmentDietitian").select_option("d1")
        page.locator("#consultationType").select_option("FOLLOW_UP")
        page.locator("#appointmentDate").fill("2027-01-15T10:00")
        page.screenshot(path=str(ARTIFACTS / f"booking-{width}.png"), full_page=True)
        page.locator('#appointmentForm button[type="submit"]').click()
        expect(page.locator("#appointmentForm")).to_have_count(0)
        booking = next(body for path, body in posts if path == "/api/v1/appointments")
        assert booking["branch_id"] == "b1" and booking["consultation_type"] == "FOLLOW_UP"
        page.evaluate("renderClientHealth('c','conditions')")
        expect(page.locator("#clientHealthForm")).to_have_count(0)
        expect(page.locator("#conditionCode")).to_have_count(0)
        expect(page.locator("#medicalDocumentForm")).to_be_visible()
        page.locator("#care-medications").fill("Synthetic supplement history")
        page.locator("#care-concerns").fill('<script>alert("xss")</script>')
        page.locator("[data-history] button").click()
        expect(page.locator(".care-workflow .appointment-note")).to_contain_text("Last history update:")
        expect(page.locator(".care-workflow")).to_have_count(1)
        expect(page.locator("#care-medications")).to_have_value("Synthetic supplement history")
        appointments[:] = [{"appointment_id": "visit-a", "client_id": "c", "dietitian_id": "d1", "status": "CONFIRMED", "appointment_date": "2020-01-15T10:00:00"}]
        page.evaluate("""async () => {
            currentUser = {id:'d1',type:'dietitian'};
            sessionStorage.removeItem(clientTokenKey);
            sessionStorage.setItem(dietitianTokenKey,'synthetic-clinician-token');
            renderClientRecord('c'); await loadClientProfile('c');
        }""")
        expect(page.locator(".care-history")).to_contain_text('Synthetic supplement history')
        expect(page.locator('[data-recommendation] button')).to_be_disabled()
        page.locator('[data-complete-consultation="visit-a"]').click()
        expect(page.locator('[data-recommendation] button')).to_be_enabled()
        expect(page.locator('[data-care-appointment]')).to_have_value('visit-a')
        expect(page.locator("#conditionForm")).to_be_visible()
        page.locator('#conditionForm input[name="condition_name"]').fill("Asthma")
        page.locator('#conditionForm input[name="icd_code"]').fill("J45")
        page.locator('#conditionForm button').click()
        page.wait_for_function("!!document.querySelector('.care-workflow')")
        assert any(path.endswith('/medical-conditions') and body['condition_name'] == 'Asthma' for path, body in posts)
        assert page.locator(".care-workflow script").count() == 0
        page.locator('[data-progress-review] textarea').fill("Reviewed and approved")
        page.locator('[data-progress-review] button').click()
        expect(page.locator(".care-progress")).to_contain_text("APPROVED")
        page.locator('[data-recommendation] textarea').fill("Follow your reviewed plan")
        page.locator('[data-recommendation] button').click()
        expect(page.locator(".care-workflow")).to_contain_text("Follow your reviewed plan")
        page.locator('[data-care-goal] input[name="target_metric"]').fill("Water (ml)")
        page.locator('[data-care-goal] input[name="target_value"]').fill("2000")
        page.locator('[data-care-goal] button').click()
        page.wait_for_function("document.querySelectorAll('.care-workflow').length === 1 && !document.querySelector('[data-care-goal] button').disabled")
        assert any(path == "/api/v1/goals" and body["client_id"] == "c" for path, body in posts)
        assert all(body.get('appointment_id') == 'visit-a' for path, body in posts if path == '/api/v1/goals' or path.endswith('/care/recommendations') or path.endswith('/progress-reviews'))
        page.evaluate("renderMealPlans()")
        expect(page.locator('#mealDraftForm select[name="appointment_id"]')).to_have_value('visit-a')
        page.locator('#mealDraftForm input[name="diet_type"]').fill('Balanced')
        page.locator('#mealDraftForm input[name="life_stage"]').fill('adult')
        page.locator('#mealDraftForm input[name="allergies"]').fill('none')
        page.locator('#mealDraftForm input[name="conditions"]').fill('none')
        page.locator('#mealDraftForm input[name="recipe_id"]').check()
        page.locator('#mealDraftForm button[type="submit"]').click()
        expect(page.locator('[data-message]')).to_contain_text('Draft saved')
        assert any(path.endswith('/meal-plans/drafts') and body['appointment_id'] == 'visit-a' for path, body in posts)
        page.evaluate("""async () => { workspaceContent.innerHTML = '<div id="aiWorkspacePanel"></div>'; await renderAIStudio('c'); }""")
        expect(page.locator('#aiForm select[name="appointment_id"]')).to_have_value('visit-a')
        page.locator('#dietaryGoal').fill('Balanced meals')
        page.locator('#aiForm button[type="submit"]').click()
        expect(page.locator('#planResult')).to_contain_text('Reviewed draft')
        assert any(path.endswith('/ai/generate-plan') and body['appointment_id'] == 'visit-a' for path, body in posts)
        page.evaluate("renderClientGoals('c')")
        expect(page.locator(".goal-list")).to_contain_text("Water (ml)")
        expect(page.locator(".goal-list")).to_contain_text("2000")
        expect(page.locator("#clientGoalForm")).to_have_count(0)
        expect(page.locator("#workspaceContent input, #workspaceContent select, #workspaceContent textarea")).to_have_count(0)
        page.evaluate("renderClientMealPlan('c')")
        expect(page.locator('.meal-summary')).to_contain_text('Reviewed recipe')
        page.evaluate("""async () => { renderClientRecord('c'); await loadClientProfile('c'); }""")
        page.screenshot(path=str(ARTIFACTS / f"care-{width}.png"), full_page=True)
        page.evaluate("""async () => {
            currentUser = {id:'c',type:'client'};
            await renderClientProgress('c');
        }""")
        expect(page.locator(".care-progress")).to_contain_text("APPROVED")
        progress[0]["weight_kg"] = 71
        page.evaluate("renderClientProgress('c')")
        expect(page.locator(".care-progress")).to_contain_text("PENDING REVIEW")
        for status in (None, "PENDING", "CANCELLED", "REJECTED"):
            appointments[:] = [] if status is None else [{"appointment_date": "2099-01-15T10:00:00", "status": status}]
            page.evaluate("renderClientCheckin('c')")
            expect(page.locator("#generateCheckinQR")).to_have_count(0)
            expect(page.locator('[data-go="client-appointments"]')).to_be_visible()
        appointments[:] = [{"appointment_id": "future-visit", "appointment_date": "2099-01-15T10:00:00", "status": "CONFIRMED"}]
        page.evaluate("renderClientCheckin('c')")
        page.locator("#generateCheckinQR").click()
        expect(page.locator("#clientQRDisplay img")).to_be_visible()
        assert any(path.endswith('/checkin-code') and body['appointment_id'] == 'future-visit' for path, body in posts)
        page.evaluate("showWorkspace({id:'d1',type:'dietitian',full_name:'Demo Dietitian'}, 'dietitian-settings')")
        doctor_views = page.locator('.side-nav .nav-item:visible').evaluate_all('(items) => items.map(item => item.dataset.view)')
        assert doctor_views == ['overview', 'appointment-requests', 'reviews', 'clients', 'support', 'dietitian-settings'], doctor_views
        expect(page.locator('[data-google-mode]')).to_be_visible()
        page.locator('[data-google-mode] select').select_option('meet')
        page.locator('[data-google-mode] button').click()
        expect(page.locator('[data-google-message]')).to_contain_text('Meeting preference saved')
        assert google_status['mode'] == 'meet'
        appointments[:] = [{"appointment_id": "virtual-a", "client_id": "c", "dietitian_id": "d1", "consultation_type": "VIRTUAL", "status": "CONFIRMED", "appointment_date": (datetime.now(timezone.utc) + timedelta(minutes=20)).isoformat(), "client_name": "Sample Patient"}]
        page.evaluate('renderAppointmentRequests()')
        expect(page.locator('[data-create-meeting]').first).to_be_visible()
        page.locator('[data-create-meeting]').first.click()
        expect(page.get_by_role('link', name='Join Google Meet').first).to_have_attribute('href', 'https://meet.google.com/abc-defg-hij')
        page.evaluate("showWorkspace({id:'c',type:'client',full_name:'Sample Patient'}, 'client-appointments')")
        expect(page.get_by_role('link', name='Join Google Meet')).to_be_visible()
        expect(page.locator('[data-create-meeting]')).to_have_count(0)
        appointments[0]['status'] = 'CANCELLED'
        page.evaluate("renderClientAppointments('c')")
        expect(page.get_by_role('link', name='Join Google Meet')).to_have_count(0)
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1"), "Horizontal page overflow"
        assert not errors, errors
        print(f"PASS: booking, history, clinician review, recommendations, goals, edited-progress review, XSS escaping at {width}px")
        page.close()
    browser.close()
