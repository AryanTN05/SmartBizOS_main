# SmartBiz-OS — Enrichment Engine Backend

AI-powered lead enrichment and scoring backend using LiteLLM, Gemini 3 Flash, and Firecrawl.

## Quick Start

### 1. Prerequisites
- Python 3.12+
- A [Neon](https://neon.tech) PostgreSQL database (schema already applied)
- API keys: [Google AI Studio](https://aistudio.google.com/), [Firecrawl](https://www.firecrawl.dev/app)

### 2. Setup

```bash
cd backend

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # macOS/Linux

# Install dependencies
pip install -r requirements.txt

cd enrichment_engine

# Configure environment
cp .env.example .env
# Edit .env with your actual keys
```

### 3. Run the Dev Server

```bash
uvicorn main:app --reload --port 8000
```

### 4. Seed the Gold Batch

```bash
python -m scripts.seed_gold_batch
```

This inserts 10 AI/tech companies, enriches each via the Gemini agent, and scores them. Note: since this script runs serially and relies on deep scraping, it can take ~20 minutes to complete.

---

## API Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/health` | Health check |
| `GET` | `/api/leads` | List leads (query: `tenant_id`, `status`, `limit`, `offset`) |
| `GET` | `/api/leads/{id}` | Get lead + enrichment |
| `POST` | `/api/leads` | Create new lead |
| `POST` | `/api/leads/{id}/enrich` | Trigger enrichment pipeline |
| `GET` | `/api/leads/{id}/enrichment` | Get enrichment dossier |
| `GET` | `/api/leads/{id}/activity` | Activity timeline |
| `GET` | `/api/leads/{id}/scores` | Score history |
| `GET` | `/stream/enrich/{id}` | SSE enrichment stream |

### SSE Stream Events

```
data: {"status": "searching",  "message": "Grounding query via Google Search..."}
data: {"status": "scraping",   "message": "Extracting intelligence for Acme Corp..."}
data: {"status": "enriching",  "message": "Processing enrichment data..."}
data: {"status": "scoring",    "message": "Calculating lead score..."}
data: {"status": "complete",   "message": "Enrichment finished", "data": {...}}
```

---

## Cloud Run Deployment

```bash
# Build container
docker build -t enrichment-engine .

# Tag for GCR
docker tag enrichment-engine gcr.io/YOUR_PROJECT/enrichment-engine

# Push
docker push gcr.io/YOUR_PROJECT/enrichment-engine

# Deploy (free tier config)
gcloud run deploy enrichment-engine \
  --image gcr.io/YOUR_PROJECT/enrichment-engine \
  --region us-central1 \
  --min-instances 0 \
  --max-instances 1 \
  --memory 512Mi \
  --set-secrets="GOOGLE_API_KEY=GOOGLE_API_KEY:latest,FIRECRAWL_API_KEY=FIRECRAWL_API_KEY:latest,DATABASE_URL=DATABASE_URL:latest" \
  --allow-unauthenticated
```

---

## Architecture

```
main.py (FastAPI)
  ├── /api/leads/*          → CRUD via SQLAlchemy → Neon PostgreSQL
  ├── /api/leads/{id}/enrich→ Runs FastAPI Background Task
  ├── /stream/enrich/{id}   → SSE (inline agent run)
  └── enrich_lead_pipeline (background task)
        ├── 1. fetch-lead
        ├── 2. mark-enriching
        ├── 3. run-enrichment  → LiteLLM + Gemini 3 Flash
        │     ├── WebSearchTool (Google Search grounding)
        │     └── deep_scrape_domain (Firecrawl)
        ├── 4. save-enrichment → enrichment table
        ├── 5. score-lead      → LiteLLM scoring agent
        ├── 6. save-score      → score_history + leads.score
        └── 7. log-activity    → activity_log
```
