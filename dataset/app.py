"""App declaration and initialization."""
import inspect

import localization
import sentry_sdk
from fastapi import FastAPI
from fastapi_pagination import add_pagination
from gino import Gino
from starlette.middleware.authentication import AuthenticationMiddleware

import dataset
from dataset.auth import BasicAuthBackend
from dataset.config import settings
from dataset.core import (
    close_redis,
    init_aws,
    init_redis,
    init_scheduler,
    init_zendesk,
    setup_logging,
    stop_scheduler,
)
from dataset.core.container import Container
from dataset.integrations.payment_systems import SYSTEMS
from dataset.middlewares import (
    AddLanguageMiddleware,
    ContextRequestMiddleware,
)
from dataset.migrations import db
from dataset.routes import init_routes
from dataset.schedule import schedule


def init_sentry() -> None:
    """Инициализация сентри если есть настройка."""
    if settings.SENTRY_DSN:
        sentry_sdk.init(
            dsn=settings.SENTRY_DSN,
            traces_sample_rate=1.0,
            release=settings.APP_VERSION,
        )


def init_container(db: Gino) -> Container:
    """Иницилизация контейнера DI."""
    table = localization.bootstrap_db(db)
    container = Container(lang_table=table, db=db)
    container.localization.config.from_pydantic(settings)
    container.config.from_pydantic(settings)
    container.localization.init_resources()
    container.localization.check_dependencies()
    container.init_resources()
    container.check_dependencies()
    packages = set()
    for _, module in inspect.getmembers(dataset, inspect.ismodule):
        packages.add(module.__name__)
    packages.remove("dataset.migrations")
    container.wire(packages=packages)
    return container


def init_app() -> FastAPI:
    """App initialization function."""
    init_sentry()
    app = FastAPI()

    db.init_app(app)
    app.state.db = db

    # middlewares
    app.add_middleware(AddLanguageMiddleware)
    app.add_middleware(AuthenticationMiddleware, backend=BasicAuthBackend())
    app.add_middleware(ContextRequestMiddleware)

    setup_logging(settings.GS_ENVIRONMENT == "dev")

    init_routes(app)

    # events
    app.state.test_mode = settings.GS_ENVIRONMENT == "test"
    app.router.on_startup.append(init_scheduler(app))
    app.router.on_shutdown.append(stop_scheduler(app))

    app.router.on_startup.append(init_redis(app))
    app.router.on_shutdown.append(close_redis(app))

    app.router.on_startup.append(init_zendesk(app))
    app.router.on_startup.append(init_aws(app))

    app.router.on_startup.append(schedule(app))
    add_pagination(app)

    app.container = init_container(db)
    localization.bootstrap(app, db, settings)  # todo временный костыль
    return app


# при изменении названия обновить в __main__.py
application = init_app()


@application.on_event("startup")
async def startup_event() -> None:
    """Обработчик события."""
    for item in SYSTEMS.values():
        await item.pre_init()
