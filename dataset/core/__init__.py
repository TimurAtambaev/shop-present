"""Basic core methods."""
import logging
from typing import AsyncIterator, Callable, Type

import aioredis
from aioredis import Redis
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI

from dataset.config import settings
from dataset.integrations.aws import AWS
from dataset.integrations.zendesk import ZenDesk


def setup_logging(debug: bool) -> None:
    """Set streaming of all loggers to stdout."""
    logging_level = logging.DEBUG if debug else logging.INFO

    stdio_handler = logging.StreamHandler()
    stdio_handler.setLevel(logging_level)

    # TODO обновить
    loggers = (
        None,
        "dataset",
        "aiohttp.access",
        "aiohttp.client",
        "aiohttp.internal",
        "aiohttp.server",
        "aiohttp.web",
        "aiohttp.websocket",
    )

    for name in loggers:
        logger = logging.getLogger(name)
        logger.addHandler(stdio_handler)
        logger.setLevel(logging_level)


# todo переводить инициализацию редиса в контейнер DI
def init_redis(app: FastAPI) -> Callable:
    """Initiate connection with redis."""

    async def inner_func() -> Type[Callable]:
        """Config нужен для кубера т.к адрес заранее не известен."""
        if hasattr(app.state, "redis"):
            return
        extra = {}
        if settings.REDIS_PASS:
            extra["password"] = settings.REDIS_PASS
        app.state.redis = await aioredis.create_redis_pool(
            f"{settings.REDIS_DRIVER}://{settings.REDIS_HOST}:{settings.REDIS_PORT}",
            db=settings.REDIS_DB,
            encoding="utf8",
            ssl=settings.REDIS_DRIVER != "redis",
            **extra,
        )

    return inner_func


def close_redis(app: FastAPI) -> Callable:
    """Close redis connection app is going down."""

    async def inner_func() -> Type[Callable]:
        redis = app.state.redis

        if redis:
            redis.close()
            await redis.wait_closed()

    return inner_func


def init_scheduler(app: FastAPI) -> Callable:
    """Initialize APScheduler and stores it in app."""

    async def inner_func() -> Type[Callable]:
        app.state.scheduler = AsyncIOScheduler()
        app.state.scheduler.start()

    return inner_func


def stop_scheduler(app: FastAPI) -> Callable:
    """Disables scheduler."""

    async def inner_func() -> Type[Callable]:
        if app.state.scheduler:
            app.state.scheduler.shutdown()

    return inner_func


def init_zendesk(app: FastAPI) -> Callable:
    """Initialize zendesk client."""

    async def inner_func() -> Type[Callable]:
        if hasattr(app.state, "zendesk"):
            return
        app.state.zendesk = ZenDesk(
            email=settings.ZENDESK_EMAIL,
            token=settings.ZENDESK_TOKEN,
            subdomain=settings.ZENDESK_SUBDOMAIN,
            is_test=settings.ZENDESK_IS_TEST,
        )

    return inner_func


def init_aws(app: FastAPI) -> Callable:
    """Initialize aws integration."""

    async def inner_func() -> Type[Callable]:
        if hasattr(app.state, "aws"):
            return

        app.state.aws = AWS(
            access_key=settings.AWS_ACCESS_KEY_ID,
            secret_key=settings.AWS_SECRET_ACCESS_KEY,
            bucket=settings.AWS_BUCKET,
            endpoint=settings.AWS_ENDPOINT,
        )

    return inner_func


async def init_redis_pool(
    driver: str, host: str, db: int, port: int, password: str
) -> AsyncIterator[Redis]:
    """Инициализация подключения к редису из контейнера зависимостей."""
    extra = {}
    if password:
        extra["password"] = password
    session = await aioredis.create_redis_pool(
        f"{driver}://{host}:{port}",
        db=db,
        encoding="utf8",
        ssl=driver != "redis",
        **extra,
    )
    yield session
    session.close()
    await session.wait_closed()
