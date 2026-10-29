"""Offline patient navigation tests. No live API, credentials or patient records are used.
Requires playwright and Chromium. Runs at desktop/mobile sizes.
"""
from pathlib import Path
from playwright.sync_api import sync_playwright
ROOT = Path(__file__).resolve().parents[1] / 'front-end'
html=(ROOT/'index.html').read_text()
css=(ROOT/'styles.css').read_text()+'\n'+(ROOT/'vibrant-theme.css').read_text()
js=(ROOT/'app.js').read_text()
support=(ROOT/'support.js').read_text()
mock='''() => {
 const bag = new Map();
 Object.defineProperty(window, 'sessionStorage', {configurable: true, value:{
   getItem:k=>bag.get(k)||null,setItem:(k,v)=>bag.set(k,String(v)),
   removeItem:k=>bag.delete(k), clear:()=>bag.clear()
 }});
 window.fetch=async(url,opts={})=>{
   const s=String(url);
   const data=s.includes('/health')?{status:'online',database:'online'}:
     s.includes('/admin/setup-status')?{available:false}:
     s==='/api/v1/account/me'?{id:'client-test',role:'client',role_label:'Patient',full_name:'Kamogelo Example',email:'test@example.org',gender:'female',has_photo:false}:
     s.includes('/clients/client-test/profile')?{conditions:[],allergies:[],metrics:[],progress:[]}:[];
   const photo=s==='/api/v1/account/photo';
   return {ok:!photo,status:photo?404:200,json:async()=>data,headers:new Headers(),blob:async()=>new Blob([])};
 };
}'''
with sync_playwright() as pw:
 browser=pw.chromium.launch(headless=True, executable_path='/usr/bin/chromium',args=['--no-sandbox','--disable-dev-shm-usage'])
 for width,height,name in [(1440,900,'desktop'),(390,844,'mobile')]:
  page=browser.new_page(viewport={'width':width,'height':height})
  errors=[]
  page.on('pageerror', lambda err: errors.append(str(err)))
  page.set_content(html,wait_until='domcontentloaded')
  page.add_style_tag(content=css)
  page.evaluate(mock)
  page.add_script_tag(content=support)
  page.add_script_tag(content=js)
  page.evaluate("showWorkspace({type:'client',id:'client-test',full_name:'Kamogelo Example',email:'test@example.org',gender:'female'})")
  page.wait_for_timeout(200)
  nav=page.locator('.workspace-sidebar .nav-item:visible')
  names=[el.inner_text().strip() for el in nav.all()]
  items=page.locator('.workspace-sidebar .nav-item:visible')
  names=[x.inner_text().strip().split('\n')[-1].strip() for x in items.all()]
  assert set(names)=={'Dashboard','Appointments','Progress','Goals','AI Coach','Settings'},(name,names)
  visual=page.evaluate("""() => [...document.querySelectorAll('.workspace-sidebar .nav-item')]
    .filter(el=>getComputedStyle(el).display!=='none' && !el.hidden)
    .map(el=>({name:el.innerText.trim().split('\\n').pop().trim(), x:el.getBoundingClientRect().x,y:el.getBoundingClientRect().y}))
    .sort((a,b)=>a.y-b.y || a.x-b.x).map(el=>el.name)""")
  assert visual==['Dashboard','Appointments','Progress','Goals','AI Coach','Settings'],(name,visual)
  # Patient sees meal plans from their care team without editing controls.
  # Settings keeps the meal plan accessible, but removes it from the main sidebar.
  page.locator('[data-view="client-settings"]').click()
  page.wait_for_timeout(150)
  assert page.locator('.patient-care-panel [data-go="client-meal-plan"]').is_visible()
  page.locator('.patient-care-panel [data-go="client-meal-plan"]').click()
  page.wait_for_timeout(150)
  assert 'Created and approved by your dietitian' in page.locator('#workspaceContent').inner_text()
  assert page.locator('#workspaceContent #clientGoalForm').count()==0
  assert page.locator('#patientAccountButton').is_visible()
  assert 'Kamogelo Example' in page.locator('#patientAccountButton').inner_text()
  page.locator('#patientAccountButton').click()
  assert page.locator('#patientAccountPanel').is_visible()
  assert page.locator('#patientAccountButton').get_attribute('aria-expanded')=='true'
  page.keyboard.press('Escape')
  assert not page.locator('#patientAccountPanel').is_visible()
  page.locator('#patientAccountButton').click()
  assert page.locator('[data-account-view="client-settings"]').count()==0
  page.locator('[data-account-view="my-profile"]').click()
  page.locator('.account-hero').wait_for(timeout=8000)
  assert page.locator('#accountInfoForm').is_visible()
  assert page.locator('.account-info-grid').is_visible()
  for destination in ('health-conditions','health-allergies','client-meal-plan'):
   assert page.locator('.account-info-grid [data-go="'+destination+'"]') .is_visible()
  assert not page.locator('#patientAccountPanel').is_visible()
  assert page.locator('[data-view="client-settings"]').is_visible()
  page.wait_for_timeout(350)
  if name=='desktop':
   page.screenshot(path=str(ROOT.parent/'qa'/'patient_navigation_desktop.png'),full_page=True)
  if name=='mobile':
   page.screenshot(path=str(ROOT.parent/'qa'/'patient_navigation_mobile.png'),full_page=True)
  page.locator('#patientAccountButton').click()
  page.locator('[data-account-view="my-profile"]').click()
  page.locator('.account-hero').wait_for(timeout=8000)
  page.locator('#patientAccountButton').click()
  page.locator('#patientAccountSignout').click()
  assert page.locator('#workspace').is_hidden()
  assert errors==[],f'{name}: page errors {errors}'
  print(f'{name}: 6-item Patient nav, avatar profile and care links, signout PASS')
  page.close()
 page=browser.new_page()
 page.set_content(html,wait_until='domcontentloaded');page.add_style_tag(content=css)
 page.evaluate(mock);page.add_script_tag(content=support);page.add_script_tag(content=js)
 page.evaluate("showWorkspace({type:'dietitian',id:'dt-test',full_name:'Dr Test Dietitian',email:'clinician@example.org'})")
 page.wait_for_timeout(250)
 assert page.locator('#patientAccount').is_visible()
 assert page.locator('#standardProfileChip').is_hidden()
 assert not page.locator('[data-view="client-settings"]').is_visible()
 assert page.locator('[data-view="my-profile"]').is_visible()
 print('dietitian: shared account menu and profile navigation PASS')
 page.close();browser.close()
