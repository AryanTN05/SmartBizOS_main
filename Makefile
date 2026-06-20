# SmartBiz OS — common dev commands.

.PHONY: help db db-stop db-reset backend frontend test test-backend test-frontend seed verify-deploy deploy-backend deploy-render deploy-frontend

help:
	@echo "SmartBiz OS — Make targets"
	@echo "  db                start Postgres + pgvector via docker compose"
	@echo "  db-stop           stop the local Postgres"
	@echo "  db-reset          stop, drop volume, restart, re-apply schema, re-seed"
	@echo "  seed              load seed data (requires db running + schema applied)"
	@echo "  backend           run the FastAPI app on :8000 (uvicorn --reload)"
	@echo "  frontend          run the Vite dev server on :5173"
	@echo "  test              run backend pytest + frontend vitest"
	@echo "  test-backend      pytest only"
	@echo "  test-frontend     vitest only"
	@echo "  verify-deploy     local dry-run of the deploy build (docker + vite) before pushing"
	@echo "  deploy-backend    Cloud Run (with-CC path — set GCP_REGION + GCP_PROJECT)"
	@echo "  deploy-render     Render (no-CC path — git push triggers deploy via render.yaml)"
	@echo "  deploy-frontend   vercel --prod"

db:
	docker compose up -d
	@echo "Postgres up at localhost:5432 (smartbiz/smartbiz/smartbiz)"

db-stop:
	docker compose down

db-reset:
	docker compose down -v
	docker compose up -d
	@echo "Waiting for db to accept connections..."
	@until docker compose exec -T db pg_isready -U smartbiz -d smartbiz >/dev/null 2>&1; do sleep 1; done
	docker compose exec -T db psql -U smartbiz -d smartbiz < backend/db/schema.sql
	$(MAKE) seed

seed:
	cd backend && \
		.venv/bin/python -m scripts.seed_all

backend:
	cd backend && \
		JWT_SECRET=$${JWT_SECRET:-dev-secret-change-me} \
		ADMIN_USERS_JSON='$${ADMIN_USERS_JSON:-[]}' \
		.venv/bin/uvicorn main:app --reload --port $${BACKEND_PORT:-8000}

frontend:
	cd frontend && npm run dev

test: test-backend test-frontend

test-backend:
	cd backend && .venv/bin/python -m pytest tests/ -q

test-frontend:
	cd frontend && npm test

deploy-backend:
	@: $${GCP_REGION:?set GCP_REGION (e.g. asia-south1)}
	@: $${GCP_PROJECT:?set GCP_PROJECT}
	gcloud builds submit backend --tag $${GCP_REGION}-docker.pkg.dev/$${GCP_PROJECT}/smartbiz/api
	gcloud run deploy smartbiz-api \
		--image $${GCP_REGION}-docker.pkg.dev/$${GCP_PROJECT}/smartbiz/api \
		--region $${GCP_REGION} \
		--allow-unauthenticated \
		--port 8000

verify-deploy:
	@echo "==> Building backend Docker image..."
	docker build -t smartbiz-api:verify backend
	@echo "==> Running container, smoke-testing /health..."
	docker run --rm -d --name smartbiz_api_verify -p 8002:8000 \
		-e DATABASE_URL=postgresql+asyncpg://localhost/x \
		-e JWT_SECRET=test -e ADMIN_USERS_JSON='[]' -e INNGEST_DEV=1 \
		smartbiz-api:verify
	@sleep 5
	@curl -fs http://127.0.0.1:8002/health || (docker stop smartbiz_api_verify && exit 1)
	@docker stop smartbiz_api_verify >/dev/null
	@echo "==> Building frontend bundle..."
	cd frontend && VITE_API_BASE_URL=$${VITE_API_BASE_URL:-https://smartbiz-api.onrender.com} npm run build
	@echo "==> Deploy verification passed — both images build + boot."

deploy-render:
	@echo "Render auto-deploys on push to main (autoDeploy: true in render.yaml)."
	@echo "First-time setup:"
	@echo "  1. Push render.yaml to main (already done if you're seeing this)."
	@echo "  2. https://dashboard.render.com → New → Blueprint → connect repo."
	@echo "  3. Set DATABASE_URL, JWT_SECRET, ADMIN_USERS_JSON in dashboard env."
	@echo "  4. Subsequent deploys: just 'git push origin main'."
	git push origin main

deploy-frontend:
	cd frontend && npx vercel --prod
