.PHONY: install run clean test lint all fix-all check-all fix-format check-format fix-lint check-lint check-types test-coverage test-system docker-build docker-shell

# Define Python interpreter
PYTHON = python

all: fix-all check-all
fix-all: fix-format fix-lint
check-all: check-format check-lint check-types 
test: test-coverage 

# Install dependencies
install:
	pip install --upgrade -r requirements.txt
	pip install --upgrade -r requirements-dev.txt
install-dev:
	pip install --upgrade -r requirements-dev.txt

fix-format:
	ruff format .

check-format:
	ruff format --diff .

fix-lint:
	ruff check --fix .

lint:
	ruff check .
	black .


test-coverage:
	pytest \
		--cov=bookabl \
		--junit-xml=tests.xml \
		--cov-report=xml:coverage.xml \
		--cov-report=html \
		--cov-report=term-missing \
		tests/unit \
		tests/integration

# Run the application
run:
	$(PYTHON) main.py

# Clean up python cache files
clean:
	find . -type f -name "*.pyc" -delete
	find . -type d -name "__pycache__" -delete
	find . -type d -name ".pytest_cache" -delete

create-venv:
	python -m venv .venv

activate:
	source .venv/bin/activate

dev:
	PYTHONPATH=. uvicorn main:app --reload --log-level debug --use-colors

