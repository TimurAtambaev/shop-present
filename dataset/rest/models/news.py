"""Модуль с моделями новостей."""
from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel


class NewsModel(BaseModel):
    """Модель для получения списка новостей."""

    id: int  # noqa A003
    title: Optional[str]
    cover_url: Optional[str]
    language: Optional[str]
    markup_text: Optional[str]
    is_published: Optional[bool]
    text: Optional[str]
    published_date: date
    created_at: datetime
    updated_at: datetime
    tags: Optional[list[str]]

    class Config:
        """Класс с настройками."""

        arbitrary_types_allowed = True
        orm_mode = True
