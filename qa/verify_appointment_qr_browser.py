"""Offline desktop/mobile UI checks for appointment-gated patient QR access."""
from datetime import datetime, timedelta
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
html = (ROOT / "front-end/index.html").read_text()
css = (ROOT / "front-end/styles.css").read_text() + "\n" + (ROOT / "front-end/vibrant-theme.css").read_text()
js = (ROOT / "front-end/app.js").read_text()
support = (ROOT / "front-end/support.js").read_text()

MOCK = '''() => {
 const bag = new Map();
 Object.defineProperty(window,'sessionStorage', {configurable:true,value:{
   getItem:k=>bag.get(k)||null,setItem:(k,v)=>bag.set(k,String(v)),removeItem:k=>bag.delete(k),clear:()=>bag.clear()
 }});
 window.mockAppointmentStatus='PENDING';
 window.mockAppointmentCalls=[];
 const tomorrow = new Date(Date.now()+3*24*3600*1000).toISOString();
 window.fetch=async(url,opts={})=>{
   const s=String(url); let data={};
   if(s==='/health') data={status:'online',database:'online'};
   else if(s.includes('/admin/setup-status'))data={available:false};
   else if(s.includes('/api/v1/appointments?'))data=[{appointment_id:'appt_123', client_id:'client-test',dietitian_id:'dietitian-test',appointment_date:tomorrow,status:window.mockAppointmentStatus}];
   else if(s==='/api/v1/dietitians')data=[{id:'dietitian-test',full_name:'Dietitian Test'}];
   else if(s.endsWith('/checkin-appointments'))data=window.mockAppointmentStatus==='CONFIRMED'?[{appointment_id:'appt_123',dietitian_id:'dietitian-test',appointment_date:tomorrow,status:'CONFIRMED'}]:[];
   else if(s.endsWith('/checkin-code')){
     window.mockAppointmentCalls.push(JSON.parse(opts.body));
     data={appointment_id:'appt_123',qr_svg:'<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"></svg>'};
   }
   else if(s.includes('/api/v1/clients?'))data=[];
   return {ok:true,status:200,headers:new Headers(),json:async()=>data};
 };
}'''
with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=True, executable_path="/usr/bin/chromium", args=["--no-sandbox", "--disable-dev-shm-usage"])
    for width, height, name in ((1440, 900, "desktop"), (390, 844, "mobile")):
        page = browser.new_page(viewport={"width": width, "height": height})
        errors = []
        page.on("pageerror", lambda err: errors.append(str(err)))
        page.set_content(html, wait_until="domcontentloaded")
        page.add_style_tag(content=css)
        page.evaluate(MOCK)
        page.add_script_tag(content=support)
        page.add_script_tag(content=js)
        page.evaluate("showWorkspace({type:'client',id:'client-test',full_name:'Kamogelo Example',email:'person@example.test'})")
        page.wait_for_timeout(100)
        assert page.locator('[data-account-view="client-checkin"]').count() == 0
        page.evaluate('renderClientAppointments("client-test", "upcoming")')
        page.wait_for_timeout(140)
        assert page.locator('[data-checkin-appointment]').count() == 0
        assert 'after the dietitian confirms' in page.locator('#workspaceContent').inner_text()
        page.evaluate("window.mockAppointmentStatus='CONFIRMED'")
        page.evaluate('renderClientAppointments("client-test", "upcoming")')
        page.wait_for_timeout(140)
        assert page.locator('[data-checkin-appointment]').count() == 1
        page.locator('[data-checkin-appointment]').click()
        page.wait_for_timeout(140)
        assert page.locator('#generateCheckinQR').is_visible()
        assert page.locator('#qrAppointment').input_value() == 'appt_123'
        page.locator('#generateCheckinQR').click()
        page.wait_for_timeout(140)
        assert page.locator('#clientQRDisplay img').is_visible()
        assert page.evaluate('window.mockAppointmentCalls[0].appointment_id') == 'appt_123'
        page.screenshot(path=str(ROOT / 'qa' / f'appointment_checkin_{name}.png'), full_page=True)
        page.evaluate("window.mockAppointmentStatus='CANCELLED'")
        page.evaluate('renderClientCheckin("client-test", "appt_123")')
        page.wait_for_timeout(150)
        assert 'No confirmed upcoming appointment' in page.locator('#workspaceContent').inner_text()
        assert page.locator('#generateCheckinQR').count() == 0
        assert errors == [], (name, errors)
        print(f'{name}: pending hidden, confirmed QR available, cancelled unavailable, request appointment-bound PASS')
        page.close()
    browser.close()
