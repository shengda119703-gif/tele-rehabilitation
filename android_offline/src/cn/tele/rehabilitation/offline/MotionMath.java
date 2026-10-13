package cn.tele.rehabilitation.offline;

/** Platform-independent measurement rules. Missing input never becomes a reading. */
public final class MotionMath {
    private MotionMath() {}
    public static final long HEART_FRESH_MS = 15000;
    public static final class Heart {
        public final int bpm;
        public final Boolean contact;
        public final Integer energy;
        public final double[] rrSeconds;
        Heart(int bpm, Boolean contact, Integer energy, double[] rr) {
            this.bpm=bpm; this.contact=contact; this.energy=energy; rrSeconds=rr;
        }
    }
    private static int u16(byte[] b,int i) {return (b[i]&255)|((b[i+1]&255)<<8);}
    public static Heart heart(byte[] b) {
        if(b==null||b.length<2)throw new IllegalArgumentException("心率数据不完整");
        int flags=b[0]&255, p=1;
        if((flags&224)!=0)throw new IllegalArgumentException("心率格式不支持");
        int width=(flags&1)!=0?2:1;
        if(b.length<p+width)throw new IllegalArgumentException("心率数据不完整");
        int bpm=width==2?u16(b,p):b[p]&255;p+=width;
        Boolean contact=(flags&4)!=0?Boolean.valueOf((flags&2)!=0):null;
        if(bpm<1||bpm>300||Boolean.FALSE.equals(contact))throw new IllegalArgumentException("未收到有效心率");
        Integer energy=null;
        if((flags&8)!=0){if(b.length<p+2)throw new IllegalArgumentException("心率数据不完整");energy=u16(b,p);p+=2;}
        boolean hasRR=(flags&16)!=0;
        if(hasRR&&(b.length-p<2||(b.length-p)%2!=0)||!hasRR&&p!=b.length)throw new IllegalArgumentException("心率数据不完整");
        double[] rr=new double[hasRR?(b.length-p)/2:0];
        for(int i=0;i<rr.length;i++){rr[i]=u16(b,p)/1024.0;p+=2;}
        return new Heart(bpm,contact,energy,rr);
    }
    public static boolean fresh(long received,long now) {return received>=0&&now>=received&&now-received<=HEART_FRESH_MS;}
    public static final class Counter {
        private double previous=Double.NaN;
        private long at=-1;
        /** First sample/reset is a baseline, not the pre-app boot count. */
        public Long accept(double value,long elapsed) {
            if(!Double.isFinite(value)||value<0||value!=Math.rint(value)||elapsed<0||elapsed<=at)return null;
            Long delta=null;
            if(Double.isFinite(previous)&&value>=previous){double d=value-previous;
                if(d<=10.0*(elapsed-at)/1000.0+5)delta=(long)d;
            }
            previous=value;at=elapsed;return delta;
        }
    }
    public static final class Fix {
        public final double lat,lon,accuracy;
        public final long elapsed;
        public Fix(double lat,double lon,double accuracy,long elapsed){this.lat=lat;this.lon=lon;this.accuracy=accuracy;this.elapsed=elapsed;}
        boolean valid(){return Double.isFinite(lat)&&Math.abs(lat)<=90&&Double.isFinite(lon)&&Math.abs(lon)<=180&&Double.isFinite(accuracy)&&accuracy>0&&accuracy<=25&&elapsed>=0;}
    }
    public static final class Segment {
        public final double metres;
        public final Double speed;
        public final String state;
        Segment(double metres,Double speed,String state){this.metres=metres;this.speed=speed;this.state=state;}
    }
    public static final class Track {
        private Fix previous;
        public Segment accept(Fix point) {
            if(!point.valid()){previous=null;return new Segment(0,null,"accuracy");}
            Fix old=previous;
            if(old==null){previous=point;return new Segment(0,null,"baseline");}
            long dt=point.elapsed-old.elapsed;
            if(dt<=0)return new Segment(0,null,"old");
            if(dt>30000){previous=point;return new Segment(0,null,"gap");}
            double distance=distance(old.lat,old.lon,point.lat,point.lon), speed=distance/(dt/1000.0);
            if(speed>12){previous=null;return new Segment(0,null,"jump");}
            if(distance<Math.max(3,Math.min(old.accuracy,point.accuracy)*.5))return new Segment(0,0.0,"still");
            previous=point;return new Segment(distance,speed,"accepted");
        }
    }
    public static double distance(double a,double b,double c,double d){
        double p=Math.toRadians(c-a),q=Math.toRadians(d-b),h=Math.sin(p/2)*Math.sin(p/2)+Math.cos(Math.toRadians(a))*Math.cos(Math.toRadians(c))*Math.sin(q/2)*Math.sin(q/2);
        return 6371000*2*Math.asin(Math.sqrt(Math.max(0,Math.min(1,h))));
    }
}
