# Data Models — Adjacency Research Engine v2.0

Full specification: SQLAlchemy ORM models, relationships, validation rules, Pydantic schemas, and TypeScript types.

> **Stack note:** This project uses Python + SQLAlchemy + SQLite, not a Node/Prisma stack.  
> Where the guideline asks for a "Prisma schema snippet", equivalent SQLAlchemy model code is provided instead.  
> A Prisma-style schema block is also included for documentation clarity.

---

## Entity Relationship Overview

```
papers ─────────────────────────────────────────────────┐
  │ 1                                                    │
  │ ↓ M                                                  │
citation_edges (source→target, both FK to papers)        │
                                                         │
papers ─── M ──── paper_concepts ─── M ──── concepts    │
  │ 1                                                    │
  │ ↓ M                                                  │
precomputed_adjacencies (seed_hash per query)            │
  │                                                      │
precomputed_lineages (query_hash per query)              │
                                                         │
db_metadata  (key-value, no FK)                         │
```

---

## 1. `papers`

Central entity. One row per unique research paper ingested from OpenAlex or arXiv.

### Fields

| Field | Type | Constraints | Default | Notes |
|-------|------|-------------|---------|-------|
| `id` | Integer | PK, auto-increment | — | Internal row ID |
| `corpus_id` | String(64) | **UNIQUE**, NOT NULL, indexed | — | OpenAlex Work ID (`W…`) or S2 ID |
| `doi` | String(256) | nullable | NULL | e.g. `10.1038/s41586-021-04086-x` |
| `arxiv_id` | String(32) | nullable | NULL | e.g. `1706.03762` |
| `title` | String(1024) | NOT NULL | — | Full paper title |
| `abstract` | Text | nullable | NULL | Truncated to 4000 chars on ingest |
| `year` | Integer | nullable, indexed | NULL | Publication year (YYYY) |
| `fields_of_study` | Text | nullable | NULL | JSON array e.g. `["AI","CS"]` |
| `citation_count` | Integer | NOT NULL | 0 | Total citations at ingest time |
| `citation_velocity` | Float | NOT NULL | 0.0 | Citations per year (computed at ingest) |
| `influential_citation_count` | Integer | NOT NULL | 0 | Highly influential citations |
| `cd_index` | Float | nullable | NULL | Disruption score: −1 (consolidating) to +1 (disrupting) |
| `novelty_score` | Float | nullable | NULL | Semantic novelty vs. prior literature (0–1) |
| `breakthrough_score` | Float | nullable, indexed | NULL | Composite ranking score (0–100) |
| `citation_velocity_percentile` | Float | NOT NULL | 0.0 | Corpus percentile (0–100) |
| `cd_index_percentile` | Float | NOT NULL | 0.0 | Corpus percentile (0–100) |
| `one_line_reason` | Text | nullable | NULL | LLM-generated breakthrough one-liner |
| `context_summary` | Text | nullable | NULL | LLM "Problem Posed / Solution Proposed" |
| `novelty_scored` | Integer | NOT NULL | 0 | `0` = not yet scored, `1` = scored |
| `embedding` | Text | nullable | NULL | JSON float array (384-dim MiniLM) |
| `source` | String(32) | nullable | NULL | `'openalex'` \| `'arxiv'` \| `'s2'` |
| `last_updated` | DateTime | NOT NULL, auto-update | `utcnow()` | UTC timestamp of last write |

### Relationships

| Relationship | Type | Via |
|---|---|---|
| Has many outgoing citation edges | One-to-Many | `citation_edges.source_corpus_id → papers.corpus_id` |
| Has many incoming citation edges | One-to-Many | `citation_edges.target_corpus_id → papers.corpus_id` |
| Belongs to many concepts | Many-to-Many | through `paper_concepts` join table |
| May have a precomputed adjacency | Zero-or-One | `precomputed_adjacencies.seed_hash` (hash of title/query, not direct FK) |

### SQLAlchemy Model

```python
class Paper(Base):
    __tablename__ = "papers"

    id                          = Column(Integer, primary_key=True, index=True)
    corpus_id                   = Column(String(64), unique=True, index=True, nullable=False)
    doi                         = Column(String(256), nullable=True)
    arxiv_id                    = Column(String(32), nullable=True)
    title                       = Column(String(1024), nullable=False)
    abstract                    = Column(Text, nullable=True)
    year                        = Column(Integer, index=True, nullable=True)
    fields_of_study             = Column(Text, nullable=True)       # JSON array
    citation_count              = Column(Integer, default=0, nullable=False)
    citation_velocity           = Column(Float, default=0.0, nullable=False)
    influential_citation_count  = Column(Integer, default=0, nullable=False)
    cd_index                    = Column(Float, nullable=True)
    novelty_score               = Column(Float, nullable=True)
    breakthrough_score          = Column(Float, index=True, nullable=True)
    citation_velocity_percentile = Column(Float, default=0.0, nullable=False)
    cd_index_percentile         = Column(Float, default=0.0, nullable=False)
    one_line_reason             = Column(Text, nullable=True)
    context_summary             = Column(Text, nullable=True)
    novelty_scored              = Column(Integer, default=0, nullable=False)
    embedding                   = Column(Text, nullable=True)       # JSON float[]
    source                      = Column(String(32), nullable=True)
    last_updated                = Column(DateTime, default=datetime.utcnow,
                                         onupdate=datetime.utcnow, nullable=False)

    # Relationships
    outgoing_citations = relationship("CitationEdge",
                                      foreign_keys="CitationEdge.source_corpus_id",
                                      primaryjoin="Paper.corpus_id==CitationEdge.source_corpus_id",
                                      back_populates="source_paper")
    incoming_citations = relationship("CitationEdge",
                                      foreign_keys="CitationEdge.target_corpus_id",
                                      primaryjoin="Paper.corpus_id==CitationEdge.target_corpus_id",
                                      back_populates="target_paper")
    concepts           = relationship("PaperConcept", back_populates="paper")
```

### Prisma-Style Schema (documentation reference)

```prisma
model Paper {
  id                         Int            @id @default(autoincrement())
  corpus_id                  String         @unique
  doi                        String?
  arxiv_id                   String?
  title                      String
  abstract                   String?
  year                       Int?
  fields_of_study            String?        // JSON array
  citation_count             Int            @default(0)
  citation_velocity          Float          @default(0)
  influential_citation_count Int            @default(0)
  cd_index                   Float?
  novelty_score              Float?
  breakthrough_score         Float?
  citation_velocity_percentile Float        @default(0)
  cd_index_percentile        Float          @default(0)
  one_line_reason            String?
  context_summary            String?
  novelty_scored             Int            @default(0)
  embedding                  String?        // JSON float[]
  source                     String?
  last_updated               DateTime       @updatedAt

  outgoing_citations CitationEdge[] @relation("SourcePaper")
  incoming_citations CitationEdge[] @relation("TargetPaper")
  concepts           PaperConcept[]

  @@index([year])
  @@index([breakthrough_score])
}
```

### Validation Rules

**Server-side (Pydantic / ingest script):**
- `corpus_id`: non-empty string, max 64 chars; must be unique (raise `IntegrityError` → skip duplicate)
- `title`: non-empty string, max 1024 chars; strip leading/trailing whitespace
- `year`: integer, must be `1800 ≤ year ≤ current_year + 1` if present
- `citation_count`: integer `≥ 0`
- `cd_index`: float `−1.0 ≤ value ≤ 1.0` if present
- `novelty_score`: float `0.0 ≤ value ≤ 1.0` if present
- `breakthrough_score`: float `0.0 ≤ value ≤ 100.0` if present
- `embedding`: if set, must be valid JSON deserialising to a list of 384 floats
- `source`: must be one of `'openalex'`, `'arxiv'`, `'s2'` if set

**Client-side (TypeScript / frontend search input):**
- Topic query: non-empty, min 2 chars, max 500 chars
- `k`: integer `1 ≤ k ≤ 20`
- Weight sliders (`w_velocity`, `w_novelty`, `w_cd`): float `0.0 ≤ value ≤ 1.0`

---

## 2. `citation_edges`

Directed citation link: **source cites target**.

### Fields

| Field | Type | Constraints | Default | Notes |
|-------|------|-------------|---------|-------|
| `id` | Integer | PK, auto-increment | — | |
| `source_corpus_id` | String(64) | NOT NULL, indexed | — | FK → `papers.corpus_id` (citing paper) |
| `target_corpus_id` | String(64) | NOT NULL, indexed | — | FK → `papers.corpus_id` (cited paper) |
| `source_year` | Integer | nullable | NULL | Denormalised year of citing paper (graph speed) |

**Unique constraint:** `(source_corpus_id, target_corpus_id)` — no duplicate edges.

### Relationships

| Relationship | Type | Via |
|---|---|---|
| Belongs to source paper | Many-to-One | `source_corpus_id → papers.corpus_id` |
| Belongs to target paper | Many-to-One | `target_corpus_id → papers.corpus_id` |

### SQLAlchemy Model

```python
class CitationEdge(Base):
    __tablename__ = "citation_edges"

    id               = Column(Integer, primary_key=True)
    source_corpus_id = Column(String(64), index=True, nullable=False)
    target_corpus_id = Column(String(64), index=True, nullable=False)
    source_year      = Column(Integer, nullable=True)

    __table_args__ = (
        UniqueConstraint("source_corpus_id", "target_corpus_id", name="uq_citation_edge"),
    )

    source_paper = relationship("Paper", foreign_keys=[source_corpus_id],
                                primaryjoin="CitationEdge.source_corpus_id==Paper.corpus_id",
                                back_populates="outgoing_citations")
    target_paper = relationship("Paper", foreign_keys=[target_corpus_id],
                                primaryjoin="CitationEdge.target_corpus_id==Paper.corpus_id",
                                back_populates="incoming_citations")
```

### Prisma-Style Schema

```prisma
model CitationEdge {
  id               Int    @id @default(autoincrement())
  source_corpus_id String
  target_corpus_id String
  source_year      Int?

  source_paper Paper @relation("SourcePaper", fields: [source_corpus_id], references: [corpus_id])
  target_paper Paper @relation("TargetPaper", fields: [target_corpus_id], references: [corpus_id])

  @@unique([source_corpus_id, target_corpus_id])
  @@index([source_corpus_id])
  @@index([target_corpus_id])
}
```

### Validation Rules

**Server-side:**
- `source_corpus_id` and `target_corpus_id`: non-empty, max 64 chars
- Self-loops forbidden: `source_corpus_id ≠ target_corpus_id`
- On duplicate `(source, target)`: silently skip (log a warning, do not raise to caller)
- `source_year`: `1800 ≤ value ≤ current_year + 1` if present

---

## 3. `concepts` *(v2.0 — new)*

OpenAlex concept taxonomy node. Loaded from `data/concepts.csv` weekly.

### Fields

| Field | Type | Constraints | Default | Notes |
|-------|------|-------------|---------|-------|
| `concept_id` | String(32) | PK | — | OpenAlex ID e.g. `C41008148` |
| `name` | String(256) | NOT NULL | — | Human-readable e.g. `"Graph Neural Network"` |
| `level` | Integer | nullable | NULL | Hierarchy depth: 0=broadest, 5=most specific |
| `ancestors` | Text | nullable | NULL | JSON array of ancestor `concept_id`s |
| `descendants` | Text | nullable | NULL | JSON array of direct child `concept_id`s |

### Relationships

| Relationship | Type | Via |
|---|---|---|
| Belongs to many papers | Many-to-Many | through `paper_concepts` |
| Has parent concepts | Self-referential (implicit) | IDs stored in `ancestors` JSON |
| Has child concepts | Self-referential (implicit) | IDs stored in `descendants` JSON |

### SQLAlchemy Model

```python
class Concept(Base):
    __tablename__ = "concepts"

    concept_id  = Column(String(32), primary_key=True)
    name        = Column(String(256), nullable=False)
    level       = Column(Integer, nullable=True)
    ancestors   = Column(Text, nullable=True)    # JSON list of concept_ids
    descendants = Column(Text, nullable=True)    # JSON list of concept_ids

    papers = relationship("PaperConcept", back_populates="concept")
```

### Prisma-Style Schema

```prisma
model Concept {
  concept_id  String  @id
  name        String
  level       Int?
  ancestors   String? // JSON array
  descendants String? // JSON array

  papers PaperConcept[]
}
```

### Validation Rules

**Server-side (ingest):**
- `concept_id`: non-empty, must start with `C` followed by digits
- `name`: non-empty, max 256 chars; strip whitespace
- `level`: `0 ≤ level ≤ 5` if present
- `ancestors`/`descendants`: if set, must be valid JSON arrays of strings

---

## 4. `paper_concepts` *(v2.0 — new)*

Many-to-many join table: paper ↔ concept with relevance score.

### Fields

| Field | Type | Constraints | Default | Notes |
|-------|------|-------------|---------|-------|
| `paper_id` | String(64) | PK (part), FK → `papers.corpus_id` | — | |
| `concept_id` | String(32) | PK (part), FK → `concepts.concept_id` | — | |
| `score` | Float | nullable | NULL | OpenAlex relevance score (0–1) |

**Primary key:** composite `(paper_id, concept_id)`

### Relationships

| Relationship | Type | Via |
|---|---|---|
| Belongs to paper | Many-to-One | `paper_id → papers.corpus_id` |
| Belongs to concept | Many-to-One | `concept_id → concepts.concept_id` |

### SQLAlchemy Model

```python
class PaperConcept(Base):
    __tablename__ = "paper_concepts"

    paper_id   = Column(String(64), ForeignKey("papers.corpus_id"), primary_key=True)
    concept_id = Column(String(32), ForeignKey("concepts.concept_id"), primary_key=True)
    score      = Column(Float, nullable=True)

    paper   = relationship("Paper", back_populates="concepts")
    concept = relationship("Concept", back_populates="papers")
```

### Prisma-Style Schema

```prisma
model PaperConcept {
  paper_id   String
  concept_id String
  score      Float?

  paper   Paper   @relation(fields: [paper_id], references: [corpus_id])
  concept Concept @relation(fields: [concept_id], references: [concept_id])

  @@id([paper_id, concept_id])
}
```

### Validation Rules

**Server-side:**
- `paper_id` must exist in `papers.corpus_id` (FK enforced)
- `concept_id` must exist in `concepts.concept_id` (FK enforced)
- `score`: `0.0 ≤ score ≤ 1.0` if present
- On duplicate composite PK: skip silently

---

## 5. `precomputed_adjacencies` *(v2.0 — new)*

Cache store for Adjacent Mapper results, keyed by query hash.

### Fields

| Field | Type | Constraints | Default | Notes |
|-------|------|-------------|---------|-------|
| `id` | Integer | PK, auto-increment | — | |
| `seed_hash` | String(64) | **UNIQUE**, NOT NULL | — | SHA-256 of `lower(strip(query))` |
| `seed_text` | String(512) | nullable | NULL | Original query text (for debugging / admin) |
| `idea_json` | Text | NOT NULL | — | JSON serialisation of `IdeaOutput[]` |
| `engines_used` | String(256) | nullable | NULL | JSON array e.g. `["semantic","concept","llm"]` |
| `created_at` | DateTime | NOT NULL | `utcnow()` | Cache write timestamp |

### Relationships

None — lookup is by hash only, no FK to `papers`.

### SQLAlchemy Model

```python
class PrecomputedAdjacency(Base):
    __tablename__ = "precomputed_adjacencies"

    id           = Column(Integer, primary_key=True)
    seed_hash    = Column(String(64), unique=True, nullable=False)
    seed_text    = Column(String(512), nullable=True)
    idea_json    = Column(Text, nullable=False)
    engines_used = Column(String(256), nullable=True)
    created_at   = Column(DateTime, default=datetime.utcnow, nullable=False)
```

### Prisma-Style Schema

```prisma
model PrecomputedAdjacency {
  id           Int      @id @default(autoincrement())
  seed_hash    String   @unique
  seed_text    String?
  idea_json    String   // JSON: IdeaOutput[]
  engines_used String?  // JSON: string[]
  created_at   DateTime @default(now())
}
```

### Validation Rules

**Server-side (cache writer):**
- `seed_hash`: must be 64-character hex string (SHA-256)
- `idea_json`: must be valid JSON deserialising to a non-empty list
- On duplicate `seed_hash`: `INSERT OR REPLACE` (upsert) — refresh with newer data
- `engines_used`: if set, must be valid JSON array of strings

---

## 6. `precomputed_lineages` *(v2.0 — new)*

Cache store for Lineage Tracer results.

### Fields

| Field | Type | Constraints | Default | Notes |
|-------|------|-------------|---------|-------|
| `id` | Integer | PK, auto-increment | — | |
| `query_hash` | String(64) | **UNIQUE**, NOT NULL | — | SHA-256 of normalised query |
| `query_text` | String(512) | nullable | NULL | Original query |
| `chain_json` | Text | NOT NULL | — | JSON: `ChainPaper[]` (chronological) |
| `narrative` | Text | nullable | NULL | LLM narrative paragraph |
| `frontier_json` | Text | nullable | NULL | JSON: `FrontierOutput[]` |
| `pivotal_id` | String(64) | nullable | NULL | `corpus_id` of pivotal paper |
| `created_at` | DateTime | NOT NULL | `utcnow()` | |

### Relationships

`pivotal_id` references a `corpus_id` in `papers` but is stored as plain string (not a FK) to allow caching even when the pivotal paper is later removed from the DB.

### SQLAlchemy Model

```python
class PrecomputedLineage(Base):
    __tablename__ = "precomputed_lineages"

    id            = Column(Integer, primary_key=True)
    query_hash    = Column(String(64), unique=True, nullable=False)
    query_text    = Column(String(512), nullable=True)
    chain_json    = Column(Text, nullable=False)
    narrative     = Column(Text, nullable=True)
    frontier_json = Column(Text, nullable=True)
    pivotal_id    = Column(String(64), nullable=True)
    created_at    = Column(DateTime, default=datetime.utcnow, nullable=False)
```

### Prisma-Style Schema

```prisma
model PrecomputedLineage {
  id            Int      @id @default(autoincrement())
  query_hash    String   @unique
  query_text    String?
  chain_json    String   // JSON: ChainPaper[]
  narrative     String?
  frontier_json String?  // JSON: FrontierOutput[]
  pivotal_id    String?
  created_at    DateTime @default(now())
}
```

### Validation Rules

**Server-side:**
- `query_hash`: 64-char hex string
- `chain_json`: valid JSON, deserialises to list of ≥1 objects
- `narrative`: max 1500 chars if set
- `frontier_json`: valid JSON list if set; each item must have `field`, `prediction`, `horizon`
- On duplicate `query_hash`: `INSERT OR REPLACE`

---

## 7. `db_metadata`

Simple operational key-value store. No relationships.

### Fields

| Field | Type | Constraints | Notes |
|-------|------|-------------|-------|
| `key` | String(128) | PK | e.g. `"last_ingestion"`, `"paper_count"`, `"faiss_built_at"` |
| `value` | String(512) | nullable | ISO 8601 strings or integer strings |

### Well-Known Keys

| Key | Format | Example |
|-----|--------|---------|
| `last_ingestion` | ISO 8601 UTC | `"2026-06-30T00:00:00Z"` |
| `paper_count` | integer string | `"42381"` |
| `faiss_built_at` | ISO 8601 UTC | `"2026-06-30T01:00:00Z"` |
| `precompute_completed_at` | ISO 8601 UTC | `"2026-06-30T03:00:00Z"` |
| `cache_hit_rate_24h` | float string | `"0.944"` |

### SQLAlchemy Model

```python
class DbMetadata(Base):
    __tablename__ = "db_metadata"

    key   = Column(String(128), primary_key=True)
    value = Column(String(512), nullable=True)
```

---

## 8. Pydantic LLM Output Schemas (`backend/llm/schemas.py`)

These models enforce the JSON contract on all LLM responses. Parsing failures trigger one automatic retry.

```python
from pydantic import BaseModel, Field, field_validator
from typing import Literal, Optional
import re

# ── Adjacent Mapper ───────────────────────────────────────────────────────────

class IdeaOutput(BaseModel):
    title: str = Field(min_length=3, max_length=120)
    description: str = Field(min_length=10, max_length=600)
    novelty_rationale: str = Field(min_length=5, max_length=200)
    confidence: int = Field(ge=0, le=100)
    engines_used: Optional[list[str]] = None

    @field_validator("title")
    @classmethod
    def title_not_empty(cls, v: str) -> str:
        return v.strip()

class AdjacentSynthesisResponse(BaseModel):
    ideas: list[IdeaOutput] = Field(min_length=3, max_length=10)

    @field_validator("ideas")
    @classmethod
    def no_duplicate_titles(cls, ideas: list[IdeaOutput]) -> list[IdeaOutput]:
        titles = [i.title.lower() for i in ideas]
        if len(titles) != len(set(titles)):
            raise ValueError("Duplicate idea titles in LLM output")
        return ideas


# ── Lineage Tracer ────────────────────────────────────────────────────────────

class TransitionOutput(BaseModel):
    from_id: str = Field(min_length=1)
    to_id: str = Field(min_length=1)
    leap: str = Field(min_length=3, max_length=80)

    @field_validator("from_id", "to_id")
    @classmethod
    def ids_differ(cls, v: str) -> str:
        return v.strip()

class NarrativeOutput(BaseModel):
    narrative: str = Field(min_length=20, max_length=1000)
    pivotal_paper_id: str = Field(min_length=1)
    transitions: list[TransitionOutput] = Field(default_factory=list)


# ── Frontier Prediction ───────────────────────────────────────────────────────

class FrontierOutput(BaseModel):
    field: str = Field(min_length=2, max_length=100)
    prediction: str = Field(min_length=10, max_length=300)
    horizon: Literal["1-2 years", "3-5 years", "5-10 years"]
    reasoning: str = Field(min_length=5, max_length=200)

class FrontierResponse(BaseModel):
    predictions: list[FrontierOutput] = Field(min_length=1, max_length=5)
```

---

## 9. TypeScript Frontend Types (`frontend/lib/types.ts`)

```typescript
// ── Mapper ────────────────────────────────────────────────────────────────────

export interface MapResult {
  field: string;
  why: string;
  blocker: string;
  leap: "near" | "mid" | "far";
  adoption_urgency: number;   // 0-100
  feasibility_now: number;    // 0-100
  confidence: number;         // 0-100
  engines_used?: string[];
  _score?: number;
}

export interface MapResponse {
  technology: string;
  results: MapResult[];
  cached_at?: string | null;  // ISO 8601
  engines_used?: string[];
}

// ── Tracer ────────────────────────────────────────────────────────────────────

export interface ChainPaper {
  corpus_id: string;
  title: string;
  abstract: string;
  year: number | null;
  citation_count: number;
  cd_index: number | null;
  novelty_score: number | null;
  breakthrough_score: number | null;
  arxiv_id: string | null;
  doi: string | null;
}

export interface EdgeLink {
  source: string;
  target: string;
}

export interface FrontierItem {
  field: string;
  prediction: string;
  horizon: "1-2 years" | "3-5 years" | "5-10 years";
  reasoning?: string;
}

export interface TransitionItem {
  from_id: string;
  to_id: string;
  leap: string;
}

export interface TraceResponse {
  query: string;
  chain: ChainPaper[];
  narrative: string;
  transitions: TransitionItem[];
  pivotal_paper_id: string | null;
  frontier: FrontierItem[];
  edges: EdgeLink[];
}

// ── Search ────────────────────────────────────────────────────────────────────

export interface Paper {
  corpus_id: string;
  doi: string | null;
  arxiv_id: string | null;
  title: string;
  abstract: string | null;
  year: number | null;
  fields_of_study: string[];
  citation_count: number;
  citation_velocity: number;
  influential_citation_count: number;
  cd_index: number | null;
  novelty_score: number;
  breakthrough_score: number;
  citation_velocity_percentile: number;
  cd_index_percentile: number;
  one_line_reason: string | null;
  context_summary: string | null;
  final_score: number;
}

// ── Feedback ──────────────────────────────────────────────────────────────────

export type VoteDirection = "up" | "down";

export interface FeedbackPayload {
  result_hash: string;
  vote: VoteDirection;
  query: string;
  timestamp: string;  // ISO 8601
}

// ── Client-side validation helpers ───────────────────────────────────────────

export function validateQuery(q: string): string | null {
  if (!q || q.trim().length < 2) return "Query must be at least 2 characters.";
  if (q.trim().length > 500) return "Query must be under 500 characters.";
  return null;
}

export function validateWeight(w: number): string | null {
  if (w < 0 || w > 1) return "Weight must be between 0 and 1.";
  return null;
}
```

---

## 10. Data Integrity Rules Summary

| Rule | Layer | Enforcement |
|------|-------|-------------|
| `corpus_id` uniqueness | DB | `UNIQUE` constraint + SQLAlchemy `IntegrityError` caught at ingest |
| Citation self-loops forbidden | App | Ingest script checks `source ≠ target` before insert |
| LLM output schema | App | Pydantic validation; one automatic retry on failure |
| Embedding dimension | App | Checked on write: must be list of exactly 384 floats (MiniLM) |
| Duplicate cache entries | DB | `seed_hash` / `query_hash` UNIQUE; upsert pattern used |
| FK referential integrity | DB | SQLite FK enforcement enabled (`PRAGMA foreign_keys = ON`) |
| Concept score range | App | Ingest script clamps to `[0.0, 1.0]` |
| Year sanity | App | Ingest script rejects `year < 1800` or `year > current_year + 1` |
| No user data without opt-in | Policy | Feedback stored as anonymous `result_hash` only; no IP, no account |
