# Install Niimbot B1 instant-print module (Web Bluetooth; no npm).
# Works from project root or INSTALL_NIIMBOT/
# Usage: .\INSTALL.ps1
$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
if (Test-Path -LiteralPath (Join-Path $ScriptDir "niimbot-module\overlay")) {
    $Root = $ScriptDir
} elseif (Test-Path -LiteralPath (Join-Path $ScriptDir "..\niimbot-module\overlay")) {
    $Root = (Resolve-Path (Join-Path $ScriptDir "..")).Path
} else {
    Write-Error "找不到 niimbot-module\overlay（請在專案根目錄或 INSTALL_NIIMBOT\ 執行）"
    exit 1
}
$Overlay = Join-Path $Root "niimbot-module\overlay"

function Die([string]$Msg) {
    Write-Error $Msg
    exit 1
}

function Ensure-EnvFlag([string]$File) {
    $raw = Get-Content -LiteralPath $File -Raw
    if ($raw -match '(?m)^\s*ENABLE_NIIMBOT_MODULE=') {
        $raw = [regex]::Replace($raw, '(?m)^\s*ENABLE_NIIMBOT_MODULE=.*$', 'ENABLE_NIIMBOT_MODULE=1')
        Set-Content -LiteralPath $File -Value $raw -NoNewline
    } else {
        Add-Content -LiteralPath $File -Value "`n# 可選 Niimbot B1 即時列印（Web Bluetooth）`nENABLE_NIIMBOT_MODULE=1"
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

Write-Host "==> 複製 Niimbot 模組覆蓋檔到：$Target"
Copy-Item -Path (Join-Path $Overlay "*") -Destination $Target -Recurse -Force

$EnvFile = Join-Path $Target ".env"
$Example = Join-Path $Target ".env.example"
if (Test-Path -LiteralPath $EnvFile) {
    Ensure-EnvFlag $EnvFile
    Write-Host "==> 已設定 .env：ENABLE_NIIMBOT_MODULE=1"
} elseif (Test-Path -LiteralPath $Example) {
    Copy-Item -LiteralPath $Example -Destination $EnvFile
    Ensure-EnvFlag $EnvFile
    Write-Host "==> 已從 .env.example 建立 .env（請填入 API Key）"
}

Write-Host @"

完成。只需啟動：

  $StartHint

  使用 Chrome／Edge（需 HTTPS 或本機 localhost）開啟回報頁，
  先按「連接印表機」配對 Niimbot B1，送出違規後會即時列印 58×80mm 罰單。

無需 npm。
"@
