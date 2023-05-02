"""Модуль с инструментами для тестов."""
import os
from argparse import Namespace
from contextlib import contextmanager
from types import SimpleNamespace
from typing import Optional, Union

from alembic.config import Config
from sqlalchemy_utils import create_database, drop_database
from sqlalchemy_utils.functions import database_exists
from yarl import URL

from dataset.config import settings


@contextmanager
def get_tmp_database(**kwargs: dict) -> str:
    """Создать временную бд для тестов."""
    if kwargs.get("template"):
        db_url = URL(settings.DB_URI).path.replace("_template_", "_test_")
    else:
        db_url = URL(settings.DB_URI).path.replace("_test_", "_template_")

    tmp_db_url = str(URL(settings.DB_URI).with_path(db_url))

    if database_exists(tmp_db_url):
        drop_database(tmp_db_url)
    create_database(tmp_db_url, **kwargs)
    try:
        yield tmp_db_url
    finally:
        if database_exists(tmp_db_url):
            drop_database(tmp_db_url)


def make_alembic_config(
    cmd_opts: Union[Namespace, SimpleNamespace],
    base_path: str = settings.BASE_DIR,
) -> Config:
    """Подготовка конфига алембика для тестов."""
    # Replace path to migrations.ini file to absolute
    if not os.path.isabs(cmd_opts.config):
        cmd_opts.config = os.path.join(base_path, cmd_opts.config)

    config = Config(
        file_=cmd_opts.config, ini_section=cmd_opts.name, cmd_opts=cmd_opts
    )

    # Replace path to migrations folder to absolute
    alembic_location = config.get_main_option("script_location").replace(
        ":", "/"
    )
    if not os.path.isabs(alembic_location):
        config.set_main_option(
            "script_location", os.path.join(base_path, alembic_location)
        )
    if cmd_opts.pg_url:
        config.set_main_option("sqlalchemy.url", cmd_opts.pg_url)

    return config


def alembic_config_from_url(pg_url: Optional[str] = None) -> Config:
    """Подготовка конфига из ссылки на БД."""
    cmd_options = SimpleNamespace(
        config="migrations.ini",
        name="migrations",
        pg_url=pg_url,
        raiseerr=False,
        x=None,
    )
    return make_alembic_config(cmd_options)
