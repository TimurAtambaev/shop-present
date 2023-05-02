"""Модуль с инициализацией роутов."""

from fastapi import APIRouter, FastAPI
from dataset.rest.views import kit


def init_routes(app: FastAPI) -> None:
    """Инициализация роутов."""
    main_router = APIRouter()
    main_router.include_router(kit.router, tags=["kit"])
    app.include_router(main_router)
