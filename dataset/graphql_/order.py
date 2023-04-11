"""Graphql type, objects, queries, mutations and etc related to order."""
from copy import deepcopy
from typing import Any, Callable, Dict, Iterable, List, Optional, Union

import graphene
import sqlalchemy as sa
import trafaret as t
from aiohttp.web_exceptions import HTTPInternalServerError
from asyncpg import UniqueViolationError
from gino import GinoConnection
from gino.transaction import GinoTransaction
from graphene import ResolveInfo
from loguru import logger
from sqlalchemy.engine import RowProxy
from sqlalchemy.sql import Select
from trafaret import Trafaret

from dataset.core.err_msgs import INVALID_CERT_NUM, USER_ID_NOT_EXIST
from dataset.core.graphql import (
    DatabaseHelper,
    InputValidationMixin,
    LanguageHelper,
    ListInputType,
    ListResultType,
    authorized_only,
    build_data_from_result,
    build_data_from_result_for_one_row,
    require_superuser,
)
from dataset.core.log import LOGGER
from dataset.graphql_.application import Application
from dataset.graphql_.payment_data import (
    PaymentData,
    PaymentDataInput,
    remember_payment_data,
)
from dataset.integrations.integration import (
    ExternalApplication,
    ProductData,
)
from dataset.tables import donation, user
from dataset.tables.application import application
from dataset.tables.country import Country, CountryManager
from dataset.tables.donation import DonationStatus, donation_purpose
from dataset.tables.order import OrderStatus, order
from dataset.tables.payment_data import payment_data, payment_data_history
from dataset.tables.user import user_history
from dataset.utils.app import ApplicationLib

logger.add("/srv/ufandao.com/backend/log/debug.log", level="DEBUG")


async def get_invalid_users(
    info: ResolveInfo, user_id_list: Iterable[str]
) -> List[int]:
    """Return list of invalid users id."""
    return [
        u.id
        for u in await DatabaseHelper.fetch_all(
            info,
            sa.select([user.c.id])
            .where(
                sa.or_(
                    user.c.verified_email.is_(None),
                    user.c.is_active == False,  # noqa E712
                )
            )
            .where(user.c.id.in_([int(u) for u in user_id_list])),
        )
    ]


async def get_invalid_orders(
    info: ResolveInfo, products: Iterable[ProductData], app_id: int
) -> List:
    """Return list of invalid order's product ids."""
    valid_orders = (
        await DatabaseHelper.fetch_all(
            info,
            sa.select([order.c.product_id, order.c.user_id])
            .select_from(order.join(payment_data, isouter=True, full=True))
            .where(payment_data.c.id is not None)
            .where(
                order.c.status.in_(
                    (
                        OrderStatus.COMPLETE.value,
                        OrderStatus.AUTO_COMPLETE.value,
                    )
                )
            )
            .where(order.c.product_id.in_([pd.product_id for pd in products])),
        )
        or []
    )

    o_map = {o.product_id: o.user_id for o in valid_orders}

    return [
        p.product_id
        for p in products
        if p.product_id not in o_map.keys()
        or o_map[p.product_id] != int(p.profile_id)
    ]


async def request_validation(
    info: ResolveInfo,
    _fn: Callable,
    app: application,
    **kwargs: Dict,
) -> List[ProductData]:
    """Run requests to external app and handles result."""
    blacklist = None
    attempts_count = 3
    blacklist_length = 0
    proceeded_blacklist: Dict[int, List[str]] = {}

    while True:
        try:
            result: List[ProductData] = await _fn(
                **{**kwargs, **{"blacklist": blacklist}},
            )
        except AssertionError as error_exc:
            error = await LanguageHelper.t(
                info, "errors.backend.order.validation_failed"
            )
            raise RuntimeError(error) from error_exc
        except RuntimeError as _e:
            LOGGER.error(_e)  # noqa G200
            logger.debug("1")
            error = await LanguageHelper.t(info, INVALID_CERT_NUM)
            raise RuntimeError(error) from _e

        pu_map = {}

        for pd_ in result:
            pu_map[pd_.product_id] = pd_.user_id

        invalid_users = await get_invalid_users(info, pu_map.values())
        invalid_orders = await get_invalid_orders(info, result, app.id)

        if len(invalid_users) == 0 and len(invalid_orders) == 0:
            break

        new_blacklist = list(
            set(invalid_users + [int(pu_map[p]) for p in invalid_orders])
        )

        for pd_ in result:
            if int(pd_.user_id) not in new_blacklist:
                continue

            _u = proceeded_blacklist.get(pd_.level) or []

            if pd_.user_id in _u:
                continue

            _u.append(int(pd_.user_id))
            proceeded_blacklist[pd_.level] = _u

        if blacklist is None:
            blacklist = []

        blacklist = blacklist + [
            bi for bi in new_blacklist if bi not in blacklist
        ]

        if len(blacklist) == blacklist_length:
            attempts_count -= 1

        blacklist_length = len(blacklist)

        if attempts_count <= 0:
            error = await LanguageHelper.t(
                info, "errors.backend.order.validation_failed"
            )
            raise RuntimeError(error)

    for res in result:
        res.blacklist = proceeded_blacklist.get(res.level)

    return result


async def validate_product(
    info: ResolveInfo, app: application, product_id: str
) -> List[ProductData]:
    """Run product validation via external app."""
    integration = ExternalApplication(
        app.integration_url, app.integration_token
    )

    return await request_validation(
        info, integration.validate, app, product_id=product_id
    )


async def reserve_product(
    info: ResolveInfo, app: application, product_id: str, profile_id: int
) -> List[ProductData]:
    """Run ticket reservation via external app."""
    integration = ExternalApplication(
        app.integration_url, app.integration_token
    )

    return await request_validation(
        info,
        integration.reserve,
        app,
        product_id=product_id,
        profile_id=profile_id,
    )


async def product_certificates(
    app: Union[object, Dict], product_id: str
) -> list:
    """Run product validation via external app."""
    integration = ExternalApplication(
        getattr(app, "integration_url", app["integration_url"]),
        getattr(app, "integration_token", app["integration_token"]),
    )

    return await integration.product_certificates(product_id)


async def payment_data_by_order_ids(
    info: ResolveInfo, order_ids: List
) -> dict:
    """Return payment data by order ids."""
    pdh = payment_data_history.alias("pdh")
    return {
        pd.order_id: pd
        for pd in await DatabaseHelper.fetch_all(
            info,
            sa.select(
                [pdh.c.payment_data_id, pdh.c.version, payment_data.c.order_id]
            )
            .select_from(pdh.join(payment_data))
            .where(payment_data.c.order_id.in_(order_ids))
            .where(
                pdh.c.version
                == sa.select([payment_data_history.c.version])
                .where(
                    payment_data_history.c.payment_data_id
                    == pdh.c.payment_data_id
                )
                .order_by(sa.desc(payment_data_history.c.version))
                .limit(1)
            ),
        )
    }


async def current_user(info: ResolveInfo, user_id: int) -> RowProxy:
    """Return current user history and version."""
    uh_ = user_history.alias("uh")
    return await DatabaseHelper.fetch_one(
        info,
        sa.select([uh_.c.user_id, uh_.c.version])
        .where(uh_.c.user_id == user_id)
        .where(
            uh_.c.version
            == sa.select([user_history.c.version])
            .where(user_history.c.user_id == uh_.c.user_id)
            .order_by(sa.desc(user_history.c.version))
            .limit(1)
        ),
    )


GraphqlOrderStatus = graphene.Enum(
    "OrderStatus", [(s.name, s.value) for s in OrderStatus]
)


class AvailableCertificate(graphene.ObjectType):
    """Available Certificate object."""

    product_id = graphene.String()
    is_available = graphene.Boolean()


class Order(graphene.ObjectType):
    """Graphql object that represents order."""

    id = graphene.Int()  # noqa: A003
    user_id = graphene.Int()
    user = graphene.Field("dataset.graphql_.user.utils.User")
    app_id = graphene.Int()
    product_id = graphene.String()
    application = graphene.Field(Application)
    status = graphene.Field(GraphqlOrderStatus)
    payment_data = graphene.Field(PaymentData)
    total_income = graphene.Decimal()
    total_pending = graphene.Decimal()
    available_certificates = graphene.List(AvailableCertificate)
    created_by_operator_id = graphene.Int()
    invite_donation_id = graphene.Int()

    created_at = graphene.DateTime()
    updated_at = graphene.DateTime()

    async def resolve_app_id(self, *args: tuple) -> Optional[int]:
        """Get shortcut for application_id."""
        if isinstance(self, dict):
            return self.get("application_id")

        if hasattr(self, "application_id"):
            return self.application_id

        return None


class OrderSearchInput(ListInputType):
    """Input for order list request."""

    status = graphene.Field(GraphqlOrderStatus)

    @classmethod
    def trafaret(cls) -> Trafaret:
        """Get trafaret."""
        return super().trafaret() + t.Dict(
            {t.Key("status", optional=True): t.Int()}
        )


class OrderCheckProductInput(graphene.InputObjectType, InputValidationMixin):
    """Input to check product id."""

    product_id = graphene.String(required=True)

    @classmethod
    def trafaret(cls) -> Trafaret:
        """Get trafaret."""
        return t.Dict({t.Key("product_id"): t.String(min_length=6)})


class OrderPublicCreateInput(OrderCheckProductInput):
    """Input to check product id."""

    class Meta:
        """Meta class."""

        name = "OrderCreateInput"


class OrderSearchResult(ListResultType):
    """Result for list of orders."""

    result = graphene.List(Order)
    unread_messages = graphene.Int()


class OrderIDInput(graphene.InputObjectType, InputValidationMixin):
    """Input where only order id required."""

    order_id = graphene.Int(required=True)

    @classmethod
    def trafaret(cls) -> Trafaret:
        """Get trafaret."""
        return t.Dict({t.Key("order_id"): t.Int(gt=0)})


class OrderCreateInput(graphene.InputObjectType, InputValidationMixin):
    """Input for order create operation."""

    product_id = graphene.String(required=True)
    app_id = graphene.Int(required=True)
    user_id = graphene.Int(required=True)
    payment_data = graphene.Field(PaymentDataInput, required=True)

    @classmethod
    def trafaret(cls) -> Trafaret:
        """Get trafaret."""
        return t.Dict(
            {
                t.Key("product_id"): t.String(),
                t.Key("app_id"): t.Int(gt=0),
                t.Key("user_id"): t.Int(gt=0),
                t.Key("payment_data"): PaymentDataInput.trafaret(),
            }
        )

    @classmethod
    async def validate(cls, value: Dict) -> Dict:
        """Run validation."""
        in_data = deepcopy(value)
        in_data["payment_data"] = await PaymentDataInput.validate(
            in_data.get("payment_data")
        )

        return await super().validate(in_data)


class OrderCreateMutation(graphene.Mutation):
    """Mutation creates order for selected user within selected application."""

    class Input:
        """Input description for mutation."""

        input = graphene.Argument(  # noqa: A003, E501
            OrderCreateInput, required=True
        )

    order = graphene.Field(Order, required=True)

    @require_superuser
    async def mutate(
        self,
        info: ResolveInfo,
        input: Dict,  # noqa: A002
        _user: object,
    ) -> dict:
        """Mutation resolver. Checks input and proceeds request."""
        data = await OrderCreateInput.validate(input)

        payment_input = data.pop("payment_data")

        country_ = await CountryManager.get_by_id(
            info, payment_input.get("country_id")
        )

        if not country_ or not country_.get("is_active"):
            raise RuntimeError(
                await LanguageHelper.t(info, "errors.backend.country.invalid")
            )

        exists_purpose = await DatabaseHelper.scalar(
            info,
            sa.exists(
                sa.select([donation_purpose.c.id]).where(
                    sa.and_(
                        donation_purpose.c.id
                        == payment_input.get("purpose_id"),
                        donation_purpose.c.is_active == True,  # noqa: E712
                    )
                )
            ).select(),
        )

        if not exists_purpose:
            raise RuntimeError(
                await LanguageHelper.t(
                    info,
                    "errors.backend.donation.purpose_not_exist",
                    msg_vars={"id": payment_input.get("purpose_id")},
                )
            )

        payment_input["created_by_operator_id"] = _user.id
        payment_input["created_at"] = sa.func.now()
        payment_input["updated_at"] = sa.func.now()

        selected_user = await DatabaseHelper.fetch_one(
            info,
            user_history.select()
            .where(user_history.c.user_id == data.get("user_id"))
            .where(
                user_history.c.version
                == sa.select(
                    [sa.func.max(user_history.c.version)],
                    user_history.c.user_id == data.get("user_id"),
                )
            ),
        )

        if selected_user is None:
            raise RuntimeError(
                await LanguageHelper.t(
                    info,
                    USER_ID_NOT_EXIST,
                    msg_vars={"user_id": data.get("user_id")},
                )
            )

        selected_application = await DatabaseHelper.fetch_one(
            info,
            application.select().where(application.c.id == data.get("app_id")),
        )

        if selected_application is None:
            raise RuntimeError(
                await LanguageHelper.t(
                    info,
                    "errors.backend.order.application_not_exist",
                    msg_vars={"app_id": data.get("app_id")},
                )
            )

        try:
            certificates = await product_certificates(
                selected_application, data.get("product_id")
            )
        except (AssertionError, RuntimeError):
            certificates = []

        certificates = [
            (
                "".join(
                    [
                        c["productId"].upper(),
                        "" if c["status"] == "NEW" else ":r",
                    ]
                )
            )
            for c in certificates or []
        ]

        _tx: GinoTransaction
        async with (await DatabaseHelper.transaction(info)) as _tx:
            conn: GinoConnection = _tx.connection

            await conn.status(
                order.insert().values(
                    user_id=data.get("user_id"),
                    user_version=selected_user.version,
                    product_id=data.get("product_id"),
                    status=OrderStatus.AUTO_COMPLETE.value,
                    created_by_operator_id=_user.id,
                    available_certificates=certificates,
                )
            )

            result = await conn.first(
                sa.select([order]).where(
                    order.c.id == sa.select([sa.func.currval("order_id_seq")])
                )
            )
            result = dict(result)

            try:
                payment_input["order_id"] = result["id"]

                await conn.status(payment_data.insert().values(payment_input))

                order_payment_data_ = await conn.first(
                    sa.select(
                        [payment_data],
                        payment_data.c.id
                        == sa.select([sa.func.currval("payment_data_id_seq")]),
                    ).select_from(payment_data.join(Country))
                )
                await remember_payment_data(
                    info, order_payment_data_, data.get("user_id")
                )
            except UniqueViolationError as error_exc:
                raise HTTPInternalServerError(
                    reason=await LanguageHelper.t(
                        info, "errors.backend.order.payment_data_error"
                    )
                ) from error_exc

            result["application"] = selected_application
            result["payment_data"] = order_payment_data_
            result["user"] = selected_user
            result["donations"] = []
            result["available_certificates"] = [
                {
                    "product_id": c.lower().replace(":r", "").upper(),
                    "is_available": not c.lower().endswith(":r"),
                }
                for c in result["available_certificates"] or []
            ]

            return {"order": result}


class OrderAdminMutation(graphene.ObjectType):
    """Order related mutations for operators."""

    order_create = OrderCreateMutation.Field()


class OrderPublicQuery(graphene.ObjectType):
    """Order queries used in public app."""

    my_orders = graphene.Field(
        OrderSearchResult,
        input=graphene.Argument(OrderSearchInput, required=True),
    )

    check_product_id = graphene.Field(
        Order, input=graphene.Argument(OrderCheckProductInput, required=True)
    )

    available_certificates = graphene.List(
        AvailableCertificate,
        input=graphene.Argument(OrderIDInput, required=True),
    )

    @authorized_only
    async def resolve_available_certificates(
        self,
        info: ResolveInfo,
        input: Dict,  # noqa: A002
        _user: object,
    ) -> list:
        """Resolve query for order's available_certificates."""
        data = await OrderIDInput.validate(input)
        order_id = data.pop("order_id")

        _order = await DatabaseHelper.fetch_one(
            info,
            sa.select(
                [
                    order.c.id.label("order_id"),
                    order.c.available_certificates,
                    order.c.product_id,
                    application,
                ]
            )
            .select_from(order.join(application))
            .where(order.c.id == order_id)
            .where(order.c.user_id == _user.id)
            .where(
                order.c.status.in_(
                    (
                        OrderStatus.COMPLETE.value,
                        OrderStatus.AUTO_COMPLETE.value,
                    )
                )
            ),
        )

        exist_payment_data = await DatabaseHelper.scalar(
            info,
            sa.select([payment_data.c.id]).where(
                payment_data.c.order_id == order_id
            ),
        )

        if not _order or not exist_payment_data:
            return []

        _order_data = build_data_from_result_for_one_row(
            _order, {"app": application}
        )

        def certs_to_result(certs: List) -> List:
            return [
                {
                    "product_id": c.lower().replace(":r", "").upper(),
                    "is_available": not c.lower().endswith(":r"),
                }
                for c in certs or []
            ]

        result = certs_to_result(_order_data["available_certificates"])

        if len(result) > 0:
            return result

        try:
            certs = await product_certificates(
                _order_data["app"], _order_data["product_id"]
            )
        except AssertionError:
            return []
        except RuntimeError:
            return []

        certs = [
            (
                f'{c["productId"].upper()}'
                f'{"" if c["status"] == "NEW" else ":r"}'
            )
            for c in certs or []
        ]

        if len(certs) == 0:
            return result

        _tx: GinoTransaction
        async with (await DatabaseHelper.transaction(info)) as _tx:
            conn = _tx.connection
            await conn.status(
                order.update()
                .values({order.c.available_certificates: certs})
                .where(order.c.id == _order.order_id)
            )

            return certs_to_result(certs)

    @authorized_only
    async def resolve_check_product_id(
        self,
        info: ResolveInfo,
        input: dict,  # noqa: A002
        _user: object,
    ) -> dict:
        """Resolve query for user's orders."""
        data = await OrderCheckProductInput.validate(input)

        product_id = data.pop("product_id")

        if not _user.verified_email:
            error = await LanguageHelper.t(
                info, "errors.backend.order.unverified_account"
            )
            raise RuntimeError(error)

        exists = await DatabaseHelper.scalar(
            info,
            sa.exists(
                sa.select([order.c.id]).where(order.c.product_id == product_id)
            ).select(),
        )

        if exists:
            logger.debug("2")
            raise RuntimeError(await LanguageHelper.t(info, INVALID_CERT_NUM))

        # get first active app ( sort by id asc )
        app = await ApplicationLib.get_first_app(info)

        if not app:
            error = await LanguageHelper.t(
                info, "errors.backend.order.invalid_application"
            )
            raise RuntimeError(error)

        validation_result = await validate_product(
            info, app["application"], product_id
        )

        if len(validation_result) == 0:
            raise RuntimeError(
                await LanguageHelper.t(
                    info, "errors.backend.order.invalid_product"
                )
            )

        return {
            "id": -1,
            "user_id": _user.id,
            "user": _user,
            "app_id": app["application"].id,
            "application": app["application"],
            "product_id": product_id,
            "status": OrderStatus.NEW.value,
            "payment_data": None,
            "donations": [
                {
                    "id": (i + 1) * -1,
                    "recipient_id": pd.user_id,
                    "recipient": await DatabaseHelper.fetch_one(
                        info, user.select().where(user.c.id == int(pd.user_id))
                    ),
                    "parent_product_id": pd.product_id,
                    "payment_data": await DatabaseHelper.fetch_one(
                        info,
                        sa.select([payment_data])
                        .select_from(order.join(payment_data))
                        .where(order.c.product_id == str(pd.product_id))
                        .where(
                            order.c.application_id == app["application"].id
                        ),
                    ),
                    "amount": app["levels"][pd.level].amount,
                    "level": app["levels"][pd.level].name,
                    "level_number": pd.level,
                    "is_primary": app["levels"][pd.level].is_primary,
                    "status": DonationStatus.NEW.value,
                }
                for i, pd in enumerate(validation_result)
            ],
        }


class OrderCreate(graphene.Mutation):
    """Mutation creates user's order and initiatebs payment procedure."""

    class Input:
        """Mutation input."""

        input = graphene.Argument(  # noqa: A003, E501
            OrderPublicCreateInput, required=True
        )

    order = graphene.Field(Order)

    @authorized_only
    async def mutate(
        self, info: ResolveInfo, input: Dict, _user: object  # noqa: A002
    ) -> dict:
        """Handle order creation. Fist order must be sent to external app."""
        data = await OrderCheckProductInput.validate(input)

        if not _user.verified_email:
            raise RuntimeError(
                await LanguageHelper.t(
                    info, "errors.backend.order.unverified_account"
                )
            )

        exists = await DatabaseHelper.scalar(
            info,
            sa.exists(
                sa.select([order.c.id]).where(
                    order.c.product_id == data.get("product_id")
                )
            ).select(),
        )

        if exists:
            logger.debug("3")
            raise RuntimeError(await LanguageHelper.t(info, INVALID_CERT_NUM))

        # get first active app
        app = await ApplicationLib.get_first_app(info)
        if not app:
            raise RuntimeError(
                await LanguageHelper.t(
                    info, "errors.backend.order.invalid_application"
                )
            )

        invite_validation_result = await validate_product(
            info, app["application"], data.get("product_id")
        )
        validation_result = await reserve_product(
            info,
            app["application"],
            product_id=data.get("product_id"),
            profile_id=_user.id,
        )

        if len(validation_result) == 0:
            raise RuntimeError(
                await LanguageHelper.t(
                    info, "errors.backend.order.invalid_product"
                )
            )

        cur_user = await current_user(info, _user.id)
        so_list = {
            o.product_id: o
            for o in await DatabaseHelper.fetch_all(
                info,
                sa.select([order]).where(
                    order.c.product_id.in_(
                        [vr.product_id for vr in validation_result]
                    )
                ),
            )
        }

        pd_list = await payment_data_by_order_ids(
            info, [o.id for o in so_list.values()]
        )

        _tx: GinoTransaction
        async with (await DatabaseHelper.transaction(info)) as _tx:
            await _tx.connection.status(
                order.insert().values(
                    {
                        "user_id": cur_user.user_id,
                        "user_version": cur_user.version,
                        "application_id": app["application"].id,
                        "product_id": data.get("product_id"),
                        "status": OrderStatus.NEW.value,
                        "created_at": sa.func.now(),
                        "updated_at": sa.func.now(),
                    }
                )
            )
            # update available certificates status for current product id
            order_available_certificates = await DatabaseHelper.fetch_all(
                info,
                sa.select(
                    [order.c.id, order.c.available_certificates],
                    order.c.available_certificates.any(data.get("product_id")),
                ),
            )
            if order_available_certificates:
                for order_certs in order_available_certificates:
                    available_certs = [
                        (
                            f"{c.upper()}"
                            f'{":r" if c == data.get("product_id") else ""}'
                        )
                        for c in order_certs["available_certificates"]
                    ]
                    await _tx.connection.status(
                        (
                            order.update()
                            .values(
                                {
                                    "available_certificates": available_certs,
                                    "updated_at": sa.func.now(),
                                }
                            )
                            .where(order.c.id == order_certs["id"])
                        )
                    )

            new_order = await _tx.connection.one(
                sa.select([order]).where(
                    order.c.id == sa.select([sa.func.currval("order_id_seq")])
                )
            )

            def get_donation_insert(validation_result: Any) -> Select:
                """
                Получить sql на создание доната.

                :param validation_result: валидированные данные
                :return: объект содержащий sql
                """
                return donation.insert().values(
                    {
                        "order_id": new_order.id,
                        "recipient_id": (
                            so_list[validation_result.product_id].user_id
                        ),
                        "recipient_version": (
                            so_list[validation_result.product_id].user_version
                        ),
                        "payment_data_id": (
                            pd_list[
                                so_list[validation_result.product_id].id
                            ].payment_data_id
                        ),
                        "payment_data_version": pd_list[
                            so_list[validation_result.product_id].id
                        ].version,
                        "level": app["levels"][validation_result.level].name,
                        "level_number": validation_result.level,
                        "amount": (
                            app["levels"][validation_result.level].amount
                        ),
                        "is_primary": app["levels"][
                            validation_result.level
                        ].is_primary,
                        "parent_product_id": validation_result.product_id,
                        "proceeded_blacklist": validation_result.blacklist,
                        "status": DonationStatus.NEW.value,
                        "created_at": sa.func.now(),
                        "updated_at": sa.func.now(),
                    }
                )

            for _vr in validation_result:
                await _tx.connection.status(get_donation_insert(_vr))

            for _vr in invite_validation_result:
                insert = get_donation_insert(_vr).returning(donation.c.id)
                donation_invite_id = await _tx.connection.scalar(insert)

            new_order = build_data_from_result_for_one_row(new_order, {})
            new_order["application"] = build_data_from_result_for_one_row(
                app["application"], {}
            )
            new_order["user"] = _user
            new_order["invite_donation_id"] = donation_invite_id

            new_order["donations"] = build_data_from_result(
                await _tx.connection.all(
                    sa.select([donation, user_history, payment_data_history])
                    .select_from(
                        (donation.join(order)).join(payment_data_history)
                    )
                    .where(donation.c.order_id == new_order.get("id"))
                ),
                {"user": user_history, "payment_data": payment_data_history},
            ).values()

            return {"order": new_order}


class OrderPublicMutation(graphene.ObjectType):
    """Order mutations for public api."""

    order_create = OrderCreate.Field()
