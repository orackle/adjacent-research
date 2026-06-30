
# Product Requirements Document (PRD) 

## Adjacency Research Engine v2.0 — "Rebuild with Prompt Engineering"

**Filename:** `prd.md`  
**Date:** 2026-06-30  
**Status:** Draft – ready for implementation  
**Baseline:** Existing codebase (`mapper.py`, `chain.py`, `graph.py`, `database.py`, frontend)


## Table of Contents
1. [Current State](#1-current-state)
2. [Vision & Goals](#2-vision--goals)
3. [Functional Requirements](#3-functional-requirements)
4. [User Stories](#4-user-stories)
5. [Non‑Functional Requirements](#5-non‑functional-requirements)
6. [Technical Architecture](#6-technical-architecture)
7. [Data Architecture](#7-data-architecture)
8. [Prompt Engineering Rules](#8-prompt-engineering-rules)
9. [Precomputation Strategy](#9-precomputation-strategy)
10. [Request‑Time Flow](#10-request‑time-flow)
11. [Implementation Plan](#11-implementation-plan)
12. [Risks & Mitigations](#12-risks--mitigations)
13. [Success Metrics](#13-success-metrics)
14. [Appendices](#14-appendices)

---

## 1. Current State

You have a working prototype with two fully integrated modes:

| Mode | Endpoint | What It Does |
|---|---|---|
| **Adjacent Mapper** | `POST /map` | Text → dense retrieval (Gemini embeddings) + LLM adjacency ideas |
| **Lineage Tracer** | `POST /trace` | Citation graph engine, BFS subgraph, bridge detection, temporal sort, LLM narrative & frontier prediction |

**Existing code assets:**
- `backend/graph.py` – pure‑Python citation graph engine (no NetworkX)
- `backend/chain.py` – temporal RAG pipeline (retrieval, enrichment, BFS, bridge, narrative, frontier)
- `backend/database.py` – SQLAlchemy models (`Paper`, `CitationEdge`)
- `backend/main.py` – FastAPI server with `/map` and `/trace`
- `backend/scripts/ingest_papers.py` – ingestion from Semantic Scholar & OpenAlex
- `frontend/` – Next.js app with two tabs, paper nodes, SVG citation graph, prediction cards

**Limitations:**
- Relies on **Semantic Scholar API** (requires key, rate‑limited) for citation edges.
- Relies on **Google Gemini** for embeddings and LLM synthesis (not free at scale).
- Real‑time heavy processing on every request (no precomputation).
- No concept‑based adjacency.
- LLM prompts are ad‑hoc, not systematically engineered.

---

## 2. Vision & Goals

Transform the existing prototype into a **fully free, prompt‑engineered, multi‑engine** adjacency research tool that:
- Runs **indefinitely at $0/month** (free tiers + open data + local models).
- Delivers **transparent, evidence‑backed** suggestions (concept paths, citation trails, semantic similarity).
- Uses **strict prompt engineering** for all LLM interactions (templates, few‑shot, chain‑of‑thought, schema validation).
- Serves **instant responses** from precomputed caches (95% < 200ms, no live API calls).
- Preserves and enhances all current user‑facing features (Mapper, Tracer, visualisations).

---

## 3. Functional Requirements

### 3.1 Adjacent Mapper (`POST /map`)
- **Input:** free text (title, abstract, keyword).
- **Output:** 5–10 adjacent research ideas, each with:
  - Title, description, novelty rationale, confidence score (0‑100).
  - Source engine(s) – semantic, concept, citation, LLM synthesis.
- **Engines (blended):**
  - **Semantic engine** – local FAISS‑based nearest‑neighbour search.
  - **Concept Walker** – sibling & co‑occurrence gap detection in OpenAlex taxonomy.
  - **Citation Bridge** – precomputed boundary‑spanning papers from local graph.
  - **LLM synthesis** – single‑call, template‑driven idea generation (offline, cached).

### 3.2 Lineage Tracer (`POST /trace`)
- **Input:** query string.
- **Output:**
  - Chronological paper chain (with years, titles, abstracts, citation counts).
  - Transition leaps (e.g., “attention → positional encoding”).
  - Pivotal paper ID.
  - Narrative paragraph (causal evolution).
  - Frontier predictions (3 directions with time horizon).
- **Engines:**
  - Local citation graph (OpenAlex‑derived edges).
  - Temporal sort & bridge detection (reuse existing `graph.py`).
  - LLM narrative & frontier generation (precomputed or free‑tier fallback).

### 3.3 Precomputation & Freshness
- Weekly ingestion pipeline fetches new papers, rebuilds indices, and recomputes suggestions for top entities.
- Cache invalidation on new publications or graph changes.
- Display “last updated” timestamp on results.

### 3.4 Transparency & Feedback
- Every suggested idea must show its **evidence trail** (which papers/concepts were used).
- Users can **upvote/downvote** ideas; feedback stored anonymously in free‑tier Firestore.
- **Shareable links** for interesting discoveries.

---

## 4. User Stories

- **As a doctoral student**, I enter my thesis abstract and get 5 concrete next steps I hadn’t considered.
- **As an industry researcher**, I trace the intellectual lineage of a breakthrough to understand its foundational steps.
- **As a curious mind**, I click a suggested idea and see the exact paper and concept links that justify it.
- **As a returning user**, I find my saved ideas and see how new literature has updated the adjacency suggestions.

---

## 5. Non‑Functional Requirements

| Category | Requirement |
|----------|-------------|
| **Cost** | $0/month sustained operational cost (hosting, APIs, models). |
| **Latency** | 95% of queries served from cache < 200ms; p99 < 2 seconds even on cache miss. |
| **Prompt reliability** | LLM output must be valid JSON > 99% of the time (enforced by Pydantic schema). |
| **Transparency** | All suggestion logic open‑source; no black‑box vendor models. |
| **Scalability** | Serve 10k MAU within free‑tier limits. |
| **Portability** | Entire system can run locally with one command. |
| **Privacy** | No user input stored unless opted in; no third‑party tracking. |

---

## 6. Technical Architecture

```
[Next.js Static Frontend – Vercel]
        ↓
[Vercel Serverless Functions (Python)]
        ↓
[Adjacency Engine Orchestrator]
   ├── Cache Lookup (SQLite precomputed tables)
   ├── Semantic Search (FAISS in‑memory)
   ├── Concept Walker (SQL queries on local DB)
   ├── Citation Graph (local SQLite edges)
   └── Fallback LLM Call (Groq Llama 3, free tier)
        ↑
[Weekly GitHub Actions Pipeline]
   ├── Fetch OpenAlex + arXiv
   ├── Compute embeddings (sentence-transformers)
   ├── Build FAISS index + update SQLite
   ├── Precompute adjacencies & lineages
   └── Commit artifacts → trigger deploy
```

**Key free‑tier services:**
- Frontend hosting: Vercel (static export).
- Backend compute: Vercel serverless functions (100 GB‑hrs/month).
- Vector index: FAISS (binary file loaded into function memory).
- Relational DB: SQLite read‑only (deployed alongside code).
- User data: Firebase Firestore (1 GB free).
- LLM: Groq (Llama 3.3 70B) free tier, used only for offline cache generation; optional on‑the‑fly fallback within rate limits.
- Scheduler: GitHub Actions (2000 min/month).
- Embedding model: `all-MiniLM-L6-v2` from HuggingFace (runs locally).

---

## 7. Data Architecture

### 7.1 Local Database (SQLite)
Replace live API dependencies with a self‑contained database:

**Tables:**
- `papers` – `id, corpus_id, title, abstract, year, citation_count, embedding (BLOB), source`
- `concepts` – `concept_id, name, level, ancestors (JSON), descendants (JSON)`
- `paper_concepts` – `paper_id, concept_id, score`
- `citation_edges` – `source_id, target_id` (local paper IDs)
- `precomputed_adjacencies` – `seed_hash, idea_json, engines_used, created_at`
- `precomputed_lineages` – `query_hash, chain_json, narrative, frontier_json, created_at`

### 7.2 Ingestion Pipeline (GitHub Actions)
1. Fetch new works from OpenAlex (by date range, specific high‑level concepts).
2. Fetch arXiv metadata via OAI‑PMH (for CS, EE, etc.).
3. For each new paper:
   - Extract abstract, year, concepts.
   - Fetch `referenced_works` from OpenAlex → create local `citation_edges` (resolving IDs to local keys).
4. Compute embeddings with `all-MiniLM-L6-v2` → store in DB.
5. Build FAISS index (`index.faiss`) and ID mapping.
6. Run precomputation (see Section 9).
7. Commit updated DB + index → auto‑deploy on Vercel.

---

## 8. Prompt Engineering Rules

All LLM interactions must follow these mandatory rules. Templates are version‑controlled and tested.

### 8.1 General Template Structure
Every prompt includes:
- **System persona** (concise role description).
- **Task instruction** (clear, bounded request).
- **Input context** (papers, concepts, formatted cleanly).
- **Output format spec** (explicit JSON schema or simple text).
- **Few‑shot examples** (≥2 for generation tasks).
- **Chain‑of‑thought trigger** (“Think step‑by‑step” or “First list the gaps…”).

### 8.2 Specific Templates

#### Adjacent Idea Synthesis (`prompts/adjacent_synthesis.txt`)
```
System: You are a research ideation assistant. Propose novel, concrete, adjacent research ideas by combining existing knowledge in unexplored ways.

User:
Seed topic: {seed_text}

Context from related literature:
{list of titles & abstracts}

Conceptual gaps identified:
{sibling concepts, co‑occurrence gaps}

Instructions:
1. Identify recurring themes and missing links.
2. Brainstorm exactly 5 novel hypotheses that bridge these gaps.
3. For each hypothesis provide:
   - title (short)
   - description (2-3 sentences)
   - novelty_rationale (1 sentence explaining the gap)
   - confidence (0-100)

Output format: JSON array of objects with keys: title, description, novelty_rationale, confidence.

Examples:
[{"title": "Quantum-enhanced Graph Neural Networks", ...}, ...]

Now think step‑by‑step and then generate the ideas.
```

#### Lineage Narrative (`prompts/lineage_narrative.txt`)
```
System: You are a science historian. Write a concise, causal narrative tracing how a chain of papers led from one discovery to another.

User:
Paper chain (chronological):
{list of papers with year, title, short description}

Identified transitions:
{from_id → to_id, key innovation}

Instructions:
- Write one paragraph (max 150 words) that explains the progression.
- Highlight the pivotal paper that enabled the leap.
- Use plain English, no jargon.

Output format: A string.

Example: "The 2017 Transformer introduced self‑attention, enabling parallel processing of sequences. This sparked BERT (2018)..."
Now write the narrative.
```

#### Frontier Prediction (`prompts/frontier_prediction.txt`)
```
System: You are a futurologist specializing in research trends. Predict emerging research frontiers based on a lineage.

User:
Trajectory summary: {narrative}
Pivotal paper: {title, year}
Recent edge papers: {list}

Instructions:
1. Based on the trajectory, list 3 promising frontier directions.
2. For each, provide:
   - field (name)
   - prediction (one sentence)
   - horizon (1-2 years, 3-5 years, 5-10 years)
   - reasoning (one sentence)

Output format: JSON array with keys: field, prediction, horizon, reasoning.

Example: [{"field": "Multi-modal Transformers", "prediction": "...", "horizon": "1-2 years", "reasoning": "..."}]
Now think step‑by‑step and predict.
```

### 8.3 Quality Gates
- **Output validation:** LLM response parsed with Pydantic models; automatic retry on mismatch.
- **Temperature:** 0.2 for narrative, 0.7 for creative frontier ideas.
- **Context window:** Trim input to 8000 tokens (Llama 3.3 context is 128k, but keep concise).
- **Deduplication:** Generated titles must not exactly match any input paper title (fuzzy check).

---

## 9. Precomputation Strategy

**Goal:** Serve >90% of user queries instantly from static cache.

### 9.1 Seed Selection
- Top 10,000 most‑cited papers in DB.
- Top 5,000 OpenAlex concepts (by usage count).
- For each seed, generate and store:
  - Adjacent ideas (from blended engines + LLM synthesis).
  - Lineage chain (graph traversal + narrative + frontier).

### 9.2 Adjacency Precomputation for a Seed
1. Retrieve seed’s embedding → FAISS top‑50 neighbours.
2. Retrieve seed’s concepts → sibling & co‑occurrence gap concepts.
3. Run `graph.find_bridge_papers()` on the neighbourhood.
4. Assemble context, call LLM with `adjacent_synthesis.txt` prompt → parse → store.

### 9.3 Lineage Precomputation for a Seed
1. Use FAISS to identify starting paper IDs related to the seed text.
2. Expand subgraph (BFS 3 hops) from those starting nodes using local edges.
3. Apply `sort_by_year()` and `find_bridge_papers()` (from `graph.py`).
4. Call LLM narrative and frontier prompts → parse → store.

### 9.4 Cache Freshness
- Rebuild entire cache weekly.
- When new papers are ingested, only seeds whose neighbourhood changed are recomputed (differential update).

---

## 10. Request‑Time Flow

1. User sends query → frontend calls `/map` or `/trace`.
2. Serverless function hashes the query and checks `precomputed_*` table.
3. **If cache hit:** return cached result (< 200ms).  
   **If cache miss (rare):**
   - Load FAISS index (already in memory) and run semantic search.
   - Run deterministic engines (concept walker, citation bridge) to build a basic result **without LLM**.
   - Optionally, if within Groq rate limits and time, call LLM for final polish.
   - Return fallback result; log the miss so a background job can precompute it for next time.

All heavy work (embeddings, LLM synthesis) is completely excluded from the real‑time path for cached queries.

---

## 11. Implementation Plan

| Phase | Tasks | Effort |
|-------|-------|--------|
| **Phase 1 – Free the Data** | Replace S2 edge fetching with OpenAlex `referenced_works`. Replace Gemini embeddings with local `sentence-transformers`. Integrate into ingestion script. | 2–3 days |
| **Phase 2 – Prompt Engineering** | Create template files, Pydantic parsers, switch LLM calls to Groq. Test output validity. | 1–2 days |
| **Phase 3 – Precomputation Pipeline** | Build GitHub Actions workflow: daily/weekly fetch, embed, build FAISS, run precompute for top seeds, commit artifacts. | 3–4 days |
| **Phase 4 – Concept Walker** | Ingest OpenAlex concept taxonomy, implement sibling/co‑occurrence gap logic. Integrate into both mapper and tracer precomputation. | 2–3 days |
| **Phase 5 – Deploy & Verify** | Convert frontend to static export, test Vercel serverless cold starts, measure latency and cost. Ensure $0/month. | 1 day |

**Total:** ~2–3 weeks part‑time.

---

## 12. Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| OpenAlex citation coverage incomplete | Supplement with Crossref reference data; graph remains useful even at 50‑70% edge coverage. |
| Groq free tier rate‑limited or deprecates | Use offline‑only LLM (cache everything); online fallback defaults to deterministic engines, which are sufficient. |
| FAISS index too large for serverless memory | Use Annoy with memory mapping; or shard by domain and load only relevant shard. |
| Precomputed cache staleness | Weekly rebuild is sufficient for research trends; display “last updated” date. |
| Prompt failures (malformed JSON) | Pydantic schema validation + automatic retry with stricter instruction. |

---

## 13. Success Metrics

- **Cost:** $0/month for 12 months continuous operation.
- **Latency:** >95% of queries served from cache (p95 < 200ms). p99 < 2 seconds.
- **Cache hit rate:** >90% within first month after launch.
- **Prompt reliability:** JSON parse success rate > 99%.
- **User satisfaction:** Upvote ratio > 0.75 on suggestions (measured from 1000+ votes).

---

## 14. Appendices

### A. Prompt Template Files (to be created)
- `prompts/adjacent_synthesis.txt`
- `prompts/lineage_narrative.txt`
- `prompts/frontier_prediction.txt`
- `schemas/idea_output.json` (Pydantic model)
- `schemas/lineage_output.json` (Pydantic model)

### B. OpenAlex Concept Taxonomy Usage
- File: `data/concepts.csv` (download from OpenAlex).
- Hierarchy levels: 0 (broad) to 5 (specific).
- Co‑occurrence gap algorithm: For seed concept C, find sibling S where S’s papers rarely contain C’s papers’ concepts → uncombined pair.

### C. Free‑tier Limits Quick Reference
| Service | Limit | Projected Usage |
|---------|-------|-----------------|
| Vercel | 100 GB‑hrs, 100 GB bandwidth | <20 GB‑hrs/month |
| GitHub Actions | 2000 min/month | ~600 min/month |
| Groq | Free tier (rate limited) | Used only offline or rare fallback |
| Firebase Firestore | 1 GB storage, 50k reads/day | << limit |
| OpenAlex | No key, polite use | Batch fetch only |

---

**End of PRD.** This document guides the rebuild of the Adjacency Research Engine into a prompt‑engineered, zero‑cost, production‑ready tool. All existing features (Mapper, Tracer, visualisations) are preserved and enhanced.
