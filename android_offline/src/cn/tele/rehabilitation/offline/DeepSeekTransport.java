package cn.tele.rehabilitation.offline;

import android.content.Context;
import android.content.SharedPreferences;
import android.security.keystore.KeyGenParameterSpec;
import android.security.keystore.KeyProperties;
import android.util.Base64;
import java.security.KeyStore;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;
import java.net.HttpURLConnection;
import java.net.URL;
import java.io.InputStream;
import java.io.ByteArrayOutputStream;
import java.nio.charset.StandardCharsets;
import org.json.JSONArray;
import org.json.JSONObject;

/** Phone-private credentials; the privileged local WebView never receives a key. */
final class DeepSeekTransport {
    private static final String ALIAS="ankang-deepseek-v1";
    private final SharedPreferences prefs;
    private int generation;
    private int requestCount;
    private String lastFailure="";
    synchronized String lastFailure(){return lastFailure;}
    synchronized int requestCount(){return requestCount;}
    synchronized void failure(Exception error){
        lastFailure=error instanceof java.net.UnknownHostException?"dns":error instanceof javax.net.ssl.SSLException?"tls":error instanceof java.net.SocketTimeoutException?"timeout":"request";
    }
    DeepSeekTransport(Context context){prefs=context.getSharedPreferences("deepseek-v1",Context.MODE_PRIVATE);}
    synchronized boolean configured(){try{return !load().isEmpty();}catch(Exception e){return false;}}
    synchronized int generation(){return generation;}
    private SecretKey secret() throws Exception {
        KeyStore ks=KeyStore.getInstance("AndroidKeyStore");ks.load(null);
        if(!ks.containsAlias(ALIAS)){
            KeyGenerator g=KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES,"AndroidKeyStore");
            g.init(new KeyGenParameterSpec.Builder(ALIAS,KeyProperties.PURPOSE_ENCRYPT|KeyProperties.PURPOSE_DECRYPT)
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM).setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE).build());g.generateKey();
        }
        return (SecretKey)ks.getKey(ALIAS,null);
    }
    synchronized void save(String input) throws Exception {
        String key=input==null?"":input.trim();
        if(!key.matches("[\\x21-\\x7e]{1,512}"))throw new Exception("请填写有效的 API Key");
        Cipher cipher=Cipher.getInstance("AES/GCM/NoPadding");cipher.init(Cipher.ENCRYPT_MODE,secret());
        byte[] encrypted=cipher.doFinal(key.getBytes(StandardCharsets.UTF_8));
        if(!prefs.edit().putString("cipher",Base64.encodeToString(encrypted,Base64.NO_WRAP))
            .putString("iv",Base64.encodeToString(cipher.getIV(),Base64.NO_WRAP)).commit())throw new Exception("无法保存本机配置");
        generation++;
    }
    synchronized void clear(){prefs.edit().clear().commit();generation++;}
    private String load() throws Exception {
        String encrypted=prefs.getString("cipher","");if(encrypted.isEmpty())return "";
        Cipher cipher=Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.DECRYPT_MODE,secret(),new GCMParameterSpec(128,Base64.decode(prefs.getString("iv",""),Base64.NO_WRAP)));
        return new String(cipher.doFinal(Base64.decode(encrypted,Base64.NO_WRAP)),StandardCharsets.UTF_8);
    }
    String request(String body) throws Exception {
        final String key;final int captured;
        synchronized(this){key=load();captured=generation;}
        if(key.isEmpty())throw new Exception("尚未配置 DeepSeek");
        if(body==null||body.length()>32000)throw new Exception("请求过长");
        JSONObject data=new JSONObject(body);JSONArray messages=data.getJSONArray("messages");
        if(messages.length()<2||messages.length()>17)throw new Exception("对话上下文无效");
        int length=0;
        for(int i=0;i<messages.length();i++){
            JSONObject message=messages.getJSONObject(i);String role=message.getString("role"),text=message.getString("content");
            if(!(role.equals("user")||role.equals("assistant")||i==0&&role.equals("system"))||text.trim().isEmpty())throw new Exception("对话上下文无效");
            length+=text.length();
        }
        if(length>16000||!messages.getJSONObject(messages.length()-1).getString("role").equals("user"))throw new Exception("对话上下文无效");
        // The endpoint and provider parameters are owned by native code.
        data.put("model","deepseek-flash").put("stream",false).put("max_tokens",700)
            .put("thinking",new JSONObject().put("type","disabled"));
        synchronized(this){requestCount++;lastFailure="";}
        HttpURLConnection c=(HttpURLConnection)new URL("https://api.deepseek.com/chat/completions").openConnection();
        long deadline=android.os.SystemClock.elapsedRealtime()+20000;
        try{
            c.setInstanceFollowRedirects(false);c.setConnectTimeout(8000);c.setReadTimeout(12000);c.setRequestMethod("POST");
            c.setRequestProperty("Content-Type","application/json");c.setRequestProperty("Authorization","Bearer "+key);
            byte[] raw=data.toString().replace(key,"[密钥已隐藏]").getBytes(StandardCharsets.UTF_8);
            c.setDoOutput(true);c.setFixedLengthStreamingMode(raw.length);try(java.io.OutputStream out=c.getOutputStream()){out.write(raw);}
            int status=c.getResponseCode();
            if(status==401||status==403)throw new Exception("密钥未通过验证，请检查本机配置");
            if(status==402)throw new Exception("服务账户余额不足");
            if(status==429)throw new Exception("服务暂时繁忙，请稍后重试");
            if(status!=200)throw new Exception("智能服务请求失败");
            try(InputStream in=c.getInputStream();ByteArrayOutputStream out=new ByteArrayOutputStream()){
                byte[] part=new byte[4096];int n;
                while(true){
                    long remaining=deadline-android.os.SystemClock.elapsedRealtime();if(remaining<=0)throw new Exception("智能服务超时");
                    c.setReadTimeout((int)Math.min(12000,remaining));n=in.read(part);if(n==-1)break;
                    if(android.os.SystemClock.elapsedRealtime()>deadline||Thread.currentThread().isInterrupted())throw new Exception("智能服务超时");
                    if(out.size()+n>128*1024)throw new Exception("智能服务响应过长");out.write(part,0,n);
                }
                synchronized(this){if(captured!=generation)throw new Exception("连接配置已改变，本轮结果未采用");}
                JSONObject response=new JSONObject(new String(out.toByteArray(),StandardCharsets.UTF_8).replace(key,"[密钥已隐藏]"));
                return new JSONObject().put("choices",response.getJSONArray("choices")).toString();
            }
        }finally{c.disconnect();}
    }
}
