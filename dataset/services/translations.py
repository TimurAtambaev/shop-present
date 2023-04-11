"""Модуль для работы с Cloud Translation API."""
from datetime import datetime
from typing import Any, Optional, Union

from aioredis import Redis
from google.cloud import translate, translate_v2
from loguru import logger

from dataset.config import settings


class TranslateService:
    """Класс для работы с автопереводами."""

    CACHE_TIME_LIMIT = settings.CACHE_TIME_LIMIT
    DATETIME_FORMAT = "%Y-%m-%d %H:%M:%S.%f"

    def __init__(self, redis: Redis = None) -> None:
        """Инициализация класса."""
        self.redis = redis
        self.project_id = settings.GOOGLE_CLOUD_PROJECT_ID
        self.location = settings.GOOGLE_CLOUD_LOCATION
        try:
            self.translate_client = translate_v2.Client()
            self.service_client = translate.TranslationServiceClient()
        except Exception as exc:
            logger.warning(exc)
            self.translate_client = None
            self.service_client = None

    def detect_language(self, text: str) -> Optional[str]:
        """Определить язык текста."""
        if not self.service_client:
            return  # noqa R502
        parent = f"projects/{self.project_id}/locations/{self.location}"
        try:
            response = self.service_client.detect_language(
                content=text,
                parent=parent,
                mime_type="text/plain",
            )
            language = response.languages[0].language_code
        except Exception as exc:
            logger.warning(exc)
            language = None
        return language

    async def get_translation(
        self, dream: dict, language: str
    ) -> Union[Union[dict, str], Any]:
        """Получить перевод названия и описания мечты на указанный язык."""
        if not language or language == dream["language"]:
            return dream
        cache_translate = await self.redis.hgetall(f"{dream['id']}_{language}")
        translation = None
        if (
            not cache_translate
            or datetime.strptime(
                cache_translate["updated_at"], self.DATETIME_FORMAT
            )
            < dream["updated_at"]
        ):
            translation = await self.translate_text(dream, language)
        if translation:
            await self.cache_translation(dream, language, translation)
            return translation
        if cache_translate:
            return cache_translate
        dream["failed_translate"] = True
        return dream

    async def translate_text(
        self, dream: dict, language: str
    ) -> Optional[dict]:
        """Перевести мечту с помощью Cloud Translation API."""
        if not self.translate_client:
            return  # noqa R502
        try:
            title = self.translate_client.translate(
                dream["title"],
                target_language=language,
                format_="text",
            )["translatedText"]
            description = (
                self.translate_client.translate(
                    dream["description"],
                    target_language=language,
                    format_="text",
                )["translatedText"]
                if dream.get("description")
                else None
            )
        except Exception as exc:
            logger.warning(exc)
            return  # noqa R502
        return {"title": title, "description": description}

    async def cache_translation(
        self, dream: dict, language: str, translation: dict
    ) -> None:
        """Закэшировать перевод."""
        if not translation.get("description"):
            return  # не кэшируем в случаях когда переводится только название
        cache_key = f"{dream['id']}_{language}"
        cache_value = {
            "title": translation["title"],
            "description": translation["description"],
            "updated_at": str(dream["updated_at"]),
        }
        await self.redis.hmset_dict(cache_key, cache_value)
        await self.redis.expire(cache_key, timeout=self.CACHE_TIME_LIMIT)
