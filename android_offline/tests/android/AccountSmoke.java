package cn.tele.rehabilitation.offline.qa;
import android.app.Activity;
import android.app.Instrumentation;
import android.content.Intent;
import android.os.Bundle;
import android.os.ParcelFileDescriptor;
import android.webkit.WebView;
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicReference;
import org.json.JSONObject;

/** Explicitly authorized single live question; no evaluation/training writes. */
public final class AccountSmoke extends Instrumentation {
 private WebView web;
 private boolean logoutOnly;
 private boolean recoveryOnly;
 private boolean dialogueViewOnly;
 private String eval(String js)throws Exception{CountDownLatch latch=new CountDownLatch(1);AtomicReference<String> result=new AtomicReference<>();runOnMainSync(()->web.evaluateJavascript(js,v->{result.set(v);latch.countDown();}));if(!latch.await(15,TimeUnit.SECONDS))throw new Exception("JS timeout");return result.get();}
 private void waitFor(String js)throws Exception{for(int i=0;i<100;i++){if("true".equals(eval(js)))return;Thread.sleep(400);}throw new Exception("Page not ready");}
 private String shell(String command)throws Exception{try(ParcelFileDescriptor fd=getUiAutomation().executeShellCommand(command);InputStream in=new FileInputStream(fd.getFileDescriptor());ByteArrayOutputStream out=new ByteArrayOutputStream()){byte[] bytes=new byte[2048];int n;while((n=in.read(bytes))!=-1){if(out.size()+n>8192)throw new Exception("QA input too large");out.write(bytes,0,n);}return new String(out.toByteArray(),StandardCharsets.UTF_8).trim();}}
 private void shot(String name)throws Exception{android.graphics.Bitmap bmp=getUiAutomation().takeScreenshot();if(bmp==null)throw new Exception("No screenshot");try(FileOutputStream out=new FileOutputStream(new File(getTargetContext().getExternalFilesDir(null),name))){bmp.compress(android.graphics.Bitmap.CompressFormat.PNG,100,out);}finally{bmp.recycle();}}
 @Override public void onCreate(Bundle b){super.onCreate(b);logoutOnly=b!=null&&"logout-and-show-login".equals(b.getString("mode"));recoveryOnly=b!=null&&"recover-existing-reply".equals(b.getString("mode"));dialogueViewOnly=b!=null&&"view-existing-dialogue-checks".equals(b.getString("mode"));start();}
 @Override public void onStart(){Bundle result=new Bundle();try{
  if(!"rehab-offline-test".equals(shell("getprop ro.boot.qemu.avd_name")))throw new Exception("Dedicated emulator required");
  if(dialogueViewOnly){
   Intent launch=getTargetContext().getPackageManager().getLaunchIntentForPackage(getTargetContext().getPackageName());launch.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);Activity activity=startActivitySync(launch);
   java.lang.reflect.Field field=activity.getClass().getDeclaredField("web");field.setAccessible(true);web=(WebView)field.get(activity);
   waitFor("!!window.PhoneLocal && !!document.querySelector('#nav a')");
   if(!"true".equals(eval("PhoneAccount.identity()?.username==='gh409'")))throw new Exception("Keep another user's session unchanged");
   eval("location.hash='#assistant'");waitFor("typeof ui!=='undefined' && ui.page==='assistant' && ui.assistantCloud?.items?.some(r=>r.operation_id==='85e26389-0f7e-41be-9848-128dee6bccb3')");
   eval("[...document.querySelectorAll('.bubble')].find(e=>e.textContent.includes('先暂停会加重腰痛的训练'))?.scrollIntoView({block:'start'})");Thread.sleep(900);shot("assistant-structured-057.png");
   result.putString("readOnlyCheck",eval("JSON.stringify({formattedReplies:ui.assistantCloud.items.filter(r=>['de009d8c-6f04-4010-97a8-e073fc08b2d6','85e26389-0f7e-41be-9848-128dee6bccb3'].includes(r.operation_id)&&r.source==='deepseek'&&r.answer.includes('先确认')).length,newReplyRawMarkdown:ui.assistantCloud.items.filter(r=>['de009d8c-6f04-4010-97a8-e073fc08b2d6','85e26389-0f7e-41be-9848-128dee6bccb3'].includes(r.operation_id)).some(r=>r.answer.includes('**')),busy:ui.busy})"));
   finish(Activity.RESULT_OK,result);return;
  }
  if(recoveryOnly){
   // Read a previously authorized reply. Never call assistantTurn or aiAsk.
   Intent launch=getTargetContext().getPackageManager().getLaunchIntentForPackage(getTargetContext().getPackageName());launch.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);Activity activity=startActivitySync(launch);
   java.lang.reflect.Field field=activity.getClass().getDeclaredField("web");field.setAccessible(true);web=(WebView)field.get(activity);
   waitFor("!!window.PhoneSignIn || !!window.PhoneLocal");
   if("true".equals(eval("!!document.querySelector('#signin-form')"))){
    JSONObject credential=new JSONObject(shell("cat /data/local/tmp/ankang-account-check.json"));
    if(!"gh409".equals(credential.getString("username")))throw new Exception("Check account required");
    eval("document.querySelector('#username').value="+JSONObject.quote(credential.getString("username"))+";document.querySelector('#password').value="+JSONObject.quote(credential.getString("password"))+";document.querySelector('#signin-form').requestSubmit()");
   }
   waitFor("!!window.PhoneLocal && !!document.querySelector('#nav a')");
   if(!"true".equals(eval("PhoneAccount.identity()?.username==='gh409'")))throw new Exception("Do not use another user's session");
   eval("window.__recoveryQA={state:'reading'};(async()=>{try{await PhoneLocal.ready;const s=PhoneLocal.store;const before=JSON.stringify([s.value.jobs,s.value.plans,s.value.daily]);const read=await PhoneAccount.assistantConversation(s);const prior=PhoneAccount.assistantPending(s);const row=read.items.find(r=>r.receipt_id==='cfdd3d9e-a971-4d9a-837f-a4c5d943d4f6'&&typeof r.answer==='string');if(!row)throw Error('Original authorized reply not found');s.change(v=>{v.cloudAssistantQueue=[...prior,{patient_id:PhoneAccount.identity().patient_id,account_id:PhoneAccount.identity().account_id,operation_id:row.operation_id,text:row.text}];v.cloudAssistantPending=v.cloudAssistantQueue[0];});window.__recoveryQA={state:'seeded',before,prior:JSON.stringify(prior),target:row.operation_id,latest:read.latest_sequence};}catch(e){window.__recoveryQA={state:'failed',error:e.message};}})()");
   waitFor("['seeded','failed'].includes(window.__recoveryQA?.state)");if(!"true".equals(eval("window.__recoveryQA.state==='seeded'")))throw new Exception(eval("window.__recoveryQA.error"));
   eval("location.hash='#assistant'");waitFor("typeof ui!=='undefined' && ui.page==='assistant' && !!document.querySelector('#draft')");
   waitFor("!PhoneAccount.assistantPending(PhoneLocal.store).some(r=>r.operation_id===window.__recoveryQA.target) && ui.assistantCloud?.items?.some(r=>r.receipt_id==='cfdd3d9e-a971-4d9a-837f-a4c5d943d4f6')");
   Thread.sleep(900);shot("account-recovered-057.png");
   result.putString("recoveryCheck",eval("JSON.stringify({restored:ui.assistantCloud.items.some(r=>r.receipt_id==='cfdd3d9e-a971-4d9a-837f-a4c5d943d4f6'),pending:PhoneAccount.assistantPending(PhoneLocal.store).length,userQuestionsUnchanged:window.__recoveryQA.prior===JSON.stringify(PhoneAccount.assistantPending(PhoneLocal.store)),retryVisible:document.querySelectorAll('.conversation [data-assistant-retry]').length,clinicalRecordsUnchanged:window.__recoveryQA.before===JSON.stringify([PhoneLocal.store.value.jobs,PhoneLocal.store.value.plans,PhoneLocal.store.value.daily]),latestSequence:ui.assistantCloud.next_after,originalLatest:window.__recoveryQA.latest,busy:ui.busy})"));
   finish(Activity.RESULT_OK,result);return;
  }
  if(logoutOnly){
   Intent intent=getTargetContext().getPackageManager().getLaunchIntentForPackage(getTargetContext().getPackageName());intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);Activity activity=startActivitySync(intent);java.lang.reflect.Field f=activity.getClass().getDeclaredField("web");f.setAccessible(true);web=(WebView)f.get(activity);
   waitFor("!!window.PhoneLocal && !!document.querySelector('#nav a')");
   if(!"true".equals(eval("PhoneAccount.identity()?.username==='gh409'")))throw new Exception("Do not close another user's session");
   eval("(async()=>{await PhoneAccount.request('logout',PhoneAccount.identity());location.href='/local/signin.html';})()");
   waitFor("!!document.querySelector('#signin-form') && document.querySelector('#signin-submit').textContent==='登录'");Thread.sleep(800);shot("account-signin-056-visible.png");result.putBoolean("loginPageVisible",true);result.putBoolean("testSessionClosed",true);finish(Activity.RESULT_OK,result);return;
  }
  File marker=new File(getTargetContext().getExternalFilesDir(null),"authorized-cloud-check-20261015.sent");if(marker.exists())throw new Exception("Single live check already attempted; do not dispatch again");
  JSONObject credential=new JSONObject(shell("cat /data/local/tmp/ankang-account-check.json"));
  if(!"gh409".equals(credential.getString("username")))throw new Exception("Authorized check account required");
  Intent launch=getTargetContext().getPackageManager().getLaunchIntentForPackage(getTargetContext().getPackageName());launch.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);Activity app=startActivitySync(launch);
  java.lang.reflect.Field field=app.getClass().getDeclaredField("web");field.setAccessible(true);web=(WebView)field.get(app);
  waitFor("!!window.PhoneSignIn && !!document.querySelector('#signin-form')");shot("account-signin-056.png");
  eval("document.querySelector('#username').value="+JSONObject.quote(credential.getString("username"))+";document.querySelector('#password').value="+JSONObject.quote(credential.getString("password"))+";document.querySelector('#signin-form').requestSubmit()");
  waitFor("!!window.PhoneLocal && !!document.querySelector('#nav a')");
  if(!"true".equals(eval("PhoneAccount.identity().username==='gh409'")))throw new Exception("Wrong account");
  eval("location.hash='#assistant'");waitFor("!!document.querySelector('#draft') && typeof ui!=='undefined' && ui.page==='assistant'");
  eval("window.__accountCheck={state:'checking'};(async()=>{try{await PhoneLocal.ready;await Promise.all([PhoneAccount.assistantPreferences(PhoneLocal.store),PhoneAccount.assistantConversation(PhoneLocal.store)]);window.__accountCheck={state:'ready',before:JSON.stringify([PhoneLocal.store.value.jobs,PhoneLocal.store.value.plans,PhoneLocal.store.value.daily])};}catch(e){window.__accountCheck={state:'failed',error:e.message};}})()");
  waitFor("window.__accountCheck?.state==='ready'");
  try(FileOutputStream out=new FileOutputStream(marker)){out.write("single dispatch authorized; never rerun automatically".getBytes(StandardCharsets.UTF_8));}
  eval("window.__accountCheck.state='sent';document.querySelector('#draft').value='连接检查：请只回复“连接正常”。';document.querySelector('#draft').dispatchEvent(new Event('input',{bubbles:true}));document.querySelector('#chat-form').requestSubmit()");
  for(int n=0;n<150;n++){
   if("true".equals(eval("!ui.busy && !PhoneLocal.store.value.cloudAssistantPending && ui.assistantCloud?.items?.some(t=>t.text==='连接检查：请只回复“连接正常”。' && t.source==='deepseek' && ['SUCCEEDED','UNMETERED'].includes(t.state))"))){
    String summary=eval("JSON.stringify((()=>{const t=ui.assistantCloud.items.find(t=>t.text==='连接检查：请只回复“连接正常”。');return{state:t.state,source:t.source,usage:t.receipt?.usage||null,receipt_id:t.receipt_id||t.receipt?.id||null,unchanged:window.__accountCheck.before===JSON.stringify([PhoneLocal.store.value.jobs,PhoneLocal.store.value.plans,PhoneLocal.store.value.daily]),busy:ui.busy};})())");
    shot("account-deepseek-056.png");result.putString("liveCheck",summary);result.putBoolean("loginAndNativeBridge",true);finish(Activity.RESULT_OK,result);return;
   }
   Thread.sleep(400);
  }
  result.putString("diagnostic",eval("JSON.stringify({busy:ui.busy,message:document.querySelector('#message')?.textContent,pending:!!PhoneLocal.store.value.cloudAssistantPending,last:ui.assistantCloud?.items?.at(-1)?.state})"));throw new Exception("Live check not confirmed; do not resend");
 }catch(Throwable e){result.putString("failure",e.toString());finish(Activity.RESULT_CANCELED,result);}finally{try{shell("rm -f /data/local/tmp/ankang-account-check.json");}catch(Exception ignored){}}}
}
