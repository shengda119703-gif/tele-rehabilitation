package cn.tele.rehabilitation.offline.qa;
import android.app.Activity;
import android.app.Instrumentation;
import android.content.Intent;
import android.os.Bundle;
import android.webkit.WebView;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

/** Explicit TEST server only, from our dedicated emulated Android device. */
public final class CloudSmoke extends Instrumentation {
 private WebView web;
 @Override public void onCreate(Bundle b){super.onCreate(b);start();}
 private String eval(String script)throws Exception{CountDownLatch latch=new CountDownLatch(1);AtomicReference<String> result=new AtomicReference<>();runOnMainSync(()->web.evaluateJavascript(script,v->{result.set(v);latch.countDown();}));if(!latch.await(15,TimeUnit.SECONDS))throw new Exception("JS timeout");return result.get();}
 @Override public void onStart(){Bundle result=new Bundle();try{
  Intent launch=getTargetContext().getPackageManager().getLaunchIntentForPackage(getTargetContext().getPackageName());launch.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);Activity app=startActivitySync(launch);
  java.lang.reflect.Field wf=app.getClass().getDeclaredField("web");wf.setAccessible(true);web=(WebView)wf.get(app);
  java.lang.reflect.Field cf=app.getClass().getDeclaredField("cloud");cf.setAccessible(true);Object cloud=cf.get(app);
  java.lang.reflect.Method connect=cloud.getClass().getDeclaredMethod("connect",String.class,String.class);connect.setAccessible(true);connect.invoke(cloud,"http://10.0.2.2:8771","TEST");
  for(int n=0;n<90;n++){if("true".equals(eval("!!window.PhoneLocal&&!!document.querySelector('#nav a')")))break;Thread.sleep(500);}
  eval("window.__cloudQa={status:'running'};(async()=>{try{await PhoneLocal.ready;const b=await PhoneLocal.backup();let revision=0;try{revision=(await PhoneCloud.request('/v1/backup')).revision;}catch(e){if(!e.message.includes('没有本人'))throw e;}await PhoneCloud.request('/v1/backup','PUT',{consent:true,revision,document:b});const read=await PhoneCloud.request('/v1/backup');if(read.document.data.owner!==PhoneLocal.store.value.owner)throw Error('Owner mismatch');await PhoneCloud.publish(PhoneLocal);const family=await PhoneCloud.request('/v1/family');if(family.familyMembers.length)throw Error('Uninvited family');OfflineAndroid.cloudDisconnect();const snap=await PhoneLocal.snapshot();if(!snap.profile||PhoneCloud.configured())throw Error('Offline fallback failed');window.__cloudQa={status:'passed',backup:true,localOwner:true,offline:true};}catch(e){window.__cloudQa={status:'failed',error:String(e)};}})();");
  for(int n=0;n<180;n++){String state=eval("JSON.stringify(window.__cloudQa)");if(state.contains("\\\"passed\\\"")){result.putString("cloud",state);finish(Activity.RESULT_OK,result);return;}if(state.contains("\\\"failed\\\""))throw new Exception(state);Thread.sleep(500);}
  throw new Exception("Cloud smoke timeout");
 }catch(Throwable e){result.putString("failure",e.toString());finish(Activity.RESULT_CANCELED,result);}}
}
