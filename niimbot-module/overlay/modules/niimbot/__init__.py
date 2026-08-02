#!/usr/bin/env python3
"""Optional Niimbot B1 Bluetooth print module (browser Web Bluetooth)."""

from __future__ import annotations

import os

from fastapi import FastAPI


def module_enabled() -> bool:
    raw = os.environ.get("ENABLE_NIIMBOT_MODULE", "0").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def register(app: FastAPI) -> None:
    """Mark Niimbot print UI as available (client-side Web Bluetooth)."""
    app.state.niimbot_module = True
    app.state.niimbot_ui = True
