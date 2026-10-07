package cn.tele.rehabilitation.offline.qa;
import android.app.Activity;
import android.app.Instrumentation;
import android.content.Intent;
import android.os.Bundle;
import android.webkit.WebView;
import android.view.accessibility.AccessibilityNodeInfo;
import org.json.JSONObject;
import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

/** QA-only: release UI, isolated TEST namespace, no host patient data. */
public final class LinSmoke extends Instrumentation {
 private WebView web;private Activity app;
 @Override public void onCreate(Bundle args){super.onCreate(args);start();}
 private String eval(String code)throws Exception{CountDownLatch done=new CountDownLatch(1);AtomicReference<String> out=new AtomicReference<>();runOnMainSync(()->web.evaluateJavascript(code,v->{out.set(v);done.countDown();}));if(!done.await(20,TimeUnit.SECONDS))throw new Exception("JS timeout");return out.get();}
 private void waitFor(String code)throws Exception{for(int n=0;n<180;n++){if("true".equals(eval(code)))return;Thread.sleep(500);}throw new Exception("UI not ready: "+eval("document.body.innerText"));}
 // Domain sessions legitimately advance their revision when reopened; compare
 // all durable records, not this in-memory-session persistence counter.
 private String saved(String key)throws Exception{return eval("(function(){const v=JSON.parse(localStorage.getItem("+JSONObject.quote(key)+"));if(!v)return null;for(const [k,x]of Object.entries(v.kv))if(k.startsWith('health:'))delete x.revision;return JSON.stringify(v)})()");}
 private void menu(String label)throws Exception{
  eval("document.querySelector('#profile').dispatchEvent(new MouseEvent('contextmenu',{bubbles:true,cancelable:true}))");
  for(int n=0;n<50;n++){AccessibilityNodeInfo root=getUiAutomation().getRootInActiveWindow();if(root!=null)for(AccessibilityNodeInfo node:root.findAccessibilityNodeInfosByText(label))if(label.contentEquals(node.getText()==null?"":node.getText())){if(!node.performAction(AccessibilityNodeInfo.ACTION_CLICK))throw new Exception("Native menu action failed");return;}Thread.sleep(100);}
  throw new Exception("Native profile menu missing: "+label);
 }
 private void open()throws Exception{Intent launch=getTargetContext().getPackageManager().getLaunchIntentForPackage(getTargetContext().getPackageName());launch.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);app=startActivitySync(launch);java.lang.reflect.Field f=app.getClass().getDeclaredField("web");f.setAccessible(true);web=(WebView)f.get(app);waitFor("!!window.PhoneLocal&&!!document.querySelector('#nav a')");eval("PhoneLocal.ready.then(()=>window.__ready=true)");waitFor("window.__ready===true");}
 private String script()throws Exception{try(InputStream in=getContext().getAssets().open("lin-smoke.js");ByteArrayOutputStream out=new ByteArrayOutputStream()){byte[] b=new byte[65536];int n;while((n=in.read(b))>0)out.write(b,0,n);return new String(out.toByteArray(),java.nio.charset.StandardCharsets.UTF_8);}}
 private String run(String phase)throws Exception{String query="qa="+phase+System.nanoTime(),url="https://appassets.androidplatform.net/"+("reports".equals(phase)?"capture?tab=history&":"?")+query;runOnMainSync(()->web.loadUrl(url));waitFor("location.search.includes("+JSONObject.quote(query)+")&&document.readyState==='complete'&&!!window.PhoneLocal && PhoneLocal.store.key===PhoneStore.LIN_KEY && "+("reports".equals(phase)?"typeof state!=='undefined'&&state.catalog.length===53":"!!document.querySelector('#nav a')"));eval("window.__linPhase="+JSONObject.quote(phase)+";"+script());for(int n=0;n<180;n++){String state=eval("JSON.stringify(window.__linQa)");if(state.contains("\\\"passed\\\""))return state;if(state.contains("\\\"failed\\\""))throw new Exception(state);Thread.sleep(500);}throw new Exception("TEST flow timeout");}
 @Override public void onStart(){Bundle result=new Bundle();try{
  open();String personal=eval("localStorage.getItem(PhoneStore.KEY)"),personalRecords=saved("ankang-phone-product-2");
  eval("PhoneLocal.selectProfile(PhoneStore.LIN_KEY)");waitFor("!!window.PhoneLocal&&PhoneLin.isLin(PhoneLocal.store)&&!!document.querySelector('#nav a')");
  result.putString("pages",run("pages"));result.putString("reports",run("reports"));
  if(!personal.equals(eval("localStorage.getItem(PhoneStore.KEY)")))throw new Exception("Personal store changed by TEST import");
  String lin=saved("ankang-phone-test-lin-1");runOnMainSync(()->app.finish());Thread.sleep(600);open();
  if(!lin.equals(saved("ankang-phone-test-lin-1")))throw new Exception("TEST records changed on reopen");
  menu("返回个人档案");waitFor("!!window.PhoneLocal&&PhoneLocal.store.key===PhoneStore.KEY&&!!document.querySelector('#nav a')");
  if(!"null".equals(personal)&&!personalRecords.equals(saved("ankang-phone-product-2")))throw new Exception("Personal records changed during account switch");
  menu("打开 TEST 林女士档案");waitFor("!!window.PhoneLocal&&PhoneLin.isLin(PhoneLocal.store)&&!!document.querySelector('#nav a')");
  if(!lin.equals(saved("ankang-phone-test-lin-1")))throw new Exception("TEST import repeated");
  result.putString("persistence","passed: reopen and both native profile menu switches, personal store retained");finish(Activity.RESULT_OK,result);
 }catch(Throwable e){result.putString("failure",e.toString());finish(Activity.RESULT_CANCELED,result);}}
}
