package cn.tele.rehabilitation.offline;

import android.Manifest;
import android.app.*;
import android.bluetooth.*;
import android.content.*;
import android.content.pm.PackageManager;
import android.content.pm.ServiceInfo;
import android.hardware.*;
import android.location.*;
import android.os.*;
import org.json.JSONObject;
import java.util.UUID;

/** Explicit user-started collection. No boot receiver, restart, upload or vendor authentication. */
public final class MotionService extends Service implements SensorEventListener,LocationListener {
    public static final String STOP="cn.tele.rehabilitation.offline.STOP_MOTION";
    static volatile MotionService current;
    static volatile String lastError="";
    static final UUID HRS=UUID.fromString("0000180d-0000-1000-8000-00805f9b34fb");
    static final UUID HRM=UUID.fromString("00002a37-0000-1000-8000-00805f9b34fb");
    private static final UUID CCCD=UUID.fromString("00002902-0000-1000-8000-00805f9b34fb");
    private final Handler handler=new Handler(Looper.getMainLooper());
    private MotionDb db;
    private SensorManager sensors;
    private LocationManager locations;
    private BluetoothGatt gatt;
    private volatile String session,owner;
    private String address;
    private boolean stepsEnabled,gpsEnabled,hrEnabled,hasGpsFix;
    private volatile boolean ending;
    private int sequence,retries,connectionGeneration;
    private long startElapsed,lastClock,lastCounterAt=-1,lastCounterWall=-1,lastHeart=-1,lastSavedHeart=-1,lastFix=-1;
    private long observedSteps,coverage;
    private double distance;
    private Integer heart;
    private Double speed;
    private String stepState="尚未开始",gpsState="未启用",heartState="未连接";
    private final MotionMath.Counter counter=new MotionMath.Counter();
    private final MotionMath.Track track=new MotionMath.Track();
    private final Runnable tick=new Runnable(){public void run(){
        if(ending||session==null)return;
        try{clock();if(SystemClock.elapsedRealtime()-startElapsed>=24*60*60*1000L){finish("limit");return;}
            ((NotificationManager)getSystemService(NOTIFICATION_SERVICE)).notify(73,notification());
        }catch(Exception e){fail("记录保存失败，请结束后重试");return;}
        handler.postDelayed(this,10000);
    }};
    private final BroadcastReceiver bluetoothState=new BroadcastReceiver(){public void onReceive(Context c,Intent i){
        if(i.getIntExtra(BluetoothAdapter.EXTRA_STATE,-1)==BluetoothAdapter.STATE_OFF){heart=null;lastHeart=-1;heartState="蓝牙已关闭";closeGatt();}
        else if(i.getIntExtra(BluetoothAdapter.EXTRA_STATE,-1)==BluetoothAdapter.STATE_ON&&hrEnabled&&gatt==null){retries=0;connectHeart();}
    }};
    @Override public void onCreate(){super.onCreate();db=new MotionDb(this);db.interrupt();current=this;lastError="";}
    private boolean allowed(String p){return checkSelfPermission(p)==PackageManager.PERMISSION_GRANTED;}
    @Override public int onStartCommand(Intent intent,int flags,int startId){
        if(intent==null||STOP.equals(intent.getAction())){finish("finished");return START_NOT_STICKY;}
        if(session!=null)return START_NOT_STICKY;
        owner=intent.getStringExtra("owner");address=intent.getStringExtra("address");
        if(owner==null||!owner.matches("[a-fA-F0-9-]{36}")){fail("请先打开本人档案");return START_NOT_STICKY;}
        sensors=(SensorManager)getSystemService(SENSOR_SERVICE);locations=(LocationManager)getSystemService(LOCATION_SERVICE);
        Sensor sensor=sensors.getDefaultSensor(Sensor.TYPE_STEP_COUNTER);
        stepsEnabled=allowed(Manifest.permission.ACTIVITY_RECOGNITION)&&sensor!=null;
        gpsEnabled=intent.getBooleanExtra("gps",false)&&allowed(Manifest.permission.ACCESS_FINE_LOCATION)&&locations.isLocationEnabled();
        hrEnabled=address!=null&&BluetoothAdapter.checkBluetoothAddress(address)&&(Build.VERSION.SDK_INT<31||allowed(Manifest.permission.BLUETOOTH_CONNECT));
        int types=(stepsEnabled?ServiceInfo.FOREGROUND_SERVICE_TYPE_HEALTH:0)|(gpsEnabled?ServiceInfo.FOREGROUND_SERVICE_TYPE_LOCATION:0)|(hrEnabled?ServiceInfo.FOREGROUND_SERVICE_TYPE_CONNECTED_DEVICE:0);
        if(types==0){fail("没有可用的数据源，请授权计步、精确定位或选择心率设备");return START_NOT_STICKY;}
        try{
            NotificationChannel channel=new NotificationChannel("phone-motion","运动与心率记录",NotificationManager.IMPORTANCE_LOW);
            ((NotificationManager)getSystemService(NOTIFICATION_SERVICE)).createNotificationChannel(channel);
            startForeground(73,notification(),types);
            startElapsed=lastClock=SystemClock.elapsedRealtime();session=db.start(owner,stepsEnabled,gpsEnabled,hrEnabled,System.currentTimeMillis());
            stepState=stepsEnabled?"等待计步传感器":"计步未授权或手机不支持";
            if(stepsEnabled&&!sensors.registerListener(this,sensor,SensorManager.SENSOR_DELAY_NORMAL)){stepState="计步传感器暂不可用";}
            if(gpsEnabled){gpsState="等待卫星定位";try{locations.requestLocationUpdates(LocationManager.GPS_PROVIDER,3000,0,this);}catch(Exception e){gpsState="定位暂不可用，其他记录继续";}}
            else if(intent.getBooleanExtra("gps",false))gpsState="未授权精确定位或定位已关闭";
            if(Build.VERSION.SDK_INT>=33)registerReceiver(bluetoothState,new IntentFilter(BluetoothAdapter.ACTION_STATE_CHANGED),Context.RECEIVER_NOT_EXPORTED);
            else registerReceiver(bluetoothState,new IntentFilter(BluetoothAdapter.ACTION_STATE_CHANGED));
            if(hrEnabled)connectHeart();handler.postDelayed(tick,10000);
        }catch(Exception e){fail("无法开始记录，请检查权限和手机定位开关");}
        return START_NOT_STICKY;
    }
    private Notification notification(){
        Intent open=new Intent(this,MainActivity.class).setFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP|Intent.FLAG_ACTIVITY_CLEAR_TOP).putExtra("motion_panel",true);
        PendingIntent activity=PendingIntent.getActivity(this,73,open,PendingIntent.FLAG_UPDATE_CURRENT|PendingIntent.FLAG_IMMUTABLE);
        PendingIntent stop=PendingIntent.getService(this,74,new Intent(this,MotionService.class).setAction(STOP),PendingIntent.FLAG_UPDATE_CURRENT|PendingIntent.FLAG_IMMUTABLE);
        String text=session==null?"正在开始记录":observedSteps+" 步 · "+String.format(java.util.Locale.CHINA,"%.2f",distance/1000)+" km";
        return new Notification.Builder(this,"phone-motion").setSmallIcon(android.R.drawable.ic_menu_mylocation).setContentTitle("安康正在记录运动").setContentText(text).setContentIntent(activity).setOngoing(true).addAction(new Notification.Action.Builder(null,"结束记录",stop).build()).build();
    }
    private void record(String kind,JSONObject data)throws Exception{
        if(ending||session==null)return;
        if(sequence>=60000)throw new IllegalStateException("本次记录达到容量上限");
        db.sample(session,++sequence,kind,data,System.currentTimeMillis(),SystemClock.elapsedRealtime());
    }
    private void clock()throws Exception{long now=SystemClock.elapsedRealtime();if(now>lastClock){record("clock",new JSONObject().put("delta_ms",now-lastClock));lastClock=now;}}
    @Override public void onSensorChanged(SensorEvent event){
        if(ending||session==null||event.sensor.getType()!=Sensor.TYPE_STEP_COUNTER||event.values.length==0)return;
        long at=event.timestamp/1000000L,wall=System.currentTimeMillis();
        if(at<=lastCounterAt||at<startElapsed||at>SystemClock.elapsedRealtime()+1000)return;
        Long delta=counter.accept(event.values[0],at);
        boolean sameDay=lastCounterWall>=0&&MotionDb.day(lastCounterWall).equals(MotionDb.day(wall));
        long interval=delta!=null&&sameDay?at-lastCounterAt:0;
        if(!sameDay)delta=null;
        try{record("steps",new JSONObject().put("counter",event.values[0]).put("sensor_elapsed_ms",at).put("interval_ms",interval).put("delta",delta==null?JSONObject.NULL:delta));
            if(delta!=null){observedSteps+=delta;coverage+=interval;stepState="正在计步";}else stepState="计步起点已记录";
            lastCounterAt=at;lastCounterWall=wall;
        }catch(Exception e){fail("计步记录保存失败");}
    }
    @Override public void onAccuracyChanged(Sensor sensor,int accuracy){}
    @Override public void onLocationChanged(Location location){
        if(ending||session==null)return;
        try{
            long elapsed=location.getElapsedRealtimeNanos()/1000000L,now=SystemClock.elapsedRealtime();
            if(elapsed>now+1000||now-elapsed>15000){gpsState="等待新的定位";return;}
            MotionMath.Segment segment=track.accept(new MotionMath.Fix(location.getLatitude(),location.getLongitude(),location.hasAccuracy()?location.getAccuracy():Double.NaN,elapsed));
            if("old".equals(segment.state))return;
            if("accepted".equals(segment.state)||"still".equals(segment.state)||"baseline".equals(segment.state)||"gap".equals(segment.state)){
                record("gps",new JSONObject().put("lat",location.getLatitude()).put("lon",location.getLongitude()).put("accuracy_m",location.getAccuracy()).put("fix_elapsed_ms",elapsed).put("segment_m",segment.metres).put("speed_m_s",segment.speed==null?JSONObject.NULL:segment.speed).put("state",segment.state));
                distance+=segment.metres;speed=segment.speed;lastFix=now;hasGpsFix=true;gpsState="定位已更新";
            }else{speed=null;lastFix=-1;gpsState="accuracy".equals(segment.state)?"定位精度不足，请到室外":"定位跳动，等待恢复";}
        }catch(Exception e){fail("定位记录保存失败");}
    }
    @Override public void onProviderDisabled(String p){speed=null;lastFix=-1;gpsState="手机定位已关闭";track.accept(new MotionMath.Fix(0,0,Double.NaN,0));}
    @Override public void onProviderEnabled(String p){gpsState="等待卫星定位";}
    @Override public void onStatusChanged(String provider,int status,Bundle extras){}
    private void connectHeart(){
        if(ending||!hrEnabled||gatt!=null)return;
        try{
            BluetoothAdapter adapter=((BluetoothManager)getSystemService(BLUETOOTH_SERVICE)).getAdapter();
            if(adapter==null||!adapter.isEnabled()){heartState="请开启手机蓝牙";return;}
            final int generation=++connectionGeneration;heartState="正在连接心率设备";
            gatt=adapter.getRemoteDevice(address).connectGatt(this,false,new BluetoothGattCallback(){
                private void dispatch(BluetoothGatt source,Runnable task){handler.post(()->{if(!ending&&generation==connectionGeneration&&source==gatt)task.run();});}
                @Override public void onConnectionStateChange(BluetoothGatt source,int status,int state){dispatch(source,()->{
                    if(status==BluetoothGatt.GATT_SUCCESS&&state==BluetoothProfile.STATE_CONNECTED){heartState="正在检查心率广播";try{if(!source.discoverServices())disconnected("无法读取设备服务");}catch(Exception e){disconnected("心率连接中断");}}
                    else if(state==BluetoothProfile.STATE_DISCONNECTED||status!=BluetoothGatt.GATT_SUCCESS)disconnected("心率设备已断开");
                });}
                @Override public void onServicesDiscovered(BluetoothGatt source,int status){dispatch(source,()->{
                    if(status!=BluetoothGatt.GATT_SUCCESS){disconnected("读取心率服务失败");return;}
                    BluetoothGattService service=source.getService(HRS);BluetoothGattCharacteristic characteristic=service==null?null:service.getCharacteristic(HRM);
                    BluetoothGattDescriptor descriptor=characteristic==null?null:characteristic.getDescriptor(CCCD);
                    if(characteristic==null||descriptor==null||(characteristic.getProperties()&BluetoothGattCharacteristic.PROPERTY_NOTIFY)==0){heartState="设备未开放标准心率广播；运动记录可继续";closeGatt();return;}
                    try{
                        if(!source.setCharacteristicNotification(characteristic,true)){disconnected("无法订阅心率");return;}
                        boolean written;
                        if(Build.VERSION.SDK_INT>=33)written=source.writeDescriptor(descriptor,BluetoothGattDescriptor.ENABLE_NOTIFICATION_VALUE)==BluetoothStatusCodes.SUCCESS;
                        else{descriptor.setValue(BluetoothGattDescriptor.ENABLE_NOTIFICATION_VALUE);written=source.writeDescriptor(descriptor);}
                        if(!written)disconnected("无法开启心率接收");
                    }catch(Exception e){disconnected("心率权限已关闭");}
                });}
                @Override public void onDescriptorWrite(BluetoothGatt source,BluetoothGattDescriptor descriptor,int status){dispatch(source,()->{if(!CCCD.equals(descriptor.getUuid()))return;if(status!=BluetoothGatt.GATT_SUCCESS)disconnected("心率订阅失败");else{heartState="等待心率，请检查手环佩戴和广播开关";handler.removeCallbacks(connectionTimeout);}});}
                @Override public void onCharacteristicChanged(BluetoothGatt source,BluetoothGattCharacteristic c){byte[] raw=c.getValue();byte[] value=raw==null?null:raw.clone();if(HRM.equals(c.getUuid()))dispatch(source,()->heartValue(value));}
                @Override public void onCharacteristicChanged(BluetoothGatt source,BluetoothGattCharacteristic c,byte[] raw){byte[] value=raw==null?null:raw.clone();if(HRM.equals(c.getUuid()))dispatch(source,()->heartValue(value));}
            },BluetoothDevice.TRANSPORT_LE);
            handler.postDelayed(connectionTimeout,20000);
        }catch(Exception e){disconnected("心率设备暂不可连接");}
    }
    private final Runnable connectionTimeout=()->disconnected("心率连接超时");
    private void heartValue(byte[] bytes){
        try{MotionMath.Heart value=MotionMath.heart(bytes);long now=SystemClock.elapsedRealtime();heart=value.bpm;lastHeart=now;heartState="心率已连接";retries=0;
            if(lastSavedHeart<0||now-lastSavedHeart>=5000){
                org.json.JSONArray rr=new org.json.JSONArray();for(double r:value.rrSeconds)rr.put(r);
                record("heart",new JSONObject().put("bpm",value.bpm).put("contact",value.contact==null?JSONObject.NULL:value.contact).put("energy_kj",value.energy==null?JSONObject.NULL:value.energy).put("rr_seconds",rr).put("source","BLE_HRS_180D_2A37").put("timestamp_kind","PHONE_RECEIPT"));lastSavedHeart=now;
            }
        }catch(IllegalArgumentException e){heart=null;lastHeart=-1;heartState="请检查手环佩戴";}
        catch(Exception e){fail("心率记录保存失败");}
    }
    private void disconnected(String message){heart=null;lastHeart=-1;heartState=message;closeGatt();if(ending)return;
        if(++retries<=3)handler.postDelayed(()->connectHeart(),retries*5000L);else heartState=message+"；可结束后重新开始";
    }
    private void closeGatt(){connectionGeneration++;handler.removeCallbacks(connectionTimeout);if(gatt!=null){BluetoothGatt old=gatt;gatt=null;try{old.disconnect();old.close();}catch(Exception ignored){}}}
    JSONObject status(String requestedOwner)throws Exception{
        if(!requestedOwner.equals(owner)||session==null||ending)return new JSONObject().put("recording",false);
        long now=SystemClock.elapsedRealtime();boolean hrFresh=heart!=null&&MotionMath.fresh(lastHeart,now),gpsFresh=lastFix>=0&&now-lastFix<=20000;
        return new JSONObject().put("recording",true).put("session_id",session).put("observed_steps",stepsEnabled&&coverage>0?observedSteps:JSONObject.NULL).put("step_coverage_ms",coverage).put("duration_ms",now-startElapsed).put("distance_m",gpsEnabled&&hasGpsFix?distance:JSONObject.NULL).put("speed_m_s",gpsFresh&&speed!=null?speed:JSONObject.NULL).put("pace_s_km",gpsFresh&&speed!=null&&speed>0?1000/speed:JSONObject.NULL).put("heart_bpm",hrFresh?heart:JSONObject.NULL).put("step_state",stepState).put("gps_state",gpsState).put("heart_state",heart!=null&&!hrFresh?"心率信号已中断":heartState);
    }
    static void stopOtherOwner(String owner){MotionService s=current;if(s!=null&&s.owner!=null&&!s.owner.equals(owner))s.finish("owner_changed");}
    private void fail(String message){lastError=message;finish("error");}
    private void finish(String reason){if(ending)return;try{if(session!=null){clock();db.end(session,reason,System.currentTimeMillis());}}catch(Exception e){lastError="本次记录被中断，已保存片段保留";}ending=true;cleanup();stopForeground(STOP_FOREGROUND_REMOVE);stopSelf();}
    private void cleanup(){handler.removeCallbacksAndMessages(null);closeGatt();if(sensors!=null)sensors.unregisterListener(this);if(locations!=null)try{locations.removeUpdates(this);}catch(Exception ignored){}try{unregisterReceiver(bluetoothState);}catch(Exception ignored){}}
    @Override public void onDestroy(){if(!ending&&session!=null){try{clock();db.end(session,"interrupted",System.currentTimeMillis());}catch(Exception ignored){}}ending=true;cleanup();if(current==this)current=null;if(db!=null)db.close();super.onDestroy();}
    @Override public IBinder onBind(Intent i){return null;}
}
