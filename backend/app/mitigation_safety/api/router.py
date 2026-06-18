"""Top-level APIRouter — registers the 6 routes + 2 shims under one router."""

from __future__ import annotations

from fastapi import APIRouter

from app.mitigation_safety.api.safemode_routes import router as safemode_router
from app.mitigation_safety.api.shim_routes import router as shim_router
from app.mitigation_safety.api.tickets_routes import router as tickets_router


def register_router() -> APIRouter:
    root = APIRouter()
    root.include_router(tickets_router)
    root.include_router(safemode_router)
    root.include_router(shim_router)
    return root
