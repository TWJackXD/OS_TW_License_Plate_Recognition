# 車證／罰單模組

掛載於 opensource 核心同一程序（`python run.py`）。

- API：`/api/permits`
- 頁面：`/permit/lookup`、`/permit/manage`、`/permit/tickets`（Jinja + `/static/permit*.js`）
- 資料：`data/permits.db`；違規仍用核心 `violations.db`

由專案根目錄 `migration.sh` / `.ps1` / `.bat` 安裝，無需 npm。
