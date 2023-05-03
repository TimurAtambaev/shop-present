"""Модуль с тестами запросов."""
import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import select, and_

from dataset.db import async_session
from dataset.tables.citizens import Citizens, Relations
from tests.json_queries import (IMPORT_CITIZENS, ADD_RELATIONS, CHANGE_CITIZEN,
                                DEL_RELATIONS, DEFAULT_IMPORT_ID)


@pytest.mark.asyncio()
async def test_import_kit(client: AsyncClient, app: FastAPI) -> None:
    """Тест импорта набора жителей."""
    response = await client.post(app.url_path_for("import_kit"),
                                 json=IMPORT_CITIZENS)

    assert response.status_code == 201

    async with async_session() as session:
        import_id = (await session.execute(select(Citizens.import_id).where(
            Citizens.citizen_id == 1))).scalar()
    assert response.json()["data"]["import_id"] == import_id


@pytest.mark.asyncio()
async def test_change_kit_add(client: AsyncClient, app: FastAPI) -> None:
    """Тест изменения информации о жителе с добавлением родственных связей."""
    await client.post(app.url_path_for("import_kit"), json=IMPORT_CITIZENS)

    response = await client.patch(app.url_path_for("change_kit",
                                                   **CHANGE_CITIZEN), json={})
    assert response.status_code == 400
    assert response.json()["detail"] == "request data cannot be empty"

    response = await client.patch(app.url_path_for("change_kit",
                                                   **CHANGE_CITIZEN),
                                  json=ADD_RELATIONS)
    assert response.status_code == 200

    async with async_session() as session:
        query = (select(Relations.relative_id).where(and_(
            Relations.import_id == CHANGE_CITIZEN["import_id"],
            Relations.citizen_id == CHANGE_CITIZEN["citizen_id"])))
        citizen_relatives = [relative[0] for relative in
                             (await session.execute(query)).all()]

        for relative_id in citizen_relatives:
            query = (select(Relations.relative_id).where(and_(
                Relations.import_id == CHANGE_CITIZEN["import_id"],
                Relations.citizen_id == relative_id)))
            relative_relatives = [relative[0] for relative in
                                  (await session.execute(query)).all()]
            assert CHANGE_CITIZEN["citizen_id"] in relative_relatives

    assert response.json()["data"]["relatives"] == ADD_RELATIONS["relatives"]
    assert response.json()["data"]["relatives"] == citizen_relatives


@pytest.mark.asyncio()
async def test_change_kit_del(client: AsyncClient, app: FastAPI) -> None:
    """Тест изменения информации о жителе с удалением родственных связей."""
    await client.post(app.url_path_for("import_kit"), json=IMPORT_CITIZENS)

    await client.patch(app.url_path_for("change_kit", **CHANGE_CITIZEN),
                       json=ADD_RELATIONS)

    response = await client.patch(app.url_path_for("change_kit",
                                                   **CHANGE_CITIZEN),
                                  json=DEL_RELATIONS)
    assert response.status_code == 200

    async with async_session() as session:
        query = (select(Relations.relative_id).where(and_(
            Relations.import_id == CHANGE_CITIZEN["import_id"],
            Relations.citizen_id == CHANGE_CITIZEN["citizen_id"])))
        citizen_relatives = [relative[0] for relative in
                             (await session.execute(query)).all()]

        for relative_id in citizen_relatives:
            query = (select(Relations.relative_id).where(and_(
                Relations.import_id == CHANGE_CITIZEN["import_id"],
                Relations.citizen_id == relative_id)))
            relative_relatives = [relative[0] for relative in
                                  (await session.execute(query)).all()]
            assert CHANGE_CITIZEN["citizen_id"] not in relative_relatives

    assert response.json()["data"]["relatives"] == DEL_RELATIONS["relatives"]
    assert response.json()["data"]["relatives"] == citizen_relatives


@pytest.mark.asyncio()
async def test_get_kit(client: AsyncClient, app: FastAPI) -> None:
    """Тест получения списка всех жителей из указанного набора данных."""
    await client.post(app.url_path_for("import_kit"), json=IMPORT_CITIZENS)

    response = await client.get(app.url_path_for(
        "get_kit", import_id=DEFAULT_IMPORT_ID))
    assert response.status_code == 200
    assert response.json()["data"] == IMPORT_CITIZENS["citizens"]


@pytest.mark.asyncio()
async def test_get_presents(client: AsyncClient, app: FastAPI) -> None:
    """Тест получения списка количества подарков родственникам по месяцам."""
    await client.post(app.url_path_for("import_kit"), json=IMPORT_CITIZENS)
    await client.patch(app.url_path_for("change_kit", **CHANGE_CITIZEN),
                       json=ADD_RELATIONS)

    response = await client.get(app.url_path_for(
        "get_presents", import_id=DEFAULT_IMPORT_ID))
    assert response.status_code == 200
    assert response.json()["data"]["12"][0]["citizen_id"] == 2
    assert response.json()["data"]["12"][0]["presents"] == 1
    assert response.json()["data"]["12"][1]["citizen_id"] == 3
    assert response.json()["data"]["12"][1]["presents"] == 1


@pytest.mark.asyncio()
async def test_get_stat_percentile(client: AsyncClient, app: FastAPI) -> None:
    """
    Тест получения перцентилей p50, p75, p99 по городам в разрезе возраста.
    """
    await client.post(app.url_path_for("import_kit"), json=IMPORT_CITIZENS)

    response = await client.get(app.url_path_for(
        "get_stat_percentile", import_id=DEFAULT_IMPORT_ID))
    assert response.status_code == 200
