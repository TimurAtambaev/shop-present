"""Модуль с инструментами для работы с моделями pydantic."""
import inspect
from enum import Enum
from typing import Any, Type

from fastapi import HTTPException
from pydantic import BaseModel, ValidationError
from pydantic.fields import ModelField
from starlette import status


class EmptyResponse(BaseModel):
    """Модель для типизации пустого ответа."""

    ...


class SortChoices(str, Enum):
    """Выбор типа сортировки."""

    asc = "asc"
    desc = "desc"


def as_form(cls: Type[BaseModel]) -> Type[BaseModel]:
    """Превратить модель в форму."""
    new_parameters = []

    for field_name, model_field in cls.__fields__.items():  # noqa B007
        model_field: ModelField  # type: ignore

        new_parameters.append(
            inspect.Parameter(
                model_field.alias,
                inspect.Parameter.POSITIONAL_ONLY,
                default=model_field.field_info,
                annotation=model_field.outer_type_,
            )
        )

    async def as_form_func(**data: Any) -> BaseModel:
        """Инициализация формы."""
        try:
            return cls(**data)
        except ValidationError as exc:
            raise HTTPException(
                detail={"error": str(exc)},
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )

    sig = inspect.signature(as_form_func)
    sig = sig.replace(parameters=new_parameters)
    as_form_func.__signature__ = sig  # type: ignore
    setattr(cls, "as_form", as_form_func)  # noqa B010
    return cls
