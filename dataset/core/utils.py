"""Module with utils for the project."""
from datetime import datetime
from typing import Dict, List, Optional

import jwt as pyjwt

EXPIRE_FORMAT = "%a, %d %b %Y %H:%M:%S GMT"


def jwt_decode(
    jwt: str,
    key: str = "",
    verify: bool = True,
    algorithms: Optional[List[str]] = None,
    options: Optional[dict] = None,
    **kwargs: Dict,
) -> dict:
    """Get payload from token with formated expires key."""
    payload = pyjwt.decode(jwt, key, verify, algorithms, options, **kwargs)
    if payload.get("exp"):
        payload["exp"] = datetime.fromtimestamp(payload.get("exp"))

    if payload.get("expires"):
        payload["exp"] = datetime.strptime(
            payload.get("expires"), EXPIRE_FORMAT
        )

    return payload
