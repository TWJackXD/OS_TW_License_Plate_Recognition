@echo off
REM Install Niimbot B1 instant-print module (Web Bluetooth; no npm).
REM Works from project root or INSTALL_NIIMBOT\
REM Usage: INSTALL.bat
setlocal EnableExtensions EnableDelayedExpansion

set "SCRIPT_DIR=%~dp0"
set "SCRIPT_DIR=%SCRIPT_DIR:~0,-1%"

if exist "%SCRIPT_DIR%\niimbot-module\overlay\" (
  set "ROOT=%SCRIPT_DIR%"
) else if exist "%SCRIPT_DIR%\..\niimbot-module\overlay\" (
  for %%I in ("%SCRIPT_DIR%\..") do set "ROOT=%%~fI"
) else (
  echo ERROR: 找不到 niimbot-module\overlay
  exit /b 1
)

set "OVERLAY=%ROOT%\niimbot-module\overlay"

if not exist "%OVERLAY%\" (
  echo ERROR: 找不到 overlay：%OVERLAY%
  exit /b 1
)

if exist "%ROOT%\opensource\run.py" (
  set "TARGET=%ROOT%\opensource"
  set "START_HINT=cd opensource ^& python run.py"
) else if exist "%ROOT%\run.py" (
  set "TARGET=%ROOT%"
  set "START_HINT=python run.py"
) else (
  echo ERROR: 找不到可安裝的核心（缺少 opensource\run.py 或 .\run.py）
  exit /b 1
)

echo ==^> 複製 Niimbot 模組覆蓋檔到：%TARGET%
xcopy "%OVERLAY%\*" "%TARGET%\" /E /I /Y /Q >nul
if errorlevel 1 (
  echo ERROR: xcopy 失敗
  exit /b 1
)

set "ENV_FILE=%TARGET%\.env"
set "EXAMPLE=%TARGET%\.env.example"
if exist "%ENV_FILE%" (
  findstr /R /C:"^[ ]*ENABLE_NIIMBOT_MODULE=" "%ENV_FILE%" >nul 2>&1
  if errorlevel 1 (
    echo.>>"%ENV_FILE%"
    echo # 可選 Niimbot B1 即時列印（Web Bluetooth）>>"%ENV_FILE%"
    echo ENABLE_NIIMBOT_MODULE=1>>"%ENV_FILE%"
  ) else (
    powershell -NoProfile -Command ^
      "(Get-Content -LiteralPath '%ENV_FILE%' -Raw) -replace '(?m)^\s*ENABLE_NIIMBOT_MODULE=.*$','ENABLE_NIIMBOT_MODULE=1' | Set-Content -LiteralPath '%ENV_FILE%' -NoNewline"
  )
  echo ==^> 已設定 .env：ENABLE_NIIMBOT_MODULE=1
) else if exist "%EXAMPLE%" (
  copy /Y "%EXAMPLE%" "%ENV_FILE%" >nul
  findstr /R /C:"^[ ]*ENABLE_NIIMBOT_MODULE=" "%ENV_FILE%" >nul 2>&1
  if errorlevel 1 (
    echo.>>"%ENV_FILE%"
    echo ENABLE_NIIMBOT_MODULE=1>>"%ENV_FILE%"
  )
  echo ==^> 已從 .env.example 建立 .env（請填入 API Key）
)

echo.
echo 完成。只需啟動：
echo.
echo   %START_HINT%
echo.
echo   使用 Chrome／Edge（需 HTTPS 或本機 localhost）開啟回報頁，
echo   先按「連接印表機」配對 Niimbot B1，送出違規後會即時列印 58×80mm 罰單。
echo.
echo 無需 npm。
exit /b 0
