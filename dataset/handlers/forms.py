"""Form handlers."""
import os
import sys
from datetime import datetime
from pathlib import Path

import trafaret as T  # noqa N812
from aiofile import async_open
from aiohttp import web
from aiohttp.abc import StreamResponse
from aiohttp.web_exceptions import HTTPBadRequest
from aiohttp.web_request import FileField, Request
from gino import GinoConnection, GinoEngine
from gino.transaction import GinoTransaction
from loguru import logger

from dataset.models.dream_form import DreamForm

logger.add(sys.stdout, level="DEBUG")


def validate_file(value: FileField) -> FileField:
    """Провалидировать файл."""
    if isinstance(value, FileField) and value:
        return value
    raise HTTPBadRequest(reason="Wrong file")


async def _save_file(file: FileField) -> str:
    """Сохранить файл."""
    media_dir = Path("media")
    media_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().timestamp()
    path = str(
        Path.joinpath(media_dir, f"{timestamp}_{file.filename}").resolve()
    )
    async with async_open(file.file, "r") as r_file, async_open(
        path, "wb"
    ) as w_file:
        async for line in r_file.iter_chunked():
            await w_file.write(line)

    return path


dream_form = T.Dict(
    {
        T.Key("title"): T.String(min_length=1),
        T.Key("description"): T.String(min_length=1),
        T.Key("name"): T.String(min_length=1),
        T.Key("goal"): T.Int(lte=os.getenv("DREAM_LIMIT", 5000)),
        T.Key("email"): T.Email,
        T.Key("picture"): validate_file,
    }
)


async def post_form(request: Request) -> StreamResponse:
    """Запрос на отправку формы."""
    try:
        content = await request.post()
        cleaned_data = dream_form.check(dict(content))
        cleaned_data["picture"] = await _save_file(cleaned_data["picture"])
        cleaned_data["goal"] = int(cleaned_data["goal"])

        engine: GinoEngine = await request.app["db"].get_for_read()
        tx_: GinoTransaction
        async with engine.transaction() as tx_:
            conn: GinoConnection = tx_.connection
            await conn.status(DreamForm.insert().values(**cleaned_data))

        return web.json_response({}, status=201)
    except Exception as err:
        logger.debug(f"DEBUG_catch {err}")  # noqa G004
        logger.exception("Catch")


async def get_max_dream_amount(request: Request) -> StreamResponse:
    """Запрос на получение лимита мечты."""
    return web.json_response({"dream_limit": os.getenv("DREAM_LIMIT", 5000)})
