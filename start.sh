#!/usr/bin/env bash
alembic -c /etc/dataset/alembic.ini upgrade head

uvicorn dataset.app:application --reload --port 8080 --host 0.0.0.0
