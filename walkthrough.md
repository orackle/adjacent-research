# Walkthrough — Temporal Graph-RAG Upgrade

## What Was Built

Your project now has two fully integrated modes:

| Mode | Endpoint | What It Does |
|---|---|---|
| Adjacent Mapper | `POST /map` | Existing — maps where a tech could go next |
| **Lineage Tracer** | **`POST /trace`** | **New — traces intellectual lineage through citation graph** |

---

## Files Changed / Created

### New Backend Files

#### [graph.py](file:///d:/vibecode/adjacency/backend/graph.py)
Pure-Python citation graph engine (no NetworkX — zero extra deps).
- `CitationGraph` class: directed adjacency dict + reverse index
- `load_graph(session)`: builds graph from DB edges
- `expand_subgraph(seeds, max_hops=3)`: BFS exploration
- `find_bridge_papers()`: hub scoring — papers connecting many ideas
- `sort_by_year()`: temporal ordering

#### [chain.py](file:///d:/vibecode/adjacency/backend/chain.py)
Full Temporal RAG pipeline:
1. Dense retrieval (Gemini embeddings, cosine similarity)
2. Live citation edge enrichment from S2 API
3. BFS subgraph expansion
4. Bridge paper detection
5. Temporal sort
6. Gemini narrative synthesis (causal "how paper A led to paper B")
7. Gemini frontier prediction (3 directions with time horizons)

### Modified Backend Files

#### [database.py](file:///d:/vibecode/adjacency/backend/database.py)
Added `CitationEdge` model with unique constraint on `(source_corpus_id, target_corpus_id)`.

#### [main.py](file:///d:/vibecode/adjacency/backend/main.py)
Added two new endpoints:
- `POST /trace` — runs the full lineage pipeline
- `POST /internal/ingest_edges` — populates citation graph from existing papers

#### [scripts/ingest_papers.py](file:///d:/vibecode/adjacency/backend/scripts/ingest_papers.py)
- Added `ingest_citation_edges()` function (Step 6 of ingestion)
- Integrated into `run_ingestion()` — now fetches references for top 30 papers

#### [mapper.py](file:///d:/vibecode/adjacency/mapper.py)
**Bug fix**: removed duplicate `call_groq_with_retry` definition that referenced undefined `client` variable — would have caused a `NameError` at runtime.

### Modified Frontend

#### [frontend/app/page.tsx](file:///d:/vibecode/adjacency/frontend/app/page.tsx)
Complete redesign with two tabs:

**Tab 1: Adjacent Mapper** — identical functionality, cleaner layout

**Tab 2: Lineage Tracer** — entirely new:
- `PaperNode` — clickable chronological paper card with year badge, citation count, arxiv link, breakthrough score; click to expand abstract
- `AbstractPanel` — inline abstract with DOI/arXiv link
- `CitationMiniGraph` — pure SVG graph showing nodes (year-labelled) connected by citation edges, pivotal paper highlighted in purple
- `NarrativeBlock` — Gemini-written causal narrative in italic pull-quote style
- Transition leap labels between paper nodes ("attention → positional encoding")
- `FrontierCard` — prediction cards with horizon badges (1-2yr green, 3-5yr amber, 5-10yr violet)

#### [frontend/app/globals.css](file:///d:/vibecode/adjacency/frontend/app/globals.css)
Added: `chip:disabled`, pivotal-pulse keyframe, tab hover styles.

---

## Build Verification

```
✓ Compiled successfully (Next.js 14.2.35)
✓ 0 TypeScript errors
✓ Backend imports: DB OK, Graph OK, Chain OK
✓ Page bundle: 8.65 kB (96 kB first load)
```

---

## How to Run the Full System

```powershell
# 1. Start backend (from repo root)
venv\Scripts\python.exe backend\main.py

# 2. Populate citation graph (if not already done via full ingestion)
curl -X POST http://localhost:8000/internal/ingest_edges

# 3. Start frontend
cd frontend
npm run dev

# 4. Open http://localhost:3000
#    → Tab: "Adjacent Mapper" — existing feature
#    → Tab: "Lineage Tracer"  — new feature
```

---

## Testing the Tracer

```bash
# Test the /trace endpoint directly:
curl -X POST http://localhost:8000/trace \
  -H "Content-Type: application/json" \
  -d '{"query": "attention mechanism transformer", "max_chain": 8}'
```

Expected response shape:
```json
{
  "query": "...",
  "chain": [ { "corpus_id": "...", "title": "...", "year": 2017, ... }, ... ],
  "narrative": "The 2017 attention paper introduced...",
  "transitions": [ { "from_id": "...", "to_id": "...", "leap": "scaled self-attention" } ],
  "pivotal_paper_id": "...",
  "frontier": [ { "field": "...", "prediction": "...", "horizon": "1-2 years" } ],
  "edges": [ { "source": "...", "target": "..." } ]
}
```

> [!IMPORTANT]
> The tracer works best with a populated citation graph. Run `POST /internal/ingest_edges`
> after the main ingestion. On first query, it also enriches edges live from S2.

---

## The LinkedIn Post (when ready)

**Hook:**
> I built a system that traces HOW the attention mechanism from 2017 led to ChatGPT, AlphaFold, and DALL-E — finding the 7 bridge papers that connected each leap.
> 
> It then predicts what's coming next.
>
> Here's the full intellectual chain 🧵

**What to show in the video:**
1. Type "attention mechanism transformer" in Lineage Tracer
2. Watch the loading steps animate
3. Scroll the narrative quote
4. Show 7 paper nodes appear with transition labels
5. Click one node to show the abstract
6. Show the citation graph SVG
7. Scroll to "Predicted Frontiers" cards

**Technical talking points for the post:**
- Graph-augmented RAG (not just flat vector retrieval)
- Citation graph BFS + betweenness-inspired bridge detection
- Temporal ordering for causal chain reconstruction
- Two Gemini calls: narrative synthesis + frontier prediction
- Built on Semantic Scholar + OpenAlex APIs
- Pure Python graph engine (no NetworkX), pure SVG (no D3)
