"""Контейнер зависимостей проекта."""
from dependency_injector import containers, providers
from gino import Gino
from localization.container import Container as LocalizationContainer
from sqlalchemy import Table

from dataset.core import init_redis_pool
from dataset.integrations.mailgun import Mailgun
from dataset.integrations.zendesk import ZenDesk
from dataset.services.review import ReviewService
from dataset.services.translations import TranslateService


class Container(containers.DeclarativeContainer):
    """Основной контейнер с зависимостями."""

    config = providers.Configuration()
    db = providers.Dependency(instance_of=Gino)
    lang_table = providers.Dependency(instance_of=Table)
    redis = providers.Resource(
        init_redis_pool,
        driver=config.REDIS_DRIVER,
        db=config.REDIS_DB,
        host=config.REDIS_HOST,
        port=config.REDIS_PORT,
        password=config.REDIS_PASS,
    )
    localization = providers.Container(
        LocalizationContainer, db=db, lang_table=lang_table
    )

    review_service = providers.Factory(ReviewService)

    translate_service = providers.Singleton(TranslateService, redis=redis)
    mailer = providers.Singleton(
        Mailgun,
        dsn=config.GS_MAILGUN,
        public_domain=config.PUBLIC_DOMAIN,
        app_domain=config.GS_APP_DOMAIN,
        support_email=config.SUPPORT_EMAIL,
        landing_domain=config.LANDING_DOMAIN,
    )

    zendesk = providers.Singleton(
        ZenDesk,
        email=config.ZENDESK_EMAIL,
        token=config.ZENDESK_TOKEN,
        subdomain=config.ZENDESK_SUBDOMAIN,
        is_test=config.ZENDESK_IS_TEST,
    )
