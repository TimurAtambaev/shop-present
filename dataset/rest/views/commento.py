"""Модуль с методами для комментариев."""
from os import getenv
from typing import Optional
from uuid import uuid4

from gino import Gino
from loguru import logger

from dataset.config import settings
from dataset.migrations import db
from dataset.tables.user import User


async def add_commenter_session(user: User, refresh: bool) -> Optional[str]:
    """Создать сессию для комментирования на сайте."""
    if getenv("TESTING"):
        return  # noqa R502
    email = getattr(user, "verified_email", user.email)
    commenter = await find_user_in_commento_db(email)
    commentertoken = uuid4().hex + uuid4().hex
    if commenter:
        commenterhex = dict(commenter).get("commenterhex")
    else:
        commenterhex = uuid4().hex + uuid4().hex
        surname = getattr(user, "surname", "")
        avatar = getattr(user, "avatar", None)
        if avatar is None:
            avatar = settings.DEFAULT_AVATAR
        name = f"{user.name} {surname}"
        await db.status(
            db.text(
                f"""
            INSERT INTO commenters (commenterhex, email, name, link, photo,
                                    provider, joindate, state, passwordhash)
                 VALUES ('{commenterhex}', '{email}',
                         '{name}', 'undefined', '{avatar}', 'commento',
                         NOW(), 'ok', '{user.password}')"""
            )
        )
        unsubscribesecrethex = uuid4().hex + uuid4().hex
        await db.status(
            db.text(
                f"""
            INSERT INTO emails (email, unsubscribesecrethex,
                                lastemailnotificationdate, pendingemails,
                                sendreplynotifications,
                                sendmoderatornotifications)
                 VALUES ('{email}', '{unsubscribesecrethex}',
                         NOW(), 0, FALSE, FALSE)"""
            )
        )
    if not refresh:
        await db.status(
            db.text(
                f"""
        INSERT INTO commentersessions (commentertoken, commenterhex,
                                       creationdate)
             VALUES ('{commentertoken}', '{commenterhex}', NOW())"""
            )
        )
    else:
        commentertoken_query = await db.first(
            db.text(
                f"""
                SELECT commentertoken
                  FROM commentersessions
                 WHERE commenterhex = '{commenterhex}';"""
            ).gino.query
        )
        if commentertoken_query:
            commentertoken = dict(commentertoken_query).get("commentertoken")

    return commentertoken  # noqa R504


async def delete_commenter_session(user: User) -> None:
    """Удалить сессию комментирования на сайте."""
    if getenv("TESTING"):
        return
    email = getattr(user, "verified_email", user.email)
    commenter = await find_user_in_commento_db(email)
    try:
        commenterhex = dict(commenter).get("commenterhex")
        await db.status(
            db.text(
                f"""
        DELETE FROM commentersessions
              WHERE commenterhex = '{commenterhex}';"""
            )
        )
    except Exception as exc:
        logger.error(exc)  # noqa G200


async def update_commenter(user: User) -> None:
    """Обновить данные пользователя в базе данных commento."""
    if getenv("TESTING"):
        return
    avatar = getattr(user, "avatar", None)
    email = getattr(user, "verified_email", user.email)
    try:
        await db.status(
            db.text(
                f"""
        UPDATE commenters
           SET photo = '{avatar}'
         WHERE email = '{email}';"""
            )
        )
    except Exception as exc:
        logger.error(exc)  # noqa G200


async def find_user_in_commento_db(email: str) -> Gino:
    """Найти пользователя по email в базе данных commento."""
    try:
        return await db.first(
            db.text(
                f"""
        SELECT *
          FROM commenters
         WHERE email = '{email}';"""
            ).gino.query
        )
    except Exception as exc:
        logger.error(exc)  # noqa G200
        return  # noqa R502
