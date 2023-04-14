"""Модуль с настройками проекта."""
import os
from typing import Any, Optional, Union
from urllib.parse import urlparse

from pydantic import BaseSettings, PostgresDsn, validator


class Settings(BaseSettings):
    """Класс настроек."""

    ALEMBIC_PATH: str = "/etc/alembic.ini"
    BASE_DIR: str = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    TESTING: bool = False
    PYTEST_XDIST_WORKER: str = ""
    PYTEST_XDIST_TESTRUNUID: str = ""
    GS_ENVIRONMENT: str = "test"
    GS_LISTEN: str = "http://0.0.0.0:8080"

    # Database settings
    DB_USER: str = "postgres"
    DB_PASS: str = "dataset"
    DB_HOST: str = "postgres"
    DB_PORT: int = 5432
    DB_NAME: str = "dataset"
    DB_URI: PostgresDsn = None

    @validator("DB_NAME", pre=True, allow_reuse=True)
    def get_actual_db_name(
        cls, v: Optional[str], values: dict[str, Any]
    ) -> str:
        """Получение названия базы, для тестов генерит отдельное название."""
        test_postfix = f"_test_{values.get('PYTEST_XDIST_WORKER')}"

        if values.get("TESTING") and not v.endswith(test_postfix):
            v += test_postfix
        return v

    @validator("DB_URI", pre=True, allow_reuse=True)
    def assemble_db_connection(
        cls, v: Optional[str], values: dict[str, Any]
    ) -> str:
        """
        Собираем коннект для подключения к БД.

        :param v: value
        :param values: Dict values
        :return: PostgresDsn
        """
        if isinstance(v, str):
            conn = urlparse(v)
            return PostgresDsn.build(
                scheme=conn.scheme,
                user=conn.username,
                password=conn.password,
                host=conn.hostname,
                port=str(conn.port),
                path=conn.path,
            )

        return PostgresDsn.build(
            scheme="postgresql+asyncpg",
            user=values["DB_USER"],
            password=values["DB_PASS"],
            host=values["DB_HOST"],
            port=str(values["DB_PORT"]),
            path=f"/{values['DB_NAME']}",
        )


settings = Settings()
