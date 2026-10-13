param([string]$SdkRoot,[string]$JdkRoot,[string]$SigningRoot)
$ErrorActionPreference='Stop'
$taskProject=(Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$taskRun=Join-Path $env:LOCALAPPDATA ('AnkangAndroid/build/agent-test-'+[guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path "$taskRun/classes","$taskRun/dex" -Force | Out-Null
$taskPlatform=Join-Path $SdkRoot 'platforms/android-35/android.jar'
$taskTools=Join-Path $SdkRoot 'build-tools/35.0.0'
$env:JAVA_HOME=$JdkRoot
function Invoke-AgentQaTool([string]$Executable,[string[]]$Arguments){& $Executable @Arguments;if($LASTEXITCODE -ne 0){throw 'Agent QA build failed'}}
$taskManifest='<manifest xmlns:android="http://schemas.android.com/apk/res/android" package="cn.tele.rehabilitation.offline.agentqa"><uses-sdk android:minSdkVersion="29" android:targetSdkVersion="35"/><application android:allowBackup="false"/><instrumentation android:name="cn.tele.rehabilitation.offline.qa.DeepSeekSmoke" android:targetPackage="cn.tele.rehabilitation.offline"/></manifest>'
[IO.File]::WriteAllText("$taskRun/AndroidManifest.xml",$taskManifest)
Invoke-AgentQaTool "$JdkRoot/bin/javac.exe" @('-encoding','UTF-8','--release','8','-classpath',$taskPlatform,'-d',"$taskRun/classes","$taskProject/tests/android/DeepSeekSmoke.java")
$taskClasses=@(Get-ChildItem "$taskRun/classes" -Recurse -Filter '*.class'|ForEach-Object {$_.FullName})
Invoke-AgentQaTool "$taskTools/d8.bat" (@('--lib',$taskPlatform,'--min-api','29','--output',"$taskRun/dex")+$taskClasses)
Invoke-AgentQaTool "$taskTools/aapt2.exe" @('link','--manifest',"$taskRun/AndroidManifest.xml",'-I',$taskPlatform,'-o',"$taskRun/unsigned.apk")
Invoke-AgentQaTool "$JdkRoot/bin/jar.exe" @('uf',"$taskRun/unsigned.apk",'-C',"$taskRun/dex",'classes.dex')
Invoke-AgentQaTool "$taskTools/zipalign.exe" @('-f','4',"$taskRun/unsigned.apk","$taskRun/aligned.apk")
$taskSecret=ConvertTo-SecureString ([IO.File]::ReadAllText("$SigningRoot/password.dpapi"))
$env:REHAB_APK_SIGNING_PASSWORD=(New-Object System.Net.NetworkCredential('',$taskSecret)).Password
try{Invoke-AgentQaTool "$taskTools/apksigner.bat" @('sign','--ks',"$SigningRoot/offline-demo.jks",'--ks-key-alias','offline-demo','--ks-pass','env:REHAB_APK_SIGNING_PASSWORD','--key-pass','env:REHAB_APK_SIGNING_PASSWORD','--out',"$taskProject/build/agent-qa.apk","$taskRun/aligned.apk")}finally{Remove-Item Env:REHAB_APK_SIGNING_PASSWORD -ErrorAction SilentlyContinue}
Write-Output "$taskProject/build/agent-qa.apk"
