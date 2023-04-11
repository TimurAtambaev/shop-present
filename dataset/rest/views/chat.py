"""Модуль с рест-запросами чата."""
from typing import List

from fastapi import Depends
from fastapi_utils.cbv import cbv
from fastapi_utils.inferring_router import InferringRouter

from dataset.rest.models.chat import (
    MessageFileModel,
    ResponseStandartMessageModel,
)
from dataset.rest.permissions import AuthChecker
from dataset.rest.views.base import BaseView
from dataset.tables.default_message import StandartMessage

router = InferringRouter()


@cbv(router)
class ChatView(BaseView):
    """Класс для рест-запросов."""

    @router.get(
        "/chat",
        dependencies=[Depends(AuthChecker(is_auth=True))],
        response_model=List[ResponseStandartMessageModel],
    )
    async def standart_messages(self) -> list[StandartMessage]:
        """Получить список стандартных сообщений из базы."""
        return await StandartMessage.query.gino.all()

    @router.post(
        "/chat/{recipient_id}/send-file",
        dependencies=[Depends(AuthChecker(is_auth=True))],
    )
    async def load_file(
        self,
        message: MessageFileModel = Depends(  # noqa B008
            MessageFileModel.as_form
        ),
    ):  # noqa ANN201
        """Загрузить файл в чате, вернуть первоначальное имя файла и ссылку."""
        return message.file
