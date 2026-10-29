const fs=require('fs'), vm=require('vm'), assert=require('assert'), path=require('path');
const source=fs.readFileSync(path.join(__dirname, '..', 'front-end', 'app.js'),'utf8');
function extractFunction(name){
 const i=source.indexOf('async function '+name+'(');
 if (i<0) throw Error(name+' missing');
 let j=source.indexOf('{',i),depth=0,inS=null,escaped=false,templateExpr=0;
 // Easier extract by next async function anchor (all these functions are contiguous).
 let after=source.indexOf('\nasync function ',j+1);
 if(name==='renderDietitianGoals') after=source.indexOf('\nasync function renderClientAppointments',j+1);
 if(after<0) throw Error('ending marker missing');
 return source.substring(i,after);
}
const listeners={};
const workspaceContent={innerHTML:'',querySelectorAll:()=>[]};
const elements={};
const doc={querySelector:(s)=>elements[s]|| (elements[s]={addEventListener:(event,cb)=>{listeners[s+':'+event]=cb},querySelector:()=>({disabled:false})})};
const goalRecords=[{goal_id:'g1',target_metric:'Balanced meals per day',target_value:3,current_value:null}];
let mealPlanShouldError=false;
const calls=[];
const context={
 workspaceContent,document:doc,
 currentUser:{type:'client',id:'p1'},
 request: async (url,opts={})=>{
  calls.push({url,opts});
  if(url.startsWith('/api/v1/goals?'))return goalRecords;
  if(url==='/api/v1/meal-plans/approved'){
   if(mealPlanShouldError)throw Error('Unexpected server error. Reference: test-ref.');
   return [{plan_id:'p',status:'APPROVED',plan:{diet_type:'Clinician plan',days:1,schedule:[{day:1,candidate_recipe:{title:'Food example'}}]}}];
  }
  return {ok:true};
 },
 pageHeading:(a,b,c)=>`<h1>${b}</h1><p>${c}</p>`,
 escapeHtml:(v)=>String(v).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;'),
 navTo:(v)=>{context.navigation=v},showWorkspaceMessage:()=>{},sessionStorage:{getItem:()=>null},
};
const code=['renderClientGoals','renderClientMealPlan','renderDietitianGoals'].map(extractFunction).join('\n');
vm.runInNewContext(code,context);
(async()=>{
 await context.renderClientGoals('p1');
 assert(workspaceContent.innerHTML.includes('Goals set by your dietitian'));
 assert(!workspaceContent.innerHTML.includes('id="clientGoalForm"'));
 assert(!workspaceContent.innerHTML.includes('Add goal'));
 assert(workspaceContent.innerHTML.includes('Target: 3'));
 await context.renderClientMealPlan('p1');
 assert(workspaceContent.innerHTML.includes('Created and approved by your dietitian'));
 assert(workspaceContent.innerHTML.includes('Food example'));
 assert(!workspaceContent.innerHTML.includes('Assign patient goal'));
 mealPlanShouldError=true;
 await context.renderClientMealPlan('p1');
 assert(workspaceContent.innerHTML.includes("We couldn't load your approved plan."));
 assert(typeof listeners['#retryApprovedPlan:click']==='function');
 context.currentUser.type='dietitian';
 await context.renderDietitianGoals('p1');
 assert(workspaceContent.innerHTML.includes('id="dietitianGoalForm"'));
 assert(workspaceContent.innerHTML.includes('Assign patient goal'));
 console.log('4 frontend logic checks passed (patient goals, approved meal-plan view, retry state, clinician goals)');
})().catch(e=>{console.error(e);process.exitCode=1});
