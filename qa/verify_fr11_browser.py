"""FR-1.1 frontend smoke test. Run with Playwright and Chromium installed.
No real server or database is contacted; network responses are mocked.
"""
from pathlib import Path
from playwright.sync_api import sync_playwright
import json
ROOT=Path(__file__).resolve().parents[1] / 'front-end'
html=(ROOT/'index.html').read_text()
js=(ROOT/'app.js').read_text()
css=(ROOT/'styles.css').read_text()+'\n'+(ROOT/'vibrant-theme.css').read_text()
with sync_playwright() as p:
 browser=p.chromium.launch(headless=True,executable_path='/usr/bin/chromium',args=['--no-sandbox'])
 for width in [1280,375]:
  page=browser.new_page(viewport={'width':width,'height':800})
  errors=[]
  page.on('pageerror',lambda e: errors.append(str(e)))
  page.set_content(html,wait_until='domcontentloaded')
  page.add_style_tag(content=css)
  page.evaluate('''() => {
      const bag = new Map();
      Object.defineProperty(window, 'sessionStorage', {configurable:true,value:{getItem:k=>bag.get(k)||null,setItem:(k,v)=>bag.set(k,String(v)),removeItem:k=>bag.delete(k),clear:()=>bag.clear()}});
      window.__requests=[];
      window.fetch=async(url, opts={})=>{
       if (url.includes('/auth/register/')) {window.__requests.push(JSON.parse(opts.body)); return {ok:true,status:200,json:async()=>({user:{type:'client',id:'cli_demo'},message:'Registered'})};}
       if (url.includes('/auth/login')) return {ok:true,status:200,json:async()=>({access_token:'testtoken',user:{id:'cli_demo',type:'client',full_name:'Taylor Example',email:'taylor@example.test'}})};
       if (url.includes('/admin/setup-status')) return {ok:true,status:200,json:async()=>({available:false})};
       return {ok:true,status:200,json:async()=>([])};
      };
    }''')
  page.add_script_tag(content=js)
  page.locator('#signupTab').click()
  page.locator('input[name=role][value=client]').check()
  assert page.locator('#patientSignupStepLabel').inner_text().startswith('Step 1')
  assert page.locator('[data-signup-step="2"]').is_hidden()
  assert page.locator('[data-signup-step="3"]').is_hidden()
  page.locator('#patientSignupNext').click()
  assert page.locator('#patientSignupStepLabel').inner_text().startswith('Step 1'), 'should block empty step 1'
  page.locator('#signupFirstName').fill('Taylor')
  page.locator('#signupLastName').fill('Example')
  page.locator('#signupEmail').fill('taylor@example.test')
  page.locator('#patientSignupNext').click()
  assert page.locator('#patientSignupStepLabel').inner_text().startswith('Step 2')
  assert page.locator('#signupFirstName').is_hidden()
  page.locator('#patientSignupBack').click()
  assert page.locator('#signupFirstName').input_value()=='Taylor'
  page.locator('#patientSignupNext').click()
  page.locator('#idNumber').fill('9005140012345')
  page.locator('#signupPhone').fill('082 123 4567')
  page.locator('#gender').select_option('other')
  page.locator('#dateOfBirth').fill('1990-05-14')
  page.locator('#patientSignupNext').click()
  assert page.locator('#patientSignupStepLabel').inner_text().startswith('Step 3')
  assert page.locator('#signupSubmit').is_visible()
  assert page.locator('#patientSignupNext').is_hidden()
  if width==1280 and __import__('os').environ.get('NUTRICARE_SAVE_FR11_SCREENSHOT') == '1':
   page.screenshot(path=str(ROOT.parent / 'qa' / 'fr11_preview.png'),full_page=True)
  page.locator('#signupPassword').fill('testpassword123')
  page.locator('#signupConfirmPassword').fill('testpassword123')
  page.locator('#signupConsentToCare').check()
  page.locator('#signupSubmit').click()
  page.wait_for_timeout(600)
  seen=page.evaluate('window.__requests')
  assert len(seen)==1, f'registration not submitted at {width}; seen {seen}, errors {errors}'
  assert seen[-1]['first_name']=='Taylor'
  assert seen[-1]['id_number']=='9005140012345'
  assert seen[-1]['password']=='testpassword123'
  assert 'role' not in seen[-1] and 'confirm_password' not in seen[-1]
  assert not errors,errors
  print(f'PASS: patient onboarding {width}px, validation, back navigation, request payload, no JS errors')
  page.close()
 page=browser.new_page()
 page.set_content(html,wait_until='domcontentloaded')
 page.add_style_tag(content=css)
 page.evaluate("""() => {const bag = new Map(); Object.defineProperty(window, 'sessionStorage', {configurable:true,value:{getItem:k=>bag.get(k)||null,setItem:(k,v)=>bag.set(k,String(v)),removeItem:k=>bag.delete(k)}});window.fetch = async () => ({ok:true,status:200,json:async()=>({available:false})})}""")
 page.add_script_tag(content=js)
 page.locator('#signupTab').click()
 assert page.locator('#patientSignupProgress').is_hidden()
 assert page.locator('#signupFirstName').is_visible()
 assert page.locator('#licenseNumber').is_visible()
 assert page.locator('#signupPassword').is_visible()
 assert page.locator('#clientFields').is_hidden()
 assert page.locator('#signupSubmit').is_visible()
 print('PASS: dietitian registration remains a one-page form')
 page.close()
 browser.close()
