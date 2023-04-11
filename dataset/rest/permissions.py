"""Модуль с разрешениями для рест запросов."""

from fastapi import HTTPException
from starlette import status
from starlette.requests import Request

from dataset.tables.operator import Operator


class AuthChecker:
    """Проверяет разрешения для рест запросов."""

    def __init__(
        self,
        is_auth: bool = True,
        is_admin: bool = False,
        is_operator: bool = False,
    ) -> None:
        """Конструктор класса."""
        self.is_auth = is_auth
        self.is_admin = is_admin
        self.is_operator = is_operator

    def __call__(self, request: Request) -> None:
        """Реализует вызов экземпляра."""
        if self.is_auth and not getattr(request, "user", None):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="User not found."
            )
        if self.is_admin and not request.user.is_superuser:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User is not superuser.",
            )
        if self.is_operator and not isinstance(
            getattr(request, "user", None), Operator
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User is not an operator.",
            )
