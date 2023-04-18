"""Модуль с представлениями обработки запросов."""
from datetime import datetime

from loguru import logger
import sqlalchemy as sa
from fastapi import Depends, HTTPException, Request, Response
from fastapi_utils.cbv import cbv
from fastapi_utils.inferring_router import InferringRouter
from sqlalchemy import update, and_, select
from starlette import status
from uuid import uuid4

from starlette.responses import JSONResponse

from dataset.config import settings
from dataset.db import async_session
from dataset.rest.models.kit import (ImportKitModel, ChangeRezidentModel,
                                     ResponseRezidentModel)
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
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="incorrect birth date format, use DD.MM.YYYY"
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

    @router.patch("/imports/{import_id}/citizens/{citizen_id}",
                  response_model=ResponseRezidentModel)
    async def change_kit(self, kit: ChangeRezidentModel, import_id: str,
                         citizen_id: int) -> ResponseRezidentModel:
        """Изменить информацию о жителе в указанном наборе данных."""
        if not kit:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="request data cannot be empty"
            )
        request_data = kit.dict()
        filled_data = {attr: request_data[attr] for attr in request_data
                       if request_data[attr]}
        query = (update(Kit)
                 .where(and_(Kit.import_id == import_id,
                             Kit.citizen_id == citizen_id))
                 .values(**filled_data))
        async with async_session() as session:
            try:
                await session.execute(query)
                await session.commit()
            except Exception as exc:
                logger.error(exc)
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
                )

            for relative_id in kit.relatives:
                query_relative = (select(Kit)
                         .where(and_(Kit.import_id == import_id,
                                     Kit.citizen_id == relative_id)))
                try:
                    relative_relatives = (
                        (await session.execute(query_relative))
                        .scalar().relatives)
                    if citizen_id not in relative_relatives:
                        relative_relatives.append(citizen_id)
                        query_update_relative = (
                            update(Kit).where(and_(
                                Kit.import_id == import_id,
                                Kit.citizen_id == relative_id))
                            .values(relatives=relative_relatives))
                        await session.execute(query_update_relative)
                        await session.commit()
                except Exception as exc:
                    logger.error(exc)
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
                    )

        query = (select(Kit)
                 .where(and_(Kit.import_id == import_id,
                             Kit.citizen_id == citizen_id)))
        async with async_session() as session:
            try:
                rezident = (await session.execute(query)).scalar()
            except Exception as exc:
                logger.error(exc)
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
                )
            if not rezident:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="rezident not found"
                )
            return rezident




