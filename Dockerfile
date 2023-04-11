FROM python:3.9.1-slim

RUN apt-get update && \
  apt-get install --no-install-recommends -y postgresql postgresql-contrib python-psycopg2 libpq-dev gcc musl-dev libc-dev libffi-dev libssl-dev cargo wget make wait-for-it curl git \
  && apt-get clean \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /srv/app

COPY start.sh ./
COPY poetry.lock pyproject.toml ./
COPY entrypoint.sh /usr/local/bin/app

ENV PATH="${PATH}:/root/.local/bin"
RUN pip install --no-cache-dir --upgrade pip && \
    curl -sSL https://install.python-poetry.org | python3 - && \
    poetry config virtualenvs.create false && \
    poetry install --no-cache

COPY tests /srv/app/tests
COPY dataset /srv/app/dataset

EXPOSE 8080

CMD ["/bin/bash", "start.sh"]

ENV TZ="UTC"
