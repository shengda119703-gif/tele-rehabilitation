package cn.tele.rehabilitation.offline;

import android.content.Context;
import android.content.SharedPreferences;
import android.security.keystore.KeyGenParameterSpec;
import android.security.keystore.KeyProperties;
import android.util.Base64;
import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.security.KeyStore;
import java.util.Arrays;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;
import javax.net.ssl.HttpsURLConnection;
import org.json.JSONObject;

/** New account channel, independent of the old family/backup connection code. */
public final class AccountTransport {
    private static final String ORIGIN="https://139.224.216.18", PREFIX="/api/cloud/v1", ALIAS="ankang-account-v1";
    private final SharedPreferences preferences;
    private JSONObject session;
    public static final class Reply { public final int status;public final String body;Reply(int s,String b){status=s;body=b;} }
    public AccountTransport(Context context){preferences=context.getSharedPreferences("account-v1",Context.MODE_PRIVATE);}
    private SecretKey key() throws Exception {
        KeyStore store=KeyStore.getInstance("AndroidKeyStore");store.load(null);
        if(store.containsAlias(ALIAS))return ((KeyStore.SecretKeyEntry)store.getEntry(ALIAS,null)).getSecretKey();
        KeyGenerator generator=KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES,"AndroidKeyStore");
        generator.init(new KeyGenParameterSpec.Builder(ALIAS,KeyProperties.PURPOSE_ENCRYPT|KeyProperties.PURPOSE_DECRYPT)
            .setBlockModes(KeyProperties.BLOCK_MODE_GCM).setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE).build());
        return generator.generateKey();
    }
    private JSONObject session() throws Exception {
        if(session!=null)return session;
        String encoded=preferences.getString("sealed",null);if(encoded==null)throw new Exception("请先登录云账号");
        try{
            byte[] raw=Base64.decode(encoded,Base64.NO_WRAP);
            Cipher cipher=Cipher.getInstance("AES/GCM/NoPadding");cipher.init(Cipher.DECRYPT_MODE,key(),new GCMParameterSpec(128,Arrays.copyOfRange(raw,0,12)));
            JSONObject value=new JSONObject(new String(cipher.doFinal(Arrays.copyOfRange(raw,12,raw.length)),StandardCharsets.UTF_8));
            if(!ORIGIN.equals(value.getString("origin"))||!"PATIENT".equals(value.getString("role")))throw new Exception();
            java.util.UUID.fromString(value.getString("patient_id"));session=value;return value;
        }catch(Exception e){throw new Exception("登录状态无法读取，请重新登录；本机记录保留");}
    }
    private void save(JSONObject value) throws Exception {
        Cipher cipher=Cipher.getInstance("AES/GCM/NoPadding");cipher.init(Cipher.ENCRYPT_MODE,key());
        byte[] data=cipher.doFinal(value.toString().getBytes(StandardCharsets.UTF_8)),iv=cipher.getIV();
        byte[] sealed=new byte[iv.length+data.length];System.arraycopy(iv,0,sealed,0,iv.length);System.arraycopy(data,0,sealed,iv.length,data.length);
        if(!preferences.edit().putString("sealed",Base64.encodeToString(sealed,Base64.NO_WRAP)).commit())throw new Exception("登录状态未保存，请重试");
        session=value;
    }
    private void clear(){preferences.edit().remove("sealed").commit();session=null;}
    private Reply http(String path,String method,JSONObject data,String token) throws Exception {
        if(!path.matches("/auth/(register|password/login|refresh|me|logout)|/patients/[a-f0-9-]{36}(/(record-events|records\\?offset=[0-9]+&limit=[0-9]+|doctor-access))?"))throw new Exception("云接口地址无效");
        HttpsURLConnection connection=(HttpsURLConnection)new URL(ORIGIN+PREFIX+path).openConnection();
        connection.setConnectTimeout(12000);connection.setReadTimeout(12000);connection.setInstanceFollowRedirects(false);connection.setRequestMethod(method);
        connection.setRequestProperty("Content-Type","application/json");connection.setRequestProperty("X-Ankang-Client","native");
        if(token!=null)connection.setRequestProperty("Authorization","Bearer "+token);
        try{
            if(data!=null){byte[] bytes=data.toString().getBytes(StandardCharsets.UTF_8);if(bytes.length>32768)throw new Exception("结果过大，本机原记录保留");connection.setDoOutput(true);try(java.io.OutputStream output=connection.getOutputStream()){output.write(bytes);}}
            int status=connection.getResponseCode();InputStream stream=status>=400?connection.getErrorStream():connection.getInputStream();
            try(InputStream in=stream;ByteArrayOutputStream out=new ByteArrayOutputStream()){
                if(in==null)throw new Exception("云回复未完成");byte[] buffer=new byte[8192];int size;
                while((size=in.read(buffer))!=-1){if(out.size()+size>512*1024)throw new Exception("云回复过大");out.write(buffer,0,size);}
                return new Reply(status,new String(out.toByteArray(),StandardCharsets.UTF_8));
            }
        }finally{connection.disconnect();}
    }
    private JSONObject success(Reply reply) throws Exception {
        JSONObject value=new JSONObject(reply.body);if(reply.status<200||reply.status>=300)throw new Exception(value.optString("message","云请求未完成"));return value;
    }
    private Reply authorized(String path,String method,JSONObject data) throws Exception {
        JSONObject value=session();Reply reply=http(path,method,data,value.getString("access_token"));
        if(reply.status!=401)return reply;
        Reply rotation=http("/auth/refresh","POST",new JSONObject().put("refresh_token",value.getString("refresh_token")),null);
        if(rotation.status==401){clear();return rotation;}
        JSONObject updated=success(rotation);value.put("access_token",updated.getString("access_token")).put("refresh_token",updated.getString("refresh_token"));save(value);
        return http(path,method,data,value.getString("access_token"));
    }
    public synchronized JSONObject login(String username,String password,boolean register) throws Exception {
        if(register)success(http("/auth/register","POST",new JSONObject().put("username",username).put("password",password).put("display_name",username),null));
        JSONObject value=success(http("/auth/password/login","POST",new JSONObject().put("username",username).put("password",password).put("client_kind","APK"),null));
        if(!"PATIENT".equals(value.getString("role"))){http("/auth/logout","POST",new JSONObject(),value.getString("access_token"));throw new Exception("请使用普通用户账号");}
        value.put("origin",ORIGIN);try{save(value);}catch(Exception e){http("/auth/logout","POST",new JSONObject(),value.getString("access_token"));throw e;}
        return identity();
    }
    public synchronized JSONObject identity() throws Exception {
        JSONObject value=session();return new JSONObject().put("account_id",value.getString("account_id")).put("patient_id",value.getString("patient_id"))
            .put("username",value.getString("username")).put("origin",ORIGIN).put("role","PATIENT");
    }
    public synchronized Reply request(String action,String raw) throws Exception {
        JSONObject data=new JSONObject(raw),value=session();String patient=value.getString("patient_id");
        if(!patient.equals(data.optString("patient_id")))throw new Exception("账号已变化，请返回当前账号档案");
        if(action.equals("identity"))return new Reply(200,identity().toString());
        if(action.equals("logout")){
            Reply reply;try{reply=authorized("/auth/logout","POST",new JSONObject());}finally{clear();}return reply;
        }
        // Validate identity before operations; no patient/installation URL comes from JS.
        JSONObject me=success(authorized("/auth/me","GET",null));if(!patient.equals(me.getString("patient_id")))throw new Exception("账号身份已变化，请重新登录");
        if(action.equals("records")){
            int offset=data.optInt("offset",0);if(offset<0)throw new Exception("查询范围无效");
            return authorized("/patients/"+patient+"/records?offset="+offset+"&limit=10","GET",null);
        }
        if(action.equals("append"))return authorized("/patients/"+patient+"/record-events","POST",data.getJSONObject("document"));
        if(action.equals("grant")){
            JSONObject current=success(authorized("/patients/"+patient,"GET",null));
            return authorized("/patients/"+patient+"/doctor-access","PUT",new JSONObject().put("enabled",data.getBoolean("enabled")).put("expected_version",current.getInt("grant_version")));
        }
        throw new Exception("没有这个云操作");
    }
}
