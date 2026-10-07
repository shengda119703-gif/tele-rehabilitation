$ErrorActionPreference='Stop'
$taskProject=(Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$taskCache=Join-Path $taskProject '.runtime/ocr-data'
New-Item -ItemType Directory -Force $taskCache | Out-Null
$taskModels=@{chi_sim='A5FCB6F0DB1E1D6D8522F39DB4E848F05984669172E584E8D76B6B3141E1F730';eng='7D4322BD2A7749724879683FC3912CB542F19906C83BCC1A52132556427170B2'}
foreach($taskLanguage in $taskModels.Keys){
    $taskFile=Join-Path $taskCache ($taskLanguage+'.traineddata')
    if(-not(Test-Path -LiteralPath $taskFile)){
        & curl.exe --fail --location --max-time 120 ('https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/main/'+$taskLanguage+'.traineddata') -o $taskFile
        if($LASTEXITCODE -ne 0){throw "OCR model download failed: $taskLanguage"}
    }
    if((Get-FileHash -LiteralPath $taskFile -Algorithm SHA256).Hash -ne $taskModels[$taskLanguage]){throw "OCR checksum mismatch: $taskLanguage; existing file was NOT overwritten"}
}
Write-Output 'Bundled OCR models verified.'
