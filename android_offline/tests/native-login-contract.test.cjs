const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const java=n=>fs.readFileSync(path.join(__dirname,'../src/cn/tele/rehabilitation/offline/',n+'.java'),'utf8');
test('native bridge and transport use the same action allowlist including personal assistant',()=>{
 const main=java('MainActivity'),account=java('AccountTransport');
 assert(main.includes('AccountTransport.supports(action)'));assert(main.includes('PhoneAccount.reply('));assert(main.includes('CLIENT_REQUEST_INVALID'));
 for(const action of ['session','assistantTurn','assistantConversation','assistantPreferences','workflow','workflowProfile','candidate','reports','shareReport','aiAsk','aiUsage'])assert(account.includes('"'+action+'"'));
 assert(!account.includes('public synchronized JSONObject identity()'));assert(account.includes('private volatile JSONObject session'));
});
test('native startup is login-first, tokens stay outside page scripts and simple passwords are supported',()=>{
 const main=java('MainActivity'),html=fs.readFileSync(path.join(__dirname,'../web/signin.html'),'utf8'),js=fs.readFileSync(path.join(__dirname,'../web/signin.js'),'utf8');
 assert(main.includes('web.loadUrl(ORIGIN + "/local/signin.html")'));assert(main.includes('accountAuthenticate'));assert(main.includes('request.isForMainFrame()'));
 assert(html.includes('type="password"'));assert(!html.includes('pattern='));assert(!html.includes('minlength='));assert(js.includes("password.value='';"));assert(!/localStorage\.setItem\([^\n]*password/.test(js));
 assert(js.includes("request('session',cached)"));assert(js.includes('openContact:false'));assert(js.includes('45000'));
});
test('native assessment plan routes use current patient identity and never accept client record/status writes',()=>{
 const account=java('AccountTransport');
 for(const action of ['assessmentPlans','assessmentPlanCancel'])assert(account.includes('"'+action+'"'));
 assert(account.includes('boolean assessmentPath=path.matches('));assert(account.includes('!assessmentPath'));
 assert(account.includes('if(action.equals("assessmentPlans"))return authorized("/patients/"+patient+"/assistant/assessment-plans","GET",null)'));
 assert(account.includes('"/assistant/assessment-plans/"+plan+"/cancel","POST",new JSONObject()'));
 assert(account.includes('!value.getString("account_id").equals(data.optString("account_id"))'));
 assert(account.indexOf('success(authorized("/auth/me"')<account.indexOf('if(action.equals("assessmentPlans"))'));
});
