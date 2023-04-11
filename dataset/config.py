"""Модуль с настройками проекта."""
import os
from os import environ
from typing import Any, Optional, Union
from urllib.parse import urlparse

import argon2
from pydantic import BaseSettings, PostgresDsn, validator


class Settings(BaseSettings):
    """Класс настроек."""

    JWT_KEY: str
    JWT_IMRIX_KEY: str
    ACCESS_LIFETIME: int = 60 * 5
    REFRESH_LIFETIME: int = 60 * 60 * 24
    RESET_LIFETIME: int = 60 * 60 * 24
    NEED_TO_DONATE_NUM: int = 4
    MINIMAL_DONATION: int = 10
    MAX_DONATION: int = 40
    MAX_DREAM_COUNT: int = 20
    FILE_SIZE: int = 500
    MAX_FILE_SIZE: int = 25_000_000
    DREAM_LIMIT: int = 5_000
    CHARITY_DREAM_LIMIT: int = 1_000_000
    MESSAGES_UPLOAD: int = 10
    FIRST_DONATION = 1
    AGE: int = 6570
    PHONE_NUMBER_MIN: int = 11
    PHONE_NUMBER_MAX: int = 20
    LEN_PASSWORD: int = 8
    LEN_NAME: int = 1
    PUBLIC_DOMAIN: str = ""
    PAYPAL_CLIENT_ID: str = (
        "AWzrdrAbCur6M_7a4itsgBDxEprLVKtaeTBNNub9Wlrw8lwh"
        "OqqsdaAGUWNDqp1KrcqyxRYVMjlujLVk"
    )
    PAYPAL_CLIENT_SECRET: str = (
        "EGgWq9l6vjRtGR0Z6DVz06tZnb9yvbWFGjECVa6gUjEI"
        "8aZXM7qvVUt_sCq26Ztq44Xw5KDOqcLK20Oh"
    )
    DREAM_MAKER_INVITATIONS: int = 10
    TIME_INTERVAL: int = 0.5
    PAYPAL_RETURN_URL: str = ""
    PAYPAL_CANCEL_URL: str = ""

    secret_key: str = environ.get("GS_SECRET_KEY", "")
    WITH_COMISSION: float = 1.05
    PAYPAL_PROD: bool = False
    HASHER = argon2.PasswordHasher()
    WEBHOOK_ID: str = "6UK274595S817700M"
    RECAPTCHA_SECRET_KEY_REGISTER: str = environ.get(
        "RECAPTCHA_SECRET_KEY_REGISTER", ""
    )
    RECAPTCHA_SECRET_KEY_LANDING: str = environ.get(
        "RECAPTCHA_SECRET_KEY_LANDING", ""
    )
    RECAPTCHA_API_SERVER: str = (
        "https://www.google.com/recaptcha/api/" "siteverify"
    )
    NSFW_CENSOR_THRESHOLD: float = 0.35
    UNREAD_EVENTS: str = "unread_events"
    UNREAD_MESSAGES: str = "unread_messages"
    UNCONFIRMED_DONATIONS: str = "unconfirmed_donations"
    ZENDESK_IS_TEST: bool = False
    ZENDESK_SUBDOMAIN: str = "ufandao"
    ZENDESK_EMAIL: str = "support@ufandao.com"
    ZENDESK_TOKEN: str = environ.get("ZENDESK_TOKEN", "")
    GS_ENVIRONMENT: str = "dev"
    API_KEY_CURRENCY: str = environ.get("API_KEY_CURRENCY", "")
    CURRENCY_API: str = "https://free.currconv.com/api/v7/convert"

    NOTIFICATION_EVENTS: tuple = (
        UNREAD_EVENTS,
        UNREAD_MESSAGES,
        UNCONFIRMED_DONATIONS,
    )
    LETTER_FROM: str = "letter_from"
    LETTER_FROM_NAMES: str = "letter_from_names"
    MAIL_POSTFIX: dict = {
        "ru": "из Ufandao <no-reply@ufandao.com>",
        "en": "from Ufandao <no-reply@ufandao.com>",
    }
    DREAM_MAKER_RISE_LIMIT: int = 3
    POPULAR_CATEGORY_ID: int = 0

    ALEMBIC_PATH: str = "/etc/dataset/migrations.ini"
    TOKEN: str = "9b5af411251e6a1676554ac402429ea9#"
    EURO_ID: int = 1
    EURO_CODE: str = "EUR"
    EURO_SYMBOL: str = "€"
    EURO_NAME: str = "Euro"
    FINANCE_RATIO: int = 100
    EMAIL_CODE_LIFETIME: int = 60 * 60 * 24
    RU_COUNTRIES: list[int] = [19, 129]  # Belarus, Russia
    DREAM_START_VALUE: int = 0
    PAYPAL_CURRENCIES: list = [
        "AUD",
        "BRL",
        "CAD",
        "CNY",
        "CZK",
        "DKK",
        "EUR",
        "HKD",
        "HUF",
        "ILS",
        "JPY",
        "MYR",
        "MXN",
        "TWD",
        "NZD",
        "NOK",
        "PHP",
        "PLN",
        "GBP",
        "RUB",
        "SGD",
        "SEK",
        "CHF",
        "THB",
        "USD",
    ]
    AWS_DEFAULT_REGION: str = ""
    AWS_DOMAIN: str = "digitaloceanspaces.com"
    SHORT_DESCRIPTION_LEN: int = 256
    NUMBER_OF_ATTEMPTS: int = 3
    HOURS_TO_ATTEMPTS: int = 24

    SENTRY_DSN: str = None
    APP_VERSION: str = "dev"
    LEN_LANDING_DREAMS: int = 30
    DREAM_CLOSED_SHOW_TIME: int = 168
    TIME_ORDER_DONATIONS_SUM: int = 48
    LEN_DREAMS_GROUP_LANDING: int = 3
    LEN_CLOSED_DREAMS: int = 10
    DREAMS_LIST_REFRESH_TERM: int = 3600
    LEN_CRYPTO_TOKEN: int = 40
    LEN_CRYPTO_NETWORK: int = 40
    LEN_CRYPTO_ADDRESS: int = 80
    LIMIT_REFERAL_LEVEL: int = 4
    CACHE_TIME_LIMIT: int = 3600 * 24 * 7
    DEFAULT_AVATAR: str = (
        "https://storage.googleapis.com/ufandao-content/avatar_placeholder.png"
    )
    LEN_DREAM_TITLE: int = 50

    BASE_DIR: str = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    TESTING: bool = False
    PYTEST_XDIST_WORKER: str = ""
    PYTEST_XDIST_TESTRUNUID: str = ""

    # Database settings
    DB_USER: str = "postgres"
    DB_PASS: str = "dataset"
    DB_HOST: str = "postgres"
    DB_PORT: int = 5432
    DB_NAME: str = "dataset"
    DB_URI: PostgresDsn = None

    @validator("DB_NAME", pre=True, allow_reuse=True)
    def get_actual_db_name(
        cls, v: Optional[str], values: dict[str, Any]
    ) -> str:
        """Получение названия базы, для тестов генерит отдельное название."""
        test_postfix = f"_test_{values.get('PYTEST_XDIST_WORKER')}"

        if values.get("TESTING") and not v.endswith(test_postfix):
            v += test_postfix
        return v

    @validator("DB_URI", pre=True, allow_reuse=True)
    def assemble_db_connection(
        cls, v: Optional[str], values: dict[str, Any]
    ) -> str:
        """
        Собираем коннект для подключения к БД.

        :param v: value
        :param values: Dict values
        :return: PostgresDsn
        """
        if isinstance(v, str):
            conn = urlparse(v)
            return PostgresDsn.build(
                scheme=conn.scheme,
                user=conn.username,
                password=conn.password,
                host=conn.hostname,
                port=str(conn.port),
                path=conn.path,
            )

        return PostgresDsn.build(
            scheme="postgresql",
            user=values["DB_USER"],
            password=values["DB_PASS"],
            host=values["DB_HOST"],
            port=str(values["DB_PORT"]),
            path=f"/{values['DB_NAME']}",
        )

    REDIS_DRIVER: str = "redis"
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 1
    REDIS_PASS: str
    GOOGLE_CLOUD_PROJECT_ID: str = ""
    GOOGLE_CLOUD_LOCATION: str = ""
    DEFAULT_LANGUAGE: str = "en"
    CATEGORIES_BLOCK: str = "categories"
    IMRIX_HOST: str = ""
    ERRORS_BLOCK: str = "errors"
    MAIL_BLOCK: str = "mail"
    LANDING_BLOCK: str = "numbersBlock"
    LK_BLOCK: str = "marketingMaterialPage"
    LANDING_DOMAIN: str = ""
    LK_DOMAIN: str = "my.ufandao"
    EMAIL_PATTERN: str = (
        "(^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$)"  # noqa W605
    )
    HEADER_COUNRTY_ID: int = 0
    HEADER_COUNRTY_TITLE: dict = {
        "en": "All countries",
        "ru": "Все страны",
        "fr": "Tous les pays",
        "es": "Todos los países",
        "pt": "Todos os países",
        "it": "Tutti i paesi",
        "de": "Alle Länder",
        "zh": "所有国家",
    }
    GS_MAILGUN: str
    GS_APP_DOMAIN: str
    SUPPORT_EMAIL: str = "support@ufandao.com"
    GS_LISTEN: str = "http://0.0.0.0:8080"

    AWS_ACCESS_KEY_ID: str
    AWS_SECRET_ACCESS_KEY: str
    AWS_BUCKET: str
    AWS_ENDPOINT: str

    ADMIN_CORS: Union[set[str], list[str]]
    PUBLIC_CORS: Union[set[str], list[str]]

    @validator("ADMIN_CORS", "PUBLIC_CORS", pre=True, allow_reuse=True)
    def validate_cors(
        cls, v: Optional[str], values: dict[str, Any]
    ) -> set[str]:
        """Валидация полей с корсами."""
        return set(v.split(","))


settings = Settings()
