"""Модуль с фабриками."""
import asyncio
from datetime import datetime, timedelta
from typing import Coroutine, Type

import factory
from gino.declarative import ModelType

from dataset.config import settings
from dataset.tables.achievement import Achievement
from dataset.tables.country import Country, CountryLanguage
from dataset.tables.currency import Currency
from dataset.tables.donate_size import DonateSize
from dataset.tables.donation import Donation, DonationStatus
from dataset.tables.kit import Category, Dream, DreamStatus, DreamType
from dataset.tables.dream_form import DreamForm
from dataset.tables.event import Event
from dataset.tables.notification import Notification
from dataset.tables.operator import Operator
from dataset.tables.post import Post
from dataset.tables.review import Review
from dataset.tables.user import User


def create_id_by_attribute(obj: Type["BaseFactory"]) -> int:
    """
    Метод получения id связанного объекта.

    Требуется в качестве замены SubFactory из-за асинхронного кода.
    """
    loop = asyncio.get_event_loop()
    related = loop.run_until_complete(obj())
    return related.id


class BaseFactory(factory.Factory):
    """Базовый класс фабрики."""

    @classmethod
    def _create(
        cls,
        model_class: ModelType,
        *args: tuple,
        **kwargs: dict,
    ) -> Coroutine:
        """Модифицированный метод создания записи в бд под gino."""

        async def create_coro(*args: tuple, **kwargs: dict) -> Coroutine:
            return await model_class.create(*args, **kwargs)

        return create_coro(*args, **kwargs)


class CurrencyFactory(BaseFactory):
    """Фабрика валют."""

    class Meta:
        """Метакласс с настройками."""

        model = Currency

    code = "EURO"
    symbol = factory.Sequence(lambda n: f"s{n}")
    name = factory.Sequence(lambda n: f"name{n}")
    course = factory.Sequence(lambda n: n + 1)
    sort_number = factory.Sequence(lambda n: n + 2)
    is_active = True
    dream_limit = factory.Sequence(lambda n: n + 5000)


class UserFactory(BaseFactory):
    """Фабрика пользователя."""

    class Meta:
        """Метакласс с настройками."""

        model = User

    name = factory.Sequence(lambda n: f"Test{n}")
    surname = factory.Sequence(lambda n: f"tseT{n}")
    verified_email = factory.Sequence(lambda n: f"test{n}@test.com")
    password = factory.LazyFunction(lambda: settings.HASHER.hash("test1234"))
    paid_till = factory.LazyFunction(
        lambda: datetime.now() + timedelta(days=1)
    )
    trial_till = factory.LazyFunction(
        lambda: datetime.now() + timedelta(days=1)
    )
    currency_id = settings.EURO_ID
    refer_code = factory.Sequence(lambda n: f"referer_{n}")


class AchievementFactory(BaseFactory):
    """Фабрика достижений."""

    class Meta:
        """Метакласс с настройками."""

        model = Achievement

    title = factory.Sequence(lambda n: f"Achievement {n}")
    type_name = "achievement"
    received_at = factory.LazyFunction(lambda: datetime.now())


class DonationFactory(BaseFactory):
    """Фабрика донатов."""

    class Meta:
        """Метакласс с настройками."""

        model = Donation

    status = DonationStatus.WAITING_FOR_CONFIRMATION.value
    amount = 1
    sender_id = factory.LazyAttribute(
        lambda obj: create_id_by_attribute(UserFactory)
    )
    first_currency_id = factory.LazyAttribute(
        lambda obj: create_id_by_attribute(CurrencyFactory)
    )


class OperatorFactory(BaseFactory):
    """Фабрика оператора."""

    class Meta:
        """Метакласс с настройками."""

        model = Operator

    name = factory.Sequence(lambda n: f"name{n}")
    email = factory.Sequence(lambda n: f"operator{n}@test.com")
    is_active = True
    is_superuser = True
    password = factory.LazyFunction(lambda: settings.HASHER.hash("test1234"))


class CategoryFactory(BaseFactory):
    """Фабрика категорий."""

    class Meta:
        """Метакласс с настройками."""

        model = Category

    title_cat = factory.Sequence(lambda n: f"Title {n}")
    image = factory.Sequence(lambda n: f"link {n}")


class DreamFactory(BaseFactory):
    """Фабрика мечт."""

    class Meta:
        """Метакласс с настройками."""

        model = Dream

    status = DreamStatus.ACTIVE.value
    title = factory.Sequence(lambda n: f"Dream {n}")
    collected = 0
    description = "description"
    picture = factory.Sequence(lambda n: f"link {n}")
    type_dream = DreamType.USER.value
    goal = 99999
    currency_id = factory.LazyAttribute(
        lambda obj: create_id_by_attribute(CurrencyFactory)
    )
    category_id = factory.LazyAttribute(
        lambda obj: create_id_by_attribute(CategoryFactory)
    )
    user_id = factory.LazyAttribute(
        lambda obj: create_id_by_attribute(UserFactory)
    )


class CountryLanguageFactory(BaseFactory):
    """Фабрика стран."""

    class Meta:
        """Метакласс с настройками."""

        model = CountryLanguage

    title = factory.Sequence(lambda n: f"Страна {n}")
    language = "en"


class CountryBaseFactory(BaseFactory):
    """Фабрика базовой модели страны."""

    class Meta:
        """Метакласс с настройками."""

        model = Country

    is_active = True


class NewsFactory(BaseFactory):
    """Фабрика новостей."""

    class Meta:
        """Метакласс с настройками."""

        model = Post

    title = factory.Sequence(lambda n: f"Title {n + 1}")
    markup_text = factory.Sequence(lambda n: f"markup_text {n + 1}")
    is_published = True
    text = factory.Sequence(lambda n: f"Text {n + 1}")
    tags = []
    created_at = factory.LazyFunction(lambda: datetime.now())
    published_date = datetime.today().date()
    language = "en"


class DonateSizeFactory(BaseFactory):
    """Фабрика размеров донатов."""

    class Meta:
        """Метакласс с настройками."""

        model = DonateSize


class DreamFormFactory(BaseFactory):
    """Фабрика форм мечт."""

    class Meta:
        """Метакласс с настройками."""

        model = DreamForm

    currency_id = factory.LazyAttribute(
        lambda obj: create_id_by_attribute(CurrencyFactory)
    )


class EventsFactory(BaseFactory):
    """Фабрика событий."""

    class Meta:
        """Метакласс с настройками."""

        model = Event


class NotificationsFactory(BaseFactory):
    """Фабрика уведомлений."""

    class Meta:
        """Метакласс с настройками."""

        model = Notification


class ReviewFactory(BaseFactory):
    """Фабрика уведомлений."""

    class Meta:
        """Метакласс с настройками."""

        model = Review

    name = factory.Sequence(lambda n: f"name {n}")
    photo = factory.Sequence(lambda n: f"link {n}")
    text = factory.Sequence(lambda n: f"text {n}")
    is_active = True
    lang = "en"
