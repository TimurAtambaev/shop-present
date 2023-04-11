"""Модуль с моделями для категорий."""
import random

from pydantic import BaseModel


class Category(BaseModel):
    """Модель категории."""

    id: int  # noqa A003
    title_cat: str

    class Config:
        """Класс с настройками."""

        arbitrary_types_allowed = True
        orm_mode = True


class CategoryWithRndImage(BaseModel):
    """Модель категории с изображением."""

    id: int  # noqa A003
    title_cat: str
    image: list

    class Config:
        """Класс с настройками."""

        orm_mode = True

    def dict(self, *args, **kwargs):  # noqa A003
        """Переопределен метод для вывода списка категорий."""
        list_category = super().dict(*args, **kwargs)
        list_category["image"] = random.choice(list_category["image"])
        return list_category
