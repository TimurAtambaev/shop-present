"""App routes declaration."""
import re

from aiohttp import hdrs
from fastapi import APIRouter, FastAPI
from graphql.execution.executors.asyncio import AsyncioExecutor
from starlette.graphql import GraphQLApp
from starlette.middleware.cors import CORSMiddleware

from dataset.config import settings
from dataset.rest.views import (
    achievement,
    admin,
    auth,
    category,
    chat,
    country,
    currency,
    donation,
    dream,
    event,
    exchange_rate,
    facebook,
    hooks,
    news,
    notifications,
    payment,
    profile,
    referal,
    registration,
    review,
    test,
    users_export,
)
from dataset.schema import ADMIN_SCHEMA, PUBLIC_SCHEMA

ADMIN_URL = "/g/1.0"
PUBLIC_URL = "/api/g/1.0"
TEST_INTEGRATION_URL = "/test/integration/1.0"
REST_ADMIN_URL = re.compile("/api/admin/")

USERS_EXPORT_URL = r"/users/export"

PUBLIC_SUBSCRIPTION_URL = r"/{lang:([a-z][a-z]/|)}api/g/1.0/ws"

ADMIN_URL_PATTERN = re.compile("^/((?P<lang>[a-z]{2})/|)g/1.0")
GQL_PUBLIC_URL_PATTERN = re.compile("^/((?P<lang>[a-z]{2})/|)api/g/1.0")
REST_PUBLIC_URL_PATTERN = re.compile("^/((?P<lang>[a-z]{2})/|)api/(?!admin).*")


def init_routes(app: FastAPI) -> None:
    """Routes initialization."""
    app.add_middleware(
        CORSMiddleware,
        allow_origins={*settings.PUBLIC_CORS, *settings.ADMIN_CORS},
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=(hdrs.CONTENT_TYPE, hdrs.AUTHORIZATION),
    )
    main_router = APIRouter(prefix="/api")

    main_router.include_router(profile.router, tags=["profile"])
    main_router.include_router(donation.router, tags=["donation"])
    main_router.include_router(payment.router, tags=["payment"])
    main_router.include_router(registration.router, tags=["registration"])
    main_router.include_router(dream.router, tags=["dream"])
    main_router.include_router(facebook.router, tags=["facebook"])
    main_router.include_router(auth.router, tags=["auth"])
    main_router.include_router(category.router, tags=["category"])
    main_router.include_router(hooks.router, tags=["hooks"])
    main_router.include_router(referal.router, tags=["referal"])
    main_router.include_router(achievement.router, tags=["achievement"])
    main_router.include_router(chat.router, tags=["chat"])
    main_router.include_router(event.router, tags=["event"])
    main_router.include_router(users_export.router, tags=["users_export"])
    main_router.include_router(news.router, tags=["news"])
    main_router.include_router(notifications.router, tags=["notifications"])
    main_router.include_router(country.router, tags=["country"])
    main_router.include_router(exchange_rate.router, tags=["exchange_rate"])
    main_router.include_router(currency.router, tags=["currency"])
    main_router.include_router(review.router, tags=["review"])
    main_router.include_router(admin.router, prefix="/admin", tags=["admin"])

    if settings.GS_ENVIRONMENT != "prod":
        main_router.include_router(test.router, tags=["test"])

    app.include_router(main_router)

    app.add_route(
        ADMIN_URL,
        GraphQLApp(schema=ADMIN_SCHEMA, executor_class=AsyncioExecutor),
    )
    app.add_route(
        PUBLIC_URL,
        GraphQLApp(schema=PUBLIC_SCHEMA, executor_class=AsyncioExecutor),
    )
