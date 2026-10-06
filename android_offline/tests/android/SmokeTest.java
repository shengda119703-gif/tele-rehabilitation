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

/** Test-only fixture bridge, NEVER compiled into the distributed APK. */
public final class SmokeTest extends Instrumentation {
    @Override public void onCreate(Bundle args) { super.onCreate(args); start(); }
    private WebView web;
    private Activity activity;
    private String eval(String expression) throws Exception {
        CountDownLatch latch = new CountDownLatch(1);
        AtomicReference<String> result = new AtomicReference<>();
        runOnMainSync(() -> web.evaluateJavascript(expression, value -> {result.set(value); latch.countDown();}));
        if (!latch.await(15, TimeUnit.SECONDS)) throw new Exception("JavaScript callback timed out");
        return result.get();
    }
    private void ready() throws Exception {
        Intent launch = getTargetContext().getPackageManager().getLaunchIntentForPackage(getTargetContext().getPackageName());
        launch.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
        activity = startActivitySync(launch);
        java.lang.reflect.Field field = activity.getClass().getDeclaredField("web"); field.setAccessible(true); web = (WebView)field.get(activity);
        for(int i=0;i<90;i++){if("true".equals(eval("typeof catalog !== 'undefined' && !!catalog && catalog.rehab.length === 53")))return; Thread.sleep(500);}
        throw new Exception("Local catalog did not open");
    }
    public final class Fixtures {
        @JavascriptInterface public String video(String name) {
            if(!"shoulder".equals(name) && !"squat".equals(name)) return "";
            try(InputStream stream=getContext().getAssets().open(name+".mp4"); ByteArrayOutputStream out=new ByteArrayOutputStream()){
                byte[] buffer=new byte[65536];int n;while((n=stream.read(buffer))>0)out.write(buffer,0,n);
                return android.util.Base64.encodeToString(out.toByteArray(),android.util.Base64.NO_WRAP);
            }catch(Exception e){return "";}
        }
    }
    @Override public void onStart(){
        Bundle result = new Bundle();
        try {
            ready();
            runOnMainSync(() -> web.addJavascriptInterface(new Fixtures(),"QaFixtures"));
            // Reload so Android exposes the test-only bridge, then wait for real bundled catalog.
            runOnMainSync(() -> web.reload());Thread.sleep(1500);
            String script="window.__qa={status:'running'};(async()=>{try{"
                + "const init=await initModel(getSpec('shoulder_abduction'));const c=new OffscreenCanvas(640,480);c.getContext('2d').fillRect(0,0,640,480);const bitmap=c.transferToImageBitmap();const blank=await requestWorker('frame',{image:bitmap,timestamp:0},[bitmap]);killWorker();"
                + "const make=name=>new File([Uint8Array.from(atob(QaFixtures.video(name)),c=>c.charCodeAt(0))],name+'.mp4',{type:'video/mp4'});"
                + "const rawTrace=[];const originalConsume=E.Engine.prototype.consume;E.Engine.prototype.consume=function(t,raw){rawTrace.push([t,raw]);return originalConsume.call(this,t,raw);};"
                + "detail('shoulder_abduction');let f=make('shoulder');selectFile(f);await analyzeFile(f,'left');const shoulder=data.records.at(-1);if(!shoulder||shoulder.exercise!=='shoulder_abduction')throw Error('Shoulder analysis failed: '+document.body.innerText);"
                + "const p=E.propose(data.records,catalog,Date.now(),data.profile);if(!p.items.length)throw Error('No usable assessment for plan; report='+JSON.stringify(shoulder.report)+';raw='+JSON.stringify(rawTrace));E.Engine.prototype.consume=originalConsume;"
                + "setTab('plan');const form=document.querySelector('#plan-form');if(!form)throw Error('Plan form missing');form.querySelectorAll('input[type=checkbox]').forEach(x=>x.checked=true);form.querySelector('select').value=1;form.requestSubmit();if(!data.plan)throw Error('Plan not saved');const item=data.plan.items[0];document.querySelector('#plan-main').click();if(!training)throw Error('Training entry did not open');selectFile(f);await analyzeFile(f,'left');"
                + "document.querySelector('#pain').value=0;document.querySelector('#fatigue').value=0;document.querySelector('#feedback').requestSubmit();if(!data.plan.items[0].complete)throw Error('Training feedback did not complete plan');"
                + "detail('fitness_squat');f=make('squat');selectFile(f);await analyzeFile(f,'left');const squat=data.records.at(-1);if(squat.exercise!=='fitness_squat')throw Error('Squat report failed');"
                + "const h=await initModel(getSpec('index_pip_flexion'));const hc=new OffscreenCanvas(320,240);hc.getContext('2d').fillRect(0,0,320,240);const image=hc.transferToImageBitmap();await requestWorker('frame',{image,timestamp:0},[image]);killWorker();"
                + "const backup={type:'rehab-offline-backup',version:1,data:JSON.parse(JSON.stringify(data))};validateBackup(backup);setTab('history');if(!document.querySelector('[data-record]'))throw Error('History did not render');bodyPage();if(!document.body.innerText.includes('身体汇总'))throw Error('Body summary missing');"
                + "window.__qa={status:'passed',shoulder:shoulder.report,squat:squat.report,plan:data.plan,blank:blank.result,records:data.records.length};"
                + "}catch(e){killWorker();window.__qa={status:'failed',error:String(e.stack||e),text:document.body.innerText};}})();true";
            eval(script);
            String evidence=null;
            for(int i=0;i<1200;i++){
                evidence=eval("JSON.stringify(window.__qa)");
                if(evidence.contains("\\\"passed\\\""))break;
                if(evidence.contains("\\\"failed\\\""))throw new Exception(evidence);
                Thread.sleep(500);
            }
            if(evidence==null||!evidence.contains("\\\"passed\\\""))throw new Exception("Inference timeout: "+evidence);
            String count=eval("data.records.length");
            runOnMainSync(() -> activity.finish());Thread.sleep(500);ready();
            if(!count.equals(eval("data.records.length")))throw new Exception("Records lost after activity reopen");
            result.putString("evidence",evidence);result.putString("reopen","passed");finish(Activity.RESULT_OK,result);
        }catch(Throwable e){result.putString("failure",e.toString());finish(Activity.RESULT_CANCELED,result);}
    }
}
