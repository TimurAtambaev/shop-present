# Shop-present

Online Gift Shop API (pet project).

# Requirements

* [Docker](https://docs.docker.com/)
* [docker-compose](https://docs.docker.com/compose/)

## Running

## Developer environment

At first, create docker network
```bash
$ docker network create shop-net
```

### Goldstream
Before running make sure port 8080 isn't used by other app.

Go to `dataset` dir.

```bash
cd dataset
docker-compose up --build --remove-orphans
```
