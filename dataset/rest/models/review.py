"""Модуль с моделями отзывов."""
from fastapi import File, Form
from pydantic import BaseModel

from dataset.rest.models.images import UploadCloudModel
from dataset.rest.models.utils import as_form


class ResponseReviewModel(BaseModel):
    """Модель для получения списка отзывов."""

    id: int  # noqa A003
    name: str
    photo: str
    lang: str
    text: str
    sort: int
    is_active: bool

    class Config:
        """Класс с настройками."""

        arbitrary_types_allowed = True
        orm_mode = True


@as_form
class ReviewModel(BaseModel):
    """Модель создания/редактирования отзыва."""

    name: str = Form(...)
    photo: UploadCloudModel.get_type() = File(...)
    lang: str = Form(...)
    text: str = Form(...)
    sort: int = Form(...)
    is_active: bool = Form(...)
