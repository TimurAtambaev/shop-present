"""Модуль с фикстурами."""
from typing import Callable, Generator, Tuple, Type, Union
from unittest.mock import AsyncMock, Mock

import aioredis
import pytest
import pytest_asyncio
from _pytest.monkeypatch import MonkeyPatch
from aioredis import Redis
from alembic.command import upgrade as alembic_upgrade
from botocore.exceptions import ClientError
from fastapi import FastAPI
from sqlalchemy.engine import Engine, create_engine
from starlette.testclient import TestClient
from yarl import URL

from dataset.app import init_app
from dataset.config import settings
from dataset.rest.views import dream as dream_views
from dataset.tables.user import User
from tests.factories import AchievementFactory, OperatorFactory, UserFactory
from tests.utils import alembic_config_from_url, get_tmp_database


@pytest.fixture(scope="session")
def monkeypatch_session() -> MonkeyPatch:
    """Инициализация monkeypatch."""
    patch = MonkeyPatch()
    yield patch
    patch.undo()


@pytest_asyncio.fixture()
async def app(
    postgres_engine: str,
    redis_connect: Redis,
) -> FastAPI:
    """Инициализация приложения."""
    application = init_app()
    await application.state.db.set_bind(postgres_engine)

    application.state.redis = redis_connect
    await application.state.redis.flushall()

    aws_mock = Mock()
    client_mock = Mock()
    client_mock.head_object = Mock(
        side_effect=ClientError({}, "operation_name")
    )
    client_mock.upload_fileobj = Mock()
    aws_mock.bucket = "test"
    aws_mock.client_factory = Mock(return_value=client_mock)
    application.state.aws = aws_mock

    application.state.mail = Mock()
    application.state.mail.send = AsyncMock()

    yield application


@pytest_asyncio.fixture()
async def redis_connect() -> Generator[Redis, None, None]:
    """Замена редиса для тестов."""
    redis = await aioredis.create_redis_pool(
        f"{settings.REDIS_DRIVER}://{settings.REDIS_HOST}:{settings.REDIS_PORT}",
        db=0 + int(settings.PYTEST_XDIST_WORKER.replace("gw", "") or 0),
        encoding="utf8",
        ssl=settings.REDIS_DRIVER != "redis",
    )
    try:
        yield redis
    finally:
        redis.close()
        await redis.wait_closed()


@pytest.fixture()
def postgres_engine(migrated_postgres: str) -> Generator[Engine, None, None]:
    """Привязанный к мигрированной базе данных SQLAlchemy engine."""
    engine = create_engine(
        migrated_postgres, echo=False, isolation_level="READ COMMITTED"
    )
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture()
def migrated_postgres(
    migrated_postgres_template: str,
) -> Generator[str, None, None]:
    """Создание базы с примененными миграциями.."""
    template_db = URL(migrated_postgres_template).name
    with get_tmp_database(template=template_db) as tmp_url:
        yield tmp_url


@pytest.fixture(scope="session")
def migrated_postgres_template(
    monkeypatch_session: MonkeyPatch,
) -> Generator[str, None, None]:
    """Создание шаблона базы с применением миграций."""
    with get_tmp_database() as tmp_url:
        alembic_config = alembic_config_from_url(tmp_url)
        monkeypatch_session.setattr(settings, "DB_URI", tmp_url)
        alembic_upgrade(alembic_config, "head")
        yield tmp_url


@pytest.fixture()
def test_client(app: FastAPI) -> TestClient:
    """Получение тестового клиента для отправки запросов."""
    with TestClient(app) as client:
        yield client


@pytest_asyncio.fixture()
async def user_token(test_client: TestClient) -> Callable:
    """Получение пользователя и его токена."""

    async def func(
        user_factory: Type[Union[UserFactory, OperatorFactory]] = UserFactory,
        *args: tuple,
        **kwargs: dict,
    ) -> Tuple[User, str]:
        user = await user_factory(**kwargs)
        path_for = "admin_obtain"
        if user_factory == UserFactory:
            path_for = "user_obtain"
            await AchievementFactory(user_id=user.id)
        response = test_client.post(
            test_client.app.url_path_for(path_for),
            json={
                "username": getattr(user, "verified_email", user.email),
                "password": "test1234",
                "re_token": "",
            },
        )
        assert "access" in response.json(), response.json()
        return user, f'JWT {response.json()["access"]}'

    return func


@pytest.fixture(autouse=True)
def _send_mail_fixture(monkeypatch_session: MonkeyPatch) -> None:
    """Заглушка для отправки почты."""
    monkeypatch_session.setattr(dream_views, "send_mail", AsyncMock())


@pytest.fixture(autouse=True)
def check_mature_content_mock(  # noqa PT004
    monkeypatch_session: MonkeyPatch,
) -> None:
    """Заглушка получения и проверки изображений."""
    monkeypatch_session.setattr(
        "dataset.rest.models.dream.UploadCloudModel.upload_file",
        Mock(return_value="https://test_image.jpg"),
    )
    monkeypatch_session.setattr(
        "dataset.rest.models.images.UploadCloudModel.check_mature_content",
        Mock(),
    )
    monkeypatch_session.setattr(
        "dataset.rest.models.dream.UploadCloudModel.validate_picture",
        Mock(return_value="https://test_image.jpg"),
    )


@pytest.fixture()
def get_translation_fixture(test_client: TestClient) -> Mock:  # noqa: PT004
    """Заглушка метода переводов."""
    service = Mock()
    service.get_translation = AsyncMock(
        return_value={"title": "test", "description": "test"}
    )
    with test_client.app.container.translate_service.override(service):
        yield service


@pytest.fixture()
def detect_language_fixture(test_client: TestClient) -> Mock:  # noqa: PT004
    """Заглушка метода определения языка."""
    service = Mock()
    service.detect_language = Mock(return_value="en")
    with test_client.app.container.translate_service.override(service):
        yield service


@pytest.fixture()
def detect_language_failed_fixture(
    test_client: TestClient,
) -> Mock:  # noqa: PT004
    """Заглушка метода определения языка возвращающая None."""
    service = Mock()
    service.detect_language = Mock(return_value=None)
    with test_client.app.container.translate_service.override(service):
        yield service
