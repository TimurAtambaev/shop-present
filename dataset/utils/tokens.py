"""Модуль для генерации токенов."""
from datetime import datetime, timedelta
from typing import Optional, Tuple, Union

from sqlalchemy.engine import RowProxy

from dataset.config import settings
from dataset.core.auth import create_token
from dataset.tables.operator import Operator
from dataset.tables.user import User


def create_auth_token(
    auth_user: Union[User, Operator, RowProxy],
    lifetime: Optional[timedelta] = None,
    access_jti: Optional[str] = None,
    return_jti: bool = False,
) -> Union[tuple[str, str], str]:
    """Create auth token with given username and signature key."""
    if not lifetime and not access_jti:
        lifetime = timedelta(seconds=settings.ACCESS_LIFETIME)
    elif not lifetime and access_jti:
        lifetime = timedelta(seconds=settings.REFRESH_LIFETIME)
    expires = datetime.utcnow() + lifetime

    payload = {
        "ufandao_id": auth_user.id,
        "iss": "ufandao",
        "is_operator": isinstance(auth_user, Operator),
    }
    if hasattr(auth_user, "imrix_id"):
        payload["imrix_id"] = auth_user.imrix_id
    token, jti = create_token(payload, expires, access_jti)
    if return_jti:
        return token, jti
    return token


def create_token_pair(active_user: Union[User, Operator]) -> Tuple[str, str]:
    """Создать пару токенов."""
    access_token, jti = create_auth_token(active_user, return_jti=True)
    refresh_token = create_auth_token(active_user, access_jti=jti)

    return access_token, refresh_token
