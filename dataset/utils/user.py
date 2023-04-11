"""Libs for user object."""
from datetime import date, datetime

import sqlalchemy as sa
from graphene import ResolveInfo

from dataset.core.graphql import DatabaseHelper
from dataset.tables import donation
from dataset.tables.country import Country, CountryLanguage
from dataset.tables.donation import DonationLevel, DonationStatus
from dataset.tables.order import OrderStatus, order
from dataset.tables.user import AchievementCode, User


class UserLib:
    """Lib for user object."""

    @classmethod
    async def get_total_users_by_country(
        cls,
        info: ResolveInfo,
        is_active_users: bool = True,
        is_active_country: bool = True,
    ) -> DatabaseHelper:
        """Get total registered users grouped by country."""
        query = (
            sa.select(
                [
                    sa.func.count(sa.distinct(User.id)).label("total_users"),
                    User.country_id.label("country_id"),
                    CountryLanguage.title.label("country_name"),
                ],
                sa.and_(
                    User.is_active == is_active_users,
                    Country.is_active == is_active_country,
                ),
            )
            .select_from(
                User.join(Country).join(
                    CountryLanguage,
                    onclause=sa.and_(
                        User.country_id == CountryLanguage.country_id,
                        CountryLanguage.language == "en",
                    ),
                ),
            )
            .group_by(User.country_id, CountryLanguage.title)
            .order_by(sa.desc("total_users"))
        )

        return await DatabaseHelper.fetch_all(info, query)

    @classmethod
    async def get_total_users(
        cls, info: ResolveInfo, is_active: bool = True
    ) -> DatabaseHelper:
        """Get total registered users."""
        return await DatabaseHelper.scalar(
            info,
            sa.select(
                [sa.func.count(sa.distinct(User.id))],
                User.is_active == is_active,
            ),
        )

    @staticmethod
    async def get_user_donation_max_count_by_level_and_product_id(
        info: ResolveInfo, user_id: int
    ) -> dict:
        """Fetch user max donations count.

        with CONFIRMED/AUTO_CONFIRMED status
        with same product id grouped by level
        """
        donation_sub_query = (
            sa.select(
                [
                    sa.func.count(donation.c.id).label("count"),
                    donation.c.level_number,
                ],
                sa.and_(
                    donation.c.recipient_id == user_id,
                    donation.c.status.in_(
                        [
                            DonationStatus.CONFIRMED.value,
                            DonationStatus.AUTO_CONFIRMED.value,
                        ]
                    ),
                ),
            )
            .group_by(donation.c.parent_product_id, donation.c.level_number)
            .alias("sub")
        )

        donations_total = await DatabaseHelper.fetch_all(
            info,
            sa.select(
                [
                    sa.func.max(donation_sub_query.c.count).label(
                        "max_product_id_donations"
                    ),
                    donation_sub_query.c.level_number,
                ]
            ).group_by("level_number"),
        )
        result = {item.value: 0 for item in DonationLevel}

        for don_ in donations_total:
            result[don_["level_number"]] = don_["max_product_id_donations"]

        return result

    @classmethod
    async def get_achievements(cls, info: ResolveInfo, user_id: int) -> list:
        """Resolve achievements."""
        # TODO путаница с ачивками
        # Certificate activation ( if have order != FAILED and > 1 ) => user_id field
        achievements = []

        certificate_activation_select = sa.select(
            [sa.func.count(order.c.id)],
            sa.and_(
                order.c.user_id == user_id,
                order.c.status.notin_((OrderStatus.FAILED.value,)),
            ),
        )

        certificate_activation_count = await DatabaseHelper.scalar(
            info, certificate_activation_select
        )
        certificate_activation = {
            "code": AchievementCode.CERTIFICATE_ACTIVATION.value,
            "is_complete": False,
            "progress": 0,
        }

        if certificate_activation_count >= 1:
            certificate_activation["is_complete"] = True
            certificate_activation["progress"] = 100

        achievements.append(certificate_activation)

        # Nacometa friend
        # count of donation with complete/autocomplete where order.user_id = user.id >=4

        nacometa_friend_count = await DatabaseHelper.scalar(
            info,
            sa.select(
                [sa.func.count(donation.c.id)],
                sa.and_(
                    order.c.user_id == user_id,
                    donation.c.status.in_(
                        (
                            DonationStatus.CONFIRMED.value,
                            DonationStatus.AUTO_CONFIRMED.value,
                        )
                    ),
                ),
            ).select_from(donation.join(order)),
        )
        nacometa_friend = {
            "code": AchievementCode.NACOMETA_FRIEND.value,
            "is_complete": False,
            "progress": (nacometa_friend_count / 4) * 100,
        }
        if nacometa_friend_count >= 4:
            nacometa_friend["is_complete"] = True
            nacometa_friend["progress"] = 100
        achievements.append(nacometa_friend)

        # Sharing friend ( count of orders at least one donation has reciepient id = user.id >=4 )
        sharing_total = (
            await cls.get_user_donation_max_count_by_level_and_product_id(
                info, user_id
            )
        )

        sharing_friend = {
            "code": AchievementCode.SHARING_FRIEND.value,
            "is_complete": False,
            "progress": (sharing_total[DonationLevel.REFERAL.value] / 4) * 100,
        }

        if sharing_total[DonationLevel.REFERAL.value] >= 4:
            sharing_friend["is_complete"] = True
            sharing_friend["progress"] = 100

        # Sharing master, Sharing expert, Sharing pro
        # count of donations with status complete/autocomplete has reciepient id = user.id
        # >= 16  master
        # >= 64 expert
        # >= 256 pro
        sharing_master = {
            "code": AchievementCode.SHARING_MASTER.value,
            "is_complete": False,
            "progress": (sharing_total[DonationLevel.BRONZE.value] / 16) * 100,
        }
        if sharing_total[DonationLevel.BRONZE.value] >= 16:
            sharing_master["is_complete"] = True
            sharing_master["progress"] = 100

        sharing_expert = {
            "code": AchievementCode.SHARING_EXPERT.value,
            "is_complete": False,
            "progress": (sharing_total[DonationLevel.SILVER.value] / 64) * 100,
        }
        if sharing_total[DonationLevel.SILVER.value] >= 64:
            sharing_expert["is_complete"] = True
            sharing_expert["progress"] = 100

        sharing_pro = {
            "code": AchievementCode.SHARING_PRO.value,
            "is_complete": False,
            "progress": (sharing_total[DonationLevel.GOLD.value] / 256) * 100,
        }

        if sharing_total[DonationLevel.GOLD.value] >= 256:
            sharing_pro["is_complete"] = True
            sharing_pro["progress"] = 100

        achievements.append(sharing_friend)
        achievements.append(sharing_master)
        achievements.append(sharing_expert)
        achievements.append(sharing_pro)
        return achievements


def user_has_subscribe(user: User) -> bool:
    """Проверка на наличие подписки у пользователя."""
    # paid_till - дата
    if user.paid_till and user.paid_till >= date.today():
        return True
    # а trial_till - timestamp, поэтому разные проверки
    if user.trial_till and user.trial_till > datetime.now():
        return True
    return False
