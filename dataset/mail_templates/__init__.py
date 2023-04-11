"""Mail templates and helpers/classes related to them."""
import os
import re
from abc import abstractmethod
from typing import Dict, List

import trafaret as T  # noqa N812
from dependency_injector.wiring import Provide, inject
from fastapi import HTTPException
from graphene import ResolveInfo
from localization.service import LanguageService
from starlette import status
from trafaret import Trafaret

from dataset.core.constants import R_EMAIL_PATTERN
from dataset.core.container import Container
from dataset.core.mail import Template
from dataset.middlewares import request_var


class BaseTemplate(Template):
    """Base Template considers with multilingual configuration."""

    layout: str = "new-base"
    VAR_PATTERN = re.compile(
        r"(?P<open>[^{]{)(?P<code>[A-z]+)(?P<close>}[^}])", re.M
    )

    @inject
    def __init__(
        self,
        info: ResolveInfo,
        language: str = None,
        language_service: LanguageService = Provide[
            Container.localization.service
        ],
        **kwargs: Dict,
    ) -> None:
        """Init base template."""
        self.__info__ = info
        self.__language__ = language
        if "email" in kwargs and not kwargs["email"]:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST)
        self.languages_service = language_service
        super().__init__(**kwargs)

    async def subject(self) -> str:
        """Return set template subject."""
        title_key = (super().template_name()).replace("-", "_")
        return await self.languages_service.get_mail_text(
            f"title_{title_key}",
            self.__get_language__(),
            self.__template_variables__,
        )

    @abstractmethod
    def trafarret(self) -> Trafaret:
        """Template init."""
        return super().trafarret()

    @staticmethod
    def __base_path__() -> str:
        """Return base path of templates location."""
        return os.path.abspath(os.path.dirname(__file__))

    def __get_language__(self) -> str:
        """Get language."""
        return self.__language__ or request_var.get()["language"]

    def __read_html_template__(self) -> str:
        """Read html template."""
        path = os.path.join(
            self.__base_path__(), "html", f"{self.template_name()}.html"
        )

        with open(path, "r") as file:
            return file.read()

    def __read_html_layout__(self) -> str:
        """Read html layout."""
        path = os.path.join(
            self.__base_path__(), "html", "layouts", f"{self.layout}.html"
        )

        with open(path, "r") as file:
            return file.read()

    def __read_vars__(self, text: str) -> List[str]:
        """Read vars."""
        template_vars: List[str] = self.VAR_PATTERN.findall(text)

        if not template_vars:
            return []
        return list({v[1] for v in template_vars})

    async def build(self) -> None:
        """Build."""
        await super().build()

        template_vars = []
        content = self.__read_html_template__()
        layout = self.__read_html_layout__()

        template_vars += self.__read_vars__(content)
        template_vars += self.__read_vars__(layout)

        template_key = self.template_name().replace("-", "_")
        lang = self.__get_language__()
        context = {
            var: await self.languages_service.get_mail_text(
                f"body_{template_key}_{var}", lang
            )
            or await self.languages_service.get_mail_text(
                f"signature_{var}", lang
            )
            or ""
            for var in template_vars
        }

        def var_to_text(match: re.Match) -> str:
            groups = match.groupdict()
            code = groups["code"]
            open_text = groups["open"]
            close_text = groups["close"]

            return f'{open_text.replace("{", "")}{context[code]}{close_text.replace("}", "")}'

        self.__html__ = self.VAR_PATTERN.sub(
            var_to_text, layout.replace("{content}", content)
        )


class ShareReferLinkTemplate(BaseTemplate):
    """Шаблон письма с приглашением в Накомету и реферальной ссылкой."""

    __template_name__ = "share-refer-link"
    __template_tags__ = (
        "refer",
        "share",
    )

    def trafarret(self) -> Trafaret:
        """Метод для замены переменной на значение в шаблоне."""
        return T.Dict(
            {
                T.Key("refer_code"): T.String(),
                T.Key("name"): T.String(),
                T.Key("email"): T.Regexp(R_EMAIL_PATTERN),
            }
        )


class SendReferLinkTemplate(BaseTemplate):
    """Шаблон письма с реферальной ссылкой пользователя."""

    __template_name__ = "new-refer-activation"
    __template_tags__ = (
        "refer",
        "email",
    )

    def trafarret(self) -> Trafaret:
        """Метод для замены переменной на значение в шаблоне."""
        return T.Dict(
            {
                T.Key("refer_code"): T.String(),
                T.Key("name"): T.String(),
                T.Key("email"): T.Regexp(R_EMAIL_PATTERN),
            }
        )


class EmailConfirmationTemplate(BaseTemplate):
    """Template to confirm mail."""

    __template_name__ = "new-confirm-registration"
    __template_tags__ = (
        "confirm",
        "registration",
    )

    def trafarret(self) -> Trafaret:
        """Template init."""
        return T.Dict(
            {
                T.Key("email"): T.Regexp(R_EMAIL_PATTERN),
                T.Key("reset_token"): T.String(),
                T.Key("name"): T.String(),
            }
        )


class PasswordRecoveryTemplate(BaseTemplate):
    """Template to confirm mail."""

    __template_name__ = "new-password-recovery"
    __template_tags__ = (
        "recovery",
        "password",
    )

    def trafarret(self) -> Trafaret:
        """Template init."""
        return T.Dict(
            {
                T.Key("reset_token"): T.String(),
                T.Key("name"): T.String(),
                T.Key("email"): T.Regexp(R_EMAIL_PATTERN),
            }
        )


class OperatorPasswordResetTemplate(BaseTemplate):
    """Template to reset password."""

    __template_name__ = "new-password"
    __template_tags__ = ("new_password",)

    def trafarret(self) -> Trafaret:
        """Template init."""
        return T.Dict(
            {
                T.Key("new_password"): T.String(),
            }
        )


class PasswordChangedTemplate(BaseTemplate):
    """Template after user change password."""

    __template_name__ = "new-change-password"
    __template_tags__ = (
        "change",
        "password",
    )

    def trafarret(self) -> Trafaret:
        """Template init."""
        return T.Dict(
            {
                T.Key("name"): T.String(),
                T.Key("email"): T.Regexp(R_EMAIL_PATTERN),
            }
        )


class SupportRequestTemplate(BaseTemplate):
    """Template to request support."""

    __template_name__ = "new-support"
    __template_tags__ = "new-support"

    def trafarret(self) -> Trafaret:
        """Template init."""
        return T.Dict(
            {
                T.Key("email"): T.Regexp(R_EMAIL_PATTERN),
                T.Key("req"): T.String(),
                T.Key("title"): T.String(),
                T.Key("name"): T.String(),
            }
        )


class ChangeEmailTemplate(BaseTemplate):
    """Template to change mail."""

    __template_name__ = "email-change-request"
    __template_subject__ = "[ufandao] Change email"
    __template_tags__ = (
        "change",
        "email",
    )

    def trafarret(self) -> Trafaret:
        """Template init."""
        return T.Dict(
            {
                T.Key("email"): T.Regexp(R_EMAIL_PATTERN),
                T.Key("reset_token"): T.String(),
            }
        )


class NewTransferTemplate(BaseTemplate):
    """Template used to notify about new donation."""

    __template_name__ = "new-transfer"
    __template_tags__ = (
        "donation",
        "new",
        "incoming",
    )

    def trafarret(self) -> Trafaret:
        """Template init."""
        return T.Dict(
            {
                T.Key("name"): T.String(),
                T.Key("amount"): T.Int(gt=0),
                T.Key("certificate"): T.String(),
                T.Key("donation_id"): T.Int(gt=0),
                T.Key("donation_id"): T.Int(gt=0),
            }
        )


class TransferSentTemplate(BaseTemplate):
    """Template used to notify donator that confirmation was successful."""

    __template_name__ = "transfer-sent"
    __template_tags__ = (
        "donation",
        "new",
        "outgoing",
    )

    def trafarret(self) -> Trafaret:
        """Template init."""
        return T.Dict(
            {
                T.Key("donation_parent_product_id"): T.String(),
                T.Key("amount"): T.Int(gt=0),
                T.Key("order_product_id"): T.String(),
                T.Key("order_id"): T.Int(gt=0),
            }
        )


class TransferConfirmedTemplate(BaseTemplate):
    """Template used to notify donator that confirmation was successful."""

    __template_name__ = "transfer-confirmed"
    __template_tags__ = (
        "donation",
        "confirmed",
        "incoming",
    )

    def trafarret(self) -> Trafaret:
        """Template init."""
        return T.Dict(
            {
                T.Key("donation_parent_product_id"): T.String(),
                T.Key("amount"): T.Int(gt=0),
                T.Key("order_product_id"): T.String(),
            }
        )


class TransferAcceptedTemplate(BaseTemplate):
    """Template used to notify donator that confirmation was successful."""

    __template_name__ = "transfer-accepted"
    __template_tags__ = (
        "donation",
        "confirmed",
        "outgoing",
    )

    def trafarret(self) -> Trafaret:
        """Template init."""
        return T.Dict(
            {
                T.Key("donation_parent_product_id"): T.String(),
                T.Key("amount"): T.Int(gt=0),
                T.Key("order_product_id"): T.String(),
                T.Key("order_id"): T.Int(gt=0),
            }
        )


class TransferAutoConfirmedTemplate(BaseTemplate):
    """Template used to notify donator that confirmation was successful."""

    __template_name__ = "transfer-autoconfirmed"
    __template_tags__ = (
        "donation",
        "confirmed",
        "incoming",
    )

    def trafarret(self) -> Trafaret:
        """Template init."""
        return T.Dict(
            {
                T.Key("donation_parent_product_id"): T.String(),
                T.Key("amount"): T.Int(gt=0),
                T.Key("order_product_id"): T.String(),
                T.Key("donation_id"): T.Int(gt=0),
                T.Key("order_id"): T.Int(gt=0),
            }
        )


class TransferAutoAcceptedTemplate(BaseTemplate):
    """Template used to notify donator that confirmation was successful."""

    __template_name__ = "transfer-autoaccepted"
    __template_tags__ = (
        "donation",
        "confirmed",
        "outgoing",
    )

    def trafarret(self) -> Trafaret:
        """Template init."""
        return T.Dict(
            {
                T.Key("donation_parent_product_id"): T.String(),
                T.Key("amount"): T.Int(gt=0),
                T.Key("order_product_id"): T.String(),
                T.Key("order_id"): T.Int(gt=0),
                T.Key("donation_id"): T.Int(gt=0),
            }
        )


class ConfirmEmailLandingTemplate(BaseTemplate):
    """Template to confirm after create dreamform."""

    __template_name__ = "email-confirm-landing"
    __template_tags__ = (
        "confirm",
        "landing",
    )

    def trafarret(self) -> Trafaret:
        """Template init."""
        return T.Dict(
            {
                T.Key("email"): T.Regexp(R_EMAIL_PATTERN),
                T.Key("code"): T.String(),
                T.Key("name"): T.String(),
                T.Key("lang"): T.String(),
            }
        )


class ConfirmEmailLandingRegTemplate(BaseTemplate):
    """Template to confirm after create dreamform for reg user."""

    __template_name__ = "email-confirm-landing-reg"
    __template_tags__ = (
        "confirm",
        "landing",
        "reg",
    )

    def trafarret(self) -> Trafaret:
        """Template init."""
        return T.Dict(
            {
                T.Key("email"): T.Regexp(R_EMAIL_PATTERN),
                T.Key("code"): T.String(),
                T.Key("name"): T.String(),
                T.Key("lang"): T.String(),
            }
        )


class DonateNotificationTemplate(BaseTemplate):
    """Template to donate notification."""

    __template_name__ = "donate-notification"
    __template_tags__ = (
        "donate",
        "notification",
    )

    def trafarret(self) -> Trafaret:
        """Template init."""
        return T.Dict(
            {
                T.Key("email"): T.Regexp(R_EMAIL_PATTERN),
                T.Key("name"): T.String(),
            }
        )


class NewMessageChatNotification(BaseTemplate):
    """Шаблон для уведомления о новом сообщении."""

    __template_name__ = "new_message_chat_notification"
    __template_tags__ = (
        "chat",
        "message",
        "notification",
    )

    def trafarret(self) -> Trafaret:
        """Template init."""
        return T.Dict(
            {
                T.Key("email"): T.Regexp(R_EMAIL_PATTERN),
                T.Key("name"): T.String(),
            }
        )
