package cn.tele.rehabilitation.offline.qa;

import android.app.Activity;
import android.app.Instrumentation;
import android.content.Intent;
import android.os.Bundle;
import android.webkit.WebView;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

/** Runs only on our dedicated AVD with emulated cameras, never a host webcam. */
public final class CameraSmoke extends Instrumentation {
    private WebView web;
    @Override public void onCreate(Bundle args){super.onCreate(args);start();}
    private String eval(String code) throws Exception {
        CountDownLatch wait=new CountDownLatch(1);AtomicReference<String> value=new AtomicReference<>();
        runOnMainSync(()->web.evaluateJavascript(code,v->{value.set(v);wait.countDown();}));
        if(!wait.await(15,TimeUnit.SECONDS))throw new Exception("JS timeout");return value.get();
    }
    @Override public void onStart(){Bundle result=new Bundle();try{
        Intent launch=getTargetContext().getPackageManager().getLaunchIntentForPackage(getTargetContext().getPackageName());launch.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
        Activity activity=startActivitySync(launch);java.lang.reflect.Field field=activity.getClass().getDeclaredField("web");field.setAccessible(true);web=(WebView)field.get(activity);
        for(int i=0;i<90;i++){if("true".equals(eval("typeof catalog!=='undefined'&&!!catalog")))break;Thread.sleep(500);}
        eval("window.__camera={status:'running'};detail('shoulder_abduction');window.__live=livePage('left');true");
        boolean ready=false;
        for(int i=0;i<180;i++){if("true".equals(eval("!!session?.stream && document.querySelector('#motion-video')?.readyState>=2 && !document.querySelector('#motion-video').paused"))){ready=true;break;}if("true".equals(eval("!session")))throw new Exception("Camera did not start: "+eval("document.body.innerText"));Thread.sleep(500);}
        if(!ready)throw new Exception("Camera start timed out");
        eval("window.__testTracks=session.stream.getTracks();offlinePause();true");
        for(int i=0;i<60;i++){if("true".equals(eval("!session && __testTracks.every(t=>t.readyState==='ended')"))){result.putString("camera","emulated stream opened, video ready, pause released all tracks");finish(Activity.RESULT_OK,result);return;}Thread.sleep(500);}
        throw new Exception("Camera tracks not released");
    }catch(Throwable error){result.putString("failure",error.toString());finish(Activity.RESULT_CANCELED,result);}}
}
