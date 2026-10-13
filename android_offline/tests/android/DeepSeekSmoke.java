package cn.tele.rehabilitation.offline.qa;
import android.app.Activity;
import android.app.Instrumentation;
import android.content.Intent;
import android.os.Bundle;
import android.os.ParcelFileDescriptor;
import android.webkit.WebView;
import java.io.ByteArrayOutputStream;
import java.io.FileInputStream;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;
import android.graphics.Bitmap;
import java.io.FileOutputStream;

/** Dedicated empty emulator only. Credentials are never embedded in either APK. */
public final class DeepSeekSmoke extends Instrumentation {
 private WebView web;
 private String eval(String script)throws Exception{
  CountDownLatch latch=new CountDownLatch(1);AtomicReference<String> result=new AtomicReference<>();
  runOnMainSync(()->web.evaluateJavascript(script,v->{result.set(v);latch.countDown();}));
  if(!latch.await(15,TimeUnit.SECONDS))throw new Exception("JS timeout");return result.get();
 }
 private void ready()throws Exception{
  for(int n=0;n<120;n++){if("true".equals(eval("typeof window.__oldPage==='undefined'&&!!window.PhoneLocal&&!!window.PhoneDeepSeek&&!!document.querySelector('#nav a')")))return;Thread.sleep(500);}throw new Exception("Local UI timeout");
 }
 @Override public void onCreate(Bundle b){super.onCreate(b);start();}
 private void screenshot(String name)throws Exception{
  Bitmap image=getUiAutomation().takeScreenshot();if(image==null)throw new Exception("Screenshot unavailable");
  try(FileOutputStream out=new FileOutputStream(new java.io.File(getTargetContext().getExternalFilesDir(null),name))){image.compress(Bitmap.CompressFormat.PNG,100,out);}finally{image.recycle();}
 }
 @Override public void onStart(){Bundle result=new Bundle();Object transport=null;try{
  Intent launch=getTargetContext().getPackageManager().getLaunchIntentForPackage(getTargetContext().getPackageName());launch.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
  Activity app=startActivitySync(launch);java.lang.reflect.Field wf=app.getClass().getDeclaredField("web");wf.setAccessible(true);web=(WebView)wf.get(app);ready();
  java.lang.reflect.Field field=app.getClass().getDeclaredField("deepSeek");field.setAccessible(true);transport=field.get(app);
  java.lang.reflect.Method save=transport.getClass().getDeclaredMethod("save",String.class);save.setAccessible(true);
  String key;
  try(ParcelFileDescriptor fd=getUiAutomation().executeShellCommand("cat /data/local/tmp/ankang-deepseek-qa-key");FileInputStream in=new FileInputStream(fd.getFileDescriptor());ByteArrayOutputStream out=new ByteArrayOutputStream()){
   byte[] bytes=new byte[1024];int n;while((n=in.read(bytes))!=-1){if(out.size()+n>512)throw new Exception("QA key length invalid");out.write(bytes,0,n);}key=new String(out.toByteArray(),StandardCharsets.UTF_8).trim();
  }
  if(key.isEmpty())throw new Exception("QA key missing");save.invoke(transport,key);
  if(getTargetContext().getSharedPreferences("deepseek-v1",0).getAll().toString().contains(key))throw new Exception("Credential was not encrypted");
  eval("window.__oldPage=true");runOnMainSync(()->web.reload());ready();
  eval("window.__deepQa={status:'running'};(async()=>{try{await PhoneLocal.ready;const before=await PhoneLocal.snapshot();if(!before.conversationModelAvailable)throw Error('not configured');const facts=JSON.stringify([before.state.events,before.state.familyEvents]);let calls=0;for(const text of ['你可以做我对象吗','你喜欢我吗','请记住这次聊天的代号是蓝鲸七号','代号是什么？']){const r=await PhoneLocal.request('/api/product/chat',{method:'POST',body:JSON.stringify({text,_conversationScope:'FORGED'})});if(r.turn.conversation?.provider!=='deepseek'||r.turn.conversation.status!=='replied')throw Error('model not called '+JSON.stringify({conversation:r.turn.conversation,safety:r.turn.appliedChanges.safetyAction,events:r.turn.appliedChanges.eventsToAppend.length,claims:r.turn.understanding.claims.map(c=>({tags:c.tags,health:c.hasHealthValue}))}));if(r.turn.reply.conversationContext!=='PHONE_LOCAL:TEST')throw Error('host scope failed');if(JSON.stringify([r.turn.snapshot.events,r.turn.snapshot.familyEvents])!==facts)throw Error('facts changed');if(calls===3&&!r.turn.reply.text.includes('蓝鲸七号'))throw Error('context missing');calls++;}const priv=await PhoneLocal.request('/api/product/chat',{method:'POST',body:JSON.stringify({text:'不要记录：TEST_PRIVATE_ANDROID'})});if(priv.turn.conversation)throw Error('private reached model');const read=await PhoneLocal.request('/api/product/chat',{method:'POST',body:JSON.stringify({text:'查看健康记录和药物清单'})});if(read.turn.conversation||read.turn.agent?.steps?.length!==2)throw Error('module path failed');const rehab=await PhoneLocal.request('/api/product/chat',{method:'POST',body:JSON.stringify({text:'查看训练计划'})});if(!rehab.turn.agent||rehab.turn.conversation)throw Error('rehab path failed');location.hash='#assistant';await load();if(!document.body.textContent.includes('DeepSeek 回复'))throw Error('source badge missing');window.__deepQa={status:'passed',liveCalls:calls,privateLocal:true,hostScope:true,moduleRead:true,rehabRead:true,noHealthFacts:true,encrypted:true};}catch(e){window.__deepQa={status:'failed',error:String(e)};}})();");
  for(int n=0;n<200;n++){
   String state=eval("JSON.stringify(window.__deepQa)");
   if(state.contains("\\\"passed\\\"")){
    java.lang.reflect.Method count=transport.getClass().getDeclaredMethod("requestCount");count.setAccessible(true);
    if(((Integer)count.invoke(transport))!=4)throw new Exception("Unexpected outbound request count");
    java.lang.reflect.Constructor<?> constructor=transport.getClass().getDeclaredConstructor(android.content.Context.class);constructor.setAccessible(true);
    Object reopened=constructor.newInstance(getTargetContext());java.lang.reflect.Method configured=reopened.getClass().getDeclaredMethod("configured");configured.setAccessible(true);
    if(!((Boolean)configured.invoke(reopened)))throw new Exception("Encrypted configuration did not reopen");
    eval("Array.from(document.querySelectorAll('.bubble')).find(e=>e.textContent.includes('DeepSeek 回复'))?.scrollIntoView({block:'center'})");Thread.sleep(700);screenshot("deepseek-chat.png");
    eval("OfflineAndroid.deepSeekSettings()");Thread.sleep(700);screenshot("deepseek-settings.png");
    result.putString("deepseek",state);result.putBoolean("outboundCountVerified",true);result.putBoolean("encryptedReopen",true);finish(Activity.RESULT_OK,result);return;
   }
   if(state.contains("\\\"failed\\\""))throw new Exception(state);Thread.sleep(500);
  }throw new Exception("DeepSeek QA timeout");
 }catch(Throwable e){try{if(transport!=null){java.lang.reflect.Method diagnostic=transport.getClass().getDeclaredMethod("lastFailure");diagnostic.setAccessible(true);result.putString("transport",String.valueOf(diagnostic.invoke(transport)));}}catch(Exception ignored){} result.putString("failure",e.toString());finish(Activity.RESULT_CANCELED,result);}
 finally{
  try{if(transport!=null){java.lang.reflect.Method clear=transport.getClass().getDeclaredMethod("clear");clear.setAccessible(true);clear.invoke(transport);}getUiAutomation().executeShellCommand("rm -f /data/local/tmp/ankang-deepseek-qa-key").close();}catch(Exception ignored){}
 }}
}
