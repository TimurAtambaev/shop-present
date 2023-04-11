"""Модуль с background_tasks уведомлений."""
from sqlalchemy import func

from dataset.config import settings
from dataset.rest.models.event import (
    CurrencyEventModel,
    DonateEventModel,
    DreamEventModel,
    EventConfirmDonateModel,
    EventDonateModel,
    EventDreamModel,
    EventNewPersonModel,
    UserEventModel,
)
from dataset.tables.currency import Currency
from dataset.tables.donation import Donation
from dataset.tables.dream import Dream
from dataset.tables.event import Event, TypeEvent
from dataset.tables.user import User


async def event_dream(user: User, dream: Dream, type_event: str) -> None:
    """Создание уведомлений для событий по мечте.

    типы уведомлений: 'execute_dream', 'dream_maker'.
    """
    data = EventDreamModel(
        user=UserEventModel.from_orm(user),
        dream=DreamEventModel.from_orm(dream),
    ).dict()
    await Event.create(
        data=data, type_event=type_event, user_id=user.id, dream_id=dream.id
    )


async def event_donate(
    user: User,
    sender: User,
    dream: Dream,
    donation: Donation,
    currency: Currency,
) -> None:
    """Создание уведомления о полученном и требующем подтверждения донате."""
    data = EventDonateModel(
        user=UserEventModel.from_orm(user),
        dream=DreamEventModel.from_orm(dream),
        sender=UserEventModel.from_orm(sender if sender else None),
        donation=DonateEventModel.from_orm(donation),
        currency=CurrencyEventModel.from_orm(currency),
    )
    data.donation.first_amount /= settings.FINANCE_RATIO

    await Event.create(
        data=data.dict(),
        type_event=TypeEvent.DONATE.value,
        user_id=user.id,
        sender_id=sender.id if sender else None,
        dream_id=dream.id,
        donation_id=donation.id,
    )


async def event_confirm_donate(sender: User, donation: Donation) -> None:
    """Создание уведомления для отправителя о подтверждении доната."""
    if event_donate := (
        await Event.query.where(Event.donation_id == donation.id).gino.first()
    ):
        user_id = event_donate.sender_id
        if not user_id:
            await event_donate.update(is_read=True).apply()
            return
        user = await User.get(user_id)
        data = EventConfirmDonateModel(
            user=UserEventModel.from_orm(user),
            sender=UserEventModel.from_orm(sender),
        ).dict()

        await (
            Event.update.values(
                data=data,
                type_event=TypeEvent.CONFIRM_DONATE.value,
                is_read=False,
                user_id=user_id,
                sender_id=sender.id,
                created_at=func.now(),
            )
            .where(Event.donation_id == donation.id)
            .gino.status()
        )


async def event_new_person(user: User, sender: User, type_event: str) -> None:
    """Создание уведомлений.

    Для событий по статусу пользователей по отношению к текущему,
    типы уведомлений: 'new_participant', 'new_friend'.
    """
    data = EventNewPersonModel(
        user=UserEventModel.from_orm(user),
        sender=UserEventModel.from_orm(sender),
    ).dict()
    await Event.create(
        data=data, type_event=type_event, user_id=user.id, sender_id=sender.id
    )
