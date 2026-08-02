@echo off
REM Install permit module (+ campus / ticket UI).
REM No npm required — UI is Jinja + static JS served by python run.py
REM Usage: migration.bat
setlocal EnableExtensions EnableDelayedExpansion

set "SCRIPT_DIR=%~dp0"
set "SCRIPT_DIR=%SCRIPT_DIR:~0,-1%"
for %%I in ("%SCRIPT_DIR%\..") do set "ROOT=%%~fI"
set "OVERLAY=%ROOT%\permit-module\overlay"

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

echo ==^> 複製模組與核心覆蓋檔到：%TARGET%
xcopy "%OVERLAY%\*" "%TARGET%\" /E /I /Y /Q >nul
if errorlevel 1 (
  echo ERROR: xcopy 失敗
  exit /b 1
)

set "ENV_FILE=%TARGET%\.env"
set "EXAMPLE=%TARGET%\.env.example"
if exist "%ENV_FILE%" (
  findstr /R /C:"^[ ]*ENABLE_PERMIT_MODULE=" "%ENV_FILE%" >nul 2>&1
  if errorlevel 1 (
    echo.>>"%ENV_FILE%"
    echo # 可選車證／罰單模組>>"%ENV_FILE%"
    echo ENABLE_PERMIT_MODULE=1>>"%ENV_FILE%"
  ) else (
    powershell -NoProfile -Command ^
      "(Get-Content -LiteralPath '%ENV_FILE%' -Raw) -replace '(?m)^\s*ENABLE_PERMIT_MODULE=.*$','ENABLE_PERMIT_MODULE=1' | Set-Content -LiteralPath '%ENV_FILE%' -NoNewline"
  )
  echo ==^> 已設定 .env：ENABLE_PERMIT_MODULE=1
) else if exist "%EXAMPLE%" (
  copy /Y "%EXAMPLE%" "%ENV_FILE%" >nul
  findstr /R /C:"^[ ]*ENABLE_PERMIT_MODULE=" "%ENV_FILE%" >nul 2>&1
  if errorlevel 1 (
    echo.>>"%ENV_FILE%"
    echo ENABLE_PERMIT_MODULE=1>>"%ENV_FILE%"
  )
  echo ==^> 已從 .env.example 建立 .env（請填入 API Key）
)

echo.
echo 完成。只需啟動：
echo.
echo   %START_HINT%
echo.
echo   http://127.0.0.1:8010/               回報
echo   http://127.0.0.1:8010/admin          歷史
echo   http://127.0.0.1:8010/permit/lookup  車證／罰單
echo.
echo 無需 npm。
exit /b 0
