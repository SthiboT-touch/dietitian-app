"""Browser smoke test for reception-assisted registration and QR check-in menus."""

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
        page = browser.new_page(viewport={"width": width, "height": 900})
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.set_content(html, wait_until="domcontentloaded")
        page.add_style_tag(content=css)
        page.evaluate("""() => {
    const mem = new Map();
    Object.defineProperty(window,'sessionStorage',{configurable:true,value:{getItem:k=>mem.get(k)||null,setItem:(k,v)=>mem.set(k,String(v)),removeItem:k=>mem.delete(k)}});
    Object.defineProperty(window,'localStorage',{configurable:true,value:{getItem:k=>null,setItem:()=>{},removeItem:()=>{}}});
    sessionStorage.setItem('nutrition-practice-session',JSON.stringify({id:'staff-a',type:'reception',full_name:'Test Reception'}));
    sessionStorage.setItem('nutrition-practice-staff-token','secret');
    window.__assisted=[]; window.__checkins=[];
    window.fetch=async(url,opts={}) => {
      if(url.includes('/api/v1/staff/me'))return {ok:true,status:200,json:async()=>({staff_id:'staff-a',full_name:'Test Reception',role:'reception',branch_id:'test-branch',is_active:true})};
      if(url.includes('/auth/register/client/assisted')) {window.__assisted.push(JSON.parse(opts.body));return {ok:true,status:200,json:async()=>({user:{id:'patient-a'},welcome_email:'queued'})};}
      if(url.includes('/reception/check-in')) {window.__checkins.push(JSON.parse(opts.body));return {ok:true,status:201,json:async()=>({client_id:'patient-a'})};}
      if(url.includes('/admin/setup-status'))return {ok:true,status:200,json:async()=>({available:false})};
      return {ok:true,status:200,json:async()=>([])};
    }
  }""")
        page.add_script_tag(content=js)
        page.wait_for_timeout(150)
        assert page.locator('[data-view="reception-onboarding"]').is_visible()
        page.evaluate("loadView('reception-onboarding')")
        page.locator("#assistedFirst").fill("Taylor")
        page.locator("#assistedLast").fill("Sample")
        page.locator("#assistedEmail").fill("taylor@example.test")
        page.locator("#assistedID").fill("9005140012345")
        page.locator("#assistedPhone").fill("0821234567")
        page.locator("#assistedDOB").fill("1990-05-14")
        page.locator("#assistedGender").select_option("other")
        page.locator("#assistedPassword").fill("testpassword123")
        page.locator('#assistedRegistration button[type="submit"]').click()
        assert page.evaluate("window.__assisted.length") == 0, "Missing patient consent allowed"
        page.locator('#assistedRegistration [name="consent_to_care"]').check()
        page.locator('#assistedRegistration button[type="submit"]').click()
        page.wait_for_timeout(100)
        assert page.evaluate("window.__assisted.length") == 1, errors
        assert page.evaluate("window.__assisted[0].consent_to_care") is True
        page.evaluate("loadView('reception-checkin')")
        page.locator("#receptionQRValue").fill(
            "NC1:EXAMPLElongrandomcodethatisnotarealcode123456789"
        )
        page.locator("#receptionCheckinForm button").click()
        page.wait_for_timeout(100)
        assert page.evaluate("window.__checkins.length") == 1, errors
        assert not errors, errors
        print(f"PASS: reception assisted consent and QR menu at {width}px")
        page.close()
    browser.close()
