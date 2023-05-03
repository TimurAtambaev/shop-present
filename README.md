# Shop-present

Online Gift Shop API (pet project).

## Requirements

* [Docker](https://docs.docker.com/)
* [docker-compose](https://docs.docker.com/compose/)

## Running

```bash
$ cd shop-present
$ cp .env.example .env
$ docker network create shop-net
$ docker-compose up --build
```

API available on localhost:8080. Documentation: localhost:8080/docs.
