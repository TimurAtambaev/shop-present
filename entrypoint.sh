#!/usr/bin/env sh

set -e

alembic -c /etc/dataset/alembic.ini upgrade head
