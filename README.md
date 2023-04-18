# Shop-present

Online Gift Shop API (pet project).

## Requirements

* [Docker](https://docs.docker.com/)
* [docker-compose](https://docs.docker.com/compose/)

## Running

Before running make sure port 8080 isn't used by other app.

```bash
$ cd shop-present
$ docker network create shop-net
$ docker-compose up --build --remove-orphans
```

API available on localhost:8080. Documentation: localhost:8080/docs.