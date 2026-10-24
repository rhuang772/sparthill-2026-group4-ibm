.PHONY: run test seed

## Start the API (offline simulator + local files by default)
run:
	uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

## Run the test suite
test:
	pytest -v

## Seed the local Chroma rules corpus from rules/seed_rules.json
seed:
	python -m app.rules.chroma_dummy
