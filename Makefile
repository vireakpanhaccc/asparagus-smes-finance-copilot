.PHONY: setup seed reseed api web test lint evidence up

# The owner token from .env (data endpoints require it). Override: make evidence TOKEN=...
TOKEN ?= demo-owner-token

setup:            ## install backend + frontend deps
	cd backend && pip install -e ".[dev]"
	cd frontend && npm install

seed:             ## load sample data (keeps existing data)
	cd backend && python -m scripts.seed_data

reseed:           ## wipe and reload sample data (also clears the audit log)
	cd backend && python -m scripts.seed_data --force

api:              ## run the API on :8000
	cd backend && uvicorn app.main:app --reload

web:              ## run the UI on :3000
	cd frontend && npm run dev

test:             ## run backend tests
	cd backend && pytest -v

lint:
	cd backend && ruff check .
	cd frontend && npm run typecheck

evidence:         ## export audit log + test report into evidence/
	curl -sf -H "X-Owner-Token: $(TOKEN)" http://localhost:8000/api/audit/export.csv -o evidence/audit_log.csv
	curl -sf -H "X-Owner-Token: $(TOKEN)" http://localhost:8000/api/audit/verify -o evidence/audit_chain_verify.json
	cd backend && pytest -v > ../evidence/test_report.txt

up:               ## everything in Docker
	docker compose up --build
