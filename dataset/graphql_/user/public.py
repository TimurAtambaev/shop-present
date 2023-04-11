"""Graphql type, objects, queries, mutations and etc related to user For Users."""
import json
from typing import Dict, Union

import graphene
import sqlalchemy as sa
import trafaret as T  # noqa N812
from graphene import ResolveInfo
from starlette.responses import Response
from trafaret import Trafaret

from dataset.core.auth import create_reset_token
from dataset.core.constants import R_EMAIL_PATTERN
from dataset.core.graphql import (
    DatabaseHelper,
    InputValidationMixin,
    anonymous,
    app_from_info,
    authorized_only,
    send_ticket,
)
from dataset.core.mail.utils import send_mail
from dataset.graphql_.user.utils import is_email_exists
from dataset.integrations.aws import AWS as AWSIntegration  # noqa N811
from dataset.mail_templates import (
    PasswordRecoveryTemplate,
    SupportRequestTemplate,
)
from dataset.middlewares import request_var
from dataset.migrations import db
from dataset.rest.views.achievement import create_achievement
from dataset.rest.views.dream import create_dream_draft
from dataset.rest.views.event_tasks import event_new_person
from dataset.rest.views.utils import send_notification
from dataset.tables.dream import Dream, DreamStatus
from dataset.tables.dream_form import DreamForm
from dataset.tables.event import TypeEvent
from dataset.tables.user import User
from dataset.tables.user import User as GinoUser


class ResetTokenInput(graphene.InputObjectType, InputValidationMixin):
    """Input for reset token."""

    reset_token = graphene.String(required=True)

    @classmethod
    def trafaret(cls) -> Trafaret:
        """Template init."""
        return T.Dict({T.Key("reset_token"): T.String()})


class RestorePasswordInput(graphene.InputObjectType, InputValidationMixin):
    """Input for reset token."""

    email = graphene.String(required=True)
    lang = graphene.String(required=False)

    @classmethod
    def trafaret(cls) -> Trafaret:
        """Template init."""
        return T.Dict(
            {
                T.Key("email"): T.Regexp(R_EMAIL_PATTERN),
                T.Key("lang", optional=True): T.String(),
            }
        )


class UserEmailConfirmationMutation(graphene.Mutation):
    """Mutation to handle user email confirmation."""

    class Input:
        """User auth input."""

        input = graphene.Argument(ResetTokenInput, required=True)  # noqa A003

    status = graphene.String(required=False)

    async def mutate(
        self,
        info: ResolveInfo,
        input: Dict,  # noqa A002
    ) -> Union[dict, Response]:
        """Handle token authorization."""
        app = app_from_info(info)
        redis = app.state.redis
        data = await ResetTokenInput.validate(input)
        language_service = app.localization_container.service()

        user_data = await redis.get(data.get("reset_token"))

        if not user_data:
            error = await language_service.get_error_text(
                "invalid_reset_token", request_var.get()["language"]
            )
            raise RuntimeError(error)

        user_data = json.loads(user_data)

        if await is_email_exists(user_data["email"]):
            error = await language_service.get_error_text(
                "email_exist", request_var.get()["language"]
            )
            raise RuntimeError(error)

        user_data["verified_email"] = user_data["email"]

        async with db.transaction():
            try:
                new_user = await GinoUser.create(**user_data)
            except Exception as exc:
                raise RuntimeError(str(exc))

            if data.get("referer"):
                user = await User.query.where(
                    User.refer_code == data.get("referer")
                ).gino.first()
                if user:
                    await event_new_person(
                        user=user,
                        sender=new_user,
                        type_event=TypeEvent.FRIEND.value,
                    )
                    await send_notification(redis, user.id)
            await create_achievement(new_user.id)

            dream_form = await DreamForm.query.where(
                DreamForm.email == new_user.email
            ).gino.first()
            try:
                await create_dream_draft(dream_form, new_user)
            except Exception as exc:
                logger.error(exc)  # noqa G200
        return {"status": True}


class UserRestorePasswordMutation(graphene.Mutation):
    """Mutation to handle user password restoring."""

    class Input:
        """User restore password input."""

        input = graphene.Argument(  # noqa A003
            RestorePasswordInput, required=True
        )

    result = graphene.String(required=True)

    @anonymous
    async def mutate(
        self,
        info: ResolveInfo,
        input: Dict,  # noqa A002
        user: object,
    ) -> dict:
        """Handle token authorization."""
        data = await RestorePasswordInput.validate(input)

        email: str = data.get("email")

        user = await GinoUser.query.where(
            GinoUser.verified_email == email
        ).gino.first()
        if not user:
            return {"result": "OK"}

        reset_token, valid_till = create_reset_token()
        await (
            user.update(
                reset_token=reset_token, reset_token_valid_till=valid_till
            ).apply()
        )

        await send_mail(
            email,
            PasswordRecoveryTemplate(
                info,
                name=user.name,
                email=user.verified_email,
                reset_token=reset_token,
                language=user.language,
            ),
            user.language,
        )

        return {"result": "OK"}


class Result(graphene.ObjectType):
    """Graphql model for result."""

    result = graphene.Boolean()


class SupportRequestInput(graphene.InputObjectType, InputValidationMixin):
    """Support Request input model."""

    title = graphene.String(required=True)
    text = graphene.String(required=True)

    @classmethod
    def trafaret(cls) -> Trafaret:
        """Template init."""
        return T.Dict(
            {
                T.Key("title"): T.String(min_length=3),
                T.Key("text"): T.String(min_length=3),
            }
        )


class SupportRequest(graphene.Mutation):
    """Support Request mutation."""

    class Input:
        """Support Request input."""

        input = graphene.Argument(  # noqa A003
            SupportRequestInput, required=True
        )

    request_id = graphene.String(required=True)

    @staticmethod
    async def proceed_donation(info: ResolveInfo, user_id: int) -> (str, str):
        """Proceeds donation search if one is provided."""
        dream_data = await DatabaseHelper.fetch_one(
            info,
            sa.select(
                [Dream.id],
                sa.and_(
                    Dream.user_id == user_id,
                    Dream.status == DreamStatus.ACTIVE.value,
                ),
            ),
        )
        if not dream_data:
            dream_data = (0,)

        return dream_data[0]

    @authorized_only
    async def mutate(
        self,
        info: ResolveInfo,
        input: dict,  # noqa A002
        _user: object,
    ) -> dict:
        """Support Request mutation resolver."""
        data = await SupportRequestInput.validate(input)
        dream_id = await SupportRequest.proceed_donation(info, _user.id)

        user_email = _user.verified_email
        if user_email is None:
            user_email = _user.email

        title = data.get("title")
        text = data.get("text")
        zendesk_message = f"{title} {text}"
        request_id = await send_ticket(info, _user, zendesk_message, dream_id)

        await send_mail(
            user_email,
            SupportRequestTemplate(
                info,
                name=_user.name,
                email=user_email,
                title=title,
                req=text,
            ),
            _user.language,
        )

        return {"request_id": request_id}
