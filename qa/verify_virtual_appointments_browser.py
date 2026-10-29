"""Offline desktop/mobile UI integration with simulated API; no real meetings are started."""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[1]
html=(ROOT/'front-end/index.html').read_text()
css=(ROOT/'front-end/styles.css').read_text()+(ROOT/'front-end/vibrant-theme.css').read_text()
appjs=(ROOT/'front-end/app.js').read_text()
supportjs=(ROOT/'front-end/support.js').read_text()

MOCK = r'''() => {
 const bag = new Map();
 Object.defineProperty(window,'sessionStorage', {configurable:true,value:{
   getItem:k=>bag.get(k)||null,setItem:(k,v)=>bag.set(k,String(v)),removeItem:k=>bag.delete(k),clear:()=>bag.clear()
 }});
 window.fakeAppointments=[];
 window.fakePostBodies=[];
 window.fakeMeetingReads=0;
 const future = new Date(Date.now()+3*24*60*60*1000).toISOString();
 window.fetch=async(url,opts={})=>{
   const s=String(url); let data={}; let status=200;
   if(s==='/health') data={status:'online',database:'in_memory'};
   else if(s.includes('/admin/setup-status'))data={available:false};
   else if(s==='/api/v1/dietitians')data=[{id:'d1',full_name:'Dr. Sample',branch_name:'Demo Branch'}];
   else if(s.startsWith('/api/v1/appointments') && (opts.method||'GET')==='GET' && !s.endsWith('/meeting')) data=window.fakeAppointments;
   else if(s==='/api/v1/appointments' && opts.method==='POST') {
     const body=JSON.parse(opts.body);
     window.fakePostBodies.push(body);
     const appt={...body,appointment_id:'appt_test'+window.fakePostBodies.length,status:'PENDING'};
     window.fakeAppointments.push(appt);
     data={message:'Appointment scheduled',appointment:appt};
   }
   else if(s.includes('/meeting')){
     window.fakeMeetingReads++;
     data={meeting_url:'https://meet.jit.si/nc-example12345'};
   }
   else if(s.includes('/api/v1/appointments/') && opts.method==='PATCH') {
     const id=s.split('/').pop();const item=window.fakeAppointments.find(x=>x.appointment_id===id);
     const action=JSON.parse(opts.body).action;
     item.status=action==='APPROVED'?'CONFIRMED':action==='CANCELLED'?'CANCELLED':'REJECTED';
     data={message:'Appointment status updated',appointment:item};
   }
   else if(s.includes('/api/v1/clients?'))data=[];
   else if(s.endsWith('/checkin-appointments'))data=[];
   return {ok:status<400,status,headers:new Headers(),json:async()=>data};
 };
 window.setFuture=future;
}'''

with sync_playwright() as pw:
 browser=pw.chromium.launch(headless=True,executable_path='/usr/bin/chromium',args=['--no-sandbox','--disable-dev-shm-usage'])
 for width,height,name in [(1440,900,'desktop'),(390,844,'mobile')]:
  page=browser.new_page(viewport={'width':width,'height':height})
  errors=[]
  page.on('pageerror',lambda err: errors.append(str(err)))
  page.set_content(html,wait_until='domcontentloaded')
  page.add_style_tag(content=css)
  page.evaluate(MOCK)
  page.add_script_tag(content=supportjs)
  page.add_script_tag(content=appjs)
  page.evaluate("showWorkspace({type:'client',id:'c1',full_name:'Test Client',email:'client@example.test'})")
  page.evaluate('renderClientAppointments("c1", "book")')
  page.wait_for_timeout(120)
  assert page.locator('input[name="consultation_type"]').count()==2, (name,page.locator('#workspaceContent').inner_text())
  assert page.locator('input[value="IN_PERSON"]').is_checked()
  page.locator('input[value="VIRTUAL"]').check()
  page.select_option('#appointmentDietitian','d1')
  page.evaluate('document.querySelector("#appointmentDate").value = window.setFuture.slice(0,16)')
  page.locator('#appointmentForm button[type="submit"]').click()
  page.wait_for_timeout(250)
  assert page.evaluate('window.fakePostBodies[0].consultation_type') == 'VIRTUAL'
  assert page.locator('[data-join-virtual]').count()==0
  assert page.locator('[data-checkin-appointment]').count()==0
  assert 'Video link available after' in page.locator('#workspaceContent').inner_text()
  page.evaluate('window.fakeAppointments[0].status = "CONFIRMED"')
  page.evaluate('renderClientAppointments("c1","upcoming")')
  page.wait_for_timeout(160)
  assert page.locator('[data-join-virtual]').count() == 1
  assert page.locator('[data-checkin-appointment]').count() == 0
  page.locator('[data-join-virtual]').click()
  page.wait_for_timeout(160)
  link=page.locator('a[href^="https://meet.jit.si/nc-"]')
  assert link.count()==1 and link.get_attribute('rel') == 'noopener noreferrer'
  assert page.evaluate('window.fakeMeetingReads')==1
  page.screenshot(path=str(ROOT/'qa'/f'virtual_appointment_{name}.png'),full_page=True)
  page.evaluate('window.fakeAppointments[0].status = "CANCELLED"')
  page.evaluate('renderClientAppointments("c1","past")')
  page.wait_for_timeout(140)
  assert page.locator('[data-join-virtual]').count()==0
  # Dietitian should see upcoming confirmed calls with join capability.
  page.evaluate('window.fakeAppointments[0].status = "CONFIRMED"')
  page.evaluate("currentUser={type:'dietitian',id:'d1',full_name:'Dr. Sample'}")
  page.evaluate('renderAppointmentRequests()')
  page.wait_for_timeout(180)
  assert 'Virtual · Video call' in page.locator('#workspaceContent').inner_text()
  assert page.locator('[data-join-virtual]').count()==1
  assert errors==[],(name,errors)
  print(f'{name}: booking options, pending state, confirmed patient join, safe link, cancellation, dietitian join PASS')
  page.close()
 browser.close()
