# Low-Level Architecture — Adjacency Research Engine v2.0

**Status:** Reference document for the v2.0 rebuild  
**Last updated:** 2026-06-30  
**Baseline:** PRD (`docs/prd.md`), existing `backend/` + `frontend/` codebase

---

## 1. Folder Structure

```
adjacency/
│
├── .github/
│   └── workflows/
│       ├── weekly_ingest.yml          # Scheduled: fetch, embed, build FAISS, precompute
│       └── deploy.yml                 # On artifact commit: trigger Vercel redeploy
│
├── backend/                           # Python API — Vercel Serverless Functions (or local Flask)
│   ├── main.py                        # [MODIFY] FastAPI app; route definitions; cache-first dispatch
│   ├── database.py                    # [MODIFY] SQLAlchemy models — add new tables (concepts, precomputed_*)
│   ├── graph.py                       # [KEEP] Pure-Python CitationGraph, BFS, bridge detection, temporal sort
│   ├── chain.py                       # [MODIFY] Lineage RAG pipeline — swap Gemini for Groq + prompt templates
│   ├── novelty.py                     # [KEEP] CD-index and novelty scoring helpers
│   ├── mapper.py                      # [MODIFY] Adjacent-possible mapper — integrate FAISS + concept walker
│   │
│   ├── engines/                       # [NEW] One module per retrieval engine
│   │   ├── __init__.py
│   │   ├── semantic.py                # FAISS nearest-neighbour search (sentence-transformers index)
│   │   ├── concept_walker.py          # OpenAlex concept sibling/co-occurrence gap detection
│   │   ├── citation_bridge.py         # Wraps graph.py bridge detection; returns ranked paper IDs
│   │   └── orchestrator.py            # Blends engine outputs → unified ranked result list
│   │
│   ├── llm/                           # [NEW] All LLM interactions, isolated and testable
│   │   ├── __init__.py
│   │   ├── client.py                  # Groq API client (free tier); retry + rate-limit handling
│   │   ├── parser.py                  # Pydantic schema validation; retry loop on bad JSON
│   │   └── schemas.py                 # Pydantic models: IdeaOutput, LineageOutput, FrontierOutput
│   │
│   ├── prompts/                       # [NEW] Version-controlled prompt templates (plain text)
│   │   ├── adjacent_synthesis.txt
│   │   ├── lineage_narrative.txt
│   │   └── frontier_prediction.txt
│   │
│   ├── cache/                         # [NEW] Cache management layer
│   │   ├── __init__.py
│   │   ├── lookup.py                  # Hash query → check precomputed_* tables; return hit/miss
│   │   └── writer.py                  # Store new precomputed result + log cache miss for backfill
│   │
│   ├── scripts/
│   │   ├── ingest_papers.py           # [MODIFY] Replace S2 edges with OpenAlex referenced_works
│   │   ├── ingest_concepts.py         # [NEW] Fetch OpenAlex concept taxonomy → populate `concepts` table
│   │   ├── build_faiss.py             # [NEW] Read embeddings from DB → write index.faiss + id_map.json
│   │   └── precompute.py              # [NEW] Batch: top seeds → run engines + LLM → store in DB cache
│   │
│   ├── data/
│   │   ├── index.faiss                # Binary FAISS index (committed artifact, rebuilt weekly)
│   │   ├── id_map.json                # Maps FAISS row index → corpus_id
│   │   └── concepts.csv               # OpenAlex concept taxonomy snapshot
│   │
│   ├── requirements.txt               # [MODIFY] Add: faiss-cpu, sentence-transformers, groq, pydantic v2
│   └── breakthrough_radar.db          # SQLite — read-only in production, rebuilt weekly by pipeline
│
├── frontend/                          # Next.js 14 (App Router) — static export to Vercel CDN
│   ├── app/
│   │   ├── layout.tsx                 # Root layout: fonts, global providers, nav
│   │   ├── page.tsx                   # [MODIFY] Landing / search entry point (currently monolithic — split out)
│   │   ├── globals.css
│   │   │
│   │   ├── map/
│   │   │   └── page.tsx               # [NEW] Adjacent Mapper page
│   │   │
│   │   ├── trace/
│   │   │   └── page.tsx               # [NEW] Lineage Tracer page
│   │   │
│   │   └── api/                       # Next.js API routes (thin proxy to Python backend)
│   │       ├── map/
│   │       │   └── route.ts           # POST /api/map → Python /map
│   │       ├── trace/
│   │       │   └── route.ts           # POST /api/trace → Python /trace
│   │       ├── search/
│   │       │   └── route.ts           # POST /api/search → Python /search
│   │       └── feedback/
│   │           └── route.ts           # POST /api/feedback → Firestore write
│   │
│   ├── components/
│   │   ├── ui/                        # Primitive design-system components
│   │   │   ├── Button.tsx
│   │   │   ├── Card.tsx
│   │   │   ├── Badge.tsx
│   │   │   ├── Spinner.tsx
│   │   │   └── Tooltip.tsx
│   │   │
│   │   ├── search/
│   │   │   ├── SearchBar.tsx          # Shared query input with debounce
│   │   │   └── WeightSliders.tsx      # Velocity / novelty / CD-index weight controls
│   │   │
│   │   ├── mapper/
│   │   │   ├── IdeaCard.tsx           # Renders one adjacent idea (title, description, confidence, sources)
│   │   │   ├── IdeaGrid.tsx           # Grid of IdeaCards with sort/filter controls
│   │   │   └── EngineTag.tsx          # Badge showing which engine(s) sourced this idea
│   │   │
│   │   ├── tracer/
│   │   │   ├── PaperNode.tsx          # Single paper in the lineage chain
│   │   │   ├── LineageTimeline.tsx    # Chronological chain of PaperNodes with transition labels
│   │   │   ├── CitationGraph.tsx      # SVG force-directed mini-graph of the BFS subgraph
│   │   │   ├── NarrativePanel.tsx     # LLM-written causal paragraph
│   │   │   └── FrontierCards.tsx      # 3 prediction cards with horizon badge
│   │   │
│   │   └── shared/
│   │       ├── EvidenceDrawer.tsx     # Slide-in panel: papers/concepts behind a suggestion
│   │       ├── FeedbackButtons.tsx    # Upvote / downvote → /api/feedback
│   │       ├── ShareButton.tsx        # Generates shareable URL with result hash
│   │       └── LastUpdatedBadge.tsx   # "Data last updated: <date>" pulled from DB metadata
│   │
│   ├── lib/
│   │   ├── api.ts                     # Typed fetch wrappers for all /api/* routes
│   │   ├── firebase.ts                # Firebase client init (Firestore for feedback)
│   │   ├── types.ts                   # Shared TypeScript interfaces (IdeaResult, LineageResult, Paper…)
│   │   └── utils.ts                   # Hashing, formatting, truncation helpers
│   │
│   ├── hooks/
│   │   ├── useMap.ts                  # SWR hook: POST /api/map, manage loading/error state
│   │   ├── useTrace.ts                # SWR hook: POST /api/trace
│   │   └── useSearch.ts              # SWR hook: POST /api/search
│   │
│   ├── next.config.js                 # [MODIFY] output: 'export' for static deploy
│   ├── package.json
│   └── tsconfig.json
│
├── docs/
│   ├── prd.md
│   ├── architecture.md                # ← this file
│   ├── component-tree.md
│   ├── testing-strategy.md
│   └── error-handling.md
│
├── .env                               # Local secrets (never committed)
├── docker-compose.yml                 # Local full-stack dev: backend + SQLite volume
├── README.md
└── walkthrough.md
```

---

## 2. Technology Choices & Justifications

### Backend

| Technology | Choice | Justification |
|---|---|---|
| **Web framework** | FastAPI (migrate from Flask) | Async support; auto-generated OpenAPI docs; Pydantic integration; better fit for Vercel serverless Python runtime |
| **Database** | SQLite (via SQLAlchemy) | Zero hosting cost; single binary file; read-only in production — perfectly suited to static artifact pattern |
| **Vector index** | FAISS (`faiss-cpu`) | In-memory ANN; no network hop; binary file committed with code; loads in ~50ms serverless cold start |
| **Embeddings** | `sentence-transformers` / `all-MiniLM-L6-v2` | Runs locally; 0 API cost; 384-dim vectors (vs 3072 for Gemini) → 8× smaller FAISS index |
| **LLM** | Groq API (`llama-3.3-70b-versatile`) | Free tier; 500 req/day; used *only* offline (precompute) and rare on-demand cache-miss fallback |
| **Prompt management** | Plain-text template files + Python `.format()` | Version-controllable; diff-friendly; no framework lock-in |
| **Schema validation** | Pydantic v2 | Enforces JSON contract on LLM output; enables retry loop; zero runtime cost |
| **Data source** | OpenAlex (papers + concepts + citation edges) | Free, no API key, polite use; 200M+ works; replaces Semantic Scholar |

### Frontend

| Technology | Choice | Justification |
|---|---|---|
| **Framework** | Next.js 14 (App Router) | Static export support (`output: 'export'`); API routes as thin proxies; existing codebase |
| **Language** | TypeScript | Type safety for API contract shared with backend schemas |
| **Styling** | Tailwind CSS | Already configured; utility-first for rapid iteration |
| **State / fetching** | SWR | Stale-while-revalidate; deduplicated requests; optimistic UI; lightweight |
| **Graph visualisation** | Custom SVG (existing) | No D3 dependency; keeps bundle lean; sufficient for citation subgraph rendering |
| **User feedback** | Firebase Firestore (free tier) | 1 GB / 50k reads per day; simple document writes; no backend session needed |
| **Hosting** | Vercel (static CDN + serverless functions) | Free tier; auto-deploy on git push; matches PRD cost requirement |

### Pipeline / DevOps

| Technology | Choice | Justification |
|---|---|---|
| **Scheduler** | GitHub Actions | 2000 free minutes/month; ~600 min projected; matrix jobs for parallel embedding |
| **Artefact storage** | Git LFS or committed binary | FAISS index + SQLite committed post-build; Vercel picks up on next deploy |

---

## 3. Data Flow: Database → UI

### 3.1 Cached Path (≥90% of requests, target <200ms)

```
User types query
      │
      ▼
[Next.js page] useMap(query) hook
      │  POST /api/map  {technology: query}
      ▼
[Next.js API route] /api/map/route.ts
      │  forwards to Python backend
      ▼
[FastAPI] POST /map
      │
      ├─ 1. SHA-256 hash of normalised query string
      │
      ├─ 2. cache/lookup.py
      │       SELECT idea_json, engines_used, created_at
      │       FROM precomputed_adjacencies
      │       WHERE seed_hash = ?
      │
      ├─ CACHE HIT ──────────────────────────────────────────┐
      │       Return JSON directly                           │
      │       {ideas: [...], engines_used, cached_at}        │
      │                                                      │
      └─ CACHE MISS (rare) ─ see §3.2                        │
                                                             │
      ▼                                                      │
[Next.js page] receives IdeaResult[]  ◄──────────────────────┘
      │
      ▼
[IdeaGrid] renders IdeaCards
      │
      ├── EngineTag (semantic | concept | citation | llm)
      ├── Confidence badge
      └── EvidenceDrawer (on click) — lists source papers & concepts
```

### 3.2 Cache Miss Path (p99 <2s)

```
[FastAPI] /map — cache miss
      │
      ├─ 3. engines/semantic.py
      │       Load FAISS index (in-memory, pre-loaded at startup)
      │       Embed query with all-MiniLM-L6-v2
      │       top-50 ANN neighbours → corpus_ids
      │       Fetch Paper rows from SQLite
      │
      ├─ 4. engines/concept_walker.py
      │       SELECT concept_id FROM paper_concepts WHERE paper_id IN (...)
      │       Find sibling concepts (same parent, low co-occurrence)
      │       Return gap concept list
      │
      ├─ 5. engines/citation_bridge.py
      │       graph.expand_subgraph(seeds, hops=3)
      │       graph.find_bridge_papers(subgraph)
      │       Fetch Paper rows for bridge IDs
      │
      ├─ 6. engines/orchestrator.py
      │       Blend + deduplicate results from engines 3-5
      │       Score: w_semantic + w_concept + w_bridge (configurable)
      │
      ├─ 7. llm/client.py  [OPTIONAL — only if within Groq rate limit]
      │       Render adjacent_synthesis.txt template
      │       POST groq.chat.completions
      │       llm/parser.py validates JSON; retry once on failure
      │
      ├─ 8. cache/writer.py
      │       INSERT INTO precomputed_adjacencies (seed_hash, idea_json, …)
      │       Log miss for background precompute job
      │
      └─ Return result to frontend
```

### 3.3 Lineage Tracer Flow

```
User types query
      │
      ▼
[FastAPI] POST /trace
      │
      ├─ Cache lookup (precomputed_lineages by query_hash)
      │
      ├─ HIT → return {chain, narrative, frontier, pivotal_paper_id}
      │
      └─ MISS:
          │
          ├─ FAISS → seed corpus_ids
          ├─ graph.expand_subgraph(seeds, hops=3)  [graph.py]
          ├─ graph.find_bridge_papers(subgraph)
          ├─ graph.sort_by_year(bridge_papers)
          ├─ Fetch full Paper rows for chain
          │
          ├─ LLM: lineage_narrative.txt → narrative string
          ├─ LLM: frontier_prediction.txt → FrontierOutput[]
          │
          ├─ Write to precomputed_lineages
          └─ Return {chain[], transitions[], pivotal_id, narrative, frontier[]}
```

### 3.4 Precomputation Pipeline (GitHub Actions — weekly)

```
[GH Actions trigger]
      │
      ├─ scripts/ingest_papers.py
      │     OpenAlex API (batch, polite) → new papers + referenced_works
      │     INSERT/UPDATE papers, citation_edges
      │
      ├─ scripts/ingest_concepts.py
      │     OpenAlex concept taxonomy → INSERT/UPDATE concepts, paper_concepts
      │
      ├─ Compute embeddings
      │     sentence-transformers all-MiniLM-L6-v2
      │     UPDATE papers SET embedding = ?
      │
      ├─ scripts/build_faiss.py
      │     SELECT id, embedding FROM papers
      │     Build IndexFlatIP (inner product on normalised vecs)
      │     Write data/index.faiss + data/id_map.json
      │
      ├─ scripts/precompute.py
      │     SELECT top 10,000 papers by citation_count
      │     For each seed:
      │       run engines (semantic + concept_walker + citation_bridge)
      │       call LLM (Groq, batched, rate-limited)
      │       INSERT INTO precomputed_adjacencies
      │       INSERT INTO precomputed_lineages
      │
      └─ git commit data/ + breakthrough_radar.db
         → triggers Vercel auto-deploy
```

---

## 4. Database Schema (SQLite)

```sql
-- Existing (keep, extend)
CREATE TABLE papers (
    id                          INTEGER PRIMARY KEY,
    corpus_id                   TEXT UNIQUE NOT NULL,
    doi                         TEXT,
    arxiv_id                    TEXT,
    title                       TEXT NOT NULL,
    abstract                    TEXT,
    year                        INTEGER,
    fields_of_study             TEXT,          -- JSON array
    citation_count              INTEGER DEFAULT 0,
    citation_velocity           REAL DEFAULT 0,
    influential_citation_count  INTEGER DEFAULT 0,
    cd_index                    REAL,
    novelty_score               REAL,
    breakthrough_score          REAL,
    citation_velocity_percentile REAL DEFAULT 0,
    cd_index_percentile         REAL DEFAULT 0,
    one_line_reason             TEXT,
    context_summary             TEXT,
    embedding                   TEXT,          -- JSON float array (MiniLM, 384-dim)
    source                      TEXT,          -- 'openalex' | 'arxiv'
    last_updated                DATETIME
);

CREATE TABLE citation_edges (
    id                INTEGER PRIMARY KEY,
    source_corpus_id  TEXT NOT NULL,           -- citing paper
    target_corpus_id  TEXT NOT NULL,           -- cited paper
    source_year       INTEGER,
    UNIQUE (source_corpus_id, target_corpus_id)
);

-- New in v2.0
CREATE TABLE concepts (
    concept_id   TEXT PRIMARY KEY,             -- OpenAlex concept ID
    name         TEXT NOT NULL,
    level        INTEGER,                      -- 0=broad … 5=specific
    ancestors    TEXT,                         -- JSON array of concept_ids
    descendants  TEXT                          -- JSON array of concept_ids
);

CREATE TABLE paper_concepts (
    paper_id    TEXT NOT NULL REFERENCES papers(corpus_id),
    concept_id  TEXT NOT NULL REFERENCES concepts(concept_id),
    score       REAL,                          -- OpenAlex relevance score
    PRIMARY KEY (paper_id, concept_id)
);

CREATE TABLE precomputed_adjacencies (
    id           INTEGER PRIMARY KEY,
    seed_hash    TEXT UNIQUE NOT NULL,         -- SHA-256 of normalised query
    seed_text    TEXT,
    idea_json    TEXT NOT NULL,               -- JSON: IdeaOutput[]
    engines_used TEXT,                         -- JSON: ["semantic","concept","llm"]
    created_at   DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE precomputed_lineages (
    id            INTEGER PRIMARY KEY,
    query_hash    TEXT UNIQUE NOT NULL,
    query_text    TEXT,
    chain_json    TEXT NOT NULL,              -- JSON: Paper[] (chronological)
    narrative     TEXT,
    frontier_json TEXT,                       -- JSON: FrontierOutput[]
    pivotal_id    TEXT,
    created_at    DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE db_metadata (
    key   TEXT PRIMARY KEY,
    value TEXT
);
-- e.g. INSERT INTO db_metadata VALUES ('last_ingestion', '2026-06-30T00:00:00Z');
```

---

## 5. API Route Design

### 5.1 Python Backend (FastAPI, port 8000)

| Method | Path | Input | Output | Notes |
|--------|------|-------|--------|-------|
| `POST` | `/map` | `{technology, top_k?, use_cache?}` | `{technology, results: IdeaResult[], cached_at?, engines_used}` | Cache-first; fallback to live engines |
| `POST` | `/trace` | `{query, max_chain?}` | `{chain: Paper[], transitions[], pivotal_id, narrative, frontier: FrontierResult[]}` | Cache-first |
| `POST` | `/search` | `{topic, k?, w_velocity?, w_novelty?, w_cd?}` | `Paper[]` with scores | Breakthrough radar — existing feature |
| `GET`  | `/health` | — | `{status, db_papers, last_ingestion}` | Vercel warmup ping |
| `POST` | `/internal/run_ingestion` | — | `{status}` | Background thread; GH Actions only |
| `POST` | `/internal/ingest_edges` | — | `{status}` | Background thread; GH Actions only |
| `POST` | `/internal/precompute` | `{top_k?}` | `{status, seeded}` | Triggered by pipeline |
| `POST` | `/internal/build_faiss` | — | `{status, index_size}` | Triggered by pipeline |

### 5.2 Next.js API Routes (thin proxies, `/app/api/`)

| Method | Route | Proxies to | Purpose |
|--------|-------|------------|---------|
| `POST` | `/api/map` | `backend /map` | CORS-safe entry point from browser |
| `POST` | `/api/trace` | `backend /trace` | CORS-safe entry point |
| `POST` | `/api/search` | `backend /search` | CORS-safe entry point |
| `POST` | `/api/feedback` | Firestore SDK | Write `{result_hash, vote, timestamp}` — never hits Python backend |

### 5.3 Frontend Pages (Next.js App Router)

| Route | File | Description |
|-------|------|-------------|
| `/` | `app/page.tsx` | Landing: search bar, mode selector, recent results |
| `/map` | `app/map/page.tsx` | Adjacent Mapper: IdeaGrid, engine breakdown, EvidenceDrawer |
| `/trace` | `app/trace/page.tsx` | Lineage Tracer: timeline, SVG citation graph, narrative, frontier cards |

---

## 6. Pydantic Schemas (LLM Contract)

```python
# backend/llm/schemas.py

from pydantic import BaseModel, Field
from typing import Literal

class IdeaOutput(BaseModel):
    title: str = Field(max_length=120)
    description: str = Field(max_length=600)
    novelty_rationale: str = Field(max_length=200)
    confidence: int = Field(ge=0, le=100)

class AdjacentSynthesisResponse(BaseModel):
    ideas: list[IdeaOutput] = Field(min_length=3, max_length=10)

class FrontierOutput(BaseModel):
    field: str
    prediction: str
    horizon: Literal["1-2 years", "3-5 years", "5-10 years"]
    reasoning: str

class LineageResponse(BaseModel):
    narrative: str = Field(max_length=1000)
    frontier: list[FrontierOutput] = Field(min_length=1, max_length=5)
```

---

## 7. Key Design Decisions & Trade-offs

| Decision | Rationale |
|----------|-----------|
| **SQLite as production DB** | Single binary; zero hosting cost; 100% consistent reads; sufficient for <10k MAU read-heavy workload. Trade-off: no concurrent writes — mitigated by making production DB read-only (pipeline rebuilds weekly). |
| **FAISS loaded at server startup** | Avoids per-request disk I/O; ~50ms cold start for 100k-vector index. Trade-off: higher memory per serverless function instance (~200 MB). Mitigation: shard by domain if needed. |
| **Precompute everything, LLM offline-only** | Eliminates real-time API cost and latency. Trade-off: results may lag new publications by up to 7 days. Acceptable for research trend use-case. |
| **Groq free tier as LLM** | Zero cost, 70B-parameter quality. Trade-off: rate-limited; must be budget strictly in pipeline. Online fallback degrades gracefully to deterministic engines only. |
| **Next.js API route proxies** | Decouples frontend origin from backend URL; allows moving backend without frontend change; simplifies CORS. |
| **Embedding swap (Gemini → MiniLM)** | 384-dim vs 3072-dim = 8× smaller FAISS index; no API cost; runs in pipeline and locally. Slight quality trade-off acceptable for research adjacency task. |
