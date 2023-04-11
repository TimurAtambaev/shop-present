"""Helpers and classes for graphql_."""
import re
from copy import deepcopy
from functools import wraps
from typing import Any, Callable, Dict, Iterable, Optional, Tuple, Union

import graphene
import sqlalchemy as sa
import trafaret as T  # noqa N812
from fastapi import FastAPI, HTTPException
from gino import GinoEngine as Engine
from gino.engine import _TransactionContext
from graphene import ResolveInfo
from pydantic.fields import Field
from sqlalchemy.engine import ResultProxy, RowProxy
from sqlalchemy.orm import Query
from sqlalchemy.sql import Alias, Select
from sqlalchemy.sql.elements import Label
from trafaret import Trafaret

from dataset.integrations.zendesk import User, ZenDesk
from dataset.middlewares import request_var

CAPITAL_CHARS = re.compile("[A-Z]")


def app_from_info(info: Union[ResolveInfo, FastAPI]) -> FastAPI:
    """Get app from ResolveInfo object."""
    if isinstance(info, FastAPI):
        return info

    return info.context.get("request").app


def follow_field(piece: str, fields: tuple) -> Optional[str]:
    """Return requested fields based on provided path."""
    for fld in fields:
        if isinstance(fld, tuple) and fld[0] == piece:
            return fld[1]

        if fld == piece:
            return tuple()  # noqa C408

    raise ValueError


def read_fields(
    info: ResolveInfo, prefix: str = None, pythonize: bool = False
) -> Tuple:
    """Read and returns list of requested fields as tuple."""
    root_field = next(
        iter([f for f in info.field_asts if f.name.value == info.field_name])
    )

    pthnzr = lambda s: CAPITAL_CHARS.sub(  # noqa E731
        lambda m: f"_{m.group().lower()}", s
    )

    def read_field(fld: Field) -> Any:
        if fld.selection_set is None or not fld.selection_set.selections:
            return pthnzr(fld.name.value) if pythonize else fld.name.value

        return (
            pythonize and pthnzr(fld.name.value) or fld.name.value,
            tuple(read_field(sf) for sf in fld.selection_set.selections),
        )

    result = tuple(
        read_field(sf) for sf in root_field.selection_set.selections
    )

    if prefix is not None:
        path = prefix.split(".")

        for pth in path:
            try:
                result = follow_field(pth, result)
            except ValueError:
                return tuple()  # noqa C408

    return result


def is_field_requested(info: ResolveInfo, field_path: str) -> bool:
    """Check and returns result was field requested.

    Path is provided in comma separated maner like "result.some.field".
    """
    path = field_path.split(".")

    fields = read_fields(info)

    for pth in path:
        try:
            fields = follow_field(pth, fields)
        except ValueError:
            return False

    return True


def build_joint_query_from_info(
    info: ResolveInfo,
    base_path: str,
    whereclause: Query,
    base_table: sa.Table,
    relation_map: Dict[
        str, Union[sa.Table, Alias, Tuple[Union[sa.Table, Alias], Any]]
    ],
) -> Select:
    """Create simplify building complex requests with join.

    based on requested fields in graphql_ query/mutation.
    """
    joins = base_table
    selects = [base_table]

    for field_name, table_data in relation_map.items():
        if not is_field_requested(info, f"{base_path}.{field_name}"):
            continue

        table = table_data
        onclause = None

        if isinstance(table, tuple):
            table, onclause = table

        selects.append(table)

        if isinstance(table, (sa.Table, Alias)):
            joins = joins.join(table, onclause=onclause)

    return sa.select(selects, whereclause).select_from(joins)


def build_data_from_result(
    rows: Union[ResultProxy, Iterable[RowProxy]],
    template: Dict,
    key_field: str = "id",
) -> Dict:
    """Build dict from query result (ResultProxy) based on provided template.

    Template can contain eather Table objects or any value. Non-Table objects
    will be used as placeholder or default value for provided field.
    """
    result = {}

    item_template = {}
    tf_map = {}
    counter = 0

    for field, table in template.items():
        if not isinstance(table, (sa.Table, Alias)):
            item_template[field] = table
            continue

        item_template[field] = {}
        tf_map[table] = field

    for row in rows:
        item = deepcopy(item_template)  # item_template.copy()

        for col in row._keymap.keys():
            if not isinstance(col, (sa.Column, Label, Alias)):
                continue

            if (
                hasattr(col, "table")
                and col.table in tf_map.keys()  # noqa SIM118
            ):
                item[tf_map[col.table]][col.name] = row[col]
            else:
                item[col.name] = row[col]

        if key_field is None:
            result_field = counter
            counter += 1
        else:
            result_field = item[key_field]

        result[result_field] = item

    return result


def build_data_from_result_for_one_row(row: RowProxy, template: Dict) -> Dict:
    """Build dict from query result for one item (ResultProxy).

    Based on provided template.
    Template can contain eather Table objects or any value. Non-Table objects
    will be used as placeholder or default value for provided field.
    """
    result = None
    data = build_data_from_result([row], template, None)

    if data:
        result = next(iter(data.values()))

    return result  # noqa R504


async def send_ticket(
    info: ResolveInfo, _user: object, text: str, dream_id: int = None
) -> None:
    """Shortcut method to create ticket in zendesk."""
    app = app_from_info(info)
    zendesk: ZenDesk = app.state.zendesk

    z_user = User(email=_user.verified_email, name=_user.name)

    return await zendesk.create_ticket(z_user, text, _user.id, dream_id)


class DatabaseHelper:
    """Helper to shortcut db operations."""

    @classmethod
    async def __get_read_db(cls, info: Union[ResolveInfo, FastAPI]) -> Engine:
        """Get db for reading (SELECT)."""
        app = app_from_info(info)
        db_engine = app.state.db

        if not db_engine:
            raise RuntimeError("Database is not set or settings is invalid")

        return db_engine

    @classmethod
    async def __get_write_db(cls, info: Union[ResolveInfo, FastAPI]) -> Engine:
        """Get db for writing (INSERT, UPDATE)."""
        app = app_from_info(info)

        db_engine = app.state.db

        if not db_engine:
            raise RuntimeError("Database is not set or settings is invalid")

        return db_engine

    @classmethod
    async def fetch_one(
        cls,
        info: Union[ResolveInfo, FastAPI],
        query: Select,
        *args: Tuple,
        **kwargs: Dict,
    ) -> RowProxy:
        """Fetch single row."""
        db_engine = await cls.__get_read_db(info)

        return await db_engine.one_or_none(query, *args, **kwargs)

    @classmethod
    async def fetch_all(
        cls,
        info: Union[ResolveInfo, FastAPI],
        query: Select,
        *args: Tuple,
        **kwargs: Dict,
    ) -> RowProxy:
        """Fetch all rows."""
        db_engine = await cls.__get_read_db(info)

        return await db_engine.all(query, *args, **kwargs)

    @classmethod
    async def scalar(
        cls,
        info: Union[ResolveInfo, FastAPI],
        query: Any,
        *args: Tuple,
        **kwargs: Dict,
    ) -> RowProxy:
        """Fetch all rows."""
        db_engine = await cls.__get_read_db(info)

        return await db_engine.scalar(query, *args, **kwargs)

    @classmethod
    async def transaction(
        cls, info: Union[ResolveInfo, FastAPI]
    ) -> _TransactionContext:
        """Return transaction object."""
        db_engine = await cls.__get_write_db(info)

        return db_engine.transaction()


class LanguageHelper:
    """Helper to handle language related operations.

    Predicted to be used for
    read operations.
    """

    @classmethod
    async def get_language(cls, info: Union[ResolveInfo, FastAPI]) -> str:
        """Return current language."""
        request = request_var.get()
        return request["language"]

    @classmethod
    async def get_default_language(cls) -> str:
        """Return default language."""
        return "en"

    @classmethod
    async def t(
        cls,
        info: Union[ResolveInfo, FastAPI],
        msg_code: str,
        n: int = None,
        msg_vars: dict = None,
        language: str = None,
    ) -> Optional[str]:
        """Return localized message."""
        lang = language

        if lang not in [l[0] for l in LANGUAGES]:  # noqa E741
            lang = await cls.get_language(info)

        locale = next(
            iter([l[2] for l in LANGUAGES if l[0] == lang])  # noqa E741
        )

        messages = await cls.get_messages(info, lang)
        msg_codes = msg_code.split(".")
        result = messages.get(msg_codes[0], "")

        for code in msg_codes[1:]:
            try:
                result = result.get(code, "")
            except Exception:
                return None

        if "|" in result and n is not None:
            result = locale.pluralize(n, result)

        if msg_vars is not None and len(msg_vars) > 0:
            result = locale.add_vars_to_message(result, msg_vars)

        return result if isinstance(result, str) else None

    @classmethod
    async def get_messages(
        cls, info: ResolveInfo, language: str = None
    ) -> Optional[list]:
        """Return list of all localization data.

        From dataset/i18n/lang_code.
        """
        i18n_data = app_from_info(info).state.config.get("i18n", {})

        lang = language or await cls.get_language(info)

        if lang not in i18n_data.keys():
            lang = await cls.get_default_language()

        return i18n_data.get(lang)


def context(f: Callable) -> Callable:
    """Pass context to decorated function."""

    def decorator(func: Callable) -> Callable:
        async def wrapper(*args: tuple, **kwargs: dict) -> Any:
            info = next(arg for arg in args if isinstance(arg, ResolveInfo))
            return await func(info.context, *args, **kwargs)

        return wrapper

    return decorator


def user_passes_test(test_func: Callable) -> Callable:
    """Test user against test test_func.

    test_func should accept one argument and return bool.
    User in request is provided as argument.
    Recommended to use lambda for test_func
    """

    def decorator(f: Callable) -> Callable:
        @wraps(f)
        @context(f)
        async def wrapper(ctx: dict, *args: Tuple, **kwargs: Dict) -> Any:
            exc = HTTPException(status_code=403, detail="Forbidden")
            if hasattr(ctx.get("request"), "user"):
                user = ctx.get("request").user
            else:
                raise exc
            if not test_func(user):
                raise exc

            if "user" in f.__code__.co_varnames:
                kwargs["user"] = user
            elif "_user" in f.__code__.co_varnames:
                kwargs["_user"] = user

            return await f(*args, **kwargs)

        return wrapper

    return decorator


anonymous = user_passes_test(lambda u: u is None)

authorized_only = user_passes_test(lambda u: u is not None and u.id)

authorized_without_content_manager = user_passes_test(
    lambda u: u is not None and not u.is_content_manager
)

require_superuser = user_passes_test(lambda u: u and u.is_superuser)

require_content_manager = user_passes_test(
    lambda u: u and (u.is_superuser or u.is_content_manager)
)


class InputValidationMixin:
    """Mixin to implement validation. Requires to override trafaret method."""

    @classmethod
    def trafaret(cls) -> Trafaret:
        """Return trafaret rules for validation."""
        raise NotImplementedError()

    @classmethod
    async def validate(cls, value: Dict) -> Dict:
        """Run validation. Throws error if validation fails."""
        return cls.trafaret().check(value)


class ListInputType(graphene.InputObjectType, InputValidationMixin):
    """Predefined class for list input.

    Has validation and declaration of
    basic input fields.
    limit - names says for itself. Limits num rows.
    offset - offset in database records.
    order - field to use for sorting. If name starts with "-" sorting is done
    in descending way.

    Has validation for this fields. Has defined method for order fields.
    Default sort by id and created_at. Override this method to set different
    fields.
    """

    limit = graphene.Int(required=False, description="Number of items")
    offset = graphene.Int(
        required=False, description="Offset from start of full list"
    )

    order = graphene.String(description="Set order")

    @classmethod
    def order_fields(cls) -> Tuple[str, ...]:
        """Fields that can be used for sorting. Used in order field."""
        return "id", "created_at"

    @classmethod
    def trafaret(cls) -> Trafaret:
        """Template init."""
        order_fields_tmpl = "|".join(cls.order_fields())

        return T.Dict(
            {
                T.Key("limit", optional=True, default=20): T.Int(),
                T.Key("offset", optional=True, default=0): T.Int(),
                T.Key("order", optional=True): T.Regexp(
                    re.compile(f"^(|-)({order_fields_tmpl})$", re.I)
                ),
            }
        )


class IDInputType(graphene.InputObjectType, InputValidationMixin):
    """Input object for requests by id."""

    id = graphene.Int(required=True, description="Item ID")  # noqa A003

    @classmethod
    def trafaret(cls) -> Trafaret:
        """Template init."""
        return T.Dict({T.Key("id"): T.Int(gt=0)})


class PasswordIDInputType(IDInputType, InputValidationMixin):
    """Input with ID and password fields."""

    password = graphene.String(required=True)

    @classmethod
    def trafaret(cls) -> Trafaret:
        """Template init."""
        return super().trafaret() + T.Dict(
            {T.Key("password"): T.String(min_length=8)}
        )


class TokenIDInputType(graphene.InputObjectType, InputValidationMixin):
    """Input with token to subscription authorization."""

    token = graphene.String(required=True)

    @classmethod
    def trafaret(cls) -> Trafaret:
        """Template init."""
        return T.Dict({T.Key("token"): T.String(min_length=1)})


class ListResultType(graphene.ObjectType):
    """Object for returning result in list manner.

    Requires defining result field with type description.
    """

    count = graphene.Int(description="Total amount of items in db")


async def build_gql_request(
    query: str,
    in_vars: Optional[Dict] = None,
    operation_name: str = None,
) -> Dict:
    """Build graphql_ request."""
    op_name = operation_name

    if not op_name:
        re_result = re.search(
            r"^(query|mutation)[\s]+(?P<operation_name>[^\\(\\{]+)",
            query,
            re.I,
        )

        op_name = re_result.groupdict().get("operation_name")

    return {
        "query": query,
        "variables": {"input": in_vars}
        if in_vars is not None and not in_vars.get("input")
        else in_vars,
        "operation_name": op_name,
    }
