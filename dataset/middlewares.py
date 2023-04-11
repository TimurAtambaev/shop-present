"""Module with middlewares."""
from contextvars import ContextVar
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from dataset.config import settings
from dataset.tables.user import User

request_var: ContextVar = ContextVar("request")


class ContextRequestMiddleware(BaseHTTPMiddleware):
    """Middleware for accessing request context in project."""

    async def dispatch(
        self, request: Request, call_next: Callable
    ) -> Response:
        """Put request in context while dispatch."""
        request_var.set(request)
        response: Response = await call_next(request)
        return response


class AddLanguageMiddleware(BaseHTTPMiddleware):
    """Middleware for add language to request."""

    async def dispatch(
        self, request: Request, call_next: Callable
    ) -> Response:
        """Функция добавления языка в запрос."""
        query_lang = request.query_params.get("lang")

        request.scope["language"] = settings.DEFAULT_LANGUAGE
        if query_lang:
            request.scope["language"] = query_lang
        elif request.cookies.get("language"):
            request.scope["language"] = request.cookies.get("language")
        elif isinstance(request.get("user"), User):
            request.scope["language"] = request.user.language

        response: Response = await call_next(request)
        return response
