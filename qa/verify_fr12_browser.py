"""Browser-level FR-1.2 smoke tests with mocked API (no production traffic)."""

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
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.set_content(html, wait_until="domcontentloaded")
        page.add_style_tag(content=css)
        page.evaluate("""() => {
            const bag = new Map();
            Object.defineProperty(window, 'sessionStorage', {configurable:true,value:{
              getItem:k=>bag.get(k)||null,setItem:(k,v)=>bag.set(k,String(v)),removeItem:k=>bag.delete(k)
            }});
            window.__registered=[];
            window.fetch=async(url,opts={})=>{
              if(url.includes('/auth/register/')) {
                window.__registered.push(JSON.parse(opts.body));
                return {ok:true,status:200,json:async()=>({user:{type:'client',id:'cli_fake'},message:'Registered'})};
              }
              if(url.includes('/auth/login')) return {ok:true,status:200,json:async()=>({access_token:'test',user:{id:'cli_fake',type:'client',full_name:'Taylor Example',email:'taylor@example.test'}})};
              if(url.includes('/admin/setup-status')) return {ok:true,status:200,json:async()=>({available:false})};
              return {ok:true,status:200,json:async()=>([])};
            };
        }""")
        page.add_script_tag(content=js)
        page.locator("#signupTab").click()
        page.locator('input[name="role"][value="client"]').check()
        page.locator("#signupFirstName").fill("Taylor")
        page.locator("#signupLastName").fill("Example")
        email = page.locator("#signupEmail")
        email.fill("not-valid")
        assert (
            email.get_attribute("aria-invalid") == "true"
        ), f"email invalid state not rendered on {width}px"
        assert "valid email" in page.locator("#signupEmailHelp").inner_text()
        page.locator("#patientSignupNext").click()
        assert page.locator("#patientSignupStepLabel").inner_text().startswith("Step 1")
        email.fill("Taylor@Example.Test")
        assert email.get_attribute("aria-invalid") == "false"
        page.locator("#patientSignupNext").click()
        assert page.locator("#patientSignupStepLabel").inner_text().startswith("Step 2")

        id_input = page.locator("#idNumber")
        phone = page.locator("#signupPhone")
        dob = page.locator("#dateOfBirth")
        id_input.fill("9005140012346")  # wrong Luhn digit
        assert id_input.get_attribute("aria-invalid") == "true"
        assert "check digit" in page.locator("#idNumberHelp").inner_text()
        phone.fill("123")
        assert phone.get_attribute("aria-invalid") == "true"
        dob.fill("1990-05-14")
        page.locator("#gender").select_option("other")
        page.locator("#patientSignupNext").click()
        assert page.locator("#patientSignupStepLabel").inner_text().startswith("Step 2")
        id_input.fill("9005140012345")
        assert id_input.get_attribute("aria-invalid") == "false"
        phone.fill("+27 82 123 4567")
        assert phone.get_attribute("aria-invalid") == "false"
        dob.fill("2000-05-14")
        assert dob.get_attribute("aria-invalid") == "true"
        dob.fill("1990-05-14")
        assert dob.get_attribute("aria-invalid") == "false"
        page.locator("#patientSignupNext").click()
        assert page.locator("#patientSignupStepLabel").inner_text().startswith("Step 3")
        page.locator("#signupPassword").fill("testpassword123")
        page.locator("#signupConfirmPassword").fill("testpassword123")
        page.locator("#signupConsentToCare").check()
        page.locator("#signupSubmit").click()
        page.wait_for_timeout(450)
        requests = page.evaluate("window.__registered")
        assert len(requests) == 1, (width, requests, errors)
        assert requests[0]["id_number"] == "9005140012345"
        assert requests[0]["phone"] == "+27 82 123 4567"
        assert requests[0]["email"] == "taylor@example.test"
        assert not errors, errors
        print(f"PASS: FR-1.2 inline validation + signup on {width}px")
        page.close()

    page = browser.new_page()
    page.set_content(html, wait_until="domcontentloaded")
    page.add_style_tag(content=css)
    page.evaluate(
        """() => {const bag=new Map();Object.defineProperty(window,'sessionStorage',{configurable:true,value:{getItem:k=>bag.get(k)||null,setItem:(k,v)=>bag.set(k,String(v)),removeItem:k=>bag.delete(k)}});window.fetch=async()=>({ok:true,status:200,json:async()=>({available:false})})} """
    )
    page.add_script_tag(content=js)
    page.locator("#signupTab").click()
    assert page.locator("#licenseNumber").is_visible()
    assert page.locator("#signupPhone").is_hidden()
    assert page.locator("#signupSubmit").is_visible()
    print("PASS: dietitian form unchanged and patient phone field hidden")
    page.close()
    browser.close()
