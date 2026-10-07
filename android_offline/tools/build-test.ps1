param([string]$JdkRoot,[string]$SdkRoot)
$ErrorActionPreference='Stop'
$apkProject=(Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$apkRoot=(Resolve-Path (Join-Path $apkProject '..')).Path
if(-not $JdkRoot){$JdkRoot=(Get-ChildItem (Join-Path $apkRoot '.runtime/apk-tools/jdk') -Directory | Select-Object -First 1).FullName}
if(-not $SdkRoot){$SdkRoot=Join-Path $apkRoot '.runtime/apk-tools/sdk'}
$env:JAVA_HOME=$JdkRoot
$apkTools=Join-Path $SdkRoot 'build-tools/35.0.0'
$apkJar=Join-Path $SdkRoot 'platforms/android-35/android.jar'
$apkTest=Join-Path $apkProject ('build/qa-'+[guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Force "$apkTest/classes","$apkTest/dex","$apkTest/assets" | Out-Null
# Raw participant fixtures stay in ignored build output and NEVER enter the release APK or Git.
Copy-Item -LiteralPath 'E:/game/test video/肩外展.mp4' -Destination "$apkTest/assets/shoulder.mp4"
Copy-Item -LiteralPath 'E:/game/test video/深蹲.mp4' -Destination "$apkTest/assets/squat.mp4"
Copy-Item -LiteralPath "$apkProject/tests/android/smoke.js" -Destination "$apkTest/assets/smoke.js"
Copy-Item -LiteralPath "$apkProject/tests/android/lin-smoke.js" -Destination "$apkTest/assets/lin-smoke.js"
function TestTool([string]$exe,[string[]]$argv){& $exe @argv;if($LASTEXITCODE -ne 0){throw "Failed: $exe"}}
TestTool "$JdkRoot/bin/javac.exe" (@('-encoding','UTF-8','--release','8','-classpath',$apkJar,'-d',"$apkTest/classes")+@(Get-ChildItem "$apkProject/tests/android" -Filter '*.java'|ForEach-Object{$_.FullName}))
$apkClasses=@(Get-ChildItem "$apkTest/classes" -Recurse -Filter '*.class'|ForEach-Object{$_.FullName})
TestTool "$apkTools/d8.bat" (@('--lib',$apkJar,'--min-api','29','--output',"$apkTest/dex")+$apkClasses)
TestTool "$apkTools/aapt2.exe" @('link','--manifest',"$apkProject/tests/android/AndroidManifest.xml",'-I',$apkJar,'-A',"$apkTest/assets",'-o',"$apkTest/unsigned.apk")
TestTool "$JdkRoot/bin/jar.exe" @('uf',"$apkTest/unsigned.apk",'-C',"$apkTest/dex",'classes.dex')
TestTool "$apkTools/zipalign.exe" @('-f','4',"$apkTest/unsigned.apk","$apkTest/aligned.apk")
$apkSecret=ConvertTo-SecureString ([IO.File]::ReadAllText("$apkProject/.runtime/signing/password.dpapi"))
$env:REHAB_APK_SIGNING_PASSWORD=(New-Object System.Net.NetworkCredential('',$apkSecret)).Password
try{TestTool "$apkTools/apksigner.bat" @('sign','--ks',"$apkProject/.runtime/signing/offline-demo.jks",'--ks-key-alias','offline-demo','--ks-pass','env:REHAB_APK_SIGNING_PASSWORD','--key-pass','env:REHAB_APK_SIGNING_PASSWORD','--out',"$apkProject/build/offline-qa.apk","$apkTest/aligned.apk")}finally{Remove-Item Env:REHAB_APK_SIGNING_PASSWORD -ErrorAction SilentlyContinue}
Write-Output "$apkProject/build/offline-qa.apk"
