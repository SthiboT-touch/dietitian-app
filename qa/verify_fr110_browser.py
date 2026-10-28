"""FR-1.6/1.10 browser acceptance: upload+draft, desktop and mobile."""

from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1] / "front-end"
html = (ROOT / "index.html").read_text()
js = (ROOT / "app.js").read_text()
css = (ROOT / "styles.css").read_text() + "\n" + (ROOT / "vibrant-theme.css").read_text()

with sync_playwright() as p:
    browser = p.chromium.launch(
        headless=True, executable_path="/usr/bin/chromium", args=["--no-sandbox"]
    )
    for width in (1280, 375):
        page = browser.new_page(viewport={"width": width, "height": 820})
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.set_content(html, wait_until="domcontentloaded")
        page.add_style_tag(content=css)
        page.evaluate("""() => {
          const mem = new Map();
          const storage = {getItem:k=>mem.get(k)||null,setItem:(k,v)=>mem.set(k,String(v)),removeItem:k=>mem.delete(k)};
          Object.defineProperty(window,'sessionStorage',{configurable:true,value:storage});
          Object.defineProperty(window,'localStorage',{configurable:true,value:storage});
          window.__registration=[];
          window.fetch=async(url,opts={}) => {
            if (url.includes('/auth/register/')) {
              window.__registration.push(JSON.parse(opts.body));
              return {ok:true,status:200,json:async()=>({user:{id:'patient-test',type:'client'},message:'ok'})};
            }
            if(url.includes('/auth/login')) return {ok:true,status:200,json:async()=>({access_token:'test-token',user:{id:'patient-test',type:'client',full_name:'Sample Client'}})};
            if(url.includes('/admin/setup-status')) return {ok:true,status:200,json:async()=>({available:false})};
            return {ok:true,status:200,json:async()=>([])};
          };
        }""")
        page.add_script_tag(content=js)
        page.locator("#signupTab").click()
        page.locator('input[name="role"][value="client"]').check()
        page.locator("#signupFirstName").fill("Sam")
        page.locator("#signupLastName").fill("Tester")
        page.locator("#signupEmail").fill("sam@example.test")
        page.locator("#signupSaveDraft").click()
        assert "saved" in page.locator("#signupDraftMessage").inner_text().lower()
        saved = page.evaluate('localStorage.getItem("nutricare-patient-onboarding-draft-v1")')
        assert "password" not in saved and "id_number" not in saved
        page.locator("#signupFirstName").fill("Changed")
        page.locator("#signupRestoreDraft").click()
        assert page.locator("#signupFirstName").input_value() == "Sam"
        page.locator("#patientSignupNext").click()
        page.locator("#idNumber").fill("9005140012345")
        page.locator("#signupPhone").fill("082 123 4567")
        page.locator("#gender").select_option("other")
        page.locator("#dateOfBirth").fill("1990-05-14")
        assert page.locator("#signupPhoto").is_visible()
        page.locator("#signupDocument").set_input_files(
            {"name": "intake.pdf", "mimeType": "application/pdf", "buffer": b"%PDF-1.4\n%%EOF"}
        )
        page.locator("#patientSignupNext").click()
        page.locator("#signupPassword").fill("testingpassword123")
        page.locator("#signupConfirmPassword").fill("testingpassword123")
        page.locator("#signupConsentToCare").check()
        page.locator("#signupSubmit").click()
        page.wait_for_timeout(250)
        payloads = page.evaluate("window.__registration")
        assert len(payloads) == 1, (payloads, errors)
        assert payloads[0]["initial_document"]["filename"] == "intake.pdf"
        assert payloads[0]["initial_document"]["data_base64"]
        assert payloads[0]["profile_photo"] is None
        assert (
            page.evaluate('localStorage.getItem("nutricare-patient-onboarding-draft-v1")') is None
        )
        assert not errors, errors
        page.close()
        print(f"PASS: FR-1.6 optional upload and FR-1.10 explicit save/restore on {width}px")
    browser.close()
