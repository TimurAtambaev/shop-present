# Gold Stream

Goldstream app to handle social network with mlm elements.

# Requirements

To run app you'll need:

* Linux based [Docker](https://docs.docker.com/)
* [docker-compose](https://docs.docker.com/compose/)

## Running

## Developer environment

At first, create docker network
```bash
$ docker network create nacometa-net
```

### Goldstream
Before running make sure port 8080 isn't used by other app.

Go to `goldstream` dir.

```bash
cd dataset
docker-compose up --build --remove-orphans
```

Base url for operators requests(graphiql app for debugging if enabled):
http://localhost:8080/g/1.0
Base url for public requests(graphiql app for debugging if enabled):
http://localhost:8080/api/g/1.0
### How to run tests
```bash
docker-compose exec app pytest -v --disable-warnings tests
```
### How to run linter checks
```bash
docker-compose exec app pylint dataset
```
### Database migration
After adding new tables to database or making any changes in existing ones, you should make database migration.
```bash
docker-compose exec app migrations revision -m "Message that describes your changes" --autogenerate
```
Don't forget to rerun the app after that



