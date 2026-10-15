package cn.tele.rehabilitation.offline;

import android.Manifest;
import android.app.*;
import android.bluetooth.*;
import android.bluetooth.le.*;
import android.content.*;
import android.content.pm.PackageManager;
import android.hardware.*;
import android.location.LocationManager;
import android.os.*;
import android.widget.*;
import org.json.*;
import java.util.*;

/** Reuses Android dialogs in the existing settings menu; no changes to the web design. */
final class MotionPanel {
    static final int PERMISSION=46;
    private final MainActivity activity;
    private final MotionDb db;
    private final Handler handler=new Handler(Looper.getMainLooper());
    private final java.util.concurrent.ExecutorService exportWork=java.util.concurrent.Executors.newSingleThreadExecutor();
    private volatile String owner="";
    private volatile boolean personal;
    private AlertDialog dialog;
    private BluetoothLeScanner scanner;
    private ScanCallback scan;
    private int scanGeneration;
    private Runnable scanTimeout;
    private String pendingOwner,pendingAction;
    private boolean pendingGps;
    private final java.util.LinkedHashMap<String,BluetoothDevice> devices=new java.util.LinkedHashMap<>();
    MotionPanel(MainActivity activity){this.activity=activity;db=new MotionDb(activity);if(MotionService.current==null)db.interrupt();}
    void bind(String value,boolean personal){
        if(value==null||!value.matches("[a-fA-F0-9-]{36}"))value="";
        final String next=value;final boolean usable=personal&&!next.isEmpty();
        if(!owner.equals(next)||this.personal!=usable){owner=next;this.personal=usable;activity.runOnUiThread(()->{
            MotionService.stopOtherOwner(usable?next:"");stopScan();if(dialog!=null)dialog.dismiss();pendingAction=null;
        });}
    }
    private boolean allowed(String p){return activity.checkSelfPermission(p)==PackageManager.PERMISSION_GRANTED;}
    private void notice(String s){Toast.makeText(activity,s,Toast.LENGTH_LONG).show();}
    private String chosen(){return activity.getSharedPreferences("phone-motion",Context.MODE_PRIVATE).getString("device:"+owner,"");}
    void open(){
        if(!personal){notice("请先从设置返回个人档案，再记录运动");return;}
        if(dialog!=null)dialog.dismiss();
        String[] choices={"开始记录","结束并保存","选择心率设备","取消心率设备","查看运动记录","查看今天汇总"};
        dialog=new AlertDialog.Builder(activity).setTitle("运动与心率").setItems(choices,(d,which)->{
            if(which==0)startDialog();else if(which==1){activity.startService(new Intent(activity,MotionService.class).setAction(MotionService.STOP));notice("已结束；记录保存在本机");}
            else if(which==2)permission("scan",false);
            else if(which==3){if(MotionService.current!=null){notice("请先结束本次记录，再更换设备");return;}activity.getSharedPreferences("phone-motion",Context.MODE_PRIVATE).edit().remove("device:"+owner).apply();notice("已取消选择，不影响小米运动健康中的绑定");}
            else if(which==4)history();else today();
        }).setPositiveButton("查看当前状态",(d,w)->live()).setNegativeButton("关闭",null).create();dialog.show();
    }
    private void startDialog(){
        if(MotionService.current!=null){live();return;}
        CheckBox gps=new CheckBox(activity);gps.setText("使用 GPS 记录路程（建议室外）");gps.setPadding(36,8,36,8);
        dialog=new AlertDialog.Builder(activity).setTitle("开始运动记录").setMessage("手机随身携带，记录步数和时长。已选择心率设备时一并接收心率。记录会显示在通知栏，结束后保存到个人档案。位置和心率只保存在本机，不自动共享。")
            .setView(gps).setPositiveButton("开始",(d,w)->permission("start",gps.isChecked())).setNegativeButton("取消",null).create();dialog.show();
    }
    private void permission(String action,boolean gps){
        if(!personal)return;
        if(action.equals("scan")&&MotionService.current!=null){notice("请先结束本次记录，再选择设备");return;}
        pendingOwner=owner;pendingAction=action;pendingGps=gps;ArrayList<String> required=new ArrayList<>();
        if(action.equals("start")){
            if(!allowed(Manifest.permission.ACTIVITY_RECOGNITION))required.add(Manifest.permission.ACTIVITY_RECOGNITION);
            if(gps&&!allowed(Manifest.permission.ACCESS_FINE_LOCATION)){required.add(Manifest.permission.ACCESS_FINE_LOCATION);required.add(Manifest.permission.ACCESS_COARSE_LOCATION);}
            if(Build.VERSION.SDK_INT>=33&&!allowed(Manifest.permission.POST_NOTIFICATIONS))required.add(Manifest.permission.POST_NOTIFICATIONS);
        }
        if(action.equals("scan")||!chosen().isEmpty()){
            if(Build.VERSION.SDK_INT>=31){if(!allowed(Manifest.permission.BLUETOOTH_CONNECT))required.add(Manifest.permission.BLUETOOTH_CONNECT);if(action.equals("scan")&&!allowed(Manifest.permission.BLUETOOTH_SCAN))required.add(Manifest.permission.BLUETOOTH_SCAN);}
            else if(action.equals("scan")&&!allowed(Manifest.permission.ACCESS_FINE_LOCATION)){required.add(Manifest.permission.ACCESS_FINE_LOCATION);required.add(Manifest.permission.ACCESS_COARSE_LOCATION);}
        }
        if(required.isEmpty())permissionsReturned();else activity.requestPermissions(required.toArray(new String[0]),PERMISSION);
    }
    void permissionsReturned(){
        String action=pendingAction;boolean gps=pendingGps;pendingAction=null;
        if(action==null||!personal||!owner.equals(pendingOwner)||activity.isFinishing())return;
        if(action.equals("scan")){scanDevices();return;}
        boolean steps=allowed(Manifest.permission.ACTIVITY_RECOGNITION)&&((SensorManager)activity.getSystemService(Context.SENSOR_SERVICE)).getDefaultSensor(Sensor.TYPE_STEP_COUNTER)!=null;
        boolean location=gps&&allowed(Manifest.permission.ACCESS_FINE_LOCATION)&&((LocationManager)activity.getSystemService(Context.LOCATION_SERVICE)).isLocationEnabled();
        String device=chosen();boolean ble=!device.isEmpty()&&(Build.VERSION.SDK_INT<31||allowed(Manifest.permission.BLUETOOTH_CONNECT));
        if(!steps&&!location&&!ble){notice("没有可用的数据源。请允许计步或精确定位，再重新开始");return;}
        if(gps&&!location)notice("定位暂不可用，先记录其他已授权的数据");
        try{
            Intent request=new Intent(activity,MotionService.class).putExtra("owner",owner).putExtra("gps",location);
            if(ble)request.putExtra("address",device);
            activity.startForegroundService(request);handler.postDelayed(()->{if(personal)live();},600);
        }catch(Exception e){notice("无法开始记录，请回到应用后重试");}
    }
    private void scanDevices(){
        if(Build.VERSION.SDK_INT>=31&&(!allowed(Manifest.permission.BLUETOOTH_SCAN)||!allowed(Manifest.permission.BLUETOOTH_CONNECT))||Build.VERSION.SDK_INT<31&&!allowed(Manifest.permission.ACCESS_FINE_LOCATION)){notice("未授权附近设备，仍可使用手机计步和 GPS");return;}
        BluetoothAdapter adapter=((BluetoothManager)activity.getSystemService(Context.BLUETOOTH_SERVICE)).getAdapter();
        try{if(adapter==null||!adapter.isEnabled()){notice("请先开启手机蓝牙");return;}
            stopScan();final int generation=++scanGeneration;devices.clear();ArrayList<String> labels=new ArrayList<>();ArrayList<String> addresses=new ArrayList<>();
            ArrayAdapter<String> rows=new ArrayAdapter<>(activity,android.R.layout.simple_list_item_1,labels);
            ListView list=new ListView(activity);list.setAdapter(rows);
            final String scanOwner=owner;
            java.util.function.Consumer<BluetoothDevice> add=device->{
                if(!personal||!owner.equals(scanOwner)||devices.containsKey(device.getAddress())||devices.size()>=60)return;
                devices.put(device.getAddress(),device);addresses.add(device.getAddress());String name=device.getName();labels.add((name==null?"附近蓝牙设备":name.substring(0,Math.min(60,name.length())))+" · "+device.getAddress().substring(12));rows.notifyDataSetChanged();
            };
            for(BluetoothDevice device:adapter.getBondedDevices())if(device.getType()!=BluetoothDevice.DEVICE_TYPE_CLASSIC)add.accept(device);
            dialog=new AlertDialog.Builder(activity).setTitle("选择心率设备").setMessage("靠近手环并开启心率广播。选择设备后，在开始记录时检查标准心率服务；没有广播的设备不会产生心率记录。无需解绑或重置。")
                .setView(list).setNegativeButton("取消",null).create();
            dialog.setOnDismissListener(d->stopScan());
            list.setOnItemClickListener((parent,view,index,id)->{if(!personal||!owner.equals(scanOwner))return;activity.getSharedPreferences("phone-motion",Context.MODE_PRIVATE).edit().putString("device:"+owner,addresses.get(index)).apply();dialog.dismiss();notice("已选择。开始记录后检查心率连接");});dialog.show();
            scanner=adapter.getBluetoothLeScanner();scan=new ScanCallback(){
                @Override public void onScanResult(int type,ScanResult result){handler.post(()->{if(scan!=null&&generation==scanGeneration&&owner.equals(scanOwner))try{add.accept(result.getDevice());}catch(Exception ignored){}});}
                @Override public void onScanFailed(int error){handler.post(()->{if(generation!=scanGeneration)return;notice("扫描未完成，可选择已绑定设备或稍后重试");stopScan();});}
            };
            scanner.startScan(Collections.emptyList(),new ScanSettings.Builder().setScanMode(ScanSettings.SCAN_MODE_LOW_LATENCY).build(),scan);
            final AlertDialog scanDialog=dialog;
            scanTimeout=()->{stopScan();if(scanDialog.isShowing())scanDialog.setTitle(labels.isEmpty()?"未发现设备；检查广播开关后重试":"扫描已结束，请选择设备");};handler.postDelayed(scanTimeout,25000);
        }catch(Exception e){stopScan();notice("无法扫描，检查蓝牙与附近设备权限");}
    }
    private void stopScan(){scanGeneration++;if(scanTimeout!=null)handler.removeCallbacks(scanTimeout);scanTimeout=null;if(scanner!=null&&scan!=null)try{scanner.stopScan(scan);}catch(Exception ignored){}scanner=null;scan=null;}
    private JSONObject status()throws Exception{MotionService s=MotionService.current;return s==null?new JSONObject().put("recording",false):s.status(owner);}
    private static String number(JSONObject v,String key,String format){return v.isNull(key)?"—":String.format(Locale.CHINA,format,v.optDouble(key));}
    private static String pace(JSONObject v){if(v.isNull("pace_s_km"))return "—";long seconds=Math.round(v.optDouble("pace_s_km"));return String.format(Locale.CHINA,"%d′%02d″ /km",seconds/60,seconds%60);}
    private static String summaryText(JSONObject s){
        String steps=s.optLong("step_coverage_ms")>0?s.optLong("observed_steps")+" 步":"—";
        return "记录内步数  "+steps+"\n路程  "+(s.isNull("distance_m")?"—":String.format(Locale.CHINA,"%.2f km",s.optDouble("distance_m")/1000))+"\n记录时长  "+s.optLong("recorded_duration_ms")/60000+" 分钟\n平均心率  "+number(s,"heart_mean","%.0f")+" bpm\n心率范围  "+number(s,"heart_min","%.0f")+"—"+number(s,"heart_max","%.0f")+" bpm\n\n只统计实际记录时段。未采集的时间不补齐，运动心率不作为静息心率。";
    }
    private void live(){
        if(!personal)return;TextView text=new TextView(activity);text.setTextSize(18);text.setPadding(40,20,40,20);
        dialog=new AlertDialog.Builder(activity).setTitle("当前运动").setView(text).setPositiveButton("关闭",null).setNeutralButton("结束记录",(d,w)->{activity.startService(new Intent(activity,MotionService.class).setAction(MotionService.STOP));}).create();
        final AlertDialog currentDialog=dialog;
        Runnable update=new Runnable(){public void run(){if(!currentDialog.isShowing()||!personal)return;try{JSONObject s=status();
            if(!s.optBoolean("recording")){text.setText(MotionService.lastError.isEmpty()?"当前未记录。开始后将显示实时数据，结束后可查看记录。":MotionService.lastError);return;}
            text.setText("步数  "+number(s,"observed_steps","%.0f")+"\n时长  "+s.optLong("duration_ms")/60000+" 分钟\n路程  "+(s.isNull("distance_m")?"—":String.format(Locale.CHINA,"%.2f km",s.optDouble("distance_m")/1000))+"\n速度  "+number(s,"speed_m_s","%.2f")+" m/s\n配速  "+pace(s)+"\n心率  "+number(s,"heart_bpm","%.0f")+" bpm\n\n"+s.optString("step_state")+"\n"+s.optString("gps_state")+"\n"+s.optString("heart_state"));
        }catch(Exception e){text.setText("记录暂不可读取，请重新打开");}handler.postDelayed(this,1000);}};
        dialog.show();update.run();
    }
    private void history(){try{
        JSONArray rows=db.history(owner,100);if(rows.length()==0){notice("暂无运动记录，先开始一次记录");return;}
        String[] names=new String[rows.length()];java.text.DateFormat date=new java.text.SimpleDateFormat("MM-dd HH:mm",Locale.CHINA);
        for(int i=0;i<rows.length();i++){JSONObject r=rows.getJSONObject(i);names[i]=date.format(new Date(r.getLong("started")))+" · "+stateLabel(r.getString("state"));}
        final String recordedOwner=owner;
        dialog=new AlertDialog.Builder(activity).setTitle("运动记录（最近100次）").setItems(names,(d,w)->{if(!personal||!owner.equals(recordedOwner))return;try{JSONObject row=rows.getJSONObject(w);String id=row.getString("session_id");
            dialog=new AlertDialog.Builder(activity).setTitle(names[w]).setMessage(summaryText(row)).setPositiveButton("关闭",null).setNeutralButton("导出记录",(a,b)->{
                if(!personal||!owner.equals(recordedOwner))return;notice("正在准备记录");
                exportWork.execute(()->{try{byte[] data=db.export(recordedOwner,id).toString().getBytes(java.nio.charset.StandardCharsets.UTF_8);
                    activity.runOnUiThread(()->{if(!personal||!owner.equals(recordedOwner)||activity.isDestroyed())return;activity.saveDocumentBytes(data,"application/json","安康-运动记录-"+id+".json");});
                }catch(Exception e){activity.runOnUiThread(()->{if(!activity.isDestroyed())notice("记录暂不可导出");});}});
            }).create();dialog.show();
        }catch(Exception e){notice("记录暂不可读取");}}).setNegativeButton("关闭",null).create();dialog.show();
    }catch(Exception e){notice("记录暂不可读取");}}
    private static String stateLabel(String s){return s.equals("recording")?"记录中":s.equals("finished")?"已完成":s.equals("owner_changed")?"切换档案结束":s.equals("limit")?"已达记录上限":"记录中断";}
    private void today(){try{dialog=new AlertDialog.Builder(activity).setTitle("今天已记录的运动").setMessage(summaryText(db.summary(owner,null,MotionDb.day(System.currentTimeMillis())))).setPositiveButton("关闭",null).create();dialog.show();}catch(Exception e){notice("汇总暂不可读取");}}
    String read(String requestedOwner){try{if(!personal||!owner.equals(requestedOwner))return "{\"available\":false}";
        MotionService s=MotionService.current;
        JSONObject result=new JSONObject().put("available",true).put("source","PHONE_SENSORS_BLE_HRS").put("current",s==null?new JSONObject().put("recording",false):s.status(requestedOwner)).put("today",db.summary(requestedOwner,null,MotionDb.day(System.currentTimeMillis()))).put("records",db.history(requestedOwner,100));
        return personal&&owner.equals(requestedOwner)?result.toString():"{\"available\":false}";
    }catch(Exception e){return "{\"available\":false,\"error\":\"记录暂不可读取\"}";}}
    void pause(){stopScan();}
    void close(){stopScan();handler.removeCallbacksAndMessages(null);exportWork.shutdownNow();if(dialog!=null)dialog.dismiss();db.close();}
}
