"""App declaration and initialization."""
from fastapi import FastAPI
from fastapi_pagination import add_pagination

from dataset.config import settings
from dataset.middlewares import ContextRequestMiddleware
from dataset.routes import init_routes


def init_app() -> FastAPI:
    """Инициализация приложения."""
    app = FastAPI()

    # middlewares
    app.add_middleware(ContextRequestMiddleware)

    init_routes(app)

    # events
    app.state.test_mode = settings.GS_ENVIRONMENT == "test"
    add_pagination(app)

    return app


application = init_app()
