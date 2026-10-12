# Build TEST-profile instrumentation only; no participant recordings copied.
param([Parameter(Mandatory=$true)][string]$SdkRoot,
      [Parameter(Mandatory=$true)][string]$JdkRoot,
      [Parameter(Mandatory=$true)][string]$SigningRoot)
$ErrorActionPreference='Stop'
$qaProject=(Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$qaOutput=Join-Path $env:LOCALAPPDATA ('AnkangAndroid/build/lin-blackbox-'+[guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path "$qaOutput/classes","$qaOutput/dex","$qaOutput/assets" -Force | Out-Null
$qaJar=Join-Path $SdkRoot 'platforms/android-35/android.jar'
$qaTools=Join-Path $SdkRoot 'build-tools/35.0.0'
$env:JAVA_HOME=$JdkRoot
function Invoke-QaTool([string]$Exe,[string[]]$ArgsList) { & $Exe @ArgsList; if ($LASTEXITCODE -ne 0) {throw 'TEST instrumentation build failed'} }
$qaManifest='<manifest xmlns:android="http://schemas.android.com/apk/res/android" package="cn.tele.rehabilitation.offline.qa"><uses-sdk android:minSdkVersion="29" android:targetSdkVersion="35"/><application android:allowBackup="false"/><instrumentation android:name="cn.tele.rehabilitation.offline.qa.LinSmoke" android:targetPackage="cn.tele.rehabilitation.offline"/></manifest>'
[IO.File]::WriteAllText("$qaOutput/AndroidManifest.xml",$qaManifest)
Copy-Item -LiteralPath "$qaProject/android_offline/tests/android/lin-smoke.js" -Destination "$qaOutput/assets/lin-smoke.js"
$qaJava=[IO.File]::ReadAllText("$qaProject/android_offline/tests/android/LinSmoke.java")
# Android menu labels may be non-clickable TextViews inside a clickable row.
$qaJava=$qaJava.Replace('if(!node.performAction(AccessibilityNodeInfo.ACTION_CLICK))throw new Exception("Native menu action failed");', 'boolean clicked=node.performAction(AccessibilityNodeInfo.ACTION_CLICK); AccessibilityNodeInfo parent=node.getParent(); for(int depth=0;!clicked && parent!=null && depth<4;depth++){if(parent.isClickable())clicked=parent.performAction(AccessibilityNodeInfo.ACTION_CLICK);parent=parent.getParent();} if(!clicked)throw new Exception("Native menu action failed");')
$qaJava=$qaJava.Replace('if(!clicked)throw new Exception("Native menu action failed");', 'if(!clicked){android.graphics.Rect rect=new android.graphics.Rect();node.getBoundsInScreen(rect);if(!rect.isEmpty()){long time=android.os.SystemClock.uptimeMillis();android.view.MotionEvent down=android.view.MotionEvent.obtain(time,time,android.view.MotionEvent.ACTION_DOWN,rect.centerX(),rect.centerY(),0);android.view.MotionEvent up=android.view.MotionEvent.obtain(time,time+80,android.view.MotionEvent.ACTION_UP,rect.centerX(),rect.centerY(),0);clicked=getUiAutomation().injectInputEvent(down,true)&&getUiAutomation().injectInputEvent(up,true);down.recycle();up.recycle();}} if(!clicked)throw new Exception("Native menu action failed");')
[IO.File]::WriteAllText("$qaOutput/LinSmoke.java",$qaJava)
Invoke-QaTool "$JdkRoot/bin/javac.exe" @('-encoding','UTF-8','--release','8','-classpath',$qaJar,'-d',"$qaOutput/classes","$qaOutput/LinSmoke.java")
$qaClasses=@(Get-ChildItem "$qaOutput/classes" -Recurse -Filter '*.class' | ForEach-Object {$_.FullName})
Invoke-QaTool "$qaTools/d8.bat" (@('--lib',$qaJar,'--min-api','29','--output',"$qaOutput/dex")+$qaClasses)
Invoke-QaTool "$qaTools/aapt2.exe" @('link','--manifest',"$qaOutput/AndroidManifest.xml",'-I',$qaJar,'-A',"$qaOutput/assets",'-o',"$qaOutput/unsigned.apk")
Invoke-QaTool "$JdkRoot/bin/jar.exe" @('uf',"$qaOutput/unsigned.apk",'-C',"$qaOutput/dex",'classes.dex')
Invoke-QaTool "$qaTools/zipalign.exe" @('-f','4',"$qaOutput/unsigned.apk","$qaOutput/aligned.apk")
$qaSecret=ConvertTo-SecureString ([IO.File]::ReadAllText("$SigningRoot/password.dpapi"))
$env:REHAB_APK_SIGNING_PASSWORD=(New-Object System.Net.NetworkCredential('',$qaSecret)).Password
try {Invoke-QaTool "$qaTools/apksigner.bat" @('sign','--ks',"$SigningRoot/offline-demo.jks",'--ks-key-alias','offline-demo','--ks-pass','env:REHAB_APK_SIGNING_PASSWORD','--key-pass','env:REHAB_APK_SIGNING_PASSWORD','--out',"$qaOutput/lin-qa.apk","$qaOutput/aligned.apk")}
finally {Remove-Item Env:REHAB_APK_SIGNING_PASSWORD -ErrorAction SilentlyContinue}
Write-Output "$qaOutput/lin-qa.apk"
