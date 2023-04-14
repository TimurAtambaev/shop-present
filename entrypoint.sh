#!/usr/bin/env sh

set -e

alembic -c /etc/alembic.ini upgrade head
