"""Модуль с представлениями обработки запросов."""
from loguru import logger
from fastapi import HTTPException
from fastapi_utils.cbv import cbv
from fastapi_utils.inferring_router import InferringRouter
from sqlalchemy import update, and_, select, insert, delete
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from starlette.responses import JSONResponse

from dataset.db import async_session
from dataset.rest.models.kit import (ImportCitizenModel,
                                     ChangeCitizenModel,
                                     ResponseCitizenModel,
                                     ResponseCitizensModel)
from dataset.tables.citizens import Imports, Citizens, Relations

router = InferringRouter()


@cbv(router)
class Handler:
    """Представление для обработки запросов."""

    @router.post("/imports")
    async def import_kit(self, kit: ImportCitizenModel):
        """Обработать и сохранить набор жителей в базе данных."""
        async with async_session() as session:
            try:
                import_id = (await session.execute(
                    insert(Imports).returning(Imports.import_id))).scalar()
                relatives_list = []
                for citizen in kit.citizens:
                    citizen.import_id = import_id
                    for relative_id in citizen.relatives:
                        relatives_list.append(
                            {"import_id": import_id,
                             "citizen_id": citizen.citizen_id,
                             "relative_id": relative_id})
                    del citizen.relatives

                session.add_all([Citizens(**citizen.dict()) for citizen
                                 in kit.citizens])

                session.add_all([Relations(**relatives)
                                 for relatives in relatives_list])

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
    async def change_kit(self, kit: ChangeCitizenModel, import_id: int,
                         citizen_id: int) -> ResponseCitizenModel:
        """Изменить информацию о жителе в указанном наборе данных."""
        if not kit:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="request data cannot be empty"
            )
        async with async_session() as session:
            citizen_relatives = await self.get_citizen_relatives(
                session, import_id, citizen_id)
            request_relatives = set(kit.relatives)
            current_relatives = set(citizen_relatives)
            delete_relatives = current_relatives - request_relatives
            add_relatives = request_relatives - current_relatives

            await self.add_relative_connections(session, import_id,
                                                citizen_id, add_relatives)
            await self.delete_relative_connections(session, import_id,
                                                   citizen_id, delete_relatives)
            await self.change_citizen(session, import_id, citizen_id,
                                      self.get_clean_data(kit))
            await session.commit()

            return await self.get_citizen(session, import_id, citizen_id)

    def get_clean_data(self, kit: ChangeCitizenModel) -> dict:
        """Подготовить данные запроса для сохранения в БД."""
        del kit.relatives
        request_data = kit.dict()
        return {attr: request_data[attr] for attr in request_data
                if request_data[attr]}

    async def change_citizen(self, session: AsyncSession, import_id: int,
                             citizen_id: int, clean_data: dict) -> None:
        """Изменить информацию о жителе."""
        query = (update(Citizens)
                 .where(and_(Citizens.import_id == import_id,
                             Citizens.citizen_id == citizen_id))
                 .values(**clean_data))
        try:
            await session.execute(query)
        except Exception as exc:
            logger.error(exc)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
            )

    async def add_relative_connections(self, session: AsyncSession,
                                       import_id: int, citizen_id: int,
                                       add_relatives: set) -> None:
        """Добавить двусторонние связи жителя с родственниками."""
        try:
            for relative_id in add_relatives:
                query_insert = (insert(Relations).values(
                    import_id=import_id,
                    citizen_id=citizen_id,
                    relative_id=relative_id))
                query_insert_reverse = (insert(Relations).values(
                    import_id=import_id,
                    citizen_id=relative_id,
                    relative_id=citizen_id))
                await session.execute(query_insert)
                await session.execute(query_insert_reverse)
        except Exception as exc:
            logger.error(exc)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
            )

    async def delete_relative_connections(self, session: AsyncSession,
                                          import_id: int, citizen_id: int,
                                          delete_relatives: set) -> None:
        """Удалить двусторонние связи жителя с родственниками."""
        try:
            for relative_id in delete_relatives:
                query_delete = (delete(Relations).where(and_(
                    Relations.import_id == import_id,
                    Relations.citizen_id == citizen_id,
                    Relations.relative_id == relative_id)))
                query_delete_reverse = (delete(Relations).where(and_(
                    Relations.import_id == import_id,
                    Relations.citizen_id == relative_id,
                    Relations.relative_id == citizen_id)))
                await session.execute(query_delete)
                await session.execute(query_delete_reverse)
        except Exception as exc:
            logger.error(exc)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
            )

    async def get_citizen_relatives(self, session: AsyncSession, import_id: int,
                                    citizen_id: int) -> list:
        """Получить список идентификаторов родственников жителя."""
        query = (select(Relations.relative_id).where(and_(
            Relations.import_id == import_id,
            Relations.citizen_id == citizen_id)))
        try:
            citizen_relatives = (await session.execute(query)).all()
        except Exception as exc:
            logger.error(exc)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
            )
        return [relative[0] for relative in citizen_relatives]

    async def get_citizen(self, session: AsyncSession, import_id: int,
                          citizen_id: int) -> ResponseCitizenModel:
        """Получить информацию о жителе."""
        query = (select(Citizens).where(and_(
            Citizens.import_id == import_id,
            Citizens.citizen_id == citizen_id)))
        try:
            citizen = (await session.execute(query)).scalar().__dict__
            citizen["birth_date"] = citizen["birth_date"].strftime("%d.%m.%Y")
            relatives = await self.get_citizen_relatives(
                session, import_id, citizen_id)
        except Exception as exc:
            logger.error(exc)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
            )
        return ResponseCitizenModel(**citizen, relatives=relatives)

    @router.get("/imports/{import_id}/citizens",
                response_model=ResponseCitizensModel)
    async def get_kit(self, import_id: str) -> dict:
        """Получить список всех жителей из указанного набора данных."""
        async with async_session() as session:
            query = select(Citizens).where(Citizens.import_id == import_id)
            try:
                citizens = (await session.execute(query)).all()
            except Exception as exc:
                logger.error(exc)
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
                )
        return {"data": [citizen[0] for citizen in citizens]}

    @router.get("/imports/{import_id}/citizens/birthdays",
                response_model=ResponseCitizensModel)
    async def get_presents(self, import_id: str) -> dict:
        """Получить список количества подарков родственникам по месяцам."""


