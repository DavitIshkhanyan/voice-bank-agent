PYTHON ?= python3

.PHONY: ingest test api

ingest:
	cd services/scraper && $(PYTHON) -m pip install -r requirements.txt && $(PYTHON) scrape_and_ingest.py

test:
	$(PYTHON) -m pip install -r requirements-dev.txt
	$(PYTHON) -m pip install -r services/retrieval-api/requirements.txt
	pytest -q

api:
	cd services/retrieval-api && $(PYTHON) -m pip install -r requirements.txt && uvicorn app.main:app --reload --port 8000
