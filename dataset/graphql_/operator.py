"""Operator related grapphql objects, queries and mutations."""
import re
import secrets
from typing import Dict

import graphene
import sqlalchemy as sa
import trafaret as T  # noqa N812
from aiohttp.web_exceptions import HTTPInternalServerError
from argon2.exceptions import VerifyMismatchError
from asyncpg import UniqueViolationError
from gino.transaction import GinoTransaction
from graphql import ResolveInfo
from sqlalchemy import desc, func, select
from trafaret import Trafaret

from dataset.config import settings
from dataset.core.constants import R_EMAIL_PATTERN
from dataset.core.graphql import (
    DatabaseHelper,
    IDInputType,
    InputValidationMixin,
    ListInputType,
    ListResultType,
    PasswordIDInputType,
    app_from_info,
    authorized_only,
    require_superuser,
)
from dataset.core.mail.utils import send_mail
from dataset.mail_templates import OperatorPasswordResetTemplate
from dataset.middlewares import request_var
from dataset.migrations import db
from dataset.tables.operator import Operator as OperatorModel


class Operator(graphene.ObjectType):
    """GraphQL operator model."""

    id = graphene.Int()  # noqa A003
    name = graphene.String()
    email = graphene.String()
    is_superuser = graphene.Boolean()
    is_active = graphene.Boolean()
    is_content_manager = graphene.Boolean()
    created_at = graphene.DateTime()
    updated_at = graphene.DateTime()


class OperatorSearchInput(ListInputType):
    """Class describes input data that can be used for search query."""

    query = graphene.String()
    is_active = graphene.Boolean()
    is_superuser = graphene.Boolean()

    @classmethod
    def trafaret(cls) -> Trafaret:
        """Template init."""
        return super().trafaret() + T.Dict(
            {
                T.Key("query"): T.String(allow_blank=True, max_length=128),
                T.Key("is_active", optional=True): T.Bool(),
                T.Key("is_superuser", optional=True): T.Bool(),
            }
        )


class OperatorsList(ListResultType):
    """Object to display list of operators in result."""

    result = graphene.List(Operator)


class OperatorCreateInput(graphene.InputObjectType, InputValidationMixin):
    """Input for Operator Create mutation."""

    name = graphene.String()
    email = graphene.String()
    is_active = graphene.Boolean()
    is_superuser = graphene.Boolean()
    is_content_manager = graphene.Boolean()
    password = graphene.String()

    @classmethod
    def trafaret(cls) -> Trafaret:
        """Template init."""
        return T.Dict(
            {
                T.Key("name"): T.String(min_length=3),
                T.Key("email"): T.Regexp(R_EMAIL_PATTERN, re.I),
                T.Key("is_active", default=True): T.Bool(),
                T.Key("is_superuser", default=False): T.Bool(),
                T.Key("is_content_manager", default=False): T.Bool(),
                T.Key("password"): T.String(min_length=8),
            }
        )


class OperatorUpdateInput(graphene.InputObjectType, InputValidationMixin):
    """Input for Operator Update mutation."""

    id = graphene.Int(required=True)  # noqa A003
    name = graphene.String(required=False)
    email = graphene.String(required=False)

    @classmethod
    def trafaret(cls) -> Trafaret:
        """Template init."""
        return T.Dict(
            {
                T.Key("id", optional=False): T.Int(),
                T.Key("name", optional=True): T.String(
                    min_length=3, allow_blank=False
                ),
                T.Key("email", optional=True): T.Regexp(R_EMAIL_PATTERN, re.I),
            }
        )


class OperatorPromotionInput(PasswordIDInputType):
    """Input for promotion and demotion mutations."""


class OperatorContentManagerInput(PasswordIDInputType):
    """Input for set unset operator as content manager."""


class OperatorBlockingInput(PasswordIDInputType):
    """Input for block and unblock mutations."""


class ResetPasswordInput(graphene.InputObjectType, InputValidationMixin):
    """Input for reset token."""

    id = graphene.Int(required=True)  # noqa A003

    @classmethod
    def trafaret(cls) -> Trafaret:
        """Template init."""
        return T.Dict(
            {
                T.Key("id", optional=False): T.Int(),
            }
        )


class OperatorQuery(graphene.ObjectType):
    """Operators graphql_ queries."""

    me = graphene.Field(Operator, description="Operators profile")
    operators = graphene.Field(
        OperatorsList,
        input=graphene.Argument(OperatorSearchInput),
        description="List of operators",
    )
    operator = graphene.Field(
        Operator,
        input=graphene.Argument(IDInputType),
        description="Get operator by ID",
    )

    @authorized_only
    async def resolve_me(self, info: ResolveInfo) -> Operator:
        """Return authorized operator profile."""
        return info.context.get("request", {}).get("user")

    @require_superuser
    async def resolve_operators(
        self,
        info: ResolveInfo,
        input: Dict,  # noqa A002
    ) -> Dict:
        """Resolve search of operators by string and parameters."""
        await OperatorSearchInput.validate(input)

        query = input.get("query", "").lower()
        is_active = input.get("is_active")
        is_superuser = input.get("is_superuser")
        limit = input.get("limit", 20)
        offset = input.get("offset", 0)

        whereclause = []

        if is_active is not None:
            whereclause.append(OperatorModel.is_active == is_active)

        if is_superuser is not None:
            whereclause.append(OperatorModel.is_superuser == is_superuser)

        if query:
            whereclause.append(
                sa.or_(
                    func.lower(OperatorModel.name).like(f"%{query}%"),
                    func.lower(OperatorModel.email).like(f"%{query}%"),
                )
            )

        whereclause = sa.and_(*whereclause)

        count = await DatabaseHelper.fetch_one(
            info, select([func.count(OperatorModel.id)]).where(whereclause)
        )
        result = await DatabaseHelper.fetch_all(
            info,
            select([OperatorModel])
            .where(whereclause)
            .offset(offset)
            .limit(limit)
            .order_by(desc(OperatorModel.id))
            .group_by(OperatorModel.id),
        )

        return {"count": count[0], "result": result}

    @require_superuser
    async def resolve_operator(
        self,
        info: ResolveInfo,
        input: Dict,  # noqa A002
    ) -> Operator:
        """Resolve returning operator by id."""
        await IDInputType.validate(input)

        return await OperatorModel.query.where(
            OperatorModel.id == input.get("id")
        ).gino.first()


class OperatorCreate(graphene.Mutation):
    """Mutation to create new operator."""

    class Input:
        """Input description."""

        input = graphene.Argument(  # noqa A003
            OperatorCreateInput, required=True
        )

    operator = graphene.Field(Operator, required=True)

    @require_superuser
    async def mutate(
        self,
        info: ResolveInfo,
        input: Dict,  # noqa A002
        user: object,
    ) -> Dict:
        """Operator creation."""
        data = await OperatorCreateInput.validate(input)

        email = data["email"] = data.get("email").lower()
        data["password"] = settings.HASHER.hash(data.get("password"))
        data["created_by_operator_id"] = user.id
        data["updated_by_operator_id"] = user.id

        if (
            data["is_superuser"]
            == data["is_content_manager"]
            == True  # noqa E712
        ):
            data["is_content_manager"] = False

        exists = await DatabaseHelper.scalar(
            info,
            sa.exists(
                select(
                    [OperatorModel.id],
                    func.lower(OperatorModel.email) == email.lower(),
                )
            ).select(),
        )

        if exists:
            raise RuntimeError(f"Operator with email {email} exists")

        _tx: GinoTransaction
        async with (await DatabaseHelper.transaction(info)) as _tx:
            conn = _tx.connection
            try:
                await conn.status(
                    OperatorModel.insert().values(
                        **data,
                    )
                )
            except UniqueViolationError as error_exc:
                raise RuntimeError(
                    f"Operator with email {email} exists"
                ) from error_exc

            return {
                "operator": await conn.first(
                    sa.select([OperatorModel]).where(
                        OperatorModel.id
                        == sa.select([sa.func.currval("operator_id_seq")])
                    )
                )
            }


class OperatorUpdate(graphene.Mutation):
    """Mutation to update operator."""

    class Input:
        """Mutation input description."""

        input = graphene.Argument(  # noqa A003
            OperatorUpdateInput, required=True
        )

    operator = graphene.Field(Operator, required=True)

    @require_superuser
    async def mutate(
        self,
        info: ResolveInfo,
        input: Dict,  # noqa A002
        user: object,
    ) -> Dict:
        """Mutation resolver."""
        data = await OperatorUpdateInput.validate(input)

        data["updated_by_operator_id"] = user.id
        data["updated_at"] = sa.func.now()

        operator_id = data.pop("id")

        exists = await DatabaseHelper.scalar(
            info,
            query=sa.exists(
                sa.select([OperatorModel.id], OperatorModel.id == operator_id)
            ).select(),
        )

        if not exists:
            raise RuntimeError(
                f"Operator with id {operator_id} " f"doesn't exist"
            )

        operator = await OperatorModel.query.where(
            OperatorModel.id == operator_id
        ).gino.first()

        try:
            await (operator.update(**data).apply())
        except UniqueViolationError as error_exc:
            email = data.get("email")
            raise RuntimeError(
                f"Operator with email {email} exists"
            ) from error_exc

        return {
            "operator": (
                await OperatorModel.query.where(
                    OperatorModel.id == operator_id
                ).gino.first()
            )
        }


class OperatorPromote(graphene.Mutation):
    """Mutation to handle operator promotion to superuser."""

    class Input:
        """Mutation input. Requires id and current operator password."""

        input = graphene.Argument(  # noqa A003
            OperatorPromotionInput, required=True
        )

    operator = graphene.Field(Operator, required=True)

    @require_superuser
    async def mutate(
        self,
        info: ResolveInfo,
        input: Dict,  # noqa A002
        user: object,
    ) -> Dict:
        """Operator promotion handler."""
        data = await OperatorPromotionInput.validate(input)

        operator_id = data.get("id")
        password = data.get("password")

        try:
            settings.HASHER.verify(user.password, password)
        except VerifyMismatchError as error_exc:
            language_service = app_from_info(
                info
            ).localization_container.service()
            error = await language_service.get_error_text(
                "invalid_password", request_var.get()["language"]
            )
            raise RuntimeError(error) from error_exc

        target_op = await OperatorModel.query.where(
            OperatorModel.id == operator_id
        ).gino.first()

        if not target_op:
            raise RuntimeError(
                f"Operator with id {operator_id} does not exist"
            )

        if target_op.is_superuser:
            raise RuntimeError(f"Operator with id {operator_id} is superuser")

        _tx: GinoTransaction
        async with db.transaction() as _tx:  # noqa F841
            operator = (
                await OperatorModel.query.where(
                    OperatorModel.id == operator_id
                )
                .where(OperatorModel.is_superuser == False)  # noqa E712
                .gino.first()
            )
            await operator.update(
                is_superuser=True,
                updated_by_operator_id=user.id,
                updated_at=sa.func.now(),
            ).apply()

            return {"operator": operator}


class OperatorDemote(graphene.Mutation):
    """Mutation to handle operator demotion to regular operator."""

    class Input:
        """Mutation input. Requires id and current operator password."""

        input = graphene.Argument(  # noqa A003
            OperatorPromotionInput, required=True
        )

    operator = graphene.Field(Operator, required=True)

    @require_superuser
    async def mutate(
        self,
        info: ResolveInfo,
        input: Dict,  # noqa A002
        user: object,
    ) -> Dict:
        """Operator demotion handler."""
        data = await OperatorPromotionInput.validate(input)

        operator_id = data.get("id")
        password = data.get("password")

        try:
            settings.HASHER.verify(user.password, password)
        except VerifyMismatchError as error_exc:
            language_service = app_from_info(
                info
            ).localization_container.service()
            error = await language_service.get_error_text(
                "invalid_password", request_var.get()["language"]
            )
            raise RuntimeError(error) from error_exc

        target_op = await OperatorModel.query.where(
            OperatorModel.id == operator_id
        ).gino.first()

        if not target_op:
            raise RuntimeError(
                f"Operator with id {operator_id} does not exist"
            )

        if not target_op.is_superuser:
            raise RuntimeError("Not a superuser")

        _tx: GinoTransaction
        async with db.transaction() as _tx:  # noqa F841
            operator = (
                await OperatorModel.query.where(
                    OperatorModel.id == operator_id
                )
                .where(OperatorModel.is_superuser == True)  # noqa E712
                .gino.first()
            )
            await operator.update(
                is_superuser=False,
                updated_by_operator_id=user.id,
                updated_at=sa.func.now(),
            ).apply()

            return {"operator": operator}


class BlockOperator(graphene.Mutation):
    """Mutation to handle operator blocking."""

    class Input:
        """Mutation input. Requires id and current operator password."""

        input = graphene.Argument(  # noqa A003
            OperatorBlockingInput, required=True
        )

    operator = graphene.Field(Operator, required=True)

    @require_superuser
    async def mutate(
        self,
        info: ResolveInfo,
        input: Dict,  # noqa A002
        user: object,
    ) -> Dict:
        """Operator demotion handler."""
        data = await OperatorBlockingInput.validate(input)

        operator_id = data.get("id")
        password = data.get("password")

        try:
            settings.HASHER.verify(user.password, password)
        except VerifyMismatchError as error_exc:
            language_service = app_from_info(
                info
            ).localization_container.service()
            error = await language_service.get_error_text(
                "invalid_password", request_var.get()["language"]
            )
            raise RuntimeError(error) from error_exc

        target_op = await OperatorModel.get(operator_id)

        if not target_op:
            raise RuntimeError(
                f"Operator with id {operator_id} does not exist"
            )

        if not target_op.is_active:
            raise RuntimeError("Operator is already blocked")

        _tx: GinoTransaction
        async with (await DatabaseHelper.transaction(info)) as _tx:
            conn = _tx.connection

            await conn.status(
                OperatorModel.update.values(
                    is_active=False,
                    updated_by_operator_id=user.id,
                    updated_at=sa.func.now(),
                )
                .where(OperatorModel.id == operator_id)
                .where(OperatorModel.is_active == True)  # noqa E712
            )

            return {
                "operator": await conn.first(
                    OperatorModel.select().where(
                        OperatorModel.id == operator_id
                    )
                )
            }


class UnblockOperator(graphene.Mutation):
    """Mutation to handle operator unblocking."""

    class Input:
        """Mutation input. Requires id and current operator password."""

        input = graphene.Argument(  # noqa A003
            OperatorBlockingInput, required=True
        )

    operator = graphene.Field(Operator, required=True)

    @require_superuser
    async def mutate(
        self,
        info: ResolveInfo,
        input: Dict,  # noqa A002
        user: object,
    ) -> Dict:
        """Operator demotion handler."""
        data = await OperatorBlockingInput.validate(input)

        operator_id = data.get("id")
        password = data.get("password")

        try:
            settings.HASHER.verify(user.password, password)
        except VerifyMismatchError as error_exc:
            language_service = app_from_info(
                info
            ).localization_container.service()
            error = await language_service.get_error_text(
                "invalid_password", request_var.get()["language"]
            )
            raise RuntimeError(error) from error_exc

        target_op = await OperatorModel.get(operator_id)

        if not target_op:
            raise RuntimeError(
                f"Operator with id {operator_id} does not exist"
            )

        if target_op.is_active:
            raise RuntimeError("Operator is already active")

        _tx: GinoTransaction
        async with (await DatabaseHelper.transaction(info)) as _tx:
            conn = _tx.connection

            await conn.status(
                OperatorModel.update.values(
                    is_active=True,
                    updated_by_operator_id=user.id,
                    updated_at=sa.func.now(),
                )
                .where(OperatorModel.id == operator_id)
                .where(OperatorModel.is_active == False)  # noqa E712
            )

            return {
                "operator": await conn.first(
                    OperatorModel.select().where(
                        OperatorModel.id == operator_id
                    )
                )
            }


class OperatorResetPasswordMutation(graphene.Mutation):
    """Mutation to reset operator password."""

    class Input:
        """Operator reset password input."""

        input = graphene.Argument(  # noqa A003
            ResetPasswordInput, required=True
        )

    result = graphene.Boolean(required=True)

    @require_superuser
    async def mutate(
        self,
        info: ResolveInfo,
        input: Dict,  # noqa A002
        user: object,
    ) -> Dict:
        """Mutation resolver."""
        data = await ResetPasswordInput.validate(input)

        operator_id = data.pop("id")
        email = await DatabaseHelper.scalar(
            info,
            query=sa.select(
                [OperatorModel.email], OperatorModel.id == operator_id
            ),
        )

        if not email:
            raise RuntimeError(
                f"Operator with id {operator_id} does not exist"
            )

        new_password = secrets.token_urlsafe(nbytes=8)
        data["password"] = settings.HASHER.hash(new_password)
        data["updated_by_operator_id"] = user.id
        data["updated_at"] = sa.func.now()

        _tx: GinoTransaction
        async with db.transaction() as _tx:  # noqa F841
            try:
                await OperatorModel.update.values(**data).where(
                    OperatorModel.id == operator_id
                ).gino.status()
            except UniqueViolationError as error_exc:
                raise HTTPInternalServerError(
                    reason="Password update error"
                ) from error_exc

        template = OperatorPasswordResetTemplate(
            info, new_password=new_password
        )

        await send_mail(email, template, request_var.get()["language"])

        return {"result": True}


class SetOperatorContentManager(graphene.Mutation):
    """Mutation to handle operator is_content_manager to true."""

    class Input:
        """Mutation input. Requires id and current operator password."""

        input = graphene.Argument(  # noqa A003
            OperatorContentManagerInput, required=True
        )

    operator = graphene.Field(Operator, required=True)

    @require_superuser
    async def mutate(
        self,
        info: ResolveInfo,
        input: Dict,  # noqa A002
        user: object,
    ) -> Dict:
        """Set Operator as content manager handler."""
        data = await OperatorContentManagerInput.validate(input)

        operator_id = data.get("id")
        password = data.get("password")

        try:
            settings.HASHER.verify(user.password, password)
        except VerifyMismatchError as error_exc:
            language_service = app_from_info(
                info
            ).localization_container.service()
            error = await language_service.get_error_text(
                "invalid_password", request_var.get()["language"]
            )
            raise RuntimeError(error) from error_exc

        target_op = await OperatorModel.query.where(
            OperatorModel.id == operator_id
        ).gino.first()

        if not target_op:
            raise RuntimeError(
                f"Operator with id {operator_id} does not exist"
            )

        if target_op.is_superuser:
            raise RuntimeError(f"Operator with id {operator_id} is superuser")

        _tx: GinoTransaction
        async with db.transaction() as _tx:  # noqa F841
            operator = (
                await OperatorModel.query.where(
                    OperatorModel.id == operator_id
                )
                .where(OperatorModel.is_superuser == False)  # noqa E712
                .gino.first()
            )
            await operator.update(
                is_content_manager=True,
                updated_by_operator_id=user.id,
                updated_at=sa.func.now(),
            ).apply()

            return {"operator": operator}


class UnsetOperatorContentManager(graphene.Mutation):
    """Mutation to handle operator is_content_manager to false."""

    class Input:
        """Mutation input. Requires id and current operator password."""

        input = graphene.Argument(  # noqa A003
            OperatorContentManagerInput, required=True
        )

    operator = graphene.Field(Operator, required=True)

    @require_superuser
    async def mutate(
        self,
        info: ResolveInfo,
        input: Dict,  # noqa A002
        user: object,
    ) -> Dict:
        """Unset Operator as content manager handler."""
        data = await OperatorContentManagerInput.validate(input)

        operator_id = data.get("id")
        password = data.get("password")

        try:
            settings.HASHER.verify(user.password, password)
        except VerifyMismatchError as error_exc:
            language_service = app_from_info(
                info
            ).localization_container.service()
            error = await language_service.get_error_text(
                "invalid_password", request_var.get()["language"]
            )
            raise RuntimeError(error) from error_exc

        target_op = await OperatorModel.query.where(
            OperatorModel.id == operator_id
        ).gino.first()

        if not target_op:
            raise RuntimeError(
                f"Operator with id {operator_id} does not exist"
            )

        _tx: GinoTransaction
        async with db.transaction() as _tx:  # noqa F841
            operator = await OperatorModel.query.where(
                OperatorModel.id == operator_id
            ).gino.first()
            await operator.update(
                is_content_manager=False,
                updated_by_operator_id=user.id,
                updated_at=sa.func.now(),
            ).apply()

            return {"operator": operator}


class OperatorMutation(graphene.ObjectType):
    """Operators mutations."""

    operator_create = OperatorCreate.Field()
    operator_reset_password = OperatorResetPasswordMutation.Field()
    operator_update = OperatorUpdate.Field()
    operator_promote = OperatorPromote.Field()
    operator_demote = OperatorDemote.Field()
    block_operator = BlockOperator.Field()
    unblock_operator = UnblockOperator.Field()
    set_content_manager = SetOperatorContentManager.Field()
    unset_content_manager = UnsetOperatorContentManager.Field()
