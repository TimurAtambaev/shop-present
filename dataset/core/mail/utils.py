"""Функции отправки писем."""
import random

from dependency_injector.wiring import Provide, inject
from localization.service import LanguageService

from dataset.config import settings
from dataset.core.container import Container
from dataset.core.log import LOGGER
from dataset.core.mail import Mailer, Message, Template
from dataset.middlewares import request_var


@inject
async def get_letter_from(
    lang_code: str,
    language_service: LanguageService = Provide[
        Container.localization.service
    ],
) -> str:
    """Подготовка имени отправителя письма."""
    mail_postfix = (
        settings.MAIL_POSTFIX.get(lang_code)
        or settings.MAIL_POSTFIX[settings.DEFAULT_LANGUAGE]
    )
    default_names = {"ru": "Катя", "en": "Bella"}
    names = await language_service.get_version(
        [settings.LETTER_FROM_NAMES], lang_code
    )
    names = list(names.get(settings.LETTER_FROM_NAMES, {}).values())
    if not names:
        lang_code = lang_code if lang_code in ("ru", "en") else "en"
        return f"{default_names[lang_code]} {mail_postfix}"
    return f"{random.choice(names)} {mail_postfix}"


@inject
async def send_mail(
    recipient: str,
    template: Template,
    language: str = None,
    mailer: Mailer = Provide[Container.mailer],
) -> str:
    """Send email message."""
    lang = language or request_var.get()["language"]
    letter_from = await get_letter_from(lang)
    message = Message(recipient, template, letter_from)

    result = await mailer.send(message)

    LOGGER.debug("Mail sent result: %s", result)

    return result
