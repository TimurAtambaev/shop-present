"""Модуль с собственными типами."""
from __future__ import annotations

import re
from typing import Any, Callable, Generator, Iterable, Type

from starlette.datastructures import UploadFile

TG_URL_PATTERN = (
    r"(https:\/\/|https:\/\/t\.me\/|t\.me\/|@|)(?P<login>[a-z0-9_+]{5,32}).*"
)
TG_URL_REGEX = re.compile(TG_URL_PATTERN)


class TGUrl(str):
    """Тип ссылки в telegram."""

    prefix = "https://t.me/"

    @classmethod
    def __get_validators__(cls) -> Generator:
        """Получить метод валидации."""
        yield cls.validate

    @classmethod
    def __modify_schema__(cls, field_schema: dict) -> None:
        """Модифицировать схему типа."""
        field_schema.update(
            pattern=TG_URL_PATTERN,
            examples=[
                "https://t.me/testovich",
                "https://t.me/+79999999999",
                "https://testovich.t.me",
                "testovich.t.me",
                "t.me/testovich",
                "@testovich",
                "testovich",
                "+79999999999",
            ],
        )

    @classmethod
    def validate(cls, value: str) -> TGUrl:
        """Валидация типа ссылки."""
        if not isinstance(value, str):
            raise TypeError("string required")
        match = TG_URL_REGEX.fullmatch(value.lower())
        if not match:
            raise ValueError("invalid format")

        return cls(f'{cls.prefix}{match.group("login")}')


class UploadFileOrLink(UploadFile):
    """Тип для загрузки файла побитово или через ссылку."""

    validator = lambda value: value  # noqa E731

    def __new__(
        cls,
        *args: tuple,
        validator: Callable = None,
        **kwargs: dict,
    ) -> type:
        """Создание нового объекта."""
        copy = type("CopyCls", cls.__bases__, dict(cls.__dict__))
        if validator:
            copy.validator = validator
        return copy

    @classmethod
    def __get_validators__(
        cls: Type["UploadFileOrLink"],
    ) -> Iterable[Callable[..., Any]]:
        """Получить валидаторы."""
        yield cls.validate

    @classmethod
    def validate(cls: Type["UploadFileOrLink"], value: Any) -> Any:
        """Провалидировать."""
        if not isinstance(value, (UploadFile, str)):
            raise ValueError(f"Expected UploadFile, received: {type(value)}")

        return cls.validator(value)
