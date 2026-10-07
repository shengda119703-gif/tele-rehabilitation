param(
    [string]$SdkRoot,
    [string]$JdkRoot,
    [string]$Python
)
$ErrorActionPreference = 'Stop'
$apkProject = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$apkWorkspace = (Resolve-Path (Join-Path $apkProject '..')).Path
if (-not $SdkRoot) { $SdkRoot = Join-Path $apkWorkspace '.runtime/apk-tools/sdk' }
if (-not $JdkRoot) {
    $apkJdkDirectory = Get-ChildItem (Join-Path $apkWorkspace '.runtime/apk-tools/jdk') -Directory | Sort-Object Name -Descending | Select-Object -First 1
    $JdkRoot = $apkJdkDirectory.FullName
}
if (-not $Python) { $Python = Join-Path $apkWorkspace 'rehab_codex_single_camera_v2_1/.venv/Scripts/python.exe' }
$apkTools = Join-Path $SdkRoot 'build-tools/35.0.0'
$apkPlatform = Join-Path $SdkRoot 'platforms/android-35/android.jar'
foreach ($apkRequired in @((Join-Path $JdkRoot 'bin/javac.exe'), $apkPlatform, (Join-Path $apkTools 'aapt2.exe'), $Python)) {
    if (-not (Test-Path -LiteralPath $apkRequired)) { throw "Missing build dependency: $apkRequired" }
}
function Invoke-ApkTool([string]$Executable, [string[]]$Arguments) {
    & $Executable @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Build failed: $Executable (exit $LASTEXITCODE)" }
}
$env:JAVA_HOME = $JdkRoot
$apkBuild = Join-Path $apkProject 'build'
$apkOutput = Join-Path $apkProject 'dist'
$apkSigning = Join-Path $apkProject '.runtime/signing'
$apkRun = Join-Path $apkBuild ([guid]::NewGuid().ToString('N'))
foreach ($apkDirectory in @($apkRun,$apkOutput,$apkSigning)) { New-Item -ItemType Directory -Force $apkDirectory | Out-Null }
Invoke-ApkTool $Python @((Join-Path $PSScriptRoot 'prepare_assets.py'))
Invoke-ApkTool 'node' @((Join-Path $PSScriptRoot 'bundle_product.cjs'))
$apkClasses = Join-Path $apkRun 'classes'
$apkDex = Join-Path $apkRun 'dex'
New-Item -ItemType Directory -Force $apkClasses,$apkDex | Out-Null
$apkSources = @(Get-ChildItem (Join-Path $apkProject 'src') -Recurse -Filter '*.java' | ForEach-Object { $_.FullName })
Invoke-ApkTool (Join-Path $JdkRoot 'bin/javac.exe') (@('-J-Dfile.encoding=UTF-8','-encoding','UTF-8','--release','8','-classpath',$apkPlatform,'-d',$apkClasses) + $apkSources)
$apkCompiled = @(Get-ChildItem $apkClasses -Recurse -Filter '*.class' | ForEach-Object { $_.FullName })
Invoke-ApkTool (Join-Path $apkTools 'd8.bat') (@('--lib',$apkPlatform,'--min-api','29','--output',$apkDex) + $apkCompiled)
Invoke-ApkTool (Join-Path $apkTools 'aapt2.exe') @('compile','--dir',(Join-Path $apkProject 'res'),'-o',(Join-Path $apkRun 'resources.zip'))
$apkUnsigned = Join-Path $apkRun 'unsigned.apk'
Invoke-ApkTool (Join-Path $apkTools 'aapt2.exe') @('link','--manifest',(Join-Path $apkProject 'AndroidManifest.xml'),'-I',$apkPlatform,'-A',(Join-Path $apkBuild 'assets'),'-o',$apkUnsigned,'--auto-add-overlay',(Join-Path $apkRun 'resources.zip'))
$apkNormalized = Join-Path $apkRun 'normalized.apk'
Invoke-ApkTool $Python @((Join-Path $PSScriptRoot 'normalize_apk.py'),$apkUnsigned,$apkNormalized)
Invoke-ApkTool (Join-Path $JdkRoot 'bin/jar.exe') @('uf',$apkNormalized,'-C',$apkDex,'classes.dex')
$apkAligned = Join-Path $apkRun 'aligned.apk'
Invoke-ApkTool (Join-Path $apkTools 'zipalign.exe') @('-f','4',$apkNormalized,$apkAligned)
$apkPasswordFile = Join-Path $apkSigning 'password.dpapi'
$apkKeystore = Join-Path $apkSigning 'offline-demo.jks'
if (-not (Test-Path $apkPasswordFile)) {
    if (Test-Path $apkKeystore) { throw 'Signing password missing; existing key was NOT overwritten' }
    $apkRandom = New-Object byte[] 32
    [System.Security.Cryptography.RandomNumberGenerator]::Fill($apkRandom)
    $apkSecret = ConvertTo-SecureString ([Convert]::ToBase64String($apkRandom)) -AsPlainText -Force
    [System.IO.File]::WriteAllText($apkPasswordFile, (ConvertFrom-SecureString $apkSecret))
}
$apkProtected = ConvertTo-SecureString ([System.IO.File]::ReadAllText($apkPasswordFile))
$apkCredential = New-Object System.Net.NetworkCredential('', $apkProtected)
$env:REHAB_APK_SIGNING_PASSWORD = $apkCredential.Password
try {
    if (-not (Test-Path $apkKeystore)) {
        Invoke-ApkTool (Join-Path $JdkRoot 'bin/keytool.exe') @('-genkeypair','-keystore',$apkKeystore,'-alias','offline-demo','-keyalg','RSA','-keysize','3072','-validity','10000','-dname','CN=Tele Rehabilitation Local Demo','-storepass:env','REHAB_APK_SIGNING_PASSWORD','-keypass:env','REHAB_APK_SIGNING_PASSWORD')
    }
    $apkFinal = Join-Path $apkOutput 'tele-rehabilitation-mobile-0.2.0.apk'
    Invoke-ApkTool (Join-Path $apkTools 'apksigner.bat') @('sign','--ks',$apkKeystore,'--ks-key-alias','offline-demo','--ks-pass','env:REHAB_APK_SIGNING_PASSWORD','--key-pass','env:REHAB_APK_SIGNING_PASSWORD','--out',$apkFinal,$apkAligned)
    Invoke-ApkTool (Join-Path $apkTools 'apksigner.bat') @('verify','--verbose','--print-certs',$apkFinal)
    Get-FileHash -LiteralPath $apkFinal -Algorithm SHA256
    Get-Item -LiteralPath $apkFinal | Select-Object FullName,Length
} finally { Remove-Item Env:REHAB_APK_SIGNING_PASSWORD -ErrorAction SilentlyContinue }
