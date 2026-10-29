"""Check patient care path, clinician review and responsive layouts offline."""
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[1]
html=(ROOT/'front-end/index.html').read_text(encoding='utf-8')
css=(ROOT/'front-end/styles.css').read_text(encoding='utf-8')+(ROOT/'front-end/vibrant-theme.css').read_text(encoding='utf-8')
appjs=(ROOT/'front-end/app.js').read_text(encoding='utf-8')
support=(ROOT/'front-end/support.js').read_text(encoding='utf-8')
mock=r'''() => {
 const bag=new Map();
 Object.defineProperty(window,'sessionStorage',{configurable:true,value:{getItem:k=>bag.get(k)||null,setItem:(k,v)=>bag.set(k,String(v)),removeItem:k=>bag.delete(k),clear:()=>bag.clear()}});
 const past=new Date(Date.now()-3*24*60*60*1000).toISOString();
 window.testAppointments=[{appointment_id:'appt1', client_id:'c1', dietitian_id:'d1', status:'CONFIRMED', appointment_date:past, consultation_type:'VIRTUAL'}];
 window.testReviews=[];
 window.testPosts=[];
 window.fetch=async(url,opts={})=>{
   const path=String(url),method=opts.method||'GET'; let data=[]; let status=200;
   if(path==='/health') data={status:'online',database:'in_memory'};
   else if(path.includes('/admin/setup-status')) data={available:false};
   else if(path==='/api/v1/dietitians')data=[{id:'d1',full_name:'Dr. Test',status:'APPROVED', branch_name:'Demo Branch'}];
   else if(path.startsWith('/api/v1/appointments') && method==='GET')data=window.testAppointments;
   else if(path.startsWith('/api/v1/clients/') && path.endsWith('/profile'))data={conditions:[{condition_name:'Example condition'}],allergies:[],metrics:[],progress:[]};
   else if(path.startsWith('/api/v1/clients/') && path.endsWith('/progress'))data=[{log_date:'2026-10-01',weight_kg:63}];
   else if(path.startsWith('/api/v1/goals'))data=[{target_metric:'Balanced meals per day',target_value:3}];
   else if(path==='/api/v1/meal-plans/approved')data=[{plan_id:'p1',plan:{diet_type:'Practice nutrition plan',schedule:[]}}];
   else if(path.startsWith('/api/v1/care-reviews') && method==='GET')data=window.testReviews;
   else if(path==='/api/v1/care-reviews' && method==='POST'){
     const body=JSON.parse(opts.body);window.testPosts.push(body);
     const review={...body,review_id:'rev1',dietitian_id:'d1',reviewed_at:new Date().toISOString()};
     window.testReviews.unshift(review);data={message:'Saved',review}; status=201;
   }
   else if(path.startsWith('/api/v1/clients?dietitian_id'))data=[{id:'c1',name:'Test Client',status:'ACTIVE'}];
   else if(path.startsWith('/api/v1/clients?client_id'))data=[{id:'c1',name:'Test Client',full_name:'Test Client',gender:'male'}];
   return {ok:status<400,status,headers:new Headers(),json:async()=>data};
 };
}'''

with sync_playwright() as pw:
  browser=pw.chromium.launch(headless=True,executable_path='/usr/bin/chromium',args=['--no-sandbox','--disable-dev-shm-usage'])
  for width,height,label in [(1440,960,'desktop'),(390,844,'mobile')]:
    page=browser.new_page(viewport={'width':width,'height':height})
    errors=[]
    page.on('pageerror',lambda error: errors.append(str(error)))
    page.set_content(html,wait_until='domcontentloaded')
    page.add_style_tag(content=css)
    page.evaluate(mock)
    page.add_script_tag(content=support)
    page.add_script_tag(content=appjs)
    page.evaluate('showWorkspace({type:"client",id:"c1",full_name:"Test Client",email:"demo@example.test",gender:"male"})')
    page.locator('#careJourneyHeading').wait_for(timeout=9000)
    assert page.locator('.care-step').count()==6, (label,page.locator('#workspaceContent').inner_text())
    assert 'Medical history' in page.locator('.care-step').first.inner_text()
    assert 'Review & monitoring' in page.locator('.care-step').last.inner_text()
    assert page.locator('.care-journey-disclaimer').is_visible()
    assert 'Approved meal plan available' in page.locator('.care-journey').inner_text()
    assert page.locator('.patient-mode').count()==1
    # Clicking an appointment CTA follows the existing navigation and new reminder.
    page.locator('.care-step-link[data-go="client-appointments"]').first.click()
    page.wait_for_timeout(150)
    assert page.locator('#workspaceContent').get_attribute('data-view')=='client-appointments'
    page.evaluate('renderClientAppointments("c1", "book")')
    page.locator('.care-booking-reminder').wait_for(timeout=8000)
    assert 'medical history' in page.locator('.care-booking-reminder').inner_text().lower()
    # Clinician follows the same client journey and explicitly records follow-up.
    page.evaluate('showWorkspace({type:"dietitian",id:"d1",full_name:"Dietitian Demo",email:"doctor@example.test"})')
    page.evaluate('renderDietitianCareReview("c1")')
    page.locator('#careReviewForm').wait_for(timeout=8000)
    page.locator('#careReviewSummary').fill('Dietitian reviewed the nutrition progress at consultation.')
    page.locator('#careMonitoringPlan').fill('Review symptom log weekly and attend scheduled follow-up.')
    page.locator('#careReviewForm button[type="submit"]').click()
    page.locator('.care-review-entry').wait_for(timeout=8000)
    assert len(page.evaluate('window.testPosts'))==1
    assert page.evaluate('window.testPosts[0].appointment_id')=='appt1'
    page.evaluate('showWorkspace({type:"client",id:"c1",full_name:"Test Client",email:"demo@example.test",gender:"male"})')
    page.locator('.care-followup-note').wait_for(timeout=8000)
    assert 'Review symptom log weekly' in page.locator('.care-followup-note').inner_text()
    assert not errors, (label,errors)
    page.close()
    print('Care journey',label,'passed: six steps, booking reminder, clinician review, patient monitoring')
  browser.close()
