package cn.tele.rehabilitation.offline.qa;

import android.app.*;
import android.content.*;
import android.os.*;
import android.graphics.Bitmap;
import android.webkit.WebView;
import org.json.*;
import java.io.FileOutputStream;
import java.lang.reflect.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicReference;

/** Fresh, isolated emulator only. DB contracts use the QA package, never personal history. */
public final class MotionSmoke extends Instrumentation {
    private WebView web;
    private int assertions;
    private void check(boolean ok,String label){assertions++;if(!ok)throw new AssertionError(label);}
    private String eval(String code)throws Exception{CountDownLatch done=new CountDownLatch(1);AtomicReference<String> value=new AtomicReference<>();runOnMainSync(()->web.evaluateJavascript(code,v->{value.set(v);done.countDown();}));if(!done.await(15,TimeUnit.SECONDS))throw new Exception("JS timeout");return value.get();}
    private void ready()throws Exception{for(int i=0;i<120;i++){if("true".equals(eval("!!window.PhoneLocal&&!!window.PhoneLocal.store&&!!document.querySelector('#nav a')"))){eval("PhoneLocal.ready.then(()=>window.__motionReady=true)");for(int n=0;n<30;n++){if("true".equals(eval("window.__motionReady===true")))return;Thread.sleep(100);} }Thread.sleep(500);}throw new Exception("UI timeout");}
    private void image(String name)throws Exception{Bitmap b=getUiAutomation().takeScreenshot();try(FileOutputStream out=new FileOutputStream(new java.io.File(getTargetContext().getExternalFilesDir(null),name))){b.compress(Bitmap.CompressFormat.PNG,100,out);}finally{b.recycle();}}
    @Override public void onCreate(Bundle args){super.onCreate(args);start();}
    @Override public void onStart(){Bundle result=new Bundle();Object database=null;try{
        Context testDbContext=new ContextWrapper(getTargetContext()){
            @Override public java.io.File getDatabasePath(String name){return super.getDatabasePath("qa-motion-"+name);}
            @Override public android.database.sqlite.SQLiteDatabase openOrCreateDatabase(String name,int mode,android.database.sqlite.SQLiteDatabase.CursorFactory factory){return super.openOrCreateDatabase("qa-motion-"+name,mode,factory);}
            @Override public android.database.sqlite.SQLiteDatabase openOrCreateDatabase(String name,int mode,android.database.sqlite.SQLiteDatabase.CursorFactory factory,android.database.DatabaseErrorHandler error){return super.openOrCreateDatabase("qa-motion-"+name,mode,factory,error);}
        };
        Class<?> cls=Class.forName("cn.tele.rehabilitation.offline.MotionDb");database=cls.getConstructor(Context.class).newInstance(testDbContext);
        final String owner=java.util.UUID.randomUUID().toString(),other=java.util.UUID.randomUUID().toString();
        Method start=cls.getMethod("start",String.class,boolean.class,boolean.class,boolean.class,long.class),sample=cls.getMethod("sample",String.class,int.class,String.class,JSONObject.class,long.class,long.class),summary=cls.getMethod("summary",String.class,String.class,String.class);
        String id=(String)start.invoke(database,owner,true,true,true,100000L);
        sample.invoke(database,id,1,"steps",new JSONObject().put("counter",10000).put("delta",JSONObject.NULL).put("interval_ms",0),100000L,1000L);
        JSONObject before=(JSONObject)summary.invoke(database,owner,id,null);check(before.isNull("observed_steps")&&before.isNull("heart_mean")&&before.isNull("distance_m"),"missing is not zero");
        sample.invoke(database,id,2,"steps",new JSONObject().put("delta",3).put("interval_ms",1000),101000L,2000L);
        sample.invoke(database,id,3,"gps",new JSONObject().put("segment_m",11.2),102000L,3000L);
        sample.invoke(database,id,4,"heart",new JSONObject().put("bpm",72),103000L,4000L);
        sample.invoke(database,id,5,"heart",new JSONObject().put("bpm",80),108000L,9000L);
        sample.invoke(database,id,6,"clock",new JSONObject().put("delta_ms",8000),108000L,9000L);
        JSONObject saved=(JSONObject)summary.invoke(database,owner,id,null);
        check(saved.getLong("observed_steps")==3&&saved.getLong("step_coverage_ms")==1000,"counter delta saved");
        check(Math.abs(saved.getDouble("distance_m")-11.2)<.0001,"route sum saved");
        check(saved.getDouble("heart_mean")==76&&saved.getInt("heart_min")==72&&saved.getInt("heart_max")==80,"HR samples summarized");
        check(saved.getLong("recorded_duration_ms")==8000&&!saved.getBoolean("complete_day"),"coverage truthful");
        check(((JSONObject)summary.invoke(database,other,id,null)).getInt("sample_count")==0,"owner-scoped query");
        JSONObject exported=(JSONObject)cls.getMethod("export",String.class,String.class).invoke(database,owner,id);
        check(exported.getJSONArray("samples").length()==6&&exported.getString("owner").equals(owner),"owner export");
        boolean denied=false;try{cls.getMethod("export",String.class,String.class).invoke(database,other,id);}catch(InvocationTargetException e){denied=true;}check(denied,"foreign export refused");
        cls.getMethod("close").invoke(database);database=cls.getConstructor(Context.class).newInstance(testDbContext);
        check(((JSONObject)summary.invoke(database,owner,id,null)).getDouble("heart_mean")==76,"reopen persistence");
        cls.getMethod("interrupt").invoke(database);JSONArray records=(JSONArray)cls.getMethod("history",String.class,int.class).invoke(database,owner,100);
        check(records.getJSONObject(0).getString("state").equals("interrupted")&&records.getJSONObject(0).isNull("ended"),"interruption not finished");
        String zero=(String)start.invoke(database,owner,true,false,false,200000L);
        sample.invoke(database,zero,1,"steps",new JSONObject().put("delta",0).put("interval_ms",1000),201000L,10000L);
        check(((JSONObject)summary.invoke(database,owner,zero,null)).getLong("observed_steps")==0,"observed zero retained");
        cls.getMethod("end",String.class,String.class,long.class).invoke(database,zero,"finished",202000L);
        check(((JSONArray)cls.getMethod("history",String.class,int.class).invoke(database,owner,100)).getJSONObject(0).getString("state").equals("finished"),"explicit stop saved");
        Intent launch=getTargetContext().getPackageManager().getLaunchIntentForPackage(getTargetContext().getPackageName()).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
        Activity app=startActivitySync(launch);Field field=app.getClass().getDeclaredField("web");field.setAccessible(true);web=(WebView)field.get(app);ready();
        eval("PhoneLocal.selectProfile(PhoneStore.LIN_KEY)");Thread.sleep(700);ready();
        check("false".equals(eval("JSON.parse(OfflineAndroid.motionRead(PhoneLocal.store.value.owner)).available")),"fixture not capture owner");
        eval("PhoneLocal.selectProfile(PhoneStore.KEY)");Thread.sleep(700);ready();
        check("true".equals(eval("JSON.parse(OfflineAndroid.motionRead(PhoneLocal.store.value.owner)).available")),"personal owner bound");
        check("false".equals(eval("JSON.parse(OfflineAndroid.motionRead('"+other+"')).available")),"bridge owner denied");
        image("motion-original-home.png");eval("OfflineAndroid.motionSettings()");Thread.sleep(500);image("motion-menu.png");
        // Exercise the actual native Android service with granted GPS, not a substituted web recorder.
        getUiAutomation().grantRuntimePermission(getTargetContext().getPackageName(),"android.permission.ACCESS_FINE_LOCATION");
        getUiAutomation().grantRuntimePermission(getTargetContext().getPackageName(),"android.permission.ACTIVITY_RECOGNITION");
        getUiAutomation().grantRuntimePermission(getTargetContext().getPackageName(),"android.permission.POST_NOTIFICATIONS");
        Field panelField=app.getClass().getDeclaredField("motionPanel");panelField.setAccessible(true);Object panel=panelField.get(app);
        Method begin=panel.getClass().getDeclaredMethod("permission",String.class,boolean.class);begin.setAccessible(true);
        Field dialogField=panel.getClass().getDeclaredField("dialog");dialogField.setAccessible(true);
        String personalOwner=new JSONArray("["+eval("PhoneLocal.store.value.owner")+"]").getString(0);
        Intent record=new Intent().setClassName(getTargetContext(),"cn.tele.rehabilitation.offline.MotionService").putExtra("owner",personalOwner).putExtra("gps",true);
        runOnMainSync(()->{try{AlertDialog existing=(AlertDialog)dialogField.get(panel);if(existing!=null)existing.dismiss();begin.invoke(panel,"start",true);}catch(Exception e){throw new RuntimeException(e);}});Thread.sleep(1500);
        check("true".equals(eval("JSON.parse(OfflineAndroid.motionRead(PhoneLocal.store.value.owner)).current.recording")),"FGS starts");
        check("true".equals(eval("JSON.parse(OfflineAndroid.motionRead(PhoneLocal.store.value.owner)).current.heart_bpm==null")),"no watch no HR");
        check("true".equals(eval("Object.hasOwn(JSON.parse(OfflineAndroid.motionRead(PhoneLocal.store.value.owner)).current,'pace_s_km')")),"release pace field present");
        image("motion-live-no-watch.png");
        eval("OfflineAndroid.motionBind('',false)");Thread.sleep(700);
        Class<?> service=Class.forName("cn.tele.rehabilitation.offline.MotionService");Field current=service.getDeclaredField("current");current.setAccessible(true);check(current.get(null)==null,"owner change stops FGS");
        eval("OfflineAndroid.motionBind(PhoneLocal.store.value.owner,true)");Thread.sleep(300);
        check("true".equals(eval("JSON.parse(OfflineAndroid.motionRead(PhoneLocal.store.value.owner)).records.at(0).state==='owner_changed'")),"owner stop survives DB");
        // Restart remains explicitly started by the user; stopping is durable.
        runOnMainSync(()->app.startForegroundService(record));Thread.sleep(700);
        runOnMainSync(()->app.startService(new Intent().setClassName(getTargetContext(),"cn.tele.rehabilitation.offline.MotionService").setAction("cn.tele.rehabilitation.offline.STOP_MOTION")));Thread.sleep(700);
        check("true".equals(eval("JSON.parse(OfflineAndroid.motionRead(PhoneLocal.store.value.owner)).records.at(0).state==='finished'")),"normal FGS stop persisted");
        result.putString("result","PASS");result.putInt("assertions",assertions);result.putString("boundary","TEST DB and emulator; no physical band, GPS accuracy or phone step validation");finish(Activity.RESULT_OK,result);
    }catch(Throwable e){e.printStackTrace();result.putString("result","FAIL");result.putString("error",e.toString()+(e.getCause()==null?"":" cause: "+e.getCause()));result.putInt("assertions",assertions);finish(Activity.RESULT_CANCELED,result);}
    finally{if(database!=null)try{database.getClass().getMethod("close").invoke(database);}catch(Exception ignored){}}
    }
}
