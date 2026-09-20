.PHONY: run test lint ruff

run:
	python -m kinotyk

test:
	pytest -q

lint:
	python tools/lint.py
	python -m compileall -q kinotyk tests

ruff:
	ruff check .
	ruff format --check .
