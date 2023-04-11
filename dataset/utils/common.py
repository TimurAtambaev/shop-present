"""Модуль с общими инструментами."""
from furl import furl

from dataset.config import settings


def get_database_url() -> str:
    """Получить ссылку на базу."""
    return settings.DB_URI


def get_ru_url(uri: str, country_id: int) -> str:
    """Получить ссылку с ру доменом."""
    redirect_uri = furl(uri)
    args = redirect_uri.host.split(".")

    redirect_uri.host = ".".join(args)
    if country_id in settings.RU_COUNTRIES:
        args[-1] = "ru"
    redirect_uri.host = ".".join(args)
    return str(redirect_uri)
