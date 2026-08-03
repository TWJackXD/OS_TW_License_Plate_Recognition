# Niimbot B1 即時列印模組

可選模組：手機 **Chrome／Edge** 經 **Web Bluetooth** 連 **Niimbot B1（203 dpi）**，在回報送出寫入資料庫後即時列印 **50×80 mm** 罰單。

> 不使用 Node/USB 版 [niimbotjs](https://github.com/dtgreene/niimbotjs)（僅適合電腦插印表機）。瀏覽器 driver 採 [niimbot-web-bluetooth](https://github.com/iscarelli/niimbot-web-bluetooth)（已 vendoring）。

## 需求

- Niimbot **B1**、50×80 mm 熱感紙（預設視為有間隙／黑標）
- 瀏覽器：Chrome 或 Edge（支援 Web Bluetooth）
- 頁面須為 **HTTPS** 或 **localhost**（手機連區網 IP 時需 HTTPS 或埠轉發）
- 同一套 `python run.py`（安裝端無需 npm）

## 安裝

```bash
# 專案根目錄（可與車證模組並存；建議先 INSTALL_PERMIT 再裝本模組）
./INSTALL_NIIMBOT/INSTALL.sh
# Windows: INSTALL_NIIMBOT\INSTALL.bat 或 .\INSTALL.ps1

cd opensource
# .env 已含 ENABLE_NIIMBOT_MODULE=1
python run.py
```

## 使用

1. 開啟回報頁 → 按「連接印表機」配對 B1  
2. 拍照、確認 GPS、填違規原因 →「送出檢舉」  
3. 寫入資料庫成功後自動列印；失敗可按「重試列印」（資料庫紀錄保留）

若已安裝車證模組，列印時會自動查詢 `/api/permits` 帶入持有人。

## 環境變數

| 變數 | 說明 |
| --- | --- |
| `ENABLE_NIIMBOT_MODULE` | `1` 啟用 |
| `NIIMBOT_LABEL_TYPE` | `gap`（預設）／`continuous` |
| `NIIMBOT_DENSITY` | 1–5（預設 3） |

## 畫布

B1 印頭寬約 **384 px**（203 dpi）；紙寬 50 mm、紙長 80 mm → 列印緩衝 **384×640 px**（母稿 591×945 @ 300 dpi）。版面為正式罰單表格。
