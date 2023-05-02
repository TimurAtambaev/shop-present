"""Модуль с настройками базы."""
from os import getenv

import sqlalchemy
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker


def get_database_url() -> str:
    """Получить url базы данных."""
    user = getenv("DB_USER")
    name = getenv("DB_NAME")
    password = getenv("DB_PASS")
    host = getenv("DB_HOST")
    port = getenv("DB_PORT")

    return f"postgresql+asyncpg://{user}:{password}@{host}:{port}/{name}"


metadata = sqlalchemy.MetaData()

async_engine = create_async_engine(
    get_database_url(),
    connect_args={"server_settings": {"jit": "off"}},
)

async_session = sessionmaker(
    async_engine,
    expire_on_commit=False,
    class_=AsyncSession,
)
