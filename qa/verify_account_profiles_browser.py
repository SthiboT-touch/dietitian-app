"""Headless browser smoke tests: shared profiles, photo crop, security and mobile."""
import io
from pathlib import Path
from PIL import Image
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
html = (ROOT / 'front-end/index.html').read_text()
css = (ROOT / 'front-end/styles.css').read_text() + '\n' + (ROOT / 'front-end/vibrant-theme.css').read_text()
js = (ROOT / 'front-end/app.js').read_text()
support = (ROOT / 'front-end/support.js').read_text()
image = Image.new('RGB', (600, 400), 'purple')
output = io.BytesIO(); image.save(output, format='PNG')
photo = output.getvalue()

mock = r'''() => {
  const storage = new Map();
  Object.defineProperty(window, 'sessionStorage', {configurable:true, value:{getItem:(k)=>storage.get(k)||null,setItem:(k,v)=>storage.set(k,String(v)),removeItem:(k)=>storage.delete(k),clear:()=>storage.clear()}});
  window.photoBlob = null;
  window.prefPayload = null;
  window.savedProfile = null;
  window.passwordRequest = null;
  window.fetch = async(url,options={}) => {
    const path=String(url), method=options.method||'GET';
    const role=window.testRole||'client';
    let status=200, payload=[];
    if(path==='/health') payload={status:'online',database:'in_memory'};
    else if(path==='/api/v1/admin/setup-status') payload={available:false};
    else if(path==='/api/v1/account/photo') {
      if(method==='PUT') {window.photoBlob=options.body.get('file'); payload={has_photo:true};}
      else if(method==='DELETE') {window.photoBlob=null;payload={has_photo:false};}
      else if(window.photoBlob) return {ok:true,status:200,headers:new Headers({'content-type':'image/webp'}),blob:async()=>window.photoBlob,json:async()=>null};
      else {status=404;payload={detail:'No photo'};}
    }
    else if(path==='/api/v1/account/me') {
      if(method==='PUT') {window.savedProfile=JSON.parse(options.body);payload={...window.testProfile,...window.savedProfile};window.testProfile=payload;}
      else payload={...window.testProfile,role,role_label:({client:'Patient',dietitian:'Dietitian',admin:'System Administrator'})[role]||'Staff',has_photo:Boolean(window.photoBlob),preferred_contact:'email',email_notifications:true,appointment_reminders:true};
    }
    else if(path==='/api/v1/account/preferences' && method==='PUT') {window.prefPayload=JSON.parse(options.body);payload={};}
    else if(path==='/api/v1/account/password' && method==='POST') {window.passwordRequest=JSON.parse(options.body);payload={message:'Password changed. Sign in again.'};}
    else if(path==='/api/v1/dietitians') payload=[{id:'d1',full_name:'Dr. Care',status:'APPROVED',branch_name:'Practice A'}];
    else if(path.includes('/clients/') && path.endsWith('/profile')) payload={conditions:[{condition_name:'Example'}],allergies:[],metrics:[],progress:[]};
    else if(path==='/api/v1/appointments') payload=[{appointment_id:'appt1', client_id:'c1', dietitian_id:'d1', status:'CONFIRMED', consultation_type:'VIRTUAL', appointment_date:'2027-01-01T10:00:00'}];
    else if(path==='/api/v1/dietitians/me/approval') payload={status:'APPROVED'};
    else if(path.startsWith('/api/v1/clients?client_id')) payload=[{id:'c1',full_name:'Test Patient'}];
    else if(path==='/api/v1/ai/recommendations/pending') payload=[];
    return {ok:status<400,status,headers:new Headers(),json:async()=>payload,blob:async()=>new Blob([])};
  };
}'''

with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=True, executable_path='/usr/bin/chromium', args=['--no-sandbox','--disable-dev-shm-usage'])
    for role, w, h in [('client',1440,980),('client',390,844),('dietitian',1440,960),('admin',1440,960),('reception',1440,960),('branch_manager',1440,960),('compliance_officer',1440,960),('executive',1440,960),('content_manager',1440,960)]:
        page=browser.new_page(viewport={'width':w,'height':h})
        errors=[]
        page.on('pageerror',lambda error: errors.append(str(error)))
        page.set_content(html,wait_until='domcontentloaded')
        page.add_style_tag(content=css)
        page.evaluate(mock)
        page.evaluate('(role)=>{window.testRole=role;window.testProfile={id:role==="client"?"c1":"user1",role,full_name:"Test Account",email:"test@nutricare.local",phone_number:"0821234567",dietitian_id:"d1",gender:"male",status:"APPROVED"};}',role)
        page.add_script_tag(content=support)
        page.add_script_tag(content=js)
        page.evaluate('(role)=>{const key=role==="client"?"nutrition-practice-client-token":role==="dietitian"?"nutrition-practice-dietitian-token":role==="admin"?"nutrition-practice-admin-token":"nutrition-practice-staff-token";sessionStorage.setItem(key,"example");showWorkspace({id:role==="client"?"c1":"user1",type:role,full_name:"Test Account",email:"test@nutricare.local",gender:"male"},"my-profile")}',role)
        page.locator('#profileHeroAvatar').wait_for(timeout=10000)
        assert page.locator('#accountInfoForm').count()==1
        assert page.locator('#patientAccount').is_visible()
        assert page.locator('#standardProfileChip').is_hidden()
        page.locator('#patientAccountButton').click()
        assert page.locator('#accountMenuFullName').inner_text() == 'Test Account'
        assert page.locator('[data-account-view="account-security"]').is_visible()
        page.locator('#patientAccountButton').click()
        if role=='client':
            assert page.locator('.account-info-grid').count()==1
            assert page.locator('.account-info-grid').inner_text().lower().find('meal plan')>=0
            assert page.locator('.nav-item[data-view="client-settings"]').count()==1
        page.locator('#accountInfoForm [name="full_name"]').fill('Jamie Updated')
        page.locator('#accountInfoForm [name="phone_number"]').fill('+27 821234567')
        page.locator('#accountInfoForm button[type="submit"]').click()
        page.wait_for_function('window.savedProfile?.full_name==="Jamie Updated"')
        assert page.locator('#patientAccountName').inner_text()=='Jamie Updated'
        # Photo input -> visual square crop -> save -> visible avatars -> removal.
        if role in ('client','dietitian','admin'):
            page.locator('#profilePhotoPicker').set_input_files(files={'name':'portrait.png','mimeType':'image/png','buffer':photo})
            page.locator('.account-crop-dialog').wait_for(timeout=6000)
            assert page.locator('.account-crop-dialog canvas').is_visible()
            page.locator('.account-zoom-control input').fill('1.3')
            page.locator('[data-crop-save]').click()
            page.wait_for_function('Boolean(window.photoBlob)')
            page.locator('#profileHeroAvatar.has-profile-photo').wait_for(timeout=8000)
            page.locator('#removeProfilePhoto').click()
            page.wait_for_function('window.photoBlob===null')
            assert not page.locator('#profileHeroAvatar').get_attribute('class').endswith('has-profile-photo')
        page.evaluate('navTo("account-security")')
        page.locator('#accountPreferencesForm').wait_for(timeout=8000)
        page.locator('input[name="appointment_reminders"]').uncheck()
        page.locator('#accountPreferencesForm button[type="submit"]').click()
        page.wait_for_function('window.prefPayload?.appointment_reminders===false')
        page.locator('#accountPasswordForm [name="current_password"]').fill('OldPassword123!')
        page.locator('#accountPasswordForm [name="new_password"]').fill('NewPassword123!')
        page.locator('#accountPasswordForm [name="confirm_password"]').fill('NewPassword123!')
        page.locator('#accountPasswordForm button[type="submit"]').click()
        page.wait_for_function('Boolean(window.passwordRequest)')
        assert page.locator('#authScreen').is_visible()
        assert not errors, (role,w,errors)
        print('Account profile browser passed:',role,'mobile' if w<500 else 'desktop')
        page.close()
    browser.close()
