"""Пакет с таблицами."""
from sqlalchemy.orm import declarative_base

Base = declarative_base()

from dataset.tables.kit import *  # noqa F401
