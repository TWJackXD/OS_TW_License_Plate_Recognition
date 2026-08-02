# 車證／罰單模組（安裝包）

將本目錄與根目錄的 `migration.*`、`.gitignore` 放在開源核心旁邊後執行 migration。

前台為 **Jinja + 靜態 JS**，與核心同一套 `python run.py`，**不需 npm**。

## 安裝

| 環境 | 指令 |
| --- | --- |
| Linux / macOS | `./migration.sh` |
| PowerShell | `.\migration.ps1` |
| Windows CMD | `migration.bat` |

會自動偵測安裝目標：`opensource/`（若存在）或目前目錄（含 `run.py` 的核心根目錄）。

## 啟動

```bash
python run.py
# 或：cd opensource && python run.py
# http://127.0.0.1:8010/permit/lookup
```
