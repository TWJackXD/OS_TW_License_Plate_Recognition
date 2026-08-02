#!/usr/bin/env python3
"""Permit module API routes (mounted onto the core FastAPI app)."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from modules.permit.db import (
    delete_permit,
    get_permit_by_id,
    get_permit_by_plate,
    insert_permit,
    list_permits,
    normalize_plate,
    update_permit,
)

router = APIRouter(tags=["permits"])


class PermitCreate(BaseModel):
    plate_number: str = Field(min_length=1, max_length=32)
    name: str = Field(min_length=1, max_length=100)
    campus: str = Field(min_length=1, max_length=100)
    department: str = Field(min_length=1, max_length=100)
    student_id: Optional[str] = Field(default=None, max_length=50)
    note: Optional[str] = Field(default=None, max_length=500)


class PermitUpdate(PermitCreate):
    pass


def _permit_dict(p) -> dict:
    return {
        "id": p.id,
        "plate_number": p.plate_number,
        "name": p.name,
        "campus": p.campus,
        "department": p.department,
        "student_id": p.student_id,
        "note": p.note,
        "created_at": p.created_at,
        "updated_at": p.updated_at,
    }


@router.get("/api/permits")
async def api_list_or_lookup(
    plate: Optional[str] = Query(default=None),
    limit: int = Query(default=500, ge=1, le=2000),
):
    if plate is not None and plate.strip():
        found = get_permit_by_plate(plate)
        if found is None:
            return {
                "found": False,
                "plate_number": normalize_plate(plate),
                "permit": None,
            }
        return {
            "found": True,
            "plate_number": found.plate_number,
            "permit": _permit_dict(found),
        }

    items = [_permit_dict(p) for p in list_permits(limit=limit)]
    return {"items": items}


@router.get("/api/permits/{permit_id}")
async def api_get_permit(permit_id: int):
    found = get_permit_by_id(permit_id)
    if found is None:
        raise HTTPException(status_code=404, detail="找不到此車證")
    return _permit_dict(found)


@router.post("/api/permits", status_code=201)
async def api_create_permit(payload: PermitCreate):
    plate = normalize_plate(payload.plate_number)
    if not plate:
        raise HTTPException(status_code=400, detail="車牌號碼不可空白")
    if get_permit_by_plate(plate) is not None:
        raise HTTPException(status_code=409, detail="此車牌已有車證紀錄")

    try:
        pid = insert_permit(
            plate_number=plate,
            name=payload.name,
            campus=payload.campus,
            department=payload.department,
            student_id=payload.student_id,
            note=payload.note,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    created = get_permit_by_id(pid)
    return {"ok": True, "permit": _permit_dict(created)}


@router.put("/api/permits/{permit_id}")
async def api_update_permit(permit_id: int, payload: PermitUpdate):
    existing = get_permit_by_id(permit_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="找不到此車證")

    plate = normalize_plate(payload.plate_number)
    if not plate:
        raise HTTPException(status_code=400, detail="車牌號碼不可空白")

    other = get_permit_by_plate(plate)
    if other is not None and other.id != permit_id:
        raise HTTPException(status_code=409, detail="此車牌已有其他車證紀錄")

    ok = update_permit(
        permit_id,
        plate_number=plate,
        name=payload.name,
        campus=payload.campus,
        department=payload.department,
        student_id=payload.student_id,
        note=payload.note,
    )
    if not ok:
        raise HTTPException(status_code=404, detail="找不到此車證")

    updated = get_permit_by_id(permit_id)
    return {"ok": True, "permit": _permit_dict(updated)}


@router.delete("/api/permits/{permit_id}")
async def api_delete_permit(permit_id: int):
    if not delete_permit(permit_id):
        raise HTTPException(status_code=404, detail="找不到此車證")
    return {"ok": True}
