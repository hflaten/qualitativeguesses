.PHONY: dev test lint typecheck api watcher worker smoke

PYTHON ?= python3
PYTHON_ENV = PYTHONDONTWRITEBYTECODE=1 PYTHONPYCACHEPREFIX=.pycache

dev: api

api:
	uvicorn qualstocks.main:app --host 0.0.0.0 --port $${PORT:-8000} --reload

watcher:
	$(PYTHON_ENV) $(PYTHON) -m qualstocks.watcher

worker:
	$(PYTHON_ENV) $(PYTHON) -m qualstocks.worker

smoke:
	$(PYTHON_ENV) $(PYTHON) -m qualstocks.runtime_smoke

test:
	$(PYTHON_ENV) $(PYTHON) -m unittest discover -s tests

lint:
	ruff check src tests

typecheck:
	$(PYTHON_ENV) $(PYTHON) -m compileall -q src tests
