#!/usr/bin/env bash

wait-for-it postgres:5432 -t 60

alembic -c /etc/dataset/alembic.ini upgrade head

uvicorn dataset.app:application --reload --port 8080 --host 0.0.0.0
