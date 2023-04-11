"""Модуль с моделями для чата."""
from datetime import datetime
from typing import Optional, Union

from fastapi import File, HTTPException
from pydantic import BaseModel
from starlette import status
from starlette.datastructures import UploadFile

from dataset.rest.models.images import MessageUploadCloudModel
from dataset.rest.models.types import UploadFileOrLink
from dataset.rest.models.utils import as_form


# TODO удалить
@as_form
class MessageFileModel(MessageUploadCloudModel):
    """Модель сообщения для загрузки файла."""

    class Config:
        """Класс с настройками."""

        arbitrary_types_allowed = True

    @staticmethod
    def validate_file(value: Union[UploadFile, str]) -> str:
        """Валидация файла."""
        if value.content_type not in [
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "application/vnd.oasis.opendocument.spreadsheet",
            "text/csv",
            "application/vnd.ms-excel",
            "application/msword",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "application/vnd.oasis.opendocument.text",
            "application/pdf",
            "text/plain",
            "application/rtf",
            "application/vnd.openxmlformats-officedocument.presentationml.template",
            "application/vnd.openxmlformats-officedocument.presentationml.slideshow",
            "application/vnd.openxmlformats-officedocument.presentationml.presentation",
            "application/vnd.oasis.opendocument.graphics",
            "application/vnd.ms-powerpoint",
            "image/jpeg",
            "image/jpg",
            "image/png",
        ]:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY
            )
        funcs = {
            UploadFile: lambda: MessageFileModel.upload_file(value),
            str: lambda: value,
        }
        if func := funcs.get(type(value)):
            return func()
        raise ValueError(f"The {type(value)} type is not supported")

    file: UploadFileOrLink(validator=validate_file) = File(...)


class ResponseStandartMessageModel(BaseModel):
    """Модель стандартных сообщений для ответа."""

    id: int  # noqa A003
    text: str
    type_message: str

    class Config:
        """Класс с настройками."""

        orm_mode = True


class MessageModel(BaseModel):
    """Модель сообщения."""

    label: Optional[str]
    id: int  # noqa A003
    user_id: int
    recipient_id: int
    text: Optional[str]
    type_message: str
    is_read: bool
    created_at: datetime

    class Config:
        """Класс с настройками."""

        orm_mode = True


class ResponseChatModel(BaseModel):
    """Модель чата для ответа."""

    id: int  # noqa A003
    name: str
    surname: Optional[str]
    country_id: Optional[int]
    avatar: Optional[str]
    active_dream: Optional[str]
    unread_messages: Optional[int]
    text: Optional[list]
    created_at: Optional[datetime]
