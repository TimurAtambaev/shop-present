"""Country and country model related models (db, and graphql_).

Country related queries and mutations.
"""
import sys
from typing import Dict, Optional, Tuple

import graphene
import sqlalchemy as sa
import trafaret as T  # noqa N812
from dependency_injector.wiring import Provide, inject
from graphql import ResolveInfo
from localization.service import LanguageService
from loguru import logger
from trafaret import Trafaret

from dataset.core.container import Container
from dataset.core.db import (
    CREATED_AT_COLUMN,
    CREATED_BY_OPERATOR_COLUMN,
    UPDATED_AT_COLUMN,
    UPDATED_BY_OPERATOR_COLUMN,
)
from dataset.core.graphql import (
    LanguageHelper,
    ListInputType,
    ListResultType,
    app_from_info,
    authorized_without_content_manager,
)
from dataset.middlewares import request_var
from dataset.migrations import db

logger.add(
    sys.stdout,
    format="{time} {level} {message}",
    filter="my_module",
    backtrace=True,
    diagnose=True,
)

COUNTRY_DESCTION = "List of countries"


class Country(db.Model):
    """Базовая модель страны."""

    __tablename__ = "country"

    id = sa.Column(  # noqa A003
        "id", sa.Integer, primary_key=True, index=True, autoincrement=True
    )
    is_active = sa.Column("is_active", sa.Boolean(), default=False)
    payment_types = sa.Column(
        "payment_types", sa.ARRAY(sa.Integer), nullable=True
    )
    created_by_operator_column = CREATED_BY_OPERATOR_COLUMN()
    updated_by_operator_column = UPDATED_BY_OPERATOR_COLUMN()
    created_at = CREATED_AT_COLUMN()
    updated_at = UPDATED_AT_COLUMN()


class CountryLanguage(db.Model):
    """Модель страны."""

    __tablename__ = "country_language"

    country_id = sa.Column(
        "country_id", sa.ForeignKey("country.id"), nullable=False
    )
    language = sa.Column("language", sa.String(64), nullable=False)
    title = sa.Column("title", sa.String(64))
    code = sa.Column("code", sa.String(8))
    created_by_operator_column = CREATED_BY_OPERATOR_COLUMN()
    updated_by_operator_column = UPDATED_BY_OPERATOR_COLUMN()
    created_at = CREATED_AT_COLUMN()
    updated_at = UPDATED_AT_COLUMN()


class CountryManager:
    """Class handles countries list and stores them in app."""

    @classmethod
    async def __read_from_db(cls, info: ResolveInfo) -> Dict:
        """Read all countries from db."""
        countries = (await Country.query.gino.all()) or []
        languages = (await CountryLanguage.query.gino.all()) or []
        result = {}

        for cntry in countries:
            result[cntry.id] = {"title": {}}

            for key, value in cntry.to_dict().items():
                result[cntry.id][key] = value

        for lang in languages:
            if lang:
                result[lang.country_id]["title"][lang.language] = lang.title

        return result

    @classmethod
    async def __get_data(cls, info: ResolveInfo) -> Dict:
        """Return countries list.

        If app doesn't have valid list list is
        rebuilt and returned
        """
        app = app_from_info(info)
        countries = getattr(app.state, "countries", None)

        if not countries:
            countries = await cls.rebuild(info)

        return countries  # noqa R504

    @classmethod
    async def rebuild(cls, info: ResolveInfo) -> dict:
        """Rebuild app countries list."""
        app = app_from_info(info)
        app.state.countries = await cls.__read_from_db(info)

        return app.state.countries

    @classmethod
    async def get_list(
        cls, info: ResolveInfo, is_active: Optional[bool] = None
    ) -> dict:
        """Return list of countries.

        with filter by activity if is_active is not None
        """
        return {  # noqa A001
            id: c
            for id, c in (await cls.__get_data(info)).items()
            if is_active is None or c.get("is_active") == is_active
        }

    @classmethod
    async def get_active(cls, info: ResolveInfo) -> dict:
        """Return list of active countries."""
        return await cls.get_list(info, True)

    @classmethod
    @inject
    async def get_by_id(
        cls,
        info: ResolveInfo,
        country_id: int,
        language_service: LanguageService = Provide[
            Container.localization.service
        ],
    ) -> dict:
        """Return country by id."""
        try:
            return (await cls.__get_data(info))[country_id]

        except KeyError as error_exc:
            error = await language_service.get_error_text(
                "invalid_country", request_var.get()["language"]
            )
            raise ValueError(error) from error_exc


class PublicCountry(graphene.ObjectType):
    """Graphql model of country."""

    id = graphene.Int()  # noqa A003
    title = graphene.String()

    async def resolve_title(self, info: ResolveInfo) -> str:
        """Return countries title in app language."""
        my_country: Dict = self
        result = my_country.get("title")

        if isinstance(result, dict):
            return result.get(await LanguageHelper.get_language(info))

    class Meta:
        """Defining name. To keep same name in admin and public scopes."""

        name = "Country"


class AdminCountry(PublicCountry):
    """Graphql model of country."""

    is_active = graphene.Boolean()

    async def resolve_title(self, info: ResolveInfo) -> str:
        """Return countries title in app language."""
        my_country: Dict = self
        result = my_country.get("title")

        if isinstance(result, dict):
            return result.get(await LanguageHelper.get_language(info))

    class Meta:
        """Defining name. To keep same name in admin and public scopes."""

        name = "Country"


class CountryPublicSearchInput(ListInputType):
    """Input object that describes valid input for country search."""

    query = graphene.String()

    @classmethod
    def order_fields(cls) -> Tuple[str, ...]:
        """Fields valid for countries order."""
        return "id", "title"

    @classmethod
    def trafaret(cls) -> Trafaret:
        """Validate rules."""
        return super().trafaret() + T.Dict(
            {T.Key("query", optional=True): T.String(allow_blank=True)}
        )

    class Meta:
        """Defining name.

        To keep same input name in admin and public scopes.
        """

        name = "CountrySearchInput"


class CountryAdminSearchInput(CountryPublicSearchInput):
    """Input object that describes valid input for country search."""

    is_active = graphene.Boolean()

    @classmethod
    def order_fields(cls) -> Tuple[str, ...]:
        """Fields valid for countries order."""
        return "id", "title"

    @classmethod
    def trafaret(cls) -> Trafaret:
        """Validate rules."""
        return super().trafaret() + T.Dict(
            {T.Key("is_active", optional=True): T.Bool()}
        )

    class Meta:
        """Defining name.

        To keep same input name in admin and public scopes.
        """

        name = "CountrySearchInput"


class CountriesPublicList(ListResultType):
    """Describe countries list output structure."""

    result = graphene.List(PublicCountry, description=COUNTRY_DESCTION)

    class Meta:
        """Defining name.

        To keep same output name in admin and public scopes.
        """

        name = "CountriesList"


class CountriesAdminList(ListResultType):
    """Describes countries list output structure."""

    result = graphene.List(PublicCountry, description=COUNTRY_DESCTION)

    class Meta:
        """Defining name.

        To keep same output name in admin and public scopes.
        """

        name = "CountriesList"


class CountryAdminQuery(graphene.ObjectType):
    """Queries for admin space."""

    countries = graphene.Field(
        CountriesAdminList,
        input=graphene.Argument(CountryAdminSearchInput, required=False),
        required=True,
        description=COUNTRY_DESCTION,
    )

    @authorized_without_content_manager
    async def resolve_countries(
        self,
        info: ResolveInfo,
        input: Dict,  # noqa A002
    ) -> dict:
        """Countries query resolver."""
        data = await CountryAdminSearchInput.validate(input)
        offset = data.get("offset")
        limit = data.get("limit")
        order = data.get("order", "title")
        query = data.get("query")
        is_active = data.get("is_active")

        result = list(
            (await CountryManager.get_list(info, is_active)).values()
        )

        if query:
            lang = await LanguageHelper.get_language(info)

            result = [
                r
                for r in result
                if query.lower() in r.get("title").get(lang).lower()
            ]

        if order.strip("-") == "title":
            lang = await LanguageHelper.get_language(info)
            result.sort(
                key=lambda c: c[order.strip("-")].get(lang, "").lower(),
                reverse=order.startswith("-"),
            )
        else:
            result.sort(
                key=lambda c: c[order.strip("-")],
                reverse=order.startswith("-"),
            )

        return {
            "count": len(result),
            "result": result[offset : (offset + limit)],  # noqa E203
        }


class CountryPublicQuery(graphene.ObjectType):
    """Queries for public space."""

    countries = graphene.Field(
        CountriesPublicList,
        input=graphene.Argument(CountryPublicSearchInput, required=False),
        required=True,
        description=COUNTRY_DESCTION,
    )

    async def resolve_countries(
        self,
        info: ResolveInfo,
        input: Dict,  # noqa A002
    ) -> dict:
        """Resolve counties."""
        try:
            """Resolves query for countries list"""
            data = await CountryPublicSearchInput.validate(input)
            offset = data.get("offset")
            limit = data.get("limit")
            order = data.get("order", "title")
            query = data.get("query")
            result = list((await CountryManager.get_active(info)).values())

            lang = await LanguageHelper.get_language(info)
            default_lang = await LanguageHelper.get_default_language()

            for country_item in result:
                if lang not in country_item["title"]:
                    country_item["title"][lang] = country_item["title"].get(
                        default_lang, ""
                    )

            if query:
                result = [
                    r
                    for r in result
                    if query.lower() in r.get("title").get(lang).lower()
                ]

            if order.strip("-") == "title":
                lang = await LanguageHelper.get_language(info)
                result.sort(
                    key=lambda c: c[order.strip("-")][lang].lower(),
                    reverse=order.startswith("-"),
                )
            else:
                result.sort(
                    key=lambda c: c[order.strip("-")],
                    reverse=order.startswith("-"),
                )

            return {
                "count": len(result),
                "result": result[offset : (offset + limit)],  # noqa E203
            }
        except Exception:
            logger.exception("tst")
