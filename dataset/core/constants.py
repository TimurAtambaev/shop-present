"""Constants used in core of app."""
import re
from enum import Enum


class AppEnvironment(Enum):
    """Class represents app environments."""

    LOCAL = "local"
    TEST = "test"
    PRODUCTION = "prod"
    DEVELOPMENT = "dev"
    STAGING = "staging"


TRUE_VALUES = (
    "1",
    "true",
)

R_EMAIL_PATTERN = re.compile("^.+@.+$", re.I)
R_COLOR_PATTERN = re.compile(r"^#[\dA-F]{8}$", re.I)
AWS_EXPIRES_IN = 3600
AWS_FORMAT_IMG_PATTERN = re.compile("^(image/pjpeg|image/jpeg|image/png)")
AWS_FORMAT_IMG_TYPES_FOR_DONATION_LIST = (
    "image/pjpeg",
    "image/jpeg",
    "image/png",
    "application/doc",
    "application/docx",
    "application/pdf",
    "application/xls",
    "application/xlsx",
)
SUPPORT_EMAIL = "support@ufandao.com"
