"""Schedule method to declare scheduled tasks."""
from typing import Callable, Type

from apscheduler.schedulers.base import BaseScheduler
from fastapi import FastAPI
from pytz import utc

from dataset.rest.views.utils import refresh_dreams_view


def schedule(app: FastAPI) -> Callable:
    """Add schedule tasks. Declare tasks above."""

    async def inner_func() -> Type[Callable]:
        scheduler: BaseScheduler = app.state.scheduler
        scheduler.add_job(
            refresh_dreams_view,
            "cron",
            id="refresh_dreams_view",
            hour="*",
            timezone=utc,
        )

    return inner_func
