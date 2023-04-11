"""API category."""
from typing import List

from fastapi_utils.cbv import cbv
from fastapi_utils.inferring_router import InferringRouter
from sqlalchemy.engine import RowProxy

from dataset.config import settings
from dataset.rest.models.country import Country
from dataset.rest.views.base import BaseView
from dataset.tables.country import CountryLanguage

router = InferringRouter()


# TODO вынести с отдельный сервис
@cbv(router)
class CountryView(BaseView):
    """Класс для работы со странами."""

    @router.get("/country", response_model=List[Country])
    async def get_countries(self) -> List[RowProxy]:
        """Получение списка стран."""
        language = self.request["language"]
        countries = (
            await CountryLanguage.query.where(
                CountryLanguage.language == language
            )
            .order_by(CountryLanguage.title)
            .gino.all()
        )
        header_country_title = settings.HEADER_COUNRTY_TITLE.get(
            language
        ) or settings.HEADER_COUNRTY_TITLE.get(settings.DEFAULT_LANGUAGE)
        header_array = {
            "country_id": settings.HEADER_COUNRTY_ID,
            "title": header_country_title,
            "language": language,
        }
        countries.append(header_array)
        return countries
