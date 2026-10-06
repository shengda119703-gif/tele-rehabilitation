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

/** Local assets only. No INTERNET permission, remote origin or arbitrary file bridge. */
public final class MainActivity extends Activity {
    private static final String ORIGIN = "https://appassets.androidplatform.net";
    private static final int PICK_FILE = 41, CAMERA_PERMISSION = 42, SAVE_FILE = 43;
    private WebView web;
    private ValueCallback<Uri[]> picker;
    private PermissionRequest cameraRequest;
    private boolean capturePending;
    private byte[] exportBytes;

    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
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
                if (path == null || !path.startsWith("/assets/") || path.contains("..") || path.contains("\\")) return denied();
                try {
                    InputStream stream = getAssets().open(path.substring(8));
                    Map<String, String> headers = new HashMap<>();
                    headers.put("Content-Security-Policy", "default-src 'self'; script-src 'self' blob: 'wasm-unsafe-eval'; worker-src 'self' blob:; connect-src 'self' blob:; img-src 'self' data: blob:; media-src 'self' blob:; style-src 'self'; object-src 'none'; frame-src 'none'; base-uri 'none'");
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
        web.loadUrl(ORIGIN + "/assets/index.html");
    }
    private static boolean trusted(Uri uri) { return "https".equals(uri.getScheme()) && "appassets.androidplatform.net".equals(uri.getHost()) && uri.getPort() == -1; }
    private static WebResourceResponse denied() { return new WebResourceResponse("text/plain", "UTF-8", 403, "Forbidden", new HashMap<>(), new ByteArrayInputStream(new byte[0])); }
    private static String mime(String path) {
        if (path.endsWith(".html")) return "text/html";
        if (path.endsWith(".js")) return "text/javascript";
        if (path.endsWith(".css")) return "text/css";
        if (path.endsWith(".json")) return "application/json";
        if (path.endsWith(".wasm")) return "application/wasm";
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
        if (code != CAMERA_PERMISSION) return;
        boolean granted = results.length > 0 && results[0] == PackageManager.PERMISSION_GRANTED;
        if (cameraRequest != null) { if (granted) cameraRequest.grant(new String[]{PermissionRequest.RESOURCE_VIDEO_CAPTURE}); else cameraRequest.deny(); cameraRequest = null; }
        if (capturePending) { capturePending = false; if (granted) captureVideo(); else { cancelPicker(); notice("未授权相机，仍可选择已有录像"); } }
    }
    @Override protected void onActivityResult(int request, int result, Intent data) {
        super.onActivityResult(request, result, data);
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
            if (json == null || json.length() > 4 * 1024 * 1024) return;
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
    }
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
    @Override protected void onPause() { web.evaluateJavascript("window.offlinePause && window.offlinePause()", null); web.onPause(); super.onPause(); }
    @Override protected void onResume() { super.onResume(); if (web != null) web.onResume(); }
    @Override protected void onDestroy() { cancelPicker(); if (cameraRequest != null) cameraRequest.deny(); web.removeJavascriptInterface("OfflineAndroid"); web.destroy(); super.onDestroy(); }
}
