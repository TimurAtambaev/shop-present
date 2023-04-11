"""Module for migrations.
Used to track changes in db schema automatically.
Extend if new modules with models added."""
from .achievement import Achievement
from .admin_settings import AdminSettings
from .application import (
    application,
    oauth2_authorization_code,
    oauth2_token,
    referent_level,
)
from .country import Country, CountryLanguage
from .currency import Currency
from .default_message import StandartMessage
from .donate_size import DonateSize
from .donation import Donation
from .dream import Category, Dream
from .dream_form import DreamForm
from .event import Event
from .message import Message
from .notification import Notification
from .operator import Operator
from .order import order
from .payment_data import BasePaymentData
from .payment_type import payment_type
from .post import post
from .review import Review
from .user import User, user_history
