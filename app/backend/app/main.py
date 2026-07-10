from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.routes.ai import router as ai_router
from app.routes.auth import router as auth_router
from app.routes.health import router as health_router
from app.routes.metrics import router as metrics_router
from app.routes.support import router as support_router

settings = get_settings()

app = FastAPI(title=settings.app_name, version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router)
app.include_router(auth_router)
app.include_router(metrics_router)
app.include_router(ai_router)
app.include_router(support_router)
