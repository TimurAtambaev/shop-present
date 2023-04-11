"""Модуль кастомной пагинации."""
from __future__ import annotations

from typing import Any, Optional, Protocol, Union, runtime_checkable

from fastapi_pagination import create_page, resolve_params
from fastapi_pagination.bases import AbstractPage, AbstractParams
from fastapi_pagination.ext.sqlalchemy import paginate_query
from gino.crud import CRUDModel
from multimethod import multimethod
from sqlalchemy import func
from sqlalchemy.sql import Select

Query = Union[Select, CRUDModel]


@runtime_checkable
class ModifiedRecord(Protocol):
    """Интерфейс для валидации перегрузки."""

    main_query: Query

    @classmethod
    def __subclasshook__(cls, other: Any) -> bool:
        """Разрешить использовать протокол в проверке issubclass."""
        return True


@multimethod
async def custom_paginate(
    items: Any, total: int = 0, params: Optional[AbstractParams] = None
) -> AbstractPage:
    """Получить инстанс модели страницы."""
    raise NotImplementedError


@custom_paginate.register
async def _(
    items: list[ModifiedRecord],
    total: int = 0,
    params: Optional[AbstractParams] = None,
) -> AbstractPage:
    """Получить инстанс модели страницы."""
    if not total and items:
        query = items[0].main_query
        total = (
            await func.count()
            .select()
            .select_from(query.alias())
            .gino.scalar()
        )
    return create_page(items, total, params)


@custom_paginate.register(CRUDModel)
@custom_paginate.register(Select)
async def _(
    query: Query, total: int = None, params: Optional[AbstractParams] = None
) -> AbstractPage:
    """Получить инстанс модели страницы."""
    params = resolve_params(params)
    items = await paginate_qs(query, params)
    return await custom_paginate(items, total, params)


async def paginate_qs(
    query: Query, params: Optional[AbstractParams] = None
) -> list[ModifiedRecord]:
    """Получить пагинированый результат."""
    params = resolve_params(params)
    result = await paginate_query(query, params).gino.all()
    for item in result:
        item.__dict__["main_query"] = query
    return result
