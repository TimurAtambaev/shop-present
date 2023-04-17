# Shop-present

Online Gift Shop API (pet project).

# Requirements

* [Docker](https://docs.docker.com/)
* [docker-compose](https://docs.docker.com/compose/)

## Running

Before running make sure port 8080 isn't used by other app.

```bash
$ docker network create shop-net
cd dataset
docker-compose up --build --remove-orphans
```
