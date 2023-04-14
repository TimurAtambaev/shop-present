"""Module with middlewares."""
from contextvars import ContextVar
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from dataset.config import settings

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
