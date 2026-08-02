#!/usr/bin/env python3
"""HTML pages for the permit module (Jinja + core static assets)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

OPENSOURCE_ROOT = Path(__file__).resolve().parent.parent.parent
WEB_DIR = OPENSOURCE_ROOT / "web"
templates = Jinja2Templates(directory=str(WEB_DIR / "templates"))

pages_router = APIRouter(tags=["permit-pages"])


def _niimbot_frontend_config() -> dict:
    label = (os.getenv("NIIMBOT_LABEL_TYPE") or "gap").strip().lower()
    label_type = 0 if label in ("continuous", "cont", "0") else 1
    try:
        density = int(os.getenv("NIIMBOT_DENSITY") or "3")
    except ValueError:
        density = 3
    density = max(1, min(5, density))
    return {"label_type": label_type, "density": density}


def _ctx(request: Optional[Request] = None, **extra):
    niimbot_ui = bool(request and getattr(request.app.state, "niimbot_ui", False))
    ctx = {
        "permit_module": True,
        "permit_ui": True,
        "niimbot_ui": niimbot_ui,
        **extra,
    }
    if niimbot_ui:
        ctx["niimbot_config"] = _niimbot_frontend_config()
    return ctx


@pages_router.get("/permit", include_in_schema=False)
@pages_router.get("/permit/", include_in_schema=False)
async def permit_index():
    return RedirectResponse(url="/permit/lookup", status_code=307)


@pages_router.get("/permit/lookup", response_class=HTMLResponse)
async def permit_lookup(request: Request):
    return templates.TemplateResponse(
        request,
        "permit_lookup.html",
        _ctx(request, title="查詢車證", permit_tab="lookup"),
    )


@pages_router.get("/permit/manage", response_class=HTMLResponse)
async def permit_manage(request: Request):
    return templates.TemplateResponse(
        request,
        "permit_manage.html",
        _ctx(request, title="車證管理", permit_tab="manage"),
    )


@pages_router.get("/permit/tickets", response_class=HTMLResponse)
async def permit_tickets(request: Request):
    return templates.TemplateResponse(
        request,
        "permit_tickets.html",
        _ctx(request, title="列印罰單", permit_tab="tickets"),
    )
