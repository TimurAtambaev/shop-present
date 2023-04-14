"""Модуль с настройками базы."""

import sqlalchemy
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from dataset.config import settings

metadata = sqlalchemy.MetaData()

async_engine = create_async_engine(
    settings.DB_URI,
    connect_args={"server_settings": {"jit": "off"}},
)

async_session = sessionmaker(
    async_engine,
    expire_on_commit=False,
    class_=AsyncSession,
)
