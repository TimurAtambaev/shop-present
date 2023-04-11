"""Модуль с представлениями событий."""
from fastapi import Depends
from fastapi_pagination import Page, Params
from fastapi_pagination.bases import AbstractPage
from fastapi_pagination.ext.gino import paginate
from fastapi_utils.cbv import cbv
from fastapi_utils.inferring_router import InferringRouter
from starlette import status
from starlette.responses import Response

from dataset.rest.models.event import EventModel
from dataset.rest.models.utils import EmptyResponse
from dataset.rest.permissions import AuthChecker
from dataset.rest.views.base import BaseView
from dataset.rest.views.utils import read_all_events, read_one_event
from dataset.tables.event import Event

router = InferringRouter()


@cbv(router)
class EventView(BaseView):
    """Класс для рест-запросов."""

    @router.get(
        "/events",
        dependencies=[Depends(AuthChecker(is_auth=True))],
        response_model=Page[EventModel],
    )
    async def get_events(
        self, params: Params = Depends()  # noqa B008
    ) -> AbstractPage:
        """Получить список всех непрочитанных уведомлений.

        Текущего пользователя с пагинацией.
        """
        events = (
            Event.query.where(Event.is_read == False)  # noqa E712
            .where(Event.user_id == self.request.user.id)
            .order_by(Event.created_at.desc())
        )
        return await paginate(events, params)

    @router.post(
        "/events/read_all",
        dependencies=[Depends(AuthChecker(is_auth=True))],
        response_model=EmptyResponse,
    )
    async def events_is_read(self) -> Response:
        """Отметить прочитанными все уведомления."""
        await (
            Event.update.values(is_read=True)
            .where(Event.user_id == self.request.user.id)
            .where(Event.is_read == False)  # noqa E712
            .gino.status()
        )
        await read_all_events(self.request.app.state.redis, self.request.user)
        return Response(status_code=status.HTTP_200_OK)

    @router.post(
        "/events/{event_id}",
        dependencies=[Depends(AuthChecker(is_auth=True))],
        response_model=EmptyResponse,
    )
    async def event_is_read(self, event_id: int) -> Response:
        """Отметить уведомление прочитанным при нажатии."""
        event_read = await Event.get(event_id)
        if not event_read:
            return Response(status_code=status.HTTP_400_BAD_REQUEST)
        await (
            Event.update.values(is_read=True)
            .where(Event.user_id == self.request.user.id)
            .where(Event.id == event_id)
            .gino.status()
        )
        await read_one_event(self.request.app.state.redis, self.request.user)
        return Response(status_code=status.HTTP_200_OK)
