format:
	poetry run isort goldstream/
	poetry run isort tests/
	poetry run black goldstream/
	poetry run black tests/

tests: tests_python

check:
	poetry run isort goldstream --check
	poetry run isort tests --check
	poetry run flake8 goldstream
	poetry run flake8 tests
	poetry run black goldstream --check
	poetry run black tests --check

tests_python:
	poetry run pytest --cov-report xml --cov goldstream -n 4 tests
