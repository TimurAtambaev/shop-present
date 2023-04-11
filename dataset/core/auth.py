"""Basic tools for authorization and permission check."""
import datetime
import secrets
from hashlib import sha256 as _sha256
from typing import Optional, Tuple
from uuid import uuid4

import sqlalchemy as sa
from authlib.jose import jwt
from authlib.oauth2 import HttpRequest
from fastapi import FastAPI
from graphene import ResolveInfo
from sqlalchemy.engine import RowProxy
from starlette.requests import Request

from dataset.config import settings
from dataset.core.graphql import DatabaseHelper
from dataset.core.utils import jwt_decode
from dataset.exceptions import BlacklistedError
from dataset.tables.user import blacklist

HEADER = {"alg": "HS256"}
AUTH_HEADER = "Authorization"


def build_key(value: str, secret_key: str) -> str:
    """Build key for jwt token."""
    return "??".join([value, secret_key])


def create_token(
    payload: dict = None,
    expires: datetime.datetime = None,
    access_jti: Optional[str] = None,
) -> Tuple[str, str]:
    """Generate JWT token."""
    if not payload:
        payload = {}

    if not expires:
        expires = datetime.datetime.utcnow() + datetime.timedelta(hours=24)

    payload = {"exp": int(expires.timestamp()), "jti": uuid4().hex, **payload}
    if access_jti:
        payload["access_jti"] = access_jti

    token = jwt.encode(HEADER, payload, settings.JWT_KEY)

    return token.decode("ASCII"), payload["jti"]


async def check_token_blacklist(app: FastAPI, jti: str) -> RowProxy:
    """Check if token in blacklist."""
    return await DatabaseHelper.scalar(
        app,
        query=sa.exists(
            blacklist.select().where(blacklist.c.jti == jti)
        ).select(),
    )


def read_token(request: HttpRequest, type_: str) -> str:
    """Read token of given type from request 'Authorization' header."""
    auth_header: str = request.headers.get(AUTH_HEADER, None)
    assert bool(auth_header), "Header is not provided"
    assert (
        auth_header.split()[0].upper() == type_.upper()
    ), "Invalid token type"
    token = auth_header.split()[1]
    return token  # noqa R504


async def read_jwt_token(
    request: Request, key: str = "", token: str = None
) -> dict:
    """
    Read access token from request header.

    (If key presents, validates signature with it)
    """
    auth_header: str = request.headers.get(AUTH_HEADER, None)

    token = token or read_token(request, "JWT")
    payload = jwt_decode(token, key=key, verify=bool(key))

    if payload["exp"] < datetime.datetime.utcnow():
        raise PermissionError
    if await check_token_blacklist(request.app, payload["jti"]):
        raise BlacklistedError
    if not any((auth_header, payload)):
        return payload

    return {**payload, "token": token}


def create_reset_token() -> Tuple[str, datetime.datetime]:
    """Create reset token."""
    reset_token = secrets.token_urlsafe(nbytes=100)

    expiry = datetime.datetime.utcnow() + datetime.timedelta(
        seconds=settings.RESET_LIFETIME
    )

    return reset_token, expiry


def sha256(str_: str, salt: str) -> str:
    """Hash string with sha256 hashing algorithm."""
    return _sha256(build_key(str_, salt).encode("utf-8")).hexdigest()


def prepare_token_from_app(token: str) -> str:
    """Handle token preparation before writing to db or query."""
    return sha256(token, settings.secret_key)


def prepare_token(info: ResolveInfo, token: str) -> str:
    """
    Do the same as prepare_token_from_app.

    (handles process via info var.)
    """
    return prepare_token_from_app(token)
