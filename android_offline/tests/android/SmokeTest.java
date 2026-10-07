package cn.tele.rehabilitation.offline.qa;
import android.app.Activity;
import android.app.Instrumentation;
import android.content.Intent;
import android.os.Bundle;
import android.webkit.JavascriptInterface;
import android.webkit.WebView;
import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;
/** Private QA bridge/recordings are never compiled into the release app. */
public final class SmokeTest extends Instrumentation{
 private WebView web;private Activity activity;private String phase="health";
 @Override public void onCreate(Bundle args){super.onCreate(args);start();}
 private String eval(String code)throws Exception{CountDownLatch done=new CountDownLatch(1);AtomicReference<String> text=new AtomicReference<>();runOnMainSync(()->web.evaluateJavascript(code,v->{text.set(v);done.countDown();}));if(!done.await(20,TimeUnit.SECONDS))throw new Exception("JS callback timeout");return text.get();}
 private void ready()throws Exception{Intent launch=getTargetContext().getPackageManager().getLaunchIntentForPackage(getTargetContext().getPackageName());launch.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);activity=startActivitySync(launch);java.lang.reflect.Field f=activity.getClass().getDeclaredField("web");f.setAccessible(true);web=(WebView)f.get(activity);for(int n=0;n<90;n++){if("true".equals(eval("!!window.PhoneLocal && !!document.querySelector('#nav a')")))return;Thread.sleep(500);}throw new Exception("New UI did not load: "+eval("document.body.innerText"));}
 private String asset(String name)throws Exception{try(InputStream in=getContext().getAssets().open(name);ByteArrayOutputStream out=new ByteArrayOutputStream()){byte[] b=new byte[65536];int n;while((n=in.read(b))>0)out.write(b,0,n);return new String(out.toByteArray(),java.nio.charset.StandardCharsets.UTF_8);}}
 public final class Fixtures{
  @JavascriptInterface public String phase(){return phase;}
  @JavascriptInterface public String video(String name){if(!"shoulder".equals(name)&&!"squat".equals(name))return "";try(InputStream in=getContext().getAssets().open(name+".mp4");ByteArrayOutputStream out=new ByteArrayOutputStream()){byte[] b=new byte[65536];int n;while((n=in.read(b))>0)out.write(b,0,n);return android.util.Base64.encodeToString(out.toByteArray(),android.util.Base64.NO_WRAP);}catch(Exception e){return "";}}
 }
 private String runPhase(String name)throws Exception{phase=name;runOnMainSync(()->{web.addJavascriptInterface(new Fixtures(),"QaFixtures");web.loadUrl("https://appassets.androidplatform.net/"+("motion".equals(name)?"capture?tab=assess":""));});Thread.sleep(1800);eval(asset("smoke.js"));String out="";for(int n=0;n<1200;n++){out=eval("JSON.stringify(window.__qa)");if(out.contains("\\\"passed\\\""))return out;if(out.contains("\\\"failed\\\""))throw new Exception(out);Thread.sleep(500);}throw new Exception("Phase timeout: "+out);}
 @Override public void onStart(){Bundle result=new Bundle();try{ready();result.putString("health",runPhase("health"));result.putString("motion",runPhase("motion"));String count=eval("PhoneLocal.store.value.jobs.length");runOnMainSync(()->activity.finish());Thread.sleep(600);ready();if(!count.equals(eval("PhoneLocal.store.value.jobs.length")))throw new Exception("Records lost on reopen");result.putString("reopen","passed");finish(Activity.RESULT_OK,result);}catch(Throwable error){result.putString("failure",error.toString());finish(Activity.RESULT_CANCELED,result);}}
}
