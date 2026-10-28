"""FR-1.3 patient consent on desktop/mobile with a mocked API."""

from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1] / "front-end"
html = (ROOT / "index.html").read_text()
js = (ROOT / "app.js").read_text()
css = (ROOT / "styles.css").read_text() + "\n" + (ROOT / "vibrant-theme.css").read_text()

with sync_playwright() as playwright:
    browser = playwright.chromium.launch(
        headless=True, executable_path="/usr/bin/chromium", args=["--no-sandbox"]
    )
    for width in (1280, 375):
        page = browser.new_page(viewport={"width": width, "height": 820})
        page_errors = []
        page.on("pageerror", lambda error: page_errors.append(str(error)))
        page.set_content(html, wait_until="domcontentloaded")
        page.add_style_tag(content=css)
        page.evaluate("""() => {
          const cache = new Map();
          Object.defineProperty(window,'sessionStorage',{configurable:true,value:{
            getItem:k=>cache.get(k)||null,setItem:(k,v)=>cache.set(k,String(v)),removeItem:k=>cache.delete(k)
          }});
          window.__registered=[];
          window.fetch=async(url,opts={})=>{
            if(url.includes('/auth/register/')) {
              window.__registered.push(JSON.parse(opts.body));
              return {ok:true,status:200,json:async()=>({user:{id:'cli_test',type:'client'},message:'Registered'})};
            }
            if(url.includes('/auth/login')) return {ok:true,status:200,json:async()=>({access_token:'token',user:{id:'cli_test',type:'client',full_name:'Test User'}})};
            if(url.includes('/admin/setup-status')) return {ok:true,status:200,json:async()=>({available:false})};
            return {ok:true,status:200,json:async()=>([])};
          }
        }""")
        page.add_script_tag(content=js)
        page.locator("#signupTab").click()
        page.locator('input[name="role"][value="client"]').check()
        page.locator("#signupFirstName").fill("Taylor")
        page.locator("#signupLastName").fill("Example")
        page.locator("#signupEmail").fill("test@example.test")
        page.locator("#patientSignupNext").click()
        page.locator("#idNumber").fill("9005140012345")
        page.locator("#signupPhone").fill("082 123 4567")
        page.locator("#gender").select_option("other")
        page.locator("#dateOfBirth").fill("1990-05-14")
        page.locator("#patientSignupNext").click()
        assert page.locator("#clientPrivacyConsent").is_visible()
        assert page.locator("#signupConsentToCare").get_attribute("required") is not None
        page.locator("#signupPassword").fill("testpassword123")
        page.locator("#signupConfirmPassword").fill("testpassword123")
        page.locator("#signupSubmit").click()
        assert (
            page.evaluate("window.__registered.length") == 0
        ), "Registration bypassed unchecked consent"
        page.locator("#registrationPrivacyNotice summary").click()
        assert page.locator(".privacy-notice-body").is_visible()
        if width == 1280:
            page.screenshot(
                path=str(ROOT.parent.parent / "NutriCare_FR13_Preview.png"), full_page=True
            )
        page.locator("#signupConsentToCare").check()
        page.locator("#signupSubmit").click()
        page.wait_for_timeout(450)
        payloads = page.evaluate("window.__registered")
        assert len(payloads) == 1, (width, payloads, page_errors)
        assert payloads[0]["consent_to_care"] is True
        assert payloads[0]["privacy_notice_version"] == "2026-10-28-v1"
        assert not page_errors, page_errors
        page.close()
        print(f"PASS: consent required, privacy notice readable, payload correct at {width}px")
    page = browser.new_page()
    page.set_content(html, wait_until="domcontentloaded")
    page.add_style_tag(content=css)
    page.evaluate("""() => {
      const cache=new Map();Object.defineProperty(window,'sessionStorage',{configurable:true,value:{getItem:k=>cache.get(k)||null,setItem:(k,v)=>cache.set(k,String(v)),removeItem:k=>cache.delete(k)}});
      window.fetch=async()=>({ok:true,status:200,json:async()=>({available:false})});
    }""")
    page.add_script_tag(content=js)
    page.locator("#signupTab").click()
    assert page.locator("#clientPrivacyConsent").is_hidden()
    assert page.locator("#signupConsentToCare").get_attribute("required") is None
    print("PASS: dietitian registration remains unchanged and consent is patient-only")
    browser.close()
