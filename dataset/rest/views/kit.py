"""Модуль с представлениями обработки запросов."""
from loguru import logger
import sqlalchemy as sa
from fastapi import Depends, HTTPException, Request, Response
from fastapi_utils.cbv import cbv
from fastapi_utils.inferring_router import InferringRouter
from starlette import status
from uuid import uuid4
from dataset.config import settings
from dataset.rest.models.kit import ImportKitModel
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
        async with db.transaction():
            for citizen in kit.citizens:
                data = citizen.dict()
                data["import_id"] = import_id
                try:
                    await Kit.create(**data)
                except Exception as exc:
                    logger.error(exc)
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST, detail=exc
                    )
        return JSONResponse(status_code=status.HTTP_201_CREATED,
                            content={"data": {"import_id": import_id}})

