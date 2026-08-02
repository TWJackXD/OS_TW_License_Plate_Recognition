#!/usr/bin/env python3
"""Optional vehicle-permit + ticket UI module for the opensource core app."""

from __future__ import annotations

import os

from fastapi import FastAPI

from modules.permit.db import init_db
from modules.permit.pages import pages_router
from modules.permit.routes import router


def module_enabled() -> bool:
    raw = os.environ.get("ENABLE_PERMIT_MODULE", "0").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def register(app: FastAPI) -> None:
    """Attach permit API and Jinja pages under /permit/*."""
    init_db()
    app.include_router(router)
    app.include_router(pages_router)
    app.state.permit_module = True
    app.state.permit_ui_mounted = True
