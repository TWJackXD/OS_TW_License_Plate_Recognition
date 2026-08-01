# 臺灣車牌辨識／違規回報系統

最小可執行套件：原圖送視覺語言模型辨識車牌 + 違規回報 PWA。

## 需求

- Python 3.10+
- OpenRouter API Key

## 安裝與啟動

將 `.env.example` 改為 `.env` 並填入 API Key。

```bash
python3 -m pip install -r requirements.txt
python3 run.py # http://127.0.0.1:8010/
```

## 環境變數

見 `.env.example`。常用：

| 變數 | 說明 |
| --- | --- |
| `VLM_BACKEND` | `openrouter`（預設）／`google`／`compat` |
| `OPENROUTER_API_KEY` | OpenRouter 金鑰 |
| `VLM_MODEL` | 例如 `google/gemma-3-4b-it` |
| `HOST` / `PORT` | 網站位址（預設 `0.0.0.0:8010`） |
