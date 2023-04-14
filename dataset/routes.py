"""Модель с инициализацией роутов."""

from fastapi import APIRouter, FastAPI
from dataset.rest.views import kit


def init_routes(app: FastAPI) -> None:
    """Инициализация роутов."""
    main_router = APIRouter(prefix="/api")
    main_router.include_router(kit.router, tags=["auth"])
    app.include_router(main_router)
