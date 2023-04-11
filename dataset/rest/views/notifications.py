"""Модуль с представлениями для обработки уведомлений."""
from fastapi import Depends
from fastapi_utils.cbv import cbv
from fastapi_utils.inferring_router import InferringRouter
from starlette import status
from starlette.responses import Response

from dataset.rest.models.base import BaseResponseModel
from dataset.rest.models.notifications import (
    NotificationsResponseModel,
    SendNotificationsModel,
)
from dataset.rest.permissions import AuthChecker
from dataset.rest.views.base import BaseView
from dataset.services.notification import NotificationsUserService

router = InferringRouter()


@cbv(router)
class NotificationsView(BaseView):
    """Представление для работы с уведомлениями."""

    @router.get(
        "/notifications",
        dependencies=[Depends(AuthChecker(is_auth=True))],
        response_model=NotificationsResponseModel,
    )
    async def get_notifications(self) -> dict:
        """Получить подписки на уведомления по юзеру."""
        notification_service = NotificationsUserService(self.request.app)
        return await notification_service.get_notifications(
            self.request.user.id
        )

    @router.post(
        "/notifications",
        dependencies=[Depends(AuthChecker(is_auth=True))],
        response_model=NotificationsResponseModel,
    )
    async def change_notifications(
        self, data: NotificationsResponseModel  # noqa B008
    ) -> dict:
        """Обновить подписки на обновления по юзеру."""
        notification_service = NotificationsUserService(app=self.request.app)
        await notification_service.update_notifications(
            data.dict(), user_id=self.request.user.id
        )
        return await notification_service.get_notifications(
            self.request.user.id
        )

    @router.post("/internal/send-notify/", response_model=BaseResponseModel)
    async def send_notifications(
        self, data: SendNotificationsModel
    ) -> Response:
        """Отправить уведомление."""
        # TODO это временное решение до запуска очередей
        notification_service = NotificationsUserService(self.request.app)
        await notification_service.send_notification(
            user_id=data.recipient_id,
            notification_type=data.notification_type,
        )
        return Response(status_code=status.HTTP_200_OK, content="OK")
