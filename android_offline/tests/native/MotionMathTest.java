import cn.tele.rehabilitation.offline.MotionMath;

/** TEST protocol bytes and geometry only, not measurements or device compatibility. */
public final class MotionMathTest {
    private static int count;
    static void check(boolean v,String name){count++;if(!v)throw new AssertionError(name);}
    static void rejected(byte[] data,String name){boolean bad=false;try{MotionMath.heart(data);}catch(IllegalArgumentException e){bad=true;}check(bad,name);}
    public static void main(String[] args){
        check(MotionMath.heart(new byte[]{0,72}).bpm==72,"8bit");
        check(MotionMath.heart(new byte[]{1,44,1}).bpm==300,"16bit unsigned");
        check(MotionMath.heart(new byte[]{6,80}).contact,"contact on");
        check(MotionMath.heart(new byte[]{0,80}).contact==null,"no contact info");
        MotionMath.Heart rr=MotionMath.heart(new byte[]{24,90,10,0,0,4,0,2});
        check(rr.energy==10&&rr.rrSeconds.length==2&&rr.rrSeconds[0]==1&&rr.rrSeconds[1]==.5,"energy and RR units");
        rejected(null,"null");rejected(new byte[]{0},"short");rejected(new byte[]{1,30},"short16");
        rejected(new byte[]{4,75},"contact absent");rejected(new byte[]{0,0},"zero");
        rejected(new byte[]{1,45,1},"over300");rejected(new byte[]{32,75},"reserved");
        rejected(new byte[]{8,75,1},"shortEnergy");rejected(new byte[]{16,75},"missingRR");
        rejected(new byte[]{16,75,1},"oddRR");rejected(new byte[]{0,75,1},"extraBytes");
        check(MotionMath.fresh(100,15100),"fresh threshold");check(!MotionMath.fresh(100,15101),"stale");
        check(!MotionMath.fresh(100,99)&&!MotionMath.fresh(-1,0),"no time travel");
        MotionMath.Counter c=new MotionMath.Counter();
        check(c.accept(10000,1000)==null,"boot count not imported");
        check(c.accept(10003,2000)==3,"observed delta");
        check(c.accept(10003,3000)==0,"real zero");
        check(c.accept(2,4000)==null,"reboot baseline");check(c.accept(3,5000)==1,"reset next reading");
        check(c.accept(8,4500)==null,"old rejected");check(c.accept(4,6000)==1,"old does not mutate baseline");
        check(c.accept(Double.NaN,7000)==null&&c.accept(-1,7000)==null&&c.accept(1.1,7000)==null,"invalid counters");
        check(c.accept(10000,7000)==null,"counter jump not activity");check(c.accept(10001,8000)==1,"jump new baseline");
        check(Math.abs(MotionMath.distance(0,0,0,.001)-111.1949)<.01,"haversine scale");
        MotionMath.Track t=new MotionMath.Track();
        check(t.accept(new MotionMath.Fix(0,0,4,1000)).state.equals("baseline"),"GPS baseline");
        MotionMath.Segment segment=t.accept(new MotionMath.Fix(0,.0001,4,5000));
        check(segment.metres>11&&segment.metres<12&&segment.speed>2&&segment.speed<3,"distance and speed");
        check(t.accept(new MotionMath.Fix(0,.00011,4,6000)).metres==0,"GPS jitter");
        check(t.accept(new MotionMath.Fix(0,.0003,4,5000)).state.equals("old"),"old GPS");
        check(t.accept(new MotionMath.Fix(0,.2,4,7000)).state.equals("jump"),"teleport rejected");
        check(t.accept(new MotionMath.Fix(0,.0002,4,8000)).metres==0,"no bridging teleport");
        check(t.accept(new MotionMath.Fix(0,.0003,60,9000)).state.equals("accuracy"),"coarse GPS rejected");
        check(t.accept(new MotionMath.Fix(0,.0004,4,10000)).metres==0,"no bridging bad accuracy");
        check(t.accept(new MotionMath.Fix(0,.0005,4,50000)).state.equals("gap"),"no bridging time gap");
        check(t.accept(new MotionMath.Fix(91,0,4,51000)).state.equals("accuracy"),"invalid lat");
        check(t.accept(new MotionMath.Fix(0,Double.NaN,4,52000)).state.equals("accuracy"),"invalid lon");
        check(t.accept(new MotionMath.Fix(0,0,Double.NaN,53000)).state.equals("accuracy"),"missing accuracy");
        System.out.println("MotionMath TEST assertions: "+count+" passed");
    }
}
