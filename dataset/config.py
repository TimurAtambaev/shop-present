"""Модуль с настройками проекта."""
import os
from typing import Any, Optional

from pydantic import BaseSettings, validator


class Settings(BaseSettings):
    """Класс настроек."""

    ALEMBIC_PATH: str = "/etc/migrations.ini"
    BASE_DIR: str = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    TESTING: bool = False
    PYTEST_XDIST_WORKER: str = ""
    PYTEST_XDIST_TESTRUNUID: str = ""
    GS_ENVIRONMENT: str = "test"
    GS_LISTEN: str = "http://0.0.0.0:8080"
    YEAR_DAYS: int = 365
    ACCURACY: int = 2

    # Database settings
    DB_USER: str = "postgres"
    DB_PASS: str = "dataset"
    DB_HOST: str = "postgres"
    DB_PORT: int = 5432
    DB_NAME: str = "dataset"

    @validator("DB_NAME", pre=True, allow_reuse=True)
    def get_actual_db_name(
        cls, v: Optional[str], values: dict[str, Any]
    ) -> str:
        """Получение названия базы, для тестов генерит отдельное название."""
        test_postfix = f"_test_{values.get('PYTEST_XDIST_WORKER')}"

        if values.get("TESTING") and not v.endswith(test_postfix):
            v += test_postfix
        return v


settings = Settings()
