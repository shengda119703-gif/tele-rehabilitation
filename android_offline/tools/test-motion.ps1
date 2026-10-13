param([string]$JdkRoot)
$ErrorActionPreference='Stop'
$taskRoot=(Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
if(-not $JdkRoot){$JdkRoot=(Get-ChildItem (Join-Path $taskRoot '.runtime/apk-tools/jdk') -Directory | Select-Object -First 1).FullName}
$taskClasses=Join-Path $taskRoot ('android_offline/build/motion-unit-'+[guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $taskClasses | Out-Null
& "$JdkRoot/bin/javac.exe" -encoding UTF-8 --release 8 -d $taskClasses "$taskRoot/android_offline/src/cn/tele/rehabilitation/offline/MotionMath.java" "$taskRoot/android_offline/tests/native/MotionMathTest.java"
if($LASTEXITCODE -ne 0){throw 'Motion unit compilation failed'}
& "$JdkRoot/bin/java.exe" -cp $taskClasses MotionMathTest
if($LASTEXITCODE -ne 0){throw 'Motion unit tests failed'}
