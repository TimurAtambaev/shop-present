"""Модуль с представлениями обработки запросов."""
from datetime import datetime

from loguru import logger
from fastapi import HTTPException
from fastapi_utils.cbv import cbv
from fastapi_utils.inferring_router import InferringRouter
from sqlalchemy import update, and_, select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status
from uuid import uuid4

from starlette.responses import JSONResponse

from dataset.db import async_session
from dataset.rest.models.kit import (ImportKitModel, ChangeCitizenModel,
                                     ResponseCitizenModel)
from dataset.tables.kit import Kit

router = InferringRouter()


@cbv(router)
class Handler:
    """Представление для обработки запросов."""

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
                  response_model=ResponseCitizenModel)
    async def change_kit(self, kit: ChangeCitizenModel, import_id: str,
                         citizen_id: int) -> ResponseCitizenModel:
        """Изменить информацию о жителе в указанном наборе данных."""
        async with async_session() as session:
            if kit.relatives:
                citizen = await self.get_citizen(session, import_id, citizen_id)
                await self.add_relative_connections(session, import_id,
                                                    citizen_id, kit.relatives)
                await self.delete_relative_connections(session, import_id,
                                                       citizen_id,
                                                       kit.relatives,
                                                       citizen.relatives)
            await self.change_citizen(session, import_id, citizen_id,
                                      self.get_clean_data(kit))
            return await self.get_citizen(session, import_id, citizen_id)

    def get_clean_data(self, kit: ChangeCitizenModel) -> dict:
        """Очистить данные запроса от пустых значений."""
        if not kit:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="request data cannot be empty"
            )
        request_data = kit.dict()
        return {attr: request_data[attr] for attr in request_data
                if request_data[attr]}

    async def change_citizen(self, session: AsyncSession, import_id: str,
                             citizen_id: int, filled_data: dict) -> None:
        """Изменить информацию о жителе."""
        query = (update(Kit)
                 .where(and_(Kit.import_id == import_id,
                             Kit.citizen_id == citizen_id))
                 .values(**filled_data))
        try:
            await session.execute(query)
            await session.commit()
        except Exception as exc:
            logger.error(exc)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
            )

    async def add_relative_connections(self, session: AsyncSession,
                                       import_id: str, citizen_id: int,
                                       request_relatives: list) -> None:
        """Добавить двусторонние связи родственникам жителя."""
        for relative_id in set(request_relatives):
            query = (select(Kit).where(and_(Kit.import_id == import_id,
                                            Kit.citizen_id == relative_id)))
            try:
                relative_relatives = (
                    (await session.execute(query))
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

    async def delete_relative_connections(self, session: AsyncSession,
                                          import_id: str, citizen_id: int,
                                          request_relatives: list,
                                          citizen_relatives: list) -> None:
        """Удалить двусторонние связи у родственников жителя."""
        delete_relatives = set(citizen_relatives) - set(request_relatives)
        for relative_id in delete_relatives:
            query = (select(Kit).where(and_(Kit.import_id == import_id,
                                            Kit.citizen_id == relative_id)))
            try:
                relative_relatives = (
                    (await session.execute(query))
                    .scalar().relatives)
                if citizen_id in relative_relatives:
                    relative_relatives.remove(citizen_id)
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

    async def get_citizen(self, session: AsyncSession, import_id: str,
                          citizen_id: int) -> Kit:
        """Получить информацию о жителе."""
        query = (select(Kit).where(and_(
            Kit.import_id == import_id, Kit.citizen_id == citizen_id)))
        try:
            citizen = (await session.execute(query)).scalar()
        except Exception as exc:
            logger.error(exc)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
            )
        if not citizen:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="citizen not found"
            )
        return citizen

    @router.get("/imports/{import_id}/citizens",
                response_model=ResponseCitizenModel)
    async def get_kit(self, import_id: str) -> ResponseCitizenModel:
        """Получить список всех жителей из указанного набора данных."""

