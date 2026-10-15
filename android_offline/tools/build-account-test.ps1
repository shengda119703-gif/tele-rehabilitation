param([string]$SdkRoot,[string]$JdkRoot)
$ErrorActionPreference='Stop'
$taskProject=(Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$taskRoot=(Resolve-Path (Join-Path $taskProject '..')).Path
if(-not $SdkRoot){$SdkRoot=Join-Path $taskRoot '.runtime/apk-tools/sdk'}
if(-not $JdkRoot){$JdkRoot=(Get-ChildItem (Join-Path $taskRoot '.runtime/apk-tools/jdk') -Directory | Select-Object -First 1).FullName}
$taskRun=Join-Path $taskProject ('build/account-qa-'+[guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path "$taskRun/classes","$taskRun/dex" -Force | Out-Null
$taskTools=Join-Path $SdkRoot 'build-tools/35.0.0'
$taskPlatform=Join-Path $SdkRoot 'platforms/android-35/android.jar'
$env:JAVA_HOME=$JdkRoot
function Invoke-AccountQa([string]$exe,[string[]]$arguments){& $exe @arguments;if($LASTEXITCODE -ne 0){throw 'Account QA build failed'}}
$taskManifest=Join-Path $taskRun 'AndroidManifest.xml'
# A generated build manifest is not a source or user-data edit.
$taskXml=New-Object System.Xml.XmlDocument
$taskXml.LoadXml('<manifest xmlns:android="http://schemas.android.com/apk/res/android" package="cn.tele.rehabilitation.offline.accountqa"><uses-sdk android:minSdkVersion="29" android:targetSdkVersion="35"/><application android:allowBackup="false"/><instrumentation android:name="cn.tele.rehabilitation.offline.qa.AccountSmoke" android:targetPackage="cn.tele.rehabilitation.offline"/></manifest>')
$taskXml.Save($taskManifest)
Invoke-AccountQa "$JdkRoot/bin/javac.exe" @('-encoding','UTF-8','--release','8','-classpath',$taskPlatform,'-d',"$taskRun/classes","$taskProject/tests/android/AccountSmoke.java")
$taskClasses=@(Get-ChildItem "$taskRun/classes" -Recurse -Filter '*.class' | ForEach-Object {$_.FullName})
Invoke-AccountQa "$taskTools/d8.bat" (@('--lib',$taskPlatform,'--min-api','29','--output',"$taskRun/dex")+$taskClasses)
Invoke-AccountQa "$taskTools/aapt2.exe" @('link','--manifest',$taskManifest,'-I',$taskPlatform,'-o',"$taskRun/unsigned.apk")
Invoke-AccountQa "$JdkRoot/bin/jar.exe" @('uf',"$taskRun/unsigned.apk",'-C',"$taskRun/dex",'classes.dex')
Invoke-AccountQa "$taskTools/zipalign.exe" @('-f','4',"$taskRun/unsigned.apk","$taskRun/aligned.apk")
$taskSigning=Join-Path $taskProject '.runtime/signing'
$taskSecret=ConvertTo-SecureString ([IO.File]::ReadAllText("$taskSigning/password.dpapi"))
$env:REHAB_APK_SIGNING_PASSWORD=(New-Object System.Net.NetworkCredential('',$taskSecret)).Password
try{Invoke-AccountQa "$taskTools/apksigner.bat" @('sign','--ks',"$taskSigning/offline-demo.jks",'--ks-key-alias','offline-demo','--ks-pass','env:REHAB_APK_SIGNING_PASSWORD','--key-pass','env:REHAB_APK_SIGNING_PASSWORD','--out',"$taskProject/build/account-qa.apk","$taskRun/aligned.apk")}finally{Remove-Item Env:REHAB_APK_SIGNING_PASSWORD -ErrorAction SilentlyContinue}
Write-Output "$taskProject/build/account-qa.apk"
