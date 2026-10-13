package cn.tele.rehabilitation.offline;

import android.content.ContentValues;
import android.content.Context;
import android.database.Cursor;
import android.database.sqlite.SQLiteDatabase;
import android.database.sqlite.SQLiteOpenHelper;
import org.json.JSONArray;
import org.json.JSONObject;
import java.time.Instant;
import java.time.ZoneId;
import java.util.UUID;

/** Private, source-separated sensor history; never writes the clinical/profile database. */
public final class MotionDb extends SQLiteOpenHelper {
    public MotionDb(Context context){super(context,"phone-motion-v1.db",null,2);setWriteAheadLoggingEnabled(true);}
    @Override public void onCreate(SQLiteDatabase db){
        db.execSQL("CREATE TABLE sessions(id TEXT PRIMARY KEY,owner TEXT NOT NULL,started INTEGER NOT NULL,ended INTEGER,state TEXT NOT NULL,steps_enabled INTEGER NOT NULL,gps_enabled INTEGER NOT NULL,hr_enabled INTEGER NOT NULL)");
        db.execSQL("CREATE INDEX session_owner ON sessions(owner,started)");
        db.execSQL("CREATE TABLE samples(session TEXT NOT NULL,seq INTEGER NOT NULL,received INTEGER NOT NULL,elapsed INTEGER NOT NULL,day TEXT NOT NULL,kind TEXT NOT NULL,body TEXT NOT NULL,delta_steps INTEGER,coverage_ms INTEGER,segment_m REAL,bpm INTEGER,delta_ms INTEGER,PRIMARY KEY(session,seq))");
        db.execSQL("CREATE INDEX samples_day ON samples(session,day,kind)");
    }
    @Override public void onUpgrade(SQLiteDatabase db,int old,int next){
        if(old!=1||next!=2)throw new IllegalStateException("运动记录版本不兼容");
        for(String column:new String[]{"delta_steps INTEGER","coverage_ms INTEGER","segment_m REAL","bpm INTEGER","delta_ms INTEGER"})db.execSQL("ALTER TABLE samples ADD COLUMN "+column);
        try(Cursor c=db.rawQuery("SELECT session,seq,kind,body FROM samples",null)){
            while(c.moveToNext())try{db.update("samples",metrics(c.getString(2),new JSONObject(c.getString(3))),"session=? AND seq=?",new String[]{c.getString(0),String.valueOf(c.getInt(1))});}catch(org.json.JSONException e){throw new IllegalStateException("原运动数据无法迁移，原件保留",e);}
        }
    }
    private static ContentValues metrics(String kind,JSONObject body){
        ContentValues values=new ContentValues();
        if(kind.equals("steps")){if(!body.isNull("delta"))values.put("delta_steps",body.optLong("delta"));values.put("coverage_ms",body.optLong("interval_ms"));}
        if(kind.equals("gps"))values.put("segment_m",body.optDouble("segment_m",0));
        if(kind.equals("heart"))values.put("bpm",body.optInt("bpm"));
        if(kind.equals("clock"))values.put("delta_ms",body.optLong("delta_ms"));
        return values;
    }
    public synchronized void interrupt(){ContentValues v=new ContentValues();v.put("state","interrupted");getWritableDatabase().update("sessions",v,"state='recording'",null);}
    public synchronized String start(String owner,boolean steps,boolean gps,boolean hr,long time){
        String id=UUID.randomUUID().toString();ContentValues v=new ContentValues();v.put("id",id);v.put("owner",owner);v.put("started",time);v.put("state","recording");v.put("steps_enabled",steps?1:0);v.put("gps_enabled",gps?1:0);v.put("hr_enabled",hr?1:0);getWritableDatabase().insertOrThrow("sessions",null,v);return id;
    }
    public synchronized void end(String id,String state,long time){ContentValues v=new ContentValues();v.put("state",state);v.put("ended",time);getWritableDatabase().update("sessions",v,"id=? AND state='recording'",new String[]{id});}
    public static String day(long wall){return Instant.ofEpochMilli(wall).atZone(ZoneId.systemDefault()).toLocalDate().toString();}
    public synchronized void sample(String id,int seq,String kind,JSONObject body,long wall,long elapsed){
        ContentValues v=metrics(kind,body);v.put("session",id);v.put("seq",seq);v.put("kind",kind);v.put("body",body.toString());v.put("received",wall);v.put("elapsed",elapsed);v.put("day",day(wall));getWritableDatabase().insertOrThrow("samples",null,v);
    }
    public synchronized JSONArray history(String owner,int limit)throws Exception{
        JSONArray list=new JSONArray();try(Cursor c=getReadableDatabase().rawQuery("SELECT id,started,ended,state,steps_enabled,gps_enabled,hr_enabled FROM sessions WHERE owner=? ORDER BY started DESC LIMIT ?",new String[]{owner,String.valueOf(Math.min(100,Math.max(1,limit)))})){
            while(c.moveToNext())list.put(summary(owner,c.getString(0),null).put("started",c.getLong(1)).put("ended",c.isNull(2)?JSONObject.NULL:c.getLong(2)).put("state",c.getString(3)).put("steps_enabled",c.getInt(4)==1).put("gps_enabled",c.getInt(5)==1).put("hr_enabled",c.getInt(6)==1));
        }return list;
    }
    public synchronized JSONObject summary(String owner,String id,String day)throws Exception{
        String where="session IN (SELECT id FROM sessions WHERE owner=?)";java.util.ArrayList<String> args=new java.util.ArrayList<>();args.add(owner);
        if(id!=null){where+=" AND session=?";args.add(id);}if(day!=null){where+=" AND day=?";args.add(day);}
        // SQL aggregates avoid parsing tens of thousands of JSON packets on every history open.
        try(Cursor c=getReadableDatabase().rawQuery("SELECT SUM(delta_steps),SUM(coverage_ms),SUM(segment_m),COUNT(bpm),AVG(bpm),MIN(bpm),MAX(bpm),MAX(received),SUM(delta_ms),SUM(CASE WHEN kind='gps' THEN 1 ELSE 0 END),COUNT(*) FROM samples WHERE "+where,args.toArray(new String[0]))){
            c.moveToFirst();long coverage=c.getLong(1);int hrCount=c.getInt(3),gpsCount=c.getInt(9);
            return new JSONObject().put("session_id",id==null?JSONObject.NULL:id).put("day",day==null?JSONObject.NULL:day).put("source","PHONE_SENSORS_BLE_HRS").put("observed_steps",coverage==0?JSONObject.NULL:c.getLong(0)).put("step_coverage_ms",coverage).put("distance_m",gpsCount==0?JSONObject.NULL:c.getDouble(2)).put("gps_sample_count",gpsCount).put("recorded_duration_ms",c.getLong(8)).put("sample_count",c.getInt(10)).put("heart_sample_count",hrCount).put("heart_mean",hrCount==0?JSONObject.NULL:c.getDouble(4)).put("heart_min",hrCount==0?JSONObject.NULL:c.getInt(5)).put("heart_max",hrCount==0?JSONObject.NULL:c.getInt(6)).put("last_received",c.isNull(7)?JSONObject.NULL:c.getLong(7)).put("complete_day",false);
        }
    }
    public synchronized JSONObject export(String owner,String id)throws Exception{
        JSONObject header=null;JSONArray rows=history(owner,100);for(int i=0;i<rows.length();i++){JSONObject row=rows.getJSONObject(i);if(row.getString("session_id").equals(id)){header=row;break;}}
        if(header==null)throw new IllegalArgumentException("找不到本人记录");JSONArray samples=new JSONArray();
        try(Cursor c=getReadableDatabase().rawQuery("SELECT seq,kind,body,received,elapsed,day FROM samples WHERE session=? AND session IN (SELECT id FROM sessions WHERE owner=?) ORDER BY seq",new String[]{id,owner})){
            while(c.moveToNext())samples.put(new JSONObject().put("sequence",c.getInt(0)).put("kind",c.getString(1)).put("data",new JSONObject(c.getString(2))).put("received_at",c.getLong(3)).put("elapsed_ms",c.getLong(4)).put("day",c.getString(5)));
        }return new JSONObject().put("kind","ankang-phone-motion").put("version",1).put("owner",owner).put("summary",header).put("samples",samples);
    }
}
