"""Модуль с представлениями обработки запросов."""
from datetime import datetime

from loguru import logger
import sqlalchemy as sa
from fastapi import Depends, HTTPException, Request, Response
from fastapi_utils.cbv import cbv
from fastapi_utils.inferring_router import InferringRouter
from sqlalchemy import update, and_
from starlette import status
from uuid import uuid4

from starlette.responses import JSONResponse

from dataset.config import settings
from dataset.db import async_session
from dataset.rest.models.kit import ImportKitModel, ChangeKitModel
from dataset.tables.kit import Kit

router = InferringRouter()


@cbv(router)
class Handler:
    """Представление для обработки запросов."""

    request: Request
    response: Response

    @router.post("/imports")
    async def import_kit(self, kit: ImportKitModel):
        """Обработать и сохранить набор жителей в базе данных."""
        import_id = uuid4().hex
        async with async_session() as session:
            for citizen in kit.citizens:
                citizen.import_id = import_id
                try:
                    citizen.birth_date = datetime.strptime(citizen.birth_date,
                                                           "%d.%m.%Y")
                except ValueError as exc:
                    logger.error(exc)
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
                    )
            try:
                session.add_all([Kit(**citizen.dict()) for citizen
                                 in kit.citizens])
                await session.commit()
            except Exception as exc:
                logger.error(exc)
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
                )
        return JSONResponse(status_code=status.HTTP_201_CREATED,
                            content={"data": {"import_id": import_id}})

    @router.patch("/imports/{import_id}/citizens/{citizen_id}")
    async def change_kit(self, kit: ChangeKitModel, import_id: str,
                         citizen_id: int):
        """Изменить информацию о жителе в указанном наборе данных."""
        if not kit:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="request data cannot be empty"
            )
        query = (update(Kit)
                 .where(and_(Kit.import_id == import_id,
                             Kit.citizen_id == citizen_id))
                 .values(**kit.dict()))
        async with async_session() as session:
            try:
                await session.execute(query)
                await session.commit()
            except Exception as exc:
                logger.error(exc)
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
                )


