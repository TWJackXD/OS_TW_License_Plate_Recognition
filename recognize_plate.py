#!/usr/bin/env python3
"""Recognize Taiwan license-plate numbers via VLM (OpenRouter by default)."""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
import time
import uuid
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from threading import Lock

import cv2
import numpy as np

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


def load_dotenv(path: Path | None = None) -> None:
    """Load simple KEY=VALUE pairs from .env into os.environ (no override)."""
    env_path = path or Path(__file__).resolve().parent / ".env"
    if not env_path.is_file():
        return
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        if key and key not in os.environ:
            os.environ[key] = value


load_dotenv()

SYSTEM_PROMPT = """你是一個臺灣車牌辨識助手。你會得到一張車輛／車牌相關圖片，請辨識出圖片中的車牌號碼。

常見格式（英數字合計，中間一定要用連字號 `-`）：
* 五碼：1234-AB、AB-1234、123-ABC、ABC-123
* 七碼：ABC-1234

規則：
1. 只回覆一個車牌號碼，不要加任何說明、標點、引號或前後綴。
2. 回覆時字母區塊與數字區塊之間必須加上 `-`（例如看到 MBS8105 請回覆 MBS-8105，不要回 MBS8105）。
3. 當英數字合計為五碼或七碼、且能清楚分成「純字母」與「純數字」兩段時，即使畫面上連字號不清楚，也請先依常見切法補上 `-` 再回覆，不要因此回 UNKNOWN。
4. 若圖片中有多個車牌，只選一個，並嚴格依下列優先順序：
   (a) 完整度：只考慮「五碼」或「七碼」的標準車牌；七碼優於五碼；略過明顯不完整、被裁切、字元數不對、或無法讀清的車牌。
   (b) 位置：在完整度相同時，選最接近畫面正中央的那一面車牌（以車牌中心點離影像中心最近為準），不要選邊角、背景、遠處或旁邊車輛的車牌。
   (c) 若中央與完整度仍難分，再選最清晰、最正面者。
5. 僅在完全無法辨識任何五碼／七碼車牌字元時才回覆 UNKNOWN，不要猜測無關內容，也不要回傳多個號碼。"""

USER_PROMPT = (
    "請辨識這張圖片中的車牌號碼。"
    "只回覆一個含連字號的號碼（如 MBS-8105 或 ABC-123）。"
    "若有多個車牌：優先選最完整的五碼或七碼（七碼優先），"
    "完整度相同時選最接近畫面正中央的那一面。"
)

# Backends:
#   openrouter — OpenRouter（預設；未 BYOK 時可能 429）
#   google     — Google AI Studio / Gemini API
#   compat     — legacy Ollama shim → vLLM
_raw_backend = (os.environ.get("VLM_BACKEND") or "").strip().lower()
GEMINI_API_KEY = (
    os.environ.get("GEMINI_API_KEY")
    or os.environ.get("GOOGLE_API_KEY")
    or os.environ.get("GOOGLE_AI_API_KEY")
    or ""
).strip()
OPENROUTER_API_KEY = (
    os.environ.get("OPENROUTER_API_KEY") or os.environ.get("OPENROUTER_API_TOKEN") or ""
).strip()

if _raw_backend:
    VLM_BACKEND = _raw_backend
elif OPENROUTER_API_KEY:
    VLM_BACKEND = "openrouter"
elif GEMINI_API_KEY:
    VLM_BACKEND = "google"
else:
    VLM_BACKEND = "openrouter"

if VLM_BACKEND in {"compat", "ollama", "vllm"}:
    VLM_BACKEND = "compat"
    DEFAULT_MODEL = (
        os.environ.get("VLM_MODEL")
        or os.environ.get("OLLAMA_MODEL")
        or "google/gemma-3-4b-it"
    )
    DEFAULT_VLM_URL = (
        os.environ.get("VLM_BASE_URL")
        or os.environ.get("OLLAMA_BASE_URL")
        or "http://127.0.0.1:11434"
    )
elif VLM_BACKEND in {"google", "gemini", "ai_studio"}:
    VLM_BACKEND = "google"
    DEFAULT_MODEL = (
        os.environ.get("VLM_MODEL")
        or os.environ.get("OLLAMA_MODEL")
        or "gemma-4-26b-a4b-it"
    )
    DEFAULT_VLM_URL = (
        os.environ.get("VLM_BASE_URL")
        or "https://generativelanguage.googleapis.com/v1beta"
    )
else:
    VLM_BACKEND = "openrouter"
    DEFAULT_MODEL = (
        os.environ.get("VLM_MODEL")
        or os.environ.get("OLLAMA_MODEL")
        or "google/gemma-3-4b-it"
    )
    DEFAULT_VLM_URL = (
        os.environ.get("VLM_BASE_URL")
        or os.environ.get("OLLAMA_BASE_URL")
        or "https://openrouter.ai/api/v1"
    )

# Backward-compatible alias used by web/app.py
DEFAULT_OLLAMA_URL = DEFAULT_VLM_URL
DEFAULT_MAX_SIDE = int(os.environ.get("VLM_MAX_SIDE") or "384")
DEFAULT_JPEG_QUALITY = int(os.environ.get("VLM_JPEG_QUALITY") or "70")
PLATE_PATTERN = re.compile(
    r"\b([A-Z0-9]{2,4}-[A-Z0-9]{2,4})\b",
    re.IGNORECASE,
)

DEFAULT_HTTP_HEADERS = {
    "User-Agent": "TaiwanPlateRecognition/1.0 (local-batch)",
    "Accept": "application/json, */*",
}


def collect_images(path: Path) -> list[Path]:
    """Collect image files from a file or directory."""
    if path.is_file():
        if path.suffix.lower() in IMAGE_EXTENSIONS:
            return [path]
        print(f"不支援的檔案格式: {path}", file=sys.stderr)
        return []

    if path.is_dir():
        return sorted(
            p
            for p in path.iterdir()
            if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS
        )

    print(f"路徑不存在: {path}", file=sys.stderr)
    return []


def log_status(message: str) -> None:
    """Print a timestamped status line to the terminal (flushed)."""
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {message}", flush=True)


def encode_image_b64(image: np.ndarray, ext: str = ".jpg", quality: int = 85) -> str:
    if ext.lower() in {".jpg", ".jpeg"}:
        ok, buf = cv2.imencode(".jpg", image, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
    else:
        ok, buf = cv2.imencode(ext, image)
    if not ok:
        raise RuntimeError("無法編碼圖片")
    return base64.b64encode(buf.tobytes()).decode("ascii")


def resize_for_vlm(image: np.ndarray, max_side: int = DEFAULT_MAX_SIDE) -> np.ndarray:
    """Downscale for faster vision inference while keeping aspect ratio."""
    h, w = image.shape[:2]
    longest = max(h, w)
    if longest <= max_side:
        return image
    scale = max_side / float(longest)
    new_w = max(1, int(round(w * scale)))
    new_h = max(1, int(round(h * scale)))
    return cv2.resize(image, (new_w, new_h), interpolation=cv2.INTER_AREA)


class VlmHttpError(RuntimeError):
    def __init__(self, code: int, url: str, detail: str) -> None:
        self.code = int(code)
        self.url = url
        self.detail = detail or ""
        super().__init__(f"VLM HTTP {self.code} ({url}): {self.detail}")


def _http_json_post(
    url: str,
    payload: dict,
    *,
    headers: dict[str, str],
    timeout: float,
    retries: int = 0,
    retry_statuses: tuple[int, ...] = (429, 502, 503),
) -> dict:
    data = json.dumps(payload).encode("utf-8")
    last_error: Exception | None = None
    attempts = max(1, retries + 1)
    for attempt in range(attempts):
        req = urllib.request.Request(
            url,
            data=data,
            headers={**DEFAULT_HTTP_HEADERS, **headers, "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:500]
            last_error = VlmHttpError(exc.code, url, detail or str(exc.reason))
            if exc.code not in retry_statuses or attempt >= attempts - 1:
                raise last_error from exc
            wait_s = min(20.0, (2 ** attempt) * 1.5)
            log_status(
                f"VLM HTTP {exc.code}，{wait_s:.1f}s 後重試（{attempt + 1}/{attempts}）…"
            )
            time.sleep(wait_s)
        except urllib.error.URLError as exc:
            last_error = RuntimeError(f"無法連線 VLM ({url}): {exc}")
            if attempt >= attempts - 1:
                raise last_error from exc
            wait_s = min(20.0, (2 ** attempt) * 1.5)
            log_status(
                f"VLM 連線失敗，{wait_s:.1f}s 後重試（{attempt + 1}/{attempts}）…"
            )
            time.sleep(wait_s)
    assert last_error is not None
    raise last_error


# OpenRouter list prices (USD per 1M tokens) for rough UI estimates
_OPENROUTER_USD_PER_1M: dict[str, tuple[float, float]] = {
    "google/gemma-3-4b-it": (0.05, 0.10),
    "google/gemma-4-26b-a4b-it": (0.07, 0.34),
    "google/gemini-2.5-flash-lite": (0.10, 0.40),
}


def _estimate_openrouter_cost_usd(
    model: str, prompt_tokens: int, completion_tokens: int
) -> float | None:
    prices = _OPENROUTER_USD_PER_1M.get((model or "").strip())
    if not prices:
        return None
    pin, pout = prices
    return (prompt_tokens / 1_000_000.0) * pin + (completion_tokens / 1_000_000.0) * pout


def _normalize_usage(raw: object, *, model: str | None = None) -> dict | None:
    """Normalize OpenAI-style usage dict for API/UI."""
    if not isinstance(raw, dict):
        return None
    prompt = raw.get("prompt_tokens")
    completion = raw.get("completion_tokens")
    total = raw.get("total_tokens")
    if prompt is None and completion is None and total is None:
        return None
    try:
        prompt_i = int(prompt or 0)
        completion_i = int(completion or 0)
        total_i = int(total) if total is not None else prompt_i + completion_i
    except (TypeError, ValueError):
        return None
    cost_usd = _estimate_openrouter_cost_usd(model or "", prompt_i, completion_i)
    out: dict = {
        "prompt_tokens": prompt_i,
        "completion_tokens": completion_i,
        "total_tokens": total_i,
    }
    if cost_usd is not None:
        out["cost_usd"] = round(cost_usd, 8)
    return out


def _google_model_id(model: str) -> str:
    """Normalize OpenRouter-style ids to Google AI Studio model ids."""
    name = (model or "").strip()
    if "/" in name:
        name = name.split("/", 1)[1]
    if name.endswith(":free"):
        name = name[: -len(":free")]
    return name or "gemma-4-26b-a4b-it"


def _usage_from_counts(
    prompt: object,
    completion: object,
    *,
    cost_usd: float | None = None,
) -> dict | None:
    try:
        prompt_i = int(prompt or 0)
        completion_i = int(completion or 0)
    except (TypeError, ValueError):
        return None
    out = {
        "prompt_tokens": prompt_i,
        "completion_tokens": completion_i,
        "total_tokens": prompt_i + completion_i,
        "cost_usd": cost_usd,
    }
    return out


def call_vlm_google(
    image: np.ndarray,
    *,
    model: str,
    base_url: str,
    api_key: str,
    timeout: float = 120.0,
) -> tuple[str, dict | None]:
    """Call Google AI Studio generateContent with the caller's own API key."""
    if not api_key:
        raise RuntimeError(
            "未設定 GEMINI_API_KEY（或 GOOGLE_API_KEY）。"
            "請到 https://aistudio.google.com/apikey 建立 Key 後寫入 .env"
        )
    model_id = _google_model_id(model)
    b64 = encode_image_b64(image, ext=".jpg", quality=DEFAULT_JPEG_QUALITY)
    payload = {
        "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
        "contents": [
            {
                "role": "user",
                "parts": [
                    {"text": USER_PROMPT},
                    {"inline_data": {"mime_type": "image/jpeg", "data": b64}},
                ],
            }
        ],
        "generationConfig": {
            "temperature": 0.0,
            "topP": 0.9,
            "maxOutputTokens": 24,
        },
    }
    url = f"{base_url.rstrip('/')}/models/{model_id}:generateContent"
    body = _http_json_post(
        url,
        payload,
        headers={"x-goog-api-key": api_key},
        timeout=timeout,
        retries=int(os.environ.get("VLM_HTTP_RETRIES", "2")),
    )
    candidates = body.get("candidates") or []
    if not candidates:
        raise RuntimeError(f"VLM 回傳空白內容: {body}")
    parts = (((candidates[0] or {}).get("content") or {}).get("parts")) or []
    texts = [
        str(part.get("text") or "").strip()
        for part in parts
        if isinstance(part, dict) and part.get("text")
    ]
    content = "\n".join(t for t in texts if t).strip()
    if not content:
        raise RuntimeError(f"VLM 回傳空白內容: {body}")

    meta = body.get("usageMetadata") or {}
    usage = _usage_from_counts(
        meta.get("promptTokenCount"),
        meta.get("candidatesTokenCount"),
        cost_usd=None,  # Google AI Studio free/paid tiers vary; don't guess USD
    )
    if usage and meta.get("totalTokenCount") is not None:
        try:
            usage["total_tokens"] = int(meta["totalTokenCount"])
        except (TypeError, ValueError):
            pass
    return content, usage


_openrouter_fallback_until = 0.0
_openrouter_fallback_lock = Lock()


def _openrouter_mark_fallback_window(window_s: float) -> None:
    global _openrouter_fallback_until
    with _openrouter_fallback_lock:
        _openrouter_fallback_until = time.monotonic() + max(0.0, window_s)


def _openrouter_in_fallback_window() -> bool:
    with _openrouter_fallback_lock:
        return time.monotonic() < _openrouter_fallback_until


def _openrouter_fallback_remaining_s() -> float:
    with _openrouter_fallback_lock:
        return max(0.0, _openrouter_fallback_until - time.monotonic())


def _is_rate_limited_error(exc: BaseException) -> bool:
    if isinstance(exc, VlmHttpError) and exc.code == 429:
        return True
    text = str(exc).lower()
    return "http 429" in text or '"code":429' in text or "rate-limited" in text


def call_vlm_openrouter(
    image: np.ndarray,
    *,
    model: str,
    base_url: str,
    api_key: str,
    timeout: float = 120.0,
) -> tuple[str, dict | None]:
    if not api_key:
        raise RuntimeError(
            "未設定 OPENROUTER_API_KEY。請在 .env 填入，或 export OPENROUTER_API_KEY=…"
        )
    primary = (model or "").strip() or "google/gemma-3-4b-it"
    fallback = (
        os.environ.get("OPENROUTER_FALLBACK_MODEL") or "google/gemini-2.5-flash-lite"
    ).strip()
    try:
        window_s = float(os.environ.get("OPENROUTER_FALLBACK_SECONDS") or "10")
    except ValueError:
        window_s = 10.0
    window_s = max(0.0, window_s)
    can_fallback = bool(fallback) and fallback != primary

    b64 = encode_image_b64(image, ext=".jpg", quality=DEFAULT_JPEG_QUALITY)
    url = f"{base_url.rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "HTTP-Referer": "https://github.com/TWJackXD/Taiwanese_License_Plate_Recognition",
        "X-Title": "Taiwan Plate Recognition",
    }
    retries = int(os.environ.get("VLM_HTTP_RETRIES", "3"))

    def _provider_for(*, prefer_google: bool) -> dict:
        provider_order = [
            p.strip()
            for p in (os.environ.get("OPENROUTER_PROVIDER_ORDER") or "").split(",")
            if p.strip()
        ]
        if prefer_google and not provider_order:
            provider_order = ["Google"]
        provider: dict = {
            "require_parameters": True,
            "allow_fallbacks": True,
        }
        if provider_order:
            provider["order"] = provider_order
        return provider

    def _once(
        model_id: str,
        *,
        retries_n: int,
        retry_statuses: tuple[int, ...],
        prefer_google: bool,
        used_fallback: bool,
    ) -> tuple[str, dict | None]:
        payload = {
            "model": model_id,
            "stream": False,
            "temperature": 0.0,
            "top_p": 0.9,
            "max_tokens": 24,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": USER_PROMPT},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
                        },
                    ],
                },
            ],
            "provider": _provider_for(prefer_google=prefer_google),
        }
        body = _http_json_post(
            url,
            payload,
            headers=headers,
            timeout=timeout,
            retries=retries_n,
            retry_statuses=retry_statuses,
        )
        choices = body.get("choices") or []
        if not choices:
            raise RuntimeError(f"VLM 回傳空白內容: {body}")
        message = choices[0].get("message") or {}
        content = (message.get("content") or "").strip()
        if isinstance(content, list):
            texts = [
                part.get("text", "")
                for part in content
                if isinstance(part, dict) and part.get("type") in {None, "text"}
            ]
            content = "\n".join(t for t in texts if t).strip()
        if not content:
            raise RuntimeError(f"VLM 回傳空白內容: {body}")
        usage = _normalize_usage(body.get("usage"), model=model_id) or {}
        usage["model"] = model_id
        usage["fallback"] = bool(used_fallback)
        return content, usage

    def _call_fallback(reason: str) -> tuple[str, dict | None]:
        _openrouter_mark_fallback_window(window_s)
        log_status(
            f"{reason} → 重試同一張圖，改用 {fallback}"
            f"（之後 {window_s:.0f}s 內優先 fallback）…"
        )
        try:
            return _once(
                fallback,
                retries_n=retries,
                retry_statuses=(502, 503),
                prefer_google=True,
                used_fallback=True,
            )
        except Exception as fallback_exc:
            if not _is_rate_limited_error(fallback_exc):
                raise
            log_status(f"fallback {fallback} 也 429，放寬供應商再試一次…")
            return _once(
                fallback,
                retries_n=max(1, retries),
                retry_statuses=(429, 502, 503),
                prefer_google=False,
                used_fallback=True,
            )

    if can_fallback and window_s > 0 and _openrouter_in_fallback_window():
        log_status(
            f"429 冷卻中（{_openrouter_fallback_remaining_s():.1f}s），"
            f"本張直接用 fallback：{fallback}"
        )
        try:
            return _once(
                fallback,
                retries_n=retries,
                retry_statuses=(502, 503),
                prefer_google=True,
                used_fallback=True,
            )
        except Exception as exc:
            if _is_rate_limited_error(exc):
                return _call_fallback(f"fallback 冷卻路徑仍 429（{fallback}）")
            raise

    try:
        # Primary: never sleep-retry 429 — switch model and retry this photo.
        return _once(
            primary,
            retries_n=retries,
            retry_statuses=(502, 503),
            prefer_google=False,
            used_fallback=False,
        )
    except Exception as exc:
        if can_fallback and _is_rate_limited_error(exc):
            return _call_fallback(f"主模型 429（{primary}）")
        raise


def call_vlm_compat(
    image: np.ndarray,
    *,
    model: str,
    base_url: str,
    timeout: float = 120.0,
) -> tuple[str, dict | None]:
    """POST /api/chat (Ollama-compatible → legacy vLLM shim)."""
    payload = {
        "model": model,
        "stream": False,
        "keep_alive": "15m",
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": USER_PROMPT,
                "images": [encode_image_b64(image, ext=".jpg", quality=DEFAULT_JPEG_QUALITY)],
            },
        ],
        "options": {
            "temperature": 0.0,
            "top_p": 0.9,
            "top_k": 20,
            "num_predict": 32,
        },
    }
    url = f"{base_url.rstrip('/')}/api/chat"
    body = _http_json_post(url, payload, headers={}, timeout=timeout)
    message = body.get("message") or {}
    content = (message.get("content") or "").strip()
    if not content:
        raise RuntimeError(f"VLM 回傳空白內容: {body}")
    # Ollama-style responses rarely include OpenAI usage; keep None if absent.
    usage = _normalize_usage(body.get("usage"))
    eval_count = body.get("eval_count")
    prompt_eval_count = body.get("prompt_eval_count")
    if usage is None and (eval_count is not None or prompt_eval_count is not None):
        try:
            prompt_i = int(prompt_eval_count or 0)
            completion_i = int(eval_count or 0)
            usage = {
                "prompt_tokens": prompt_i,
                "completion_tokens": completion_i,
                "total_tokens": prompt_i + completion_i,
                "cost_usd": None,
            }
        except (TypeError, ValueError):
            usage = None
    return content, usage


def call_vlm_chat(
    image: np.ndarray,
    *,
    model: str = DEFAULT_MODEL,
    base_url: str = DEFAULT_VLM_URL,
    timeout: float = 120.0,
    backend: str | None = None,
    api_key: str | None = None,
) -> tuple[str, dict | None]:
    """Send a plate image to the configured VLM backend and return (text, usage)."""
    h, w = image.shape[:2]
    backend_name = (backend or VLM_BACKEND).strip().lower()
    log_status(f"編碼圖片送往 VLM（{w}x{h}，backend={backend_name}）…")
    t0 = time.perf_counter()
    try:
        if backend_name in {"compat", "ollama", "vllm"}:
            content, usage = call_vlm_compat(
                image, model=model, base_url=base_url, timeout=timeout
            )
        elif backend_name in {"google", "gemini", "ai_studio"}:
            content, usage = call_vlm_google(
                image,
                model=model,
                base_url=base_url
                if "generativelanguage.googleapis.com" in base_url
                else "https://generativelanguage.googleapis.com/v1beta",
                api_key=(api_key if api_key is not None else GEMINI_API_KEY),
                timeout=timeout,
            )
        else:
            content, usage = call_vlm_openrouter(
                image,
                model=model,
                base_url=base_url,
                api_key=(api_key if api_key is not None else OPENROUTER_API_KEY),
                timeout=timeout,
            )
    except RuntimeError as exc:
        elapsed = time.perf_counter() - t0
        log_status(f"VLM 失敗（{elapsed:.1f}s）：{exc}")
        raise

    elapsed = time.perf_counter() - t0
    if usage:
        log_status(
            f"VLM 回應完成（{elapsed:.1f}s）：{content!r}；"
            f"tokens in={usage.get('prompt_tokens')} out={usage.get('completion_tokens')} "
            f"total={usage.get('total_tokens')}"
        )
    else:
        log_status(f"VLM 回應完成（{elapsed:.1f}s）：{content!r}")
    return content, usage


# Backward-compatible alias
call_ollama_vision = call_vlm_chat


def call_web_recognize(
    image_path: Path,
    *,
    server_url: str,
    timeout: float = 180.0,
) -> dict:
    """POST multipart to remote web `/api/recognize` (e.g. RunPod HTTP 8010 proxy)."""
    url = f"{server_url.rstrip('/')}/api/recognize"
    raw = image_path.read_bytes()
    boundary = f"----PlateBoundary{uuid.uuid4().hex}"
    filename = image_path.name or "upload.jpg"
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="image"; filename="{filename}"\r\n'
        f"Content-Type: application/octet-stream\r\n\r\n"
    ).encode("utf-8") + raw + f"\r\n--{boundary}--\r\n".encode("utf-8")

    log_status(
        f"上傳至伺服器 {url}（{len(raw) / 1024:.1f} KB，逾時 {timeout:.0f}s）…"
    )
    t0 = time.perf_counter()
    req = urllib.request.Request(
        url,
        data=body,
        headers={
            **DEFAULT_HTTP_HEADERS,
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            result = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        elapsed = time.perf_counter() - t0
        detail = exc.read().decode("utf-8", errors="replace")[:300]
        log_status(f"伺服器 HTTP {exc.code}（{elapsed:.1f}s）：{detail or exc.reason}")
        raise RuntimeError(
            f"無法連線辨識伺服器 ({url}): HTTP {exc.code} {exc.reason}"
            + (f" — {detail}" if detail else "")
        ) from exc
    except urllib.error.URLError as exc:
        elapsed = time.perf_counter() - t0
        log_status(f"伺服器連線失敗（{elapsed:.1f}s）：{exc}")
        raise RuntimeError(f"無法連線辨識伺服器 ({url}): {exc}") from exc

    elapsed = time.perf_counter() - t0
    plate = (result.get("plate_number") or "").strip()
    log_status(
        f"伺服器回應完成（{elapsed:.1f}s）："
        f"{plate or result.get('error') or result!r}"
    )
    return result


def insert_hyphen_for_compact_plate(text: str) -> str | None:
    """If text is 5/7 alnum with one letter↔digit split, insert '-' (e.g. MBS8105 → MBS-8105)."""
    if "-" in text:
        return None
    if len(text) not in (5, 7):
        return None
    if not re.fullmatch(r"[A-Z0-9]+", text):
        return None
    if not (re.search(r"[A-Z]", text) and re.search(r"[0-9]", text)):
        return None

    for i in range(1, len(text)):
        left, right = text[:i], text[i:]
        ok_split = (left.isalpha() and right.isdigit()) or (
            left.isdigit() and right.isalpha()
        )
        if ok_split and 2 <= len(left) <= 4 and 2 <= len(right) <= 4:
            return f"{left}-{right}"
    return None


def normalize_plate_text(raw: str) -> str | None:
    """Extract and normalize a TW plate string from model output."""
    text = raw.strip().upper().replace(" ", "").replace("_", "-")
    text = text.replace("—", "-").replace("–", "-")

    match = PLATE_PATTERN.search(text)
    if match:
        candidate = match.group(1).upper()
        if re.search(r"[A-Z]", candidate) and re.search(r"[0-9]", candidate):
            return candidate

    # Fallback: keep only A-Z / digits / hyphen
    cleaned = re.sub(r"[^A-Z0-9\-]", "", text)
    if PLATE_PATTERN.fullmatch(cleaned):
        if re.search(r"[A-Z]", cleaned) and re.search(r"[0-9]", cleaned):
            return cleaned

    # Model often omits hyphen (MBS8105); recover for 5/7-char plates
    compact = cleaned.replace("-", "")
    repaired = insert_hyphen_for_compact_plate(compact)
    if repaired and PLATE_PATTERN.fullmatch(repaired):
        return repaired

    return None


def format_progress_bar(done: int, total: int, width: int = 28) -> str:
    total = max(total, 1)
    done = min(max(done, 0), total)
    ratio = done / total
    filled = int(round(width * ratio))
    bar = "█" * filled + "░" * (width - filled)
    return f"[{bar}] {done}/{total} ({ratio * 100:5.1f}%)"


def print_scan_progress(
    *,
    index: int,
    total: int,
    name: str,
    status: str,
    message: str,
    workers: int,
) -> None:
    """Print one progress line for batch recognition."""
    bar = format_progress_bar(index, total)
    if workers <= 1:
        head = f"掃描第 {index}/{total} 張"
    else:
        head = f"已完成 {index}/{total} 張"
    print(f"{bar}  {head}  [{status}] {name}: {message}", flush=True)


def sanitize_filename(plate: str) -> str:
    return re.sub(r"[^A-Z0-9\-_]", "", plate.upper())


def unique_output_path(
    output_dir: Path,
    plate: str,
    suffix: str = ".png",
    extra: str = "",
) -> Path:
    base = sanitize_filename(plate) or "UNKNOWN"
    if extra:
        base = f"{base}_{extra}"
    candidate = output_dir / f"{base}{suffix}"
    if not candidate.exists():
        return candidate
    idx = 2
    while True:
        candidate = output_dir / f"{base}_{idx}{suffix}"
        if not candidate.exists():
            return candidate
        idx += 1


def recognize_bgr_image(
    image: np.ndarray,
    *,
    model: str = DEFAULT_MODEL,
    base_url: str = DEFAULT_VLM_URL,
    use_binary: bool = False,
    max_side: int = DEFAULT_MAX_SIDE,
    backend: str | None = None,
) -> dict:
    """Resize original photo and send to VLM (no OpenCV plate-box step).

    `use_binary` is ignored (API compat).

    Returns dict with keys:
      ok, plate, raw, box_points, boxed_bgr, processed_bgr, error
    """
    del use_binary
    total_t0 = time.perf_counter()
    h, w = image.shape[:2]
    log_status(f"開始辨識（原圖 {w}x{h}，略過邊框偵測）")

    box_points = None
    boxed = None

    ocr_image = resize_for_vlm(image, max_side=max_side)
    oh, ow = ocr_image.shape[:2]
    log_status(f"縮放後尺寸 {ow}x{oh}（max_side={max_side}）")

    try:
        raw, usage = call_vlm_chat(
            ocr_image, model=model, base_url=base_url, backend=backend
        )
    except RuntimeError as exc:
        log_status(f"辨識失敗：{exc}")
        return {
            "ok": False,
            "plate": None,
            "raw": None,
            "box_points": box_points,
            "boxed_bgr": boxed,
            "processed_bgr": ocr_image,
            "error": str(exc),
            "usage": None,
            "elapsed_sec": round(time.perf_counter() - total_t0, 3),
        }

    plate = normalize_plate_text(raw)
    elapsed = time.perf_counter() - total_t0
    if plate is None and raw.strip().upper() == "UNKNOWN":
        log_status(f"結果：UNKNOWN（總耗時 {elapsed:.1f}s）")
        return {
            "ok": False,
            "plate": None,
            "raw": raw,
            "box_points": box_points,
            "boxed_bgr": boxed,
            "processed_bgr": ocr_image,
            "error": "模型回覆 UNKNOWN",
            "usage": usage,
            "elapsed_sec": round(elapsed, 3),
        }

    if plate:
        log_status(f"結果：{plate}（總耗時 {elapsed:.1f}s）")
    else:
        log_status(f"結果無法解析：{raw!r}（總耗時 {elapsed:.1f}s）")

    return {
        "ok": plate is not None,
        "plate": plate,
        "raw": raw,
        "box_points": box_points,
        "boxed_bgr": boxed,
        "processed_bgr": ocr_image,
        "error": None if plate else f"無法解析號碼（模型回覆: {raw!r}）",
        "usage": usage,
        "elapsed_sec": round(elapsed, 3),
    }


def process_one(
    image_path: Path,
    output_dir: Path,
    *,
    model: str,
    base_url: str,
    save_boxed: bool,
    use_binary: bool = False,
    server_url: str | None = None,
    backend: str | None = None,
) -> tuple[bool, str]:
    """Recognize plate → save under plate filename. Returns (ok, message).

    If `server_url` is set, POST to remote web `/api/recognize`.
    Otherwise call configured VLM backend (OpenRouter or legacy compat).
    """
    image = cv2.imread(str(image_path))
    if image is None:
        return False, f"無法讀取 {image_path}"

    if server_url:
        try:
            remote = call_web_recognize(image_path, server_url=server_url)
        except RuntimeError as exc:
            safe_raw = sanitize_filename(str(exc))[:32] or "UNKNOWN"
            out_path = unique_output_path(output_dir, f"UNKNOWN_{safe_raw}")
            cv2.imwrite(str(out_path), image)
            return False, f"{exc} → {out_path.name}"

        plate = normalize_plate_text(remote.get("plate_number") or "")
        raw = remote.get("raw") or remote.get("plate_number") or ""
        ok = bool(remote.get("ok")) and plate is not None
        error = remote.get("error") or "伺服器未回傳車牌"
        if not ok or plate is None:
            safe_raw = sanitize_filename(str(raw or error))[:32] or "UNKNOWN"
            out_path = unique_output_path(output_dir, f"UNKNOWN_{safe_raw}")
            cv2.imwrite(str(out_path), image)
            return False, f"{error} → {out_path.name}"

        out_path = unique_output_path(output_dir, plate, suffix=".jpg")
        cv2.imwrite(str(out_path), image)
        return True, f"{plate} ← {raw!r} → {out_path.name}"

    result = recognize_bgr_image(
        image,
        model=model,
        base_url=base_url,
        use_binary=use_binary,
        backend=backend,
    )

    plate = result["plate"]
    raw = result["raw"] or ""
    # Prefer original resolution for archive; fall back to resized send-copy.
    save_image = image if image is not None else result["processed_bgr"]

    if not result["ok"] or plate is None:
        safe_raw = sanitize_filename(raw)[:32] or "UNKNOWN"
        out_path = unique_output_path(output_dir, f"UNKNOWN_{safe_raw}")
        if save_image is not None:
            cv2.imwrite(str(out_path), save_image)
        return False, f"{result['error']} → {out_path.name}"

    out_path = unique_output_path(output_dir, plate, suffix=".jpg")
    cv2.imwrite(str(out_path), save_image)

    if save_boxed and result["boxed_bgr"] is not None:
        boxed_path = unique_output_path(output_dir, plate, suffix=".jpg", extra="boxed")
        cv2.imwrite(str(boxed_path), result["boxed_bgr"])

    return True, f"{plate} ← {raw!r} → {out_path.name}"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="臺灣車牌號碼辨識（原圖直送 VLM /api/chat → vLLM）"
    )
    parser.add_argument(
        "path",
        nargs="?",
        default=None,
        help="單張圖片路徑（與 --input 二選一）",
    )
    parser.add_argument(
        "--input",
        "-i",
        type=Path,
        default=None,
        help="輸入圖片資料夾（預設: images）",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=Path("output"),
        help="輸出資料夾（預設: output）",
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help=f"VLM 模型名稱（預設: {DEFAULT_MODEL}）",
    )
    parser.add_argument(
        "--ollama-url",
        "--vlm-url",
        dest="ollama_url",
        default=DEFAULT_VLM_URL,
        help=(
            f"VLM API 根網址（預設: {DEFAULT_VLM_URL}；"
            "OpenRouter 用 …/api/v1，legacy compat 用 …:11434）"
        ),
    )
    parser.add_argument(
        "--backend",
        choices=("google", "openrouter", "compat"),
        default=VLM_BACKEND if VLM_BACKEND in {"google", "openrouter", "compat"} else "openrouter",
        help=f"推論後端（預設: {VLM_BACKEND}）",
    )
    parser.add_argument(
        "--server-url",
        "--web-url",
        dest="server_url",
        default=os.environ.get("RECOGNIZE_SERVER_URL") or None,
        help=(
            "遠端網站根網址（POST /api/recognize）。"
            "例如本機批次打已部署的網站"
        ),
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="最多處理幾張（測試用）",
    )
    parser.add_argument(
        "--clear-output",
        action="store_true",
        help="開始前清空 output 資料夾內舊圖",
    )
    parser.add_argument(
        "--save-boxed",
        action="store_true",
        help="（已停用）過去會存綠框圖；現已略過邊框偵測",
    )
    parser.add_argument(
        "--use-enhanced",
        action="store_true",
        help="（已停用）不再做影像前處理，此參數忽略",
    )
    parser.add_argument(
        "--workers",
        "-j",
        type=int,
        default=int(os.environ.get("BATCH_WORKERS", "1")),
        help="並行請求數（預設 1；RunPod L4 建議 2，需 OLLAMA_NUM_PARALLEL≥此值）",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    if args.path is not None:
        source = Path(args.path)
    elif args.input is not None:
        source = args.input
    else:
        source = Path("images")

    images = collect_images(source)
    if args.limit is not None:
        images = images[: max(args.limit, 0)]
    if not images:
        print("沒有找到可處理的圖片。", file=sys.stderr)
        return 1

    output_dir = args.output
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.clear_output:
        for old in output_dir.iterdir():
            if old.is_file() and old.suffix.lower() in {
                ".jpg",
                ".jpeg",
                ".png",
                ".bmp",
                ".webp",
            }:
                old.unlink()

    workers = max(1, args.workers)
    total = len(images)
    endpoint = (
        f"server={args.server_url}"
        if args.server_url
        else f"backend={args.backend}, vlm={args.ollama_url}, model={args.model}"
    )
    print(
        f"處理 {total} 張 → {output_dir}/  "
        f"({endpoint}, workers={workers}, preprocess=off)"
    )
    print(format_progress_bar(0, total) + "  開始…", flush=True)

    success = 0
    print_lock = Lock()
    done_count = 0

    def _run(img_path: Path) -> tuple[Path, bool, str]:
        ok, message = process_one(
            img_path,
            output_dir,
            model=args.model,
            base_url=args.ollama_url,
            save_boxed=args.save_boxed,
            use_binary=False,
            server_url=args.server_url,
            backend=args.backend,
        )
        return img_path, ok, message

    if workers == 1:
        for i, img_path in enumerate(images, start=1):
            print(
                f"{format_progress_bar(i - 1, total)}  "
                f"掃描第 {i}/{total} 張（進行中）: {img_path.name}…",
                flush=True,
            )
            img_path, ok, message = _run(img_path)
            status = "OK" if ok else "FAIL"
            print_scan_progress(
                index=i,
                total=total,
                name=img_path.name,
                status=status,
                message=message,
                workers=1,
            )
            if ok:
                success += 1
    else:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(_run, p): p for p in images}
            for fut in as_completed(futures):
                img_path, ok, message = fut.result()
                status = "OK" if ok else "FAIL"
                with print_lock:
                    done_count += 1
                    print_scan_progress(
                        index=done_count,
                        total=total,
                        name=img_path.name,
                        status=status,
                        message=message,
                        workers=workers,
                    )
                if ok:
                    success += 1

    failed = total - success
    print(format_progress_bar(total, total) + "  全部完成", flush=True)
    print(f"完成: 成功 {success} / 失敗 {failed} / 總計 {total}")
    return 0 if success > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
