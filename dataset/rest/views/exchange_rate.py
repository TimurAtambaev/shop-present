"""Модуль с представлениями для работы с курсами валют."""
import requests
from fastapi_utils.cbv import cbv
from fastapi_utils.inferring_router import InferringRouter

from dataset.config import settings
from dataset.rest.models.exchange_rate import ExchangeRate
from dataset.rest.views.base import BaseView
from dataset.tables.admin_settings import AdminSettings

router = InferringRouter()


@cbv(router)
class ExchangeRate(BaseView):
    """Представление курса валют."""

    @router.get("/exchange_rate", response_model=ExchangeRate)
    async def get_exchange_rate(self) -> dict:
        """Получить курс валют."""
        ex_rate = await AdminSettings.query.gino.first()
        return {"rate": ex_rate.exchange_rate}

    @router.get("/update/exchange_rate")
    async def update_exchange_rate(self, token: str = None):  # noqa
        """Ежедневна задача для обновления курса валют."""
        if token != settings.TOKEN:
            return None
        new_ex_rate = requests.get(
            f"{settings.CURRENCY_API}"
            f"?apiKey={settings.API_KEY_CURRENCY}"
            "&q=EUR_RUB&compact=ultra"
        )
        result = new_ex_rate.json()
        return await AdminSettings.update.values(
            exchange_rate=result["EUR_RUB"]
        ).gino.status()
