#!/usr/bin/env python3
"""FastAPI web app for Taiwan license-plate violation reporting."""

from __future__ import annotations

import asyncio
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

from typing import Optional

import cv2
import numpy as np
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from recognize_plate import (  # noqa: E402
    DEFAULT_MODEL,
    DEFAULT_OLLAMA_URL,
    DEFAULT_VLM_URL,
    log_status,
    recognize_bgr_image,
)
from web.db import (  # noqa: E402
    BOXED_DIR,
    ORIGINAL_DIR,
    PROCESSED_DIR,
    UPLOAD_DIR,
    ensure_dirs,
    delete_violation,
    init_db,
    insert_violation,
    list_violations,
)
from web.osm_location import (  # noqa: E402
    campus_boundaries_geojson,
    campus_enforce_enabled,
    fetch_buildings_geojson,
    resolve_campus_location,
)

WEB_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(WEB_DIR / "templates"))

ensure_dirs()

app = FastAPI(title="臺灣違規車牌回報系統")
app.mount("/static", StaticFiles(directory=str(WEB_DIR / "static")), name="static")
app.mount("/media", StaticFiles(directory=str(UPLOAD_DIR)), name="media")


@app.middleware("http")
async def disable_html_cache(request: Request, call_next):
    response = await call_next(request)
    path = request.url.path
    if (
        path in {"/", "/admin", "/pressure", "/sw.js", "/manifest.webmanifest"}
        or path.startswith("/permit")
        or path.endswith(".html")
    ):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
    return response


@app.on_event("startup")
def on_startup() -> None:
    init_db()


def _niimbot_frontend_config() -> dict:
    label_raw = os.environ.get("NIIMBOT_LABEL_TYPE", "gap").strip().lower()
    label_type = 0 if label_raw in {"continuous", "cont", "0"} else 1
    try:
        density = int(os.environ.get("NIIMBOT_DENSITY", "3"))
    except ValueError:
        density = 3
    density = max(1, min(5, density))
    return {"density": density, "label_type": label_type}


def _page_ctx(**extra):
    niimbot_ui = bool(getattr(app.state, "niimbot_ui", False))
    ctx = {
        "permit_module": bool(getattr(app.state, "permit_module", False)),
        "permit_ui": bool(getattr(app.state, "permit_ui_mounted", False)),
        "niimbot_ui": niimbot_ui,
        **extra,
    }
    if niimbot_ui:
        ctx["niimbot_config"] = _niimbot_frontend_config()
    return ctx


class SubmitPayload(BaseModel):
    plate_number: str = Field(min_length=1, max_length=32)
    reason: str = Field(min_length=1, max_length=500)
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    original_path: str
    boxed_path: Optional[str] = None
    processed_path: Optional[str] = None


def _rel_upload_path(path: Path) -> str:
    """Store paths relative to data/uploads for stable media URLs."""
    return str(path.relative_to(ROOT / "data" / "uploads"))


def _decode_upload(data: bytes) -> np.ndarray:
    arr = np.frombuffer(data, dtype=np.uint8)
    image = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if image is None:
        raise HTTPException(status_code=400, detail="無法解碼圖片")
    return image


def _stamp() -> str:
    return datetime.now(timezone.utc).astimezone().strftime("%Y%m%d_%H%M%S")


@app.get("/sw.js")
async def service_worker():
    path = WEB_DIR / "static" / "sw.js"
    return FileResponse(
        path,
        media_type="application/javascript",
        headers={"Service-Worker-Allowed": "/", "Cache-Control": "no-cache"},
    )


@app.get("/manifest.webmanifest")
async def web_manifest():
    return FileResponse(
        WEB_DIR / "static" / "manifest.webmanifest",
        media_type="application/manifest+json",
    )


@app.get("/", response_class=HTMLResponse)
async def capture_page(request: Request):
    return templates.TemplateResponse(
        request,
        "capture.html",
        _page_ctx(title="違規回報"),
    )


@app.get("/admin", response_class=HTMLResponse)
async def admin_page(request: Request):
    return templates.TemplateResponse(
        request,
        "admin.html",
        _page_ctx(title="歷史紀錄"),
    )


@app.get("/pressure", response_class=HTMLResponse)
async def pressure_page(request: Request):
    return templates.TemplateResponse(
        request,
        "pressure.html",
        _page_ctx(title="API 壓力測試"),
    )


@app.post("/api/recognize")
async def api_recognize(
    image: UploadFile = File(...),
    latitude: Optional[float] = Form(default=None),
    longitude: Optional[float] = Form(default=None),
):
    log_status("—— 收到辨識請求 ——")
    raw_bytes = await image.read()
    if not raw_bytes:
        raise HTTPException(status_code=400, detail="空的圖片內容")

    log_status(f"上傳檔案 {len(raw_bytes) / 1024:.1f} KB，解碼中…")
    bgr = _decode_upload(raw_bytes)
    stamp = _stamp()
    uid = uuid.uuid4().hex[:8]

    original_path = ORIGINAL_DIR / f"{stamp}_{uid}.jpg"
    cv2.imwrite(str(original_path), bgr)
    log_status(f"已存原圖：{original_path.name}")

    if latitude is not None and longitude is not None:
        log_status(f"GPS：{latitude}, {longitude}")
    else:
        log_status("GPS：無")

    result = recognize_bgr_image(
        bgr,
        model=DEFAULT_MODEL,
        base_url=DEFAULT_VLM_URL or DEFAULT_OLLAMA_URL,
        use_binary=False,
    )

    boxed_rel = None
    processed_rel = None

    if result["boxed_bgr"] is not None:
        boxed_path = BOXED_DIR / f"{stamp}_{uid}_boxed.jpg"
        cv2.imwrite(str(boxed_path), result["boxed_bgr"])
        boxed_rel = _rel_upload_path(boxed_path)

    if result["processed_bgr"] is not None:
        processed_path = PROCESSED_DIR / f"{stamp}_{uid}_processed.jpg"
        cv2.imwrite(str(processed_path), result["processed_bgr"])
        processed_rel = _rel_upload_path(processed_path)

    if result["ok"]:
        log_status(f"回傳前台：車牌 {result['plate']}")
    else:
        log_status(f"回傳前台：失敗 — {result['error']}")
    log_status("—— 辨識請求結束 ——")

    return {
        "ok": result["ok"],
        "plate_number": result["plate"] or "",
        "raw": result["raw"],
        "error": result["error"],
        "usage": result.get("usage"),
        "elapsed_sec": result.get("elapsed_sec"),
        "model": (result.get("usage") or {}).get("model") if isinstance(result.get("usage"), dict) else None,
        "latitude": latitude,
        "longitude": longitude,
        "original_path": _rel_upload_path(original_path),
        "boxed_path": boxed_rel,
        "processed_path": processed_rel,
        "original_url": f"/media/{_rel_upload_path(original_path)}",
        "boxed_url": f"/media/{boxed_rel}" if boxed_rel else None,
        "processed_url": f"/media/{processed_rel}" if processed_rel else None,
    }


@app.post("/api/violations")
async def api_submit_violation(payload: SubmitPayload):
    plate = payload.plate_number.strip().upper()
    reason = payload.reason.strip()
    if not plate:
        raise HTTPException(status_code=400, detail="車牌號碼不可空白")
    if not reason:
        raise HTTPException(status_code=400, detail="請填寫違規原因")

    # Basic path safety: must stay under uploads
    for rel in (payload.original_path, payload.boxed_path, payload.processed_path):
        if rel is None:
            continue
        if ".." in rel or rel.startswith("/"):
            raise HTTPException(status_code=400, detail="非法圖片路徑")

    location_name = None
    if campus_enforce_enabled():
        result = await asyncio.to_thread(
            resolve_campus_location, payload.latitude, payload.longitude
        )
        if not result.ok:
            raise HTTPException(status_code=400, detail=result.error or "不在校區範圍內")
        location_name = result.location_name
        log_status(f"地點：{location_name}（{result.campus_name}）")
    elif payload.latitude is not None and payload.longitude is not None:
        try:
            result = await asyncio.to_thread(
                resolve_campus_location, payload.latitude, payload.longitude
            )
            if result.ok:
                location_name = result.location_name
                log_status(f"地點：{location_name}")
            else:
                log_status(f"地點未通過校區檢查：{result.error}")
        except Exception as exc:
            log_status(f"地點解析失敗：{exc}")

    vid = insert_violation(
        latitude=payload.latitude,
        longitude=payload.longitude,
        original_path=payload.original_path,
        boxed_path=payload.boxed_path,
        processed_path=payload.processed_path,
        plate_number=plate,
        reason=reason,
        location_name=location_name,
    )

    return {"ok": True, "id": vid, "location_name": location_name}


@app.get("/api/violations")
async def api_list_violations(limit: int = 200):
    limit = max(1, min(limit, 1000))
    items = []
    for row in list_violations(limit=limit):
        items.append(
            {
                "id": row.id,
                "created_at": row.created_at,
                "latitude": row.latitude,
                "longitude": row.longitude,
                "plate_number": row.plate_number,
                "reason": row.reason,
                "location_name": row.location_name,
                "original_path": row.original_path,
                "boxed_path": row.boxed_path,
                "processed_path": row.processed_path,
                "original_url": f"/media/{row.original_path}",
                "boxed_url": f"/media/{row.boxed_path}" if row.boxed_path else None,
                "processed_url": (
                    f"/media/{row.processed_path}" if row.processed_path else None
                ),
            }
        )
    return {"items": items}


@app.delete("/api/violations/{violation_id}")
async def api_delete_violation(violation_id: int):
    if not delete_violation(violation_id):
        raise HTTPException(status_code=404, detail="找不到此違規紀錄")
    return {"ok": True}


@app.get("/api/map/buildings")
async def api_map_buildings(
    south: float,
    west: float,
    north: float,
    east: float,
):
    """Return OSM building footprints (GeoJSON) for the admin map overlay."""
    try:
        return await asyncio.to_thread(
            fetch_buildings_geojson, south, west, north, east
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"OSM 查詢失敗：{exc}") from exc


@app.get("/api/map/campus")
async def api_map_campus():
    """Return configured campus boundary polygons as GeoJSON."""
    try:
        return await asyncio.to_thread(campus_boundaries_geojson)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"載入校區範圍失敗：{exc}") from exc


@app.post("/api/violations/resolve-locations")
async def api_resolve_locations(limit: int = 300):
    """Backfill location_name for existing GPS records (must be inside campus)."""
    from web.db import update_location_name

    def _run() -> dict:
        updated = 0
        skipped = 0
        outside = 0
        for row in list_violations(limit=max(1, min(limit, 1000))):
            if row.latitude is None or row.longitude is None:
                skipped += 1
                continue
            result = resolve_campus_location(row.latitude, row.longitude)
            if not result.ok:
                outside += 1
                continue
            if row.location_name == result.location_name:
                skipped += 1
                continue
            update_location_name(row.id, result.location_name)
            updated += 1
        return {
            "ok": True,
            "updated": updated,
            "skipped": skipped,
            "outside_campus": outside,
        }

    return await asyncio.to_thread(_run)


def _maybe_register_permit_module() -> None:
    """Optionally attach modules/permit (API + /permit SPA)."""
    app.state.permit_module = False
    app.state.permit_ui_mounted = False
    try:
        from modules.permit import module_enabled, register
    except ImportError:
        return
    if not module_enabled():
        return
    register(app)


def _maybe_register_niimbot_module() -> None:
    """Optionally enable Niimbot B1 print UI hooks."""
    app.state.niimbot_module = False
    app.state.niimbot_ui = False
    try:
        from modules.niimbot import module_enabled, register
    except ImportError:
        return
    if not module_enabled():
        return
    register(app)


_maybe_register_permit_module()
_maybe_register_niimbot_module()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8010)
