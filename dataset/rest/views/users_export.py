"""Module for request handlers related to export users.

Used for integration that does not support graphql_
"""
from datetime import datetime, timedelta

import sqlalchemy as sa
from dateutil import relativedelta
from fastapi import Depends, HTTPException
from fastapi_utils.inferring_router import InferringRouter
from gino import GinoConnection
from gino.transaction import GinoTransaction
from openpyxl import Workbook
from openpyxl.writer.excel import save_virtual_workbook
from starlette import status
from starlette.requests import Request
from starlette.responses import Response

from dataset.core.log import LOGGER
from dataset.migrations import db
from dataset.rest.permissions import AuthChecker
from dataset.tables.country import CountryLanguage
from dataset.tables.operator import Operator
from dataset.tables.user import User

router = InferringRouter()

XLS_TITLES = [
    "ID",
    "NAME",
    "EMAIL",
    "COUNTRY",
    "LANGUAGE",
    "BIRTH DATE",
    "GENDER",
    "PHONE",
    "IS ACTIVE",
    "CREATED AT",
]


@router.get(
    "/admin/users/export",
    dependencies=[Depends(AuthChecker(is_operator=True))],
)
async def users_export(
    request: Request, date_from: str, date_to: str
):  # noqa ANN201
    """Handle users export for operators."""
    operator: Operator = request.get("user")

    if not operator:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)

    if operator.is_content_manager or not operator.is_superuser:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)

    # set default date values - last 30 days
    to_date = datetime.utcnow()
    from_date = to_date - timedelta(days=30)

    whereclause = []

    try:
        if date_from:
            from_date = datetime.strptime(date_from, "%Y%m%d")
        if date_to:
            to_date = datetime.strptime(date_to, "%Y%m%d")
    except ValueError:
        return error_response("Wrong date format; Date pattern must be YYMMDD")

    # check month difference between dates
    date_diff = relativedelta.relativedelta(to_date, from_date)

    if (
        date_diff.months > 1
        or (date_diff.months == 1 and date_diff.days > 1)
        or from_date > to_date
    ):
        raise HTTPException(
            detail="Date difference between date_from "
            "and date_to must be not more than a month",
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    to_date = to_date.replace(hour=23, minute=59, second=59)
    from_date = from_date.replace(hour=0, minute=0, second=0)

    whereclause.append(User.created_at >= from_date)
    whereclause.append(User.created_at <= to_date)

    try:
        tx_: GinoTransaction
        async with db.transaction() as tx_:
            conn: GinoConnection = tx_.connection
            user_list = await conn.all(
                sa.select(
                    [User, CountryLanguage.title.label("country_name")],
                    sa.and_(*whereclause),
                )
                .select_from(
                    User.outerjoin(
                        CountryLanguage,
                        onclause=sa.and_(
                            (User.country_id == CountryLanguage.country_id),
                            CountryLanguage.language == "en",
                        ),
                    )
                )
                .order_by(User.id)
            )

            xls_data = generate_xls_data(user_list)
            filename = f'Users{datetime.now().strftime("%Y%m%d%H%M")}.xlsx'
            return Response(
                headers={
                    "Content-Disposition": f"attachment;"
                    f" filename={filename}"
                },
                content=save_virtual_workbook(xls_data),
                status_code=status.HTTP_200_OK,
                media_type="ms-excel",
            )
    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=error
        )


def generate_xls_data(user_list: list) -> Workbook:
    """Generate xls data."""
    xls_book = Workbook()
    sheet = xls_book.active
    sheet.append(XLS_TITLES)

    for item in user_list:
        sheet.append(
            [
                item["id"],
                item["name"],
                (
                    item["verified_email"]
                    if item["verified_email"]
                    else item["email"]
                ),
                item["country_name"],
                item["language"],
                (
                    item["birth_date"].strftime("%d-%m-%Y")
                    if item["birth_date"]
                    else item["birth_date"]
                ),
                ("female" if item["is_female"] else "male"),
                item["phone"],
                ("yes" if item["is_active"] else "no"),
                (
                    item["created_at"].strftime("%Y-%m-%d %H:%M")
                    if item["created_at"]
                    else item["created_at"]
                ),
            ]
        )

    return xls_book


def error_response(message: str, status=400):  # noqa ANN201
    """Return error response."""
    if message:
        LOGGER.error(message)

    return Response(
        content=message or "FAIL",
        status_code=status,
        media_type="text/plain",
    )
