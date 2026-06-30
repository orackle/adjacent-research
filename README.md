# Interlace — Research Intelligence Platform

Interlace is a research intelligence platform with two modes:

**Adjacent Mapper** — Scans research publications, scores novelty, citation velocity, and disruptiveness (CD index), then maps where a technology could plausibly be applied next — ranked by adoption urgency × feasibility.

**Lineage Tracer** *(new)* — Given a research topic, traces the intellectual lineage through the citation graph: retrieves seed papers, expands a BFS subgraph (3 hops), detects "bridge" papers that connected ideas across time, sorts them chronologically, and synthesises a Gemini-written narrative explaining HOW each paper built on the last — then predicts the 3 most likely frontier directions.

## Architecture

```
Ingestion Pipeline
  └─ Semantic Scholar / OpenAlex → Papers + Citation Edges → SQLite

Adjacent Mapper  (GET /map)
  └─ LLM field generation → feasibility scoring → ranked adjacency cards

Lineage Tracer  (GET /trace)
  └─ Dense retrieval → BFS graph expansion → bridge detection
     → temporal sort → Gemini narrative → frontier prediction
```

## Directory Structure

- `backend/` — FastAPI/Flask server
  - `main.py` — All API endpoints (`/search`, `/map`, `/trace`, `/internal/*`)
  - `database.py` — SQLAlchemy models: `Paper`, `CitationEdge`
  - `graph.py` — Citation graph builder, BFS expansion, bridge detection
  - `chain.py` — Temporal RAG synthesis pipeline
  - `novelty.py` — LLM-as-judge novelty scorer
  - `mapper.py` — Adjacent-possible mapper (multi-step LLM pipeline)
  - `scripts/ingest_papers.py` — Paper + citation edge ingestion
- `frontend/` — Next.js dashboard
  - `app/page.tsx` — Dual-tab UI: Adjacent Mapper + Lineage Tracer

## Getting Started

### 1. Setup Environment Variables
Create a `.env` file in the root directory:
```env
GEMINI_API_KEY=your_gemini_api_key_here
S2_API_KEY=optional_semantic_scholar_api_key
GROQ_API_KEY=optional_groq_api_key
```

### 2. Launch the Backend
```bash
# From repo root, using the venv:
venv\Scripts\python.exe backend\main.py
# Or:
cd backend
pip install -r requirements.txt
python main.py
```
The backend runs at `http://localhost:8000`.

### 3. Run Ingestion (Populate Database)
```bash
# Full ingestion (papers + embeddings + citation edges):
curl -X POST http://localhost:8000/internal/run_ingestion

# Citation edges only (if you already have papers):
curl -X POST http://localhost:8000/internal/ingest_edges
```

### 4. Run the Frontend
```bash
cd frontend
npm install
npm run dev
```
Open `http://localhost:3000`.

## New Endpoints

| Endpoint | Description |
|---|---|
| `POST /trace` | Trace intellectual lineage — returns chain, narrative, transitions, frontier |
| `POST /internal/ingest_edges` | Populate citation graph from Semantic Scholar references |

## The Lineage Tracer — How It Works

1. **Dense retrieval** — embeds query, cosine-similarity top-30 seed papers
2. **Live edge enrichment** — fetches references from S2 API for seeds not yet in graph
3. **BFS expansion** — explores citation graph 3 hops out (up to 200 nodes)
4. **Bridge detection** — scores nodes by in-degree + out-degree within subgraph (hub score)
5. **Temporal sort** — orders bridge papers chronologically by year
6. **Narrative synthesis** — Gemini writes a causal "how each paper built on the last" narrative
7. **Frontier prediction** — Gemini predicts 3 frontier directions with time horizons
