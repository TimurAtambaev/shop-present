"""Модуль с фикстурами."""
from contextlib import contextmanager
from os import getenv
from typing import Generator
import pytest
import pytest_asyncio
from alembic.command import upgrade
from alembic.config import Config
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy_utils import database_exists, drop_database, create_database
from yarl import URL
from dataset.config import settings


@contextmanager
def get_tmp_database(**kwargs: dict) -> str:
    """Создать временную бд для тестов."""
    tmp_db_url = getenv("WRITE_DB")
    if kwargs.get("template"):
        db_url = URL(tmp_db_url).path.replace("_template", "_test")
    else:
        db_url = URL(tmp_db_url).path.replace("_test", "_template")

    tmp_db_url = str(URL(tmp_db_url).with_path(db_url)) + str(
        getenv("PYTEST_XDIST_WORKER", "")
    )

    if tmp_db_url and database_exists(tmp_db_url):
        drop_database(tmp_db_url)
    create_database(tmp_db_url, **kwargs)
    try:
        yield tmp_db_url
    finally:
        if database_exists(tmp_db_url):
            drop_database(tmp_db_url)


@pytest.fixture()
def app() -> FastAPI:
    """Инициализация приложения."""
    from dataset.app import init_app
    yield init_app()


@pytest.fixture(autouse=True, scope="session")
async def db(migrated_postgres_template: str) -> str:
    """Инициализация подключения к бд."""
    template_db = URL(migrated_postgres_template).name
    with get_tmp_database(template=template_db) as tmp_url:
        yield tmp_url


@pytest.fixture(scope="session")
def migrated_postgres_template() -> Generator[str, None, None]:
    """Создание шаблона базы с применением миграций."""
    with get_tmp_database() as tmp_url:
        alembic_config = Config(file_=settings.ALEMBIC_PATH)
        alembic_config.set_main_option("sqlalchemy.url", tmp_url)
        upgrade(alembic_config, "head")
        yield tmp_url


@pytest_asyncio.fixture()
async def client(app: FastAPI) -> AsyncClient:
    """Создание тестового асинхронного клиента."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        yield client
