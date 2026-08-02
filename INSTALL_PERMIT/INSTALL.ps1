# Install permit module (+ campus / ticket UI).
# No npm required — UI is Jinja + static JS served by python run.py
# Usage: .\migration.ps1
$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Root = Split-Path -Parent $ScriptDir
$Overlay = Join-Path $Root "permit-module\overlay"

function Die([string]$Msg) {
    Write-Error $Msg
    exit 1
}

function Ensure-EnvFlag([string]$File) {
    $raw = Get-Content -LiteralPath $File -Raw
    if ($raw -match '(?m)^\s*ENABLE_PERMIT_MODULE=') {
        $raw = [regex]::Replace($raw, '(?m)^\s*ENABLE_PERMIT_MODULE=.*$', 'ENABLE_PERMIT_MODULE=1')
        Set-Content -LiteralPath $File -Value $raw -NoNewline
    } else {
        Add-Content -LiteralPath $File -Value "`n# 可選車證／罰單模組`nENABLE_PERMIT_MODULE=1"
    }
}

if (-not (Test-Path -LiteralPath $Overlay)) { Die "找不到 overlay：$Overlay" }

$OpenSourceRun = Join-Path $Root "opensource\run.py"
$RootRun = Join-Path $Root "run.py"
if (Test-Path -LiteralPath $OpenSourceRun) {
    $Target = Join-Path $Root "opensource"
    $StartHint = "cd opensource; python run.py"
} elseif (Test-Path -LiteralPath $RootRun) {
    $Target = $Root
    $StartHint = "python run.py"
} else {
    Die "找不到可安裝的核心（缺少 opensource\run.py 或 .\run.py）"
}

Write-Host "==> 複製模組與核心覆蓋檔到：$Target"
Copy-Item -Path (Join-Path $Overlay "*") -Destination $Target -Recurse -Force

$EnvFile = Join-Path $Target ".env"
$Example = Join-Path $Target ".env.example"
if (Test-Path -LiteralPath $EnvFile) {
    Ensure-EnvFlag $EnvFile
    Write-Host "==> 已設定 .env：ENABLE_PERMIT_MODULE=1"
} elseif (Test-Path -LiteralPath $Example) {
    Copy-Item -LiteralPath $Example -Destination $EnvFile
    Ensure-EnvFlag $EnvFile
    Write-Host "==> 已從 .env.example 建立 .env（請填入 API Key）"
}

Write-Host @"

完成。只需啟動：

  $StartHint

  http://127.0.0.1:8010/               回報
  http://127.0.0.1:8010/admin          歷史
  http://127.0.0.1:8010/permit/lookup  車證／罰單

無需 npm。
"@
