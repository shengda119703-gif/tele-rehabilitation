package cn.tele.rehabilitation.offline;

import android.content.Context;
import android.content.SharedPreferences;
import org.json.JSONObject;
import java.net.URI;
import java.net.HttpURLConnection;
import java.nio.charset.StandardCharsets;
import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.util.UUID;

/** Optional, explicitly configured server. No cookies or credentials reach remote pages. */
final class CloudTransport {
    private final SharedPreferences prefs;
    CloudTransport(Context context) { prefs=context.getSharedPreferences("cloud-v2",Context.MODE_PRIVATE); }
    boolean configured() { return prefs.getBoolean("enabled",false) && !prefs.getString("token", "").isEmpty(); }
    String address() { return prefs.getString("url", ""); }
    void disconnect() { prefs.edit().putBoolean("enabled",false).apply(); }
    static boolean lan(String host) {
        if (host == null) return false;
        if (host.equals("localhost") || host.equals("127.0.0.1")) return true;
        String[] p=host.split("\\."); if(p.length!=4)return false;
        try { int[] v=new int[4];for(int i=0;i<4;i++){if(!p[i].matches("[0-9]{1,3}"))return false;v[i]=Integer.parseInt(p[i]);if(v[i]>255)return false;}
            return v[0]==10 || v[0]==192&&v[1]==168 || v[0]==172&&v[1]>=16&&v[1]<=31;
        } catch(Exception e){return false;}
    }
    static String validate(String input) throws Exception {
        URI u=new URI(input.trim());
        if(u.getUserInfo()!=null||u.getQuery()!=null||u.getFragment()!=null||u.getHost()==null||!("https".equals(u.getScheme())||"http".equals(u.getScheme())&&lan(u.getHost()))||!(u.getPath()==null||u.getPath().isEmpty()||u.getPath().equals("/")))throw new Exception("请输入 HTTPS 云端地址；HTTP 仅支持显式的可信局域网 IP");
        return input.trim().replaceAll("/$", "");
    }
    void connect(String input,String code) throws Exception {
        String url=validate(input);
        if(url.equals(address())&&!prefs.getString("token", "").isEmpty()){
            Reply valid=send(url+"/v1/family","GET","",prefs.getString("token",""));
            if(valid.status==200){prefs.edit().putBoolean("enabled",true).apply();return;}
        }
        String client=UUID.randomUUID().toString();
        JSONObject data=new JSONObject().put("code",code).put("client_id",client);
        Reply out=send(url+"/v1/enroll","POST",data.toString(),"");
        if(out.status!=200)throw new Exception(new JSONObject(out.body).optString("detail","连接失败"));
        JSONObject result=new JSONObject(out.body);prefs.edit().putString("url",url).putString("token",result.getString("token")).putBoolean("enabled",true).apply();
    }
    Reply request(String path,String method,String body) throws Exception {
        // Only this versioned API; no absolute addresses, queries or redirections.
        if(!configured()||!path.matches("/v1/(family|summary|backup)(/[a-zA-Z0-9-]+)?")||!(method.equals("GET")||method.equals("POST")||method.equals("PUT")||method.equals("DELETE")))throw new Exception("云端操作无效");
        return send(address()+path,method,body,prefs.getString("token",""));
    }
    static final class Reply {final int status;final String body;Reply(int status,String body){this.status=status;this.body=body;}}
    private static Reply send(String url,String method,String body,String token) throws Exception {
        HttpURLConnection c=(HttpURLConnection)new URI(url).toURL().openConnection();
        try {
            c.setInstanceFollowRedirects(false);c.setConnectTimeout(8000);c.setReadTimeout(10000);c.setRequestMethod(method);c.setRequestProperty("Content-Type","application/json");
            if(!token.isEmpty())c.setRequestProperty("Authorization","Bearer "+token);
            if(!body.isEmpty()){byte[] raw=body.getBytes(StandardCharsets.UTF_8);if(raw.length>12*1024*1024)throw new Exception("备份过大，请先单独导出资料");c.setDoOutput(true);c.setFixedLengthStreamingMode(raw.length);try(java.io.OutputStream o=c.getOutputStream()){o.write(raw);}}
            int status=c.getResponseCode();if(status>=300&&status<400)throw new Exception("云端地址发生跳转，请填写最终 HTTPS 地址");
            InputStream stream=status>=400?c.getErrorStream():c.getInputStream();if(stream==null)throw new Exception("云端没有返回结果");
            try(InputStream in=stream;ByteArrayOutputStream out=new ByteArrayOutputStream()){byte[] part=new byte[8192];int n;while((n=in.read(part))!=-1){if(out.size()+n>12*1024*1024)throw new Exception("云端响应过大");out.write(part,0,n);}return new Reply(status,new String(out.toByteArray(),StandardCharsets.UTF_8));}
        } finally {c.disconnect();}
    }
}
