from fastapi import APIRouter

from app.config import get_settings
from app.db import fetch_one

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict:
    db = fetch_one("select current_database() as database, now() as checked_at")
    return {"status": "ok", "app": get_settings().app_name, "database": db}
