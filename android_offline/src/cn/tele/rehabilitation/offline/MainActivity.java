package cn.tele.rehabilitation.offline;

import android.Manifest;
import android.app.Activity;
import android.app.AlertDialog;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.graphics.Color;
import android.net.Uri;
import android.os.Bundle;
import android.provider.MediaStore;
import android.view.View;
import android.webkit.JavascriptInterface;
import android.webkit.PermissionRequest;
import android.webkit.ValueCallback;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceRequest;
import android.webkit.WebResourceResponse;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.net.http.SslError;
import android.webkit.SslErrorHandler;
import android.widget.Toast;
import android.widget.FrameLayout;
import java.io.ByteArrayInputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
import java.util.HashMap;
import java.util.Map;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.speech.SpeechRecognizer;
import android.speech.RecognizerIntent;
import android.speech.RecognitionListener;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import org.json.JSONObject;

/** Local UI/model assets; optional authenticated companion through an allowlisted native transport. */
public final class MainActivity extends Activity {
    private static final String ORIGIN = "https://appassets.androidplatform.net";
    private static final int PICK_FILE = 41, CAMERA_PERMISSION = 42, SAVE_FILE = 43;
    private WebView web;
    private ValueCallback<Uri[]> picker;
    private PermissionRequest cameraRequest;
    private boolean capturePending;
    private byte[] exportBytes;
    private CloudTransport cloud;
    private final ExecutorService network = Executors.newFixedThreadPool(2);
    private SpeechRecognizer speech;
    private static final int IMPORT_BACKUP=44, SPEECH_PERMISSION=45;

    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        cloud=new CloudTransport(this);
        getWindow().setStatusBarColor(Color.WHITE);
        getWindow().setNavigationBarColor(Color.WHITE);
        getWindow().getDecorView().setSystemUiVisibility(View.SYSTEM_UI_FLAG_LIGHT_STATUS_BAR | View.SYSTEM_UI_FLAG_LIGHT_NAVIGATION_BAR);
        web = new WebView(this);
        FrameLayout container = new FrameLayout(this);
        container.setBackgroundColor(Color.WHITE);
        container.addView(web, new FrameLayout.LayoutParams(-1, -1));
        container.setOnApplyWindowInsetsListener((view, insets) -> {
            view.setPadding(insets.getSystemWindowInsetLeft(), insets.getSystemWindowInsetTop(), insets.getSystemWindowInsetRight(), insets.getSystemWindowInsetBottom());
            return insets.consumeSystemWindowInsets();
        });
        setContentView(container);
        container.requestApplyInsets();
        web.setBackgroundColor(Color.WHITE);
        WebSettings settings = web.getSettings();
        settings.setJavaScriptEnabled(true);
        settings.setDomStorageEnabled(true);
        settings.setAllowFileAccess(false);
        settings.setAllowContentAccess(true); // system picker content URIs, not raw files
        settings.setMixedContentMode(WebSettings.MIXED_CONTENT_NEVER_ALLOW);
        settings.setMediaPlaybackRequiresUserGesture(true);
        settings.setSupportMultipleWindows(false);
        web.addJavascriptInterface(new ExportBridge(), "OfflineAndroid");
        web.setWebViewClient(new WebViewClient() {
            @Override public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                // Never navigate the privileged WebView to remote, file or content pages.
                return !trusted(request.getUrl());
            }
            @Override public WebResourceResponse shouldInterceptRequest(WebView view, WebResourceRequest request) {
                if (!trusted(request.getUrl()) || !"GET".equals(request.getMethod())) return denied();
                String path = request.getUrl().getPath();
                if (path == null || path.contains("..") || path.contains("\\")) return denied();
                if ("/".equals(path)) path = "/index.html";
                if ("/capture".equals(path)) path = "/capture.html";
                if (path.startsWith("/assets/")) path = path.substring(7);
                try {
                    InputStream stream = getAssets().open(path.substring(1));
                    Map<String, String> headers = new HashMap<>();
                    headers.put("Content-Security-Policy", "default-src 'self'; script-src 'self' blob: 'wasm-unsafe-eval'; worker-src 'self' blob:; connect-src 'self' blob: data:; img-src 'self' data: blob:; media-src 'self' blob:; style-src 'self' 'unsafe-inline'; object-src 'none'; frame-src 'none'; base-uri 'none'");
                    headers.put("X-Content-Type-Options", "nosniff");
                    headers.put("Cache-Control", "no-store");
                    return new WebResourceResponse(mime(path), "UTF-8", 200, "OK", headers, stream);
                } catch (Exception e) {
                    return new WebResourceResponse("text/plain", "UTF-8", 404, "Not Found", new HashMap<>(), new ByteArrayInputStream(new byte[0]));
                }
            }
            @Override public void onReceivedSslError(WebView view, SslErrorHandler handler, SslError error) { handler.cancel(); }
        });
        web.setWebChromeClient(new WebChromeClient() {
            @Override public boolean onShowFileChooser(WebView view, ValueCallback<Uri[]> callback, FileChooserParams params) {
                cancelPicker(); picker = callback;
                if (params.isCaptureEnabled() && java.util.Arrays.toString(params.getAcceptTypes()).contains("video")) {
                    if (checkSelfPermission(Manifest.permission.CAMERA) != PackageManager.PERMISSION_GRANTED) {
                        capturePending = true; requestPermissions(new String[]{Manifest.permission.CAMERA}, CAMERA_PERMISSION);
                    } else captureVideo();
                } else selectDocument(params.getAcceptTypes());
                return true;
            }
            @Override public void onPermissionRequest(PermissionRequest request) {
                if (!ORIGIN.equals(request.getOrigin().toString().replaceAll("/$", ""))) { request.deny(); return; }
                boolean video = java.util.Arrays.asList(request.getResources()).contains(PermissionRequest.RESOURCE_VIDEO_CAPTURE);
                if (!video || cameraRequest != null) { request.deny(); return; }
                if (checkSelfPermission(Manifest.permission.CAMERA) == PackageManager.PERMISSION_GRANTED) {
                    request.grant(new String[]{PermissionRequest.RESOURCE_VIDEO_CAPTURE});
                } else { cameraRequest = request; requestPermissions(new String[]{Manifest.permission.CAMERA}, CAMERA_PERMISSION); }
            }
            @Override public void onPermissionRequestCanceled(PermissionRequest request) {
                if (cameraRequest == request) cameraRequest = null;
            }
            @Override public boolean onJsAlert(WebView view, String url, String message, android.webkit.JsResult result) {
                new AlertDialog.Builder(MainActivity.this).setMessage(message).setPositiveButton("知道了", (d, w) -> result.confirm()).setOnCancelListener(d -> result.cancel()).show(); return true;
            }
            @Override public boolean onJsConfirm(WebView view, String url, String message, android.webkit.JsResult result) {
                new AlertDialog.Builder(MainActivity.this).setMessage(message).setPositiveButton("确认", (d, w) -> result.confirm()).setNegativeButton("取消", (d, w) -> result.cancel()).setOnCancelListener(d -> result.cancel()).show(); return true;
            }
        });
        web.loadUrl(ORIGIN + "/");
    }
    private static boolean trusted(Uri uri) { return "https".equals(uri.getScheme()) && "appassets.androidplatform.net".equals(uri.getHost()) && uri.getPort() == -1; }
    private static WebResourceResponse denied() { return new WebResourceResponse("text/plain", "UTF-8", 403, "Forbidden", new HashMap<>(), new ByteArrayInputStream(new byte[0])); }
    private static String mime(String path) {
        if (path.endsWith(".html")) return "text/html";
        if (path.endsWith(".js")) return "text/javascript";
        if (path.endsWith(".css")) return "text/css";
        if (path.endsWith(".json")) return "application/json";
        if (path.endsWith(".wasm")) return "application/wasm";
        if (path.endsWith(".svg")) return "image/svg+xml";
        if (path.endsWith(".png")) return "image/png";
        return "application/octet-stream";
    }
    private void selectDocument(String[] types) {
        Intent intent = new Intent(Intent.ACTION_OPEN_DOCUMENT).addCategory(Intent.CATEGORY_OPENABLE).setType("*/*");
        java.util.List<String> accepted = new java.util.ArrayList<>();
        for (String type : types) if (type.contains("/")) accepted.add(type);
        if (!accepted.isEmpty()) intent.putExtra(Intent.EXTRA_MIME_TYPES, accepted.toArray(new String[0]));
        try { startActivityForResult(intent, PICK_FILE); } catch (Exception e) { cancelPicker(); notice("没有找到文件选择器"); }
    }
    private void captureVideo() {
        capturePending = false;
        Intent intent = new Intent(MediaStore.ACTION_VIDEO_CAPTURE).putExtra(MediaStore.EXTRA_DURATION_LIMIT, 120).putExtra(MediaStore.EXTRA_VIDEO_QUALITY, 1);
        try { startActivityForResult(intent, PICK_FILE); } catch (Exception e) { notice("无法打开相机，请选择已有视频"); selectDocument(new String[]{"video/*"}); }
    }
    private void cancelPicker() { if (picker != null) { picker.onReceiveValue(null); picker = null; } }
    @Override public void onRequestPermissionsResult(int code, String[] permissions, int[] results) {
        super.onRequestPermissionsResult(code, permissions, results);
        if (code==SPEECH_PERMISSION){if(results.length>0&&results[0]==PackageManager.PERMISSION_GRANTED)startSpeech();else speechResult("","未授权麦克风，原草稿保留");return;}
        if (code != CAMERA_PERMISSION) return;
        boolean granted = results.length > 0 && results[0] == PackageManager.PERMISSION_GRANTED;
        if (cameraRequest != null) { if (granted) cameraRequest.grant(new String[]{PermissionRequest.RESOURCE_VIDEO_CAPTURE}); else cameraRequest.deny(); cameraRequest = null; }
        if (capturePending) { capturePending = false; if (granted) captureVideo(); else { cancelPicker(); notice("未授权相机，仍可选择已有录像"); } }
    }
    @Override protected void onActivityResult(int request, int result, Intent data) {
        super.onActivityResult(request, result, data);
        if(request==IMPORT_BACKUP&&result==RESULT_OK&&data!=null){network.execute(()->{
            try(InputStream in=getContentResolver().openInputStream(data.getData());java.io.ByteArrayOutputStream out=new java.io.ByteArrayOutputStream()){
                byte[] block=new byte[8192];int n;while((n=in.read(block))!=-1){if(out.size()+n>12*1024*1024)throw new Exception("备份超过 12 MB");out.write(block,0,n);}
                String json=new String(out.toByteArray(),StandardCharsets.UTF_8);new JSONObject(json);
                runOnUiThread(()->web.evaluateJavascript("PhoneLocal.restore("+JSONObject.quote(json)+")",null));
            }catch(Exception e){runOnUiThread(()->notice("备份无法读取，原数据未覆盖"));}
        });}
        if (request == PICK_FILE && picker != null) {
            Uri uri = result == RESULT_OK && data != null ? data.getData() : null;
            picker.onReceiveValue(uri == null ? null : new Uri[]{uri}); picker = null;
        }
        if (request == SAVE_FILE) {
            byte[] payload = exportBytes; exportBytes = null;
            if (result == RESULT_OK && data != null && payload != null) {
                try (OutputStream output = getContentResolver().openOutputStream(data.getData())) { output.write(payload); notice("已保存"); }
                catch (Exception e) { notice("保存失败，请重试"); }
            }
        }
    }
    public final class ExportBridge {
        @JavascriptInterface public void saveJson(String json) {
            if (json == null || json.length() > 12 * 1024 * 1024) {runOnUiThread(()->notice("备份过大，请单独导出资料"));return;}
            try { new org.json.JSONObject(json); } catch (Exception e) { return; }
            saveDocumentBytes(json.getBytes(StandardCharsets.UTF_8), "application/json", "康复随行-报告或备份.json");
        }
        @JavascriptInterface public void saveDocument(String name, String base64, String type) {
            if (base64 == null || base64.length() > 12 * 1024 * 1024 || name == null) return;
            if (!java.util.Arrays.asList("application/pdf", "image/jpeg", "image/png", "text/plain").contains(type)) return;
            try {
                byte[] bytes = android.util.Base64.decode(base64, android.util.Base64.DEFAULT);
                if (bytes.length > 8 * 1024 * 1024) return;
                String safeName = name.replaceAll("[\\\\/:*?\"<>|\\p{Cntrl}]", "_");
                if (safeName.length() > 100) safeName = safeName.substring(safeName.length()-100);
                saveDocumentBytes(bytes, type, safeName);
            } catch (Exception e) { runOnUiThread(() -> notice("资料读取失败")); }
        }
        @JavascriptInterface public boolean cloudConfigured(){return cloud.configured();}
        @JavascriptInterface public void cloudDisconnect(){cloud.disconnect();}
        @JavascriptInterface public void cloudRequest(String id,String path,String method,String body){
            if(id==null||!id.matches("[0-9]{1,10}")||body==null||body.length()>12*1024*1024)return;
            network.execute(()->{int status;String json;try{CloudTransport.Reply reply=cloud.request(path,method,body);status=reply.status;json=reply.body;}catch(Exception e){status=503;json="{\"detail\":\"云端暂时无法连接，本机记录保留\"}";}
                final int code=status;final String value=json;runOnUiThread(()->{if(!isDestroyed())web.evaluateJavascript("PhoneCloud.reply("+JSONObject.quote(id)+","+code+","+JSONObject.quote(value)+")",null);});});
        }
        @JavascriptInterface public void settings(){runOnUiThread(()->new AlertDialog.Builder(MainActivity.this).setTitle("手机与云端").setItems(new String[]{"连接云端","暂停云端连接","导出本机备份","恢复本机备份","备份到云端","恢复云端备份"},(d,which)->{
            if(which==0)connectionDialog();
            else if(which==1){cloud.disconnect();notice("已暂停云端连接，本机功能可继续使用");}
            else if(which==2)web.evaluateJavascript("PhoneLocal.exportBackup()",null);
            else if(which==3)new AlertDialog.Builder(MainActivity.this).setMessage("恢复会替换当前文字记录和计划。旧数据将保留恢复前副本，录像与资料原件请单独保管。继续选择备份？").setPositiveButton("选择备份",(a,b)->startActivityForResult(new Intent(Intent.ACTION_OPEN_DOCUMENT).addCategory(Intent.CATEGORY_OPENABLE).setType("application/json"),IMPORT_BACKUP)).setNegativeButton("取消",null).show();
            else web.evaluateJavascript(which==4?"PhoneLocal.cloudBackup()":"PhoneLocal.cloudRestore()",null);
        }).show());}
        @JavascriptInterface public boolean speechAvailable(){return android.os.Build.VERSION.SDK_INT>=31&&SpeechRecognizer.isOnDeviceRecognitionAvailable(MainActivity.this);}
        @JavascriptInterface public void speechStart(){runOnUiThread(()->{if(!speechAvailable()){speechResult("","手机未安装本地语音识别服务，可使用键盘语音输入");return;}if(checkSelfPermission(Manifest.permission.RECORD_AUDIO)!=PackageManager.PERMISSION_GRANTED)requestPermissions(new String[]{Manifest.permission.RECORD_AUDIO},SPEECH_PERMISSION);else startSpeech();});}
        @JavascriptInterface public void speechCancel(){runOnUiThread(()->{endSpeech();speechResult("","已取消，原草稿保留");});}
        @JavascriptInterface public void printPage(){runOnUiThread(()->{android.print.PrintManager manager=(android.print.PrintManager)getSystemService(PRINT_SERVICE);manager.print("安康康复报告",web.createPrintDocumentAdapter("安康康复报告"),null);});}
    }
    private void connectionDialog(){
        LinearLayout fields=new LinearLayout(this);fields.setOrientation(LinearLayout.VERTICAL);fields.setPadding(40,0,40,0);
        EditText address=new EditText(this);address.setHint("https://云端地址 或 http://局域网IP:8770");address.setText(cloud.address());fields.addView(address);
        EditText code=new EditText(this);code.setHint("云端启动窗口的连接码");code.setInputType(android.text.InputType.TYPE_CLASS_TEXT|android.text.InputType.TYPE_TEXT_VARIATION_PASSWORD);fields.addView(code);
        new AlertDialog.Builder(this).setTitle("连接云端辅助").setMessage("个人功能在手机上运行。家庭共享与备份会发往你填写的服务器；HTTP 只用于可信局域网演示，异地必须 HTTPS。").setView(fields).setPositiveButton("连接",(d,w)->{
            final String endpoint=address.getText().toString(),key=code.getText().toString();network.execute(()->{try{cloud.connect(endpoint,key);runOnUiThread(()->{notice("已连接云端辅助");web.evaluateJavascript("PhoneLocal.cloudRefresh()",null);});}catch(Exception e){runOnUiThread(()->notice(e.getMessage()));}});
        }).setNegativeButton("取消",null).show();
    }
    private void startSpeech(){
        if(android.os.Build.VERSION.SDK_INT<31||!SpeechRecognizer.isOnDeviceRecognitionAvailable(this)){speechResult("","本地语音服务不可用");return;}
        endSpeech();speech=SpeechRecognizer.createOnDeviceSpeechRecognizer(this);
        speech.setRecognitionListener(new RecognitionListener(){
            public void onReadyForSpeech(Bundle b){}public void onBeginningOfSpeech(){}public void onRmsChanged(float f){}public void onBufferReceived(byte[] b){}public void onEndOfSpeech(){}public void onPartialResults(Bundle b){}public void onEvent(int t,Bundle b){}
            public void onError(int e){speechResult("","未识别到语音，原草稿保留（"+e+"）");endSpeech();}
            public void onResults(Bundle b){java.util.ArrayList<String> texts=b.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION);speechResult(texts==null||texts.isEmpty()?"":texts.get(0),"");endSpeech();}
        });
        Intent request=new Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH).putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL,RecognizerIntent.LANGUAGE_MODEL_FREE_FORM).putExtra(RecognizerIntent.EXTRA_LANGUAGE,"zh-CN").putExtra(RecognizerIntent.EXTRA_PREFER_OFFLINE,true);
        try{speech.startListening(request);}catch(Exception e){speechResult("","本地语音无法启动");endSpeech();}
    }
    private void endSpeech(){if(speech!=null){speech.cancel();speech.destroy();speech=null;}}
    private void speechResult(String text,String error){web.evaluateJavascript("PhoneLocal.speechResult("+JSONObject.quote(text)+","+JSONObject.quote(error)+")",null);}
    private void saveDocumentBytes(byte[] bytes, String type, String name) {
        runOnUiThread(() -> {
            if (exportBytes != null) { notice("请先完成上一次保存"); return; }
            exportBytes = bytes;
            Intent intent = new Intent(Intent.ACTION_CREATE_DOCUMENT).addCategory(Intent.CATEGORY_OPENABLE).setType(type).putExtra(Intent.EXTRA_TITLE, name);
            try { startActivityForResult(intent, SAVE_FILE); } catch (Exception e) { exportBytes = null; notice("无法打开保存窗口"); }
        });
    }
    private void notice(String text) { Toast.makeText(this, text, Toast.LENGTH_LONG).show(); }
    @Override public void onBackPressed() {
        web.evaluateJavascript("window.offlineBack && window.offlineBack()", value -> { if (!"true".equals(value)) new AlertDialog.Builder(this).setMessage("退出康复随行？").setPositiveButton("退出", (d,w) -> finish()).setNegativeButton("继续使用", null).show(); });
    }
    @Override protected void onPause() { endSpeech();web.evaluateJavascript("window.offlinePause && window.offlinePause()", null); web.onPause(); super.onPause(); }
    @Override protected void onResume() { super.onResume(); if (web != null) web.onResume(); }
    @Override protected void onDestroy() { network.shutdownNow();endSpeech();cancelPicker(); if (cameraRequest != null) cameraRequest.deny(); web.removeJavascriptInterface("OfflineAndroid"); web.destroy(); super.onDestroy(); }
}
