# API Contracts — Adjacency Research Engine v2.0

Full specification: all REST endpoints, request/response shapes, error codes, and auth requirements.

---

## Authentication & Authorization Model

> **Current v1 stance:** The API is **public and unauthenticated** for all read/query endpoints.  
> Write/internal endpoints are protected by a shared secret header.

### Auth Tiers

| Tier | Who | Mechanism | Applied to |
|------|-----|-----------|-----------|
| **Public** | Any browser client | No auth required | `POST /map`, `POST /trace`, `POST /search`, `GET /health` |
| **Internal** | GitHub Actions pipeline only | `X-Internal-Token: <secret>` header | `POST /internal/*` |
| **Firestore** | Next.js API route server-side only | Firebase Admin SDK service account | `POST /api/feedback` writes to Firestore |

### Internal Token

All `/internal/*` routes validate:
```python
token = request.headers.get("X-Internal-Token", "")
if token != os.environ.get("INTERNAL_API_SECRET", ""):
    return jsonify({"error": "Unauthorized"}), 401
```

`INTERNAL_API_SECRET` is a random 32-byte hex string set in the Vercel environment and GitHub Actions secrets.

### Rate Limiting

No per-user rate limiting is applied in v1 (public, anonymous). Vercel serverless function invocation limits serve as a natural ceiling. Future v2 may add IP-based rate limiting via Vercel middleware.

---

## Base URLs

| Environment | Next.js Frontend | Python Backend |
|-------------|-----------------|----------------|
| Local dev | `http://localhost:3000` | `http://localhost:8000` |
| Production | `https://adjacency.vercel.app` | Vercel Serverless (same domain via `/api/*` proxy) |

> All browser requests go to `/api/*` (Next.js routes), never directly to port 8000.

---

## Global Error Envelope

All error responses from the Python backend and Next.js API routes use:

```json
{
  "error": "Human-readable error description."
}
```

Unexpected server exceptions return `500` with a sanitised message (no stack traces exposed to client).

---

## 1. Adjacent Mapper

### `POST /map` — Python Backend

Maps a technology/topic seed to adjacent research ideas using blended engines.

**Auth:** Public (no auth required)  
**Cache:** SHA-256 hash of normalised `technology` checked against `precomputed_adjacencies` table. Hit = <200ms. Miss = live engines (<2s).

#### Request Body

```json
{
  "technology": "diffusion models",
  "top_k": 10,
  "use_cache": true
}
```

| Field | Type | Required | Constraints | Default |
|-------|------|----------|-------------|---------|
| `technology` | `string` | ✅ | min 2 chars, max 500 chars | — |
| `top_k` | `integer` | ❌ | 3 ≤ value ≤ 15 | `10` |
| `use_cache` | `boolean` | ❌ | — | `true` |

#### Success Response — `200 OK`

```json
{
  "technology": "diffusion models",
  "results": [
    {
      "field": "Latent Diffusion for Medical Imaging",
      "why": "Stable Diffusion's latent compression generalises to CT/MRI reconstruction, reducing scan radiation doses.",
      "blocker": "Regulatory approval pipelines for AI-generated diagnostic imagery remain 3–5 years behind capability.",
      "leap": "near",
      "adoption_urgency": 79,
      "feasibility_now": 68,
      "confidence": 82,
      "engines_used": ["semantic", "concept"],
      "_score": 0.89
    }
  ],
  "cached_at": "2026-06-30T00:00:00Z",
  "engines_used": ["semantic", "concept", "citation", "llm"]
}
```

| Field | Type | Notes |
|-------|------|-------|
| `technology` | `string` | Echo of input after normalisation |
| `results` | `MapResult[]` | Sorted by `_score` descending; max `top_k` items |
| `results[].field` | `string` | Adjacent research area name |
| `results[].why` | `string` | Justification (1–3 sentences) |
| `results[].blocker` | `string` | Key adoption obstacle |
| `results[].leap` | `"near"\|"mid"\|"far"` | Adjacent Possible / Stretch / Frontier |
| `results[].adoption_urgency` | `integer 0–100` | How pressing the need is |
| `results[].feasibility_now` | `integer 0–100` | Technical readiness today |
| `results[].confidence` | `integer 0–100` | Engine/LLM confidence |
| `results[].engines_used` | `string[]` | Subset of `["semantic","concept","citation","llm"]` |
| `results[]._score` | `float` | Internal blended score (0–1); exposed for transparency |
| `cached_at` | `string\|null` | ISO 8601 UTC; `null` if live computation |
| `engines_used` | `string[]` | All engines that ran for this query |

#### Error Responses

| Status | Condition | Response Body |
|--------|-----------|---------------|
| `400 Bad Request` | `technology` missing or empty | `{"error": "technology field is required"}` |
| `400 Bad Request` | `top_k` out of range | `{"error": "top_k must be between 3 and 15"}` |
| `500 Internal Server Error` | Engine exception, DB failure | `{"error": "<sanitised message>"}` |

---

### `POST /api/map` — Next.js Proxy Route

**Auth:** Public  
**Purpose:** CORS-safe browser entry point. Forwards body verbatim to `${BACKEND_URL}/map` and returns response unchanged.  
**Additional behaviour:** Injects `BACKEND_URL` from server-side env (`BACKEND_URL` env var); never exposed to client.

---

## 2. Lineage Tracer

### `POST /trace` — Python Backend

Traces the intellectual citation lineage for a query and returns LLM narrative + frontier predictions.

**Auth:** Public (no auth required)  
**Cache:** SHA-256 hash of normalised `query` checked against `precomputed_lineages`. Hit = <200ms.

#### Request Body

```json
{
  "query": "attention mechanism deep learning",
  "max_chain": 8
}
```

| Field | Type | Required | Constraints | Default |
|-------|------|----------|-------------|---------|
| `query` | `string` | ✅ | min 2 chars, max 500 chars | — |
| `max_chain` | `integer` | ❌ | 4 ≤ value ≤ 12 | `8` |

#### Success Response — `200 OK`

```json
{
  "query": "attention mechanism deep learning",
  "chain": [
    {
      "corpus_id": "204e3073870fae3d05bcbc2f6a8e263d9b72e776",
      "title": "Attention Is All You Need",
      "abstract": "The dominant sequence transduction models are based on complex recurrent or convolutional neural networks...",
      "year": 2017,
      "citation_count": 98532,
      "cd_index": 0.42,
      "novelty_score": 0.88,
      "breakthrough_score": 94.1,
      "arxiv_id": "1706.03762",
      "doi": "10.48550/arXiv.1706.03762"
    }
  ],
  "narrative": "The 2017 Transformer paper introduced self-attention as a primary sequence modelling mechanism, replacing recurrence entirely. This enabled parallel computation that BERT (2018) exploited for bidirectional pretraining. GPT-2 then scaled the decoder-only variant, establishing the template for all subsequent large language models.",
  "transitions": [
    {
      "from_id": "204e3073870fae3d05bcbc2f6a8e263d9b72e776",
      "to_id": "df2b0347a3c2d17ba5cd14c9f86a285b8fb45a0d",
      "leap": "bidirectional pretraining via masked language modelling"
    }
  ],
  "pivotal_paper_id": "204e3073870fae3d05bcbc2f6a8e263d9b72e776",
  "frontier": [
    {
      "field": "State-Space Models",
      "prediction": "Linear-time SSMs will displace transformers for contexts exceeding 100k tokens within two years.",
      "horizon": "1-2 years",
      "reasoning": "Mamba demonstrated subquadratic scaling with competitive quality on language benchmarks."
    }
  ],
  "edges": [
    {
      "source": "204e3073870fae3d05bcbc2f6a8e263d9b72e776",
      "target": "df2b0347a3c2d17ba5cd14c9f86a285b8fb45a0d"
    }
  ]
}
```

| Field | Type | Notes |
|-------|------|-------|
| `chain` | `ChainPaper[]` | Chronological, oldest first; 4–12 items |
| `chain[].corpus_id` | `string` | Unique paper ID |
| `chain[].year` | `integer\|null` | Publication year |
| `chain[].cd_index` | `float\|null` | Disruption score (−1 to +1) |
| `chain[].breakthrough_score` | `float\|null` | 0–100 composite score |
| `narrative` | `string` | LLM prose, ≤150 words |
| `transitions` | `TransitionItem[]` | One per adjacent pair; may be empty on cache miss without LLM |
| `pivotal_paper_id` | `string\|null` | corpus_id of pivotal bridge paper |
| `frontier` | `FrontierItem[]` | Exactly 3 items when LLM is available; may be `[]` on fallback |
| `frontier[].horizon` | `string` | One of `"1-2 years"`, `"3-5 years"`, `"5-10 years"` |
| `edges` | `EdgeLink[]` | Citation edges within the chain for SVG graph; may be `[]` |

#### Error Responses

| Status | Condition | Response Body |
|--------|-----------|---------------|
| `400` | `query` missing or empty | `{"error": "query field is required"}` |
| `400` | `max_chain` out of range | `{"error": "max_chain must be between 4 and 12"}` |
| `500` | Graph traversal or LLM failure | `{"error": "<sanitised message>"}` |

#### Degraded Response (no LLM available)

When Groq rate limit is exceeded and the result is not cached, a partial result is returned with `200`:

```json
{
  "query": "...",
  "chain": [...],
  "narrative": "These papers form a significant intellectual chain in this research area.",
  "transitions": [],
  "pivotal_paper_id": null,
  "frontier": [],
  "edges": [...]
}
```

---

### `POST /api/trace` — Next.js Proxy Route

**Auth:** Public  
Forwards to `${BACKEND_URL}/trace`.

---

## 3. Breakthrough Search

### `POST /search` — Python Backend

Scores and re-ranks papers against a topic using weighted linear combination of citation velocity, novelty, and CD-index.

**Auth:** Public  
**Cache:** None — re-ranks live each call (fast; SQLite cosine similarity, no LLM).

#### Request Body

```json
{
  "topic": "protein folding transformer",
  "k": 5,
  "w_velocity": 0.4,
  "w_novelty": 0.3,
  "w_cd": 0.3
}
```

| Field | Type | Required | Constraints | Default |
|-------|------|----------|-------------|---------|
| `topic` | `string` | ✅ | min 2 chars, max 500 chars | — |
| `k` | `integer` | ❌ | 1 ≤ value ≤ 20 | `5` |
| `w_velocity` | `float` | ❌ | 0.0 ≤ value ≤ 1.0 | `0.4` |
| `w_novelty` | `float` | ❌ | 0.0 ≤ value ≤ 1.0 | `0.3` |
| `w_cd` | `float` | ❌ | 0.0 ≤ value ≤ 1.0 | `0.3` |

> Weights need not sum to 1.0; they scale the corresponding percentile (0–100) in a linear combination.

#### Success Response — `200 OK`

Array of `Paper` objects, sorted by `final_score` descending.

```json
[
  {
    "corpus_id": "W2741809807",
    "doi": "10.1038/s41586-021-03819-2",
    "arxiv_id": null,
    "title": "Highly accurate protein structure prediction with AlphaFold",
    "abstract": "Proteins are essential to life, and understanding their structure is key to elucidating their biological function...",
    "year": 2021,
    "fields_of_study": ["Biology", "Biochemistry", "Computer Science"],
    "citation_count": 22847,
    "citation_velocity": 5711.75,
    "influential_citation_count": 1891,
    "cd_index": 0.38,
    "novelty_score": 0.92,
    "breakthrough_score": 97.4,
    "citation_velocity_percentile": 99.1,
    "cd_index_percentile": 85.3,
    "one_line_reason": "First system to predict protein 3D structure from sequence alone at near-experimental accuracy.",
    "context_summary": "**Problem Posed:** Protein folding from amino acid sequence alone had resisted solution for 50 years.\n\n**Solution Proposed:** AlphaFold uses an attention-based transformer with evolutionary multi-sequence alignment to achieve sub-Ångström accuracy at scale.",
    "final_score": 96.2
  }
]
```

| Field | Type | Notes |
|-------|------|-------|
| `final_score` | `float` | `w_velocity × velocity_pct + w_novelty × (novelty × 100) + w_cd × cd_pct` |
| `context_summary` | `string\|null` | Contains `**Problem Posed:**` and `**Solution Proposed:**` labels |

#### Empty Result Response — `200 OK`

```json
[]
```

Returned when no papers exist in the DB or no matches pass the similarity threshold. Frontend displays an empty state message.

#### Error Responses

| Status | Condition | Response Body |
|--------|-----------|---------------|
| `400` | `topic` missing or empty | No explicit error; returns `[]` |
| `500` | DB session failure | `{"error": "<message>"}` |

---

### `POST /api/search` — Next.js Proxy Route

**Auth:** Public  
Forwards to `${BACKEND_URL}/search`.

---

## 4. User Feedback

### `POST /api/feedback` — Next.js API Route

Records an anonymous upvote or downvote on a suggestion. Writes directly to Firebase Firestore using the **server-side** Firebase Admin SDK. The Python backend is **never involved**.

**Auth:** Public from browser, but write uses Firebase Admin credentials (server-side only — client never sees service account key).

#### Request Body

```json
{
  "result_hash": "a3f8b2c1d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a1",
  "vote": "up",
  "query": "diffusion models",
  "timestamp": "2026-06-30T15:45:00Z"
}
```

| Field | Type | Required | Constraints | Notes |
|-------|------|----------|-------------|-------|
| `result_hash` | `string` | ✅ | 64-char hex | SHA-256 of `{query}:{idea_title}` |
| `vote` | `"up"\|"down"` | ✅ | enum | Vote direction |
| `query` | `string` | ✅ | max 500 chars | For analytics grouping |
| `timestamp` | `string` | ✅ | ISO 8601 | Client-side timestamp |

#### Firestore Operation

Uses `FieldValue.increment(1)` for atomic counting. Document is created on first vote.

```
Collection: feedback
Document ID: <result_hash>
Fields:
  result_hash: string
  query: string
  votes.up: number   (incremented)
  votes.down: number (incremented)
  first_seen: Timestamp (set on create)
  last_vote: Timestamp  (always updated)
```

#### Success Response — `200 OK`

```json
{ "ok": true }
```

#### Error Responses

| Status | Condition | Response Body |
|--------|-----------|---------------|
| `400` | `vote` not `"up"` or `"down"` | `{"error": "vote must be 'up' or 'down'"}` |
| `400` | `result_hash` missing or not 64-char hex | `{"error": "invalid result_hash"}` |
| `500` | Firestore write failure | `{"error": "Failed to record feedback."}` |

---

## 5. Health Check

### `GET /health` — Python Backend

Used by Vercel warmup pings, uptime monitors, and the GitHub Actions pipeline to verify the backend is alive.

**Auth:** Public

#### Success Response — `200 OK`

```json
{
  "status": "ok",
  "db_papers": 42381,
  "last_ingestion": "2026-06-30T00:00:00Z",
  "faiss_loaded": true,
  "cache_hit_rate_24h": 0.944
}
```

| Field | Type | Notes |
|-------|------|-------|
| `status` | `"ok"\|"degraded"` | `"degraded"` if FAISS not loaded or DB empty |
| `db_papers` | `integer` | Current row count in `papers` table |
| `last_ingestion` | `string\|null` | ISO 8601 from `db_metadata` key `last_ingestion` |
| `faiss_loaded` | `boolean` | Whether FAISS index is in memory |
| `cache_hit_rate_24h` | `float\|null` | Ratio of cached responses in last 24h; null if no data |

#### Error Responses

| Status | Condition |
|--------|-----------|
| `500` | DB unreachable |

---

## 6. Internal Pipeline Endpoints

All `/internal/*` routes require the `X-Internal-Token` header. Called exclusively by GitHub Actions.

**Auth:** `X-Internal-Token: <INTERNAL_API_SECRET>`

### `POST /internal/run_ingestion`

Triggers `scripts/ingest_papers.py` in a background thread. Fetches new papers from OpenAlex + arXiv.

**Request Body:** `{}` (empty)

**Success Response — `200 OK`:**
```json
{ "status": "Ingestion triggered in background." }
```

**Error Responses:**

| Status | Condition | Body |
|--------|-----------|------|
| `401` | Missing or invalid token | `{"error": "Unauthorized"}` |
| `409` | Ingestion already running | `{"error": "Ingestion already in progress."}` |

---

### `POST /internal/ingest_edges`

Triggers citation edge ingestion for all existing papers via OpenAlex `referenced_works` (replaces Semantic Scholar).

**Request Body:** `{}` (empty)

**Success Response — `200 OK`:**
```json
{ "status": "Citation edge ingestion triggered in background." }
```

---

### `POST /internal/build_faiss`

Reads all `embedding` columns from the DB, builds a FAISS `IndexFlatIP` over normalised vectors, writes `backend/data/index.faiss` and `backend/data/id_map.json`.

**Request Body:** `{}` (empty)

**Success Response — `200 OK`:**
```json
{
  "status": "FAISS index built.",
  "index_size": 42381,
  "dimension": 384,
  "built_at": "2026-06-30T01:00:00Z"
}
```

**Error Responses:**

| Status | Condition | Body |
|--------|-----------|------|
| `401` | Invalid token | `{"error": "Unauthorized"}` |
| `500` | No embeddings found | `{"error": "No papers with embeddings found."}` |

---

### `POST /internal/precompute`

Runs adjacency + lineage precomputation for the top-K papers by citation count. Uses blended engines + Groq LLM (rate-limited). Inserts into `precomputed_adjacencies` and `precomputed_lineages`.

**Request Body:**
```json
{ "top_k": 10000 }
```

| Field | Type | Required | Constraints | Default |
|-------|------|----------|-------------|---------|
| `top_k` | `integer` | ❌ | 100 ≤ value ≤ 50000 | `10000` |

**Success Response — `200 OK`:**
```json
{
  "status": "Precompute complete.",
  "seeded": 9842,
  "skipped": 158,
  "duration_seconds": 3621
}
```

| Field | Notes |
|-------|-------|
| `seeded` | Number of seeds successfully precomputed |
| `skipped` | Seeds skipped (already cached, or errors) |
| `duration_seconds` | Wall-clock time for the full batch |

**Error Responses:**

| Status | Condition | Body |
|--------|-----------|------|
| `401` | Invalid token | `{"error": "Unauthorized"}` |
| `500` | FAISS not loaded | `{"error": "FAISS index not loaded. Run build_faiss first."}` |

---

## 7. CORS Policy

### Python Backend (Flask/FastAPI)

```python
CORS(app, resources={
    r"/*": {
        "origins": [
            "http://localhost:3000",
            "https://adjacency.vercel.app",
        ],
        "methods": ["GET", "POST", "OPTIONS"],
        "allow_headers": ["Content-Type", "X-Internal-Token"],
    }
})
```

### Production Architecture

In production, all browser requests go to Next.js proxy routes (`/api/*`) which forward server-to-server.  
No cross-origin requests from the browser to port 8000 occur in production — CORS is only needed for local development.

---

## 8. Request Flow Diagram

```
Browser
  │
  │  POST /api/map  (same-origin, Next.js)
  ▼
Next.js API Route  /api/map/route.ts
  │  fetch() server-to-server
  │  POST http://backend:8000/map
  ▼
FastAPI  /map
  ├── hash(technology) → check precomputed_adjacencies
  ├── HIT → return JSON  (<200ms)
  └── MISS
        ├── FAISS semantic search
        ├── Concept Walker (SQLite)
        ├── Citation Bridge (graph.py)
        ├── [optional] Groq LLM
        └── Write cache → return JSON  (<2s)
  │
  ▼
Next.js API Route returns response to browser
  │
  ▼
React component renders IdeaGrid
```

---

## 9. Versioning

APIs are currently unversioned (no `/v1/` prefix). When breaking changes are introduced in v2.0:
- New fields will be **additive** (non-breaking) — clients must tolerate unknown fields.
- Removed or renamed fields will be documented in `CHANGELOG.md` and communicated via the `/health` response's `api_version` field (to be added).
- Internal endpoints may change without notice; they are not public contracts.
