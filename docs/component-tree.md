# Component Tree — Adjacency Research Engine v2.0

Describes the React/Next.js component hierarchy, component responsibilities, props contracts, and state ownership.

---

## 1. Page-Level Structure

```
<RootLayout>                   app/layout.tsx
  └── <Home>                   app/page.tsx            ← currently monolithic; to be split
        ├── <ShaderGradientBackground />               animated WebGL backdrop (fixed, z=-1)
        ├── <Sidebar>
        │     ├── <AppLogo />                          brand name + tagline
        │     ├── <ModeSwitcher>                       "map" | "trace" tab selector (Framer motion)
        │     │     ├── <ModeTabButton mode="map" />
        │     │     └── <ModeTabButton mode="trace" />
        │     ├── <QueryPanel mode="map">              search input + example chips for Mapper
        │     │     ├── <SearchInput />
        │     │     └── <ExampleChips examples={EXAMPLES_MAP} />
        │     └── <QueryPanel mode="trace">            search input + example chips for Tracer
        │           ├── <SearchInput />
        │           └── <ExampleChips examples={EXAMPLES_TRACE} />
        │
        └── <MainContent>
              ├── [mode="map"]  → <MapperView>
              └── [mode="trace"] → <TracerView>
```

---

## 2. Mapper View (`<MapperView>`)

**Owns:** `mapResponse`, `mapLoading`, `mapError`, `mapEmpty`, `selectedMapIndex`

```
<MapperView>
  ├── <LoadingIndicator steps={MAP_STEPS} currentStep={mapStep} />   (while loading)
  ├── <EmptyState message={mapEmpty} />                              (on empty result)
  ├── <ErrorBanner message={mapError} />                             (on fetch error)
  │
  └── [when mapResponse ≠ null]
        ├── <MapperHeader technology={mapResponse.technology} count={results.length} />
        │     └── <LastUpdatedBadge />                                "Data as of…" timestamp
        │
        ├── <ScatterPlot
        │     results={results}
        │     selectedIndex={selectedMapIndex}
        │     onSelectIndex={setSelectedMapIndex}
        │   />                                                        SVG: urgency × feasibility axes
        │
        ├── <IdeaGrid results={results} selectedIndex={selectedMapIndex}>
        │     └── <IdeaCard> × N
        │           ├── <LeapBadge leap={result.leap} />              "Adjacent Possible" | "Stretch" | "Frontier"
        │           ├── <ConfidenceMeter value={result.confidence} />  numeric 0-100
        │           ├── <AdoptionBar value={result.adoption_urgency} />
        │           ├── <FeasibilityBar value={result.feasibility_now} />
        │           ├── <EngineTag engines={result.engines_used} />   "semantic | concept | llm"
        │           ├── <EvidenceDrawer>                              slide-in on click
        │           │     ├── <PaperCitation> × M                    source papers
        │           │     └── <ConceptChip> × K                      source concept gaps
        │           └── <FeedbackButtons resultHash={hash} />         upvote / downvote
        │
        └── <ShareButton resultHash={queryHash} />
```

### IdeaCard Props

```ts
interface IdeaCardProps {
  result: MapResult;
  isSelected: boolean;
  onClick: () => void;
}

interface MapResult {
  field: string;
  why: string;
  blocker: string;
  leap: "near" | "mid" | "far";
  adoption_urgency: number;    // 0-100
  feasibility_now: number;     // 0-100
  confidence: number;          // 0-100
  engines_used?: string[];
  evidence_papers?: string[];  // corpus_ids
  evidence_concepts?: string[];
}
```

---

## 3. Tracer View (`<TracerView>`)

**Owns:** `traceResponse`, `traceLoading`, `traceError`, `activeTracePaperId`

```
<TracerView>
  ├── <LoadingIndicator steps={TRACE_STEPS} currentStep={traceStep} />  (while loading)
  ├── <ErrorBanner message={traceError} />
  │
  └── [when traceResponse ≠ null]
        ├── <TracerHeader query={traceResponse.query} />
        │     └── <LastUpdatedBadge />
        │
        ├── <CitationMiniGraph
        │     chain={chain}
        │     edges={edges}
        │     pivotalId={pivotal_paper_id}
        │   />                                                          SVG: node per paper, edges as lines
        │
        ├── <NarrativeBlock narrative={narrative} />                     LLM prose block (styled blockquote)
        │
        ├── <LineageTimeline
        │     papers={chain}
        │     transitions={transitions}
        │     pivotalId={pivotal_paper_id}
        │     activePaperId={activeTracePaperId}
        │     onSelectPaper={setActiveTracePaperId}
        │   >
        │     └── <TimelinePaperNode> × N
        │           ├── year label (absolute left)
        │           ├── <TransitionLeap label={transition.leap} />       inline badge before card
        │           ├── paper card (title, citation count, arxiv link)
        │           └── [expanded] abstract + DOI + arXiv links
        │
        └── <FrontierCards predictions={frontier}>
              └── <FrontierCard> × 3
                    ├── field title
                    ├── prediction sentence
                    ├── <HorizonBadge horizon="1-2 years" />
                    └── reasoning note
```

### ChainPaper Props (shared type)

```ts
interface ChainPaper {
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
```

---

## 4. Shared / UI Primitives

| Component | File | Purpose |
|-----------|------|---------|
| `<LoadingIndicator>` | `components/ui/LoadingIndicator.tsx` | Step-by-step progress bar with checkmarks; fake timer driven |
| `<Spinner>` | `components/ui/Spinner.tsx` | CSS border-spin animation; accepts `size` + `color` props |
| `<ErrorBanner>` | `components/ui/ErrorBanner.tsx` | Red-tinted dismissable alert |
| `<EmptyState>` | `components/ui/EmptyState.tsx` | Centred message with suggestion text |
| `<LeapBadge>` | `components/ui/LeapBadge.tsx` | Color-coded pill: `near` (green) / `mid` (amber) / `far` (purple) |
| `<HorizonBadge>` | `components/ui/HorizonBadge.tsx` | Time-range pill for frontier cards |
| `<EngineTag>` | `components/ui/EngineTag.tsx` | Icon + label chip per engine source |
| `<LastUpdatedBadge>` | `components/shared/LastUpdatedBadge.tsx` | Reads `db_metadata.last_ingestion`; renders "Updated: Jun 30" |
| `<EvidenceDrawer>` | `components/shared/EvidenceDrawer.tsx` | Slide-in panel: papers + concepts that justify a suggestion |
| `<FeedbackButtons>` | `components/shared/FeedbackButtons.tsx` | 👍 / 👎 → POST `/api/feedback`; optimistic UI toggle |
| `<ShareButton>` | `components/shared/ShareButton.tsx` | Copies `?result=<hash>` URL to clipboard; toast confirmation |
| `<ExampleChips>` | `components/search/ExampleChips.tsx` | Row of clickable preset queries |
| `<SearchInput>` | `components/search/SearchInput.tsx` | Controlled text input with icon, clear button, Enter submit |

---

## 5. State Architecture

State is managed with local `useState` at the page level (no global store needed for v2.0).  
SWR is used for data fetching; results are cached by the SWR key (query string).

```
page.tsx (Home)
  │
  ├── activeTab: "map" | "trace"          ← Tab selector (sidebar)
  │
  ├── MAP STATE
  │     mapQuery: string
  │     mapLoading: boolean
  │     mapStep: number                   ← fake progress step index
  │     mapResponse: MapResponse | null
  │     mapError: string | null
  │     mapEmpty: string | null
  │     selectedMapIndex: number | null   ← which IdeaCard is expanded
  │
  └── TRACE STATE
        traceQuery: string
        traceLoading: boolean
        traceStep: number
        traceResponse: TraceResponse | null
        traceError: string | null
        activeTracePaperId: string | null  ← which TimelinePaperNode is expanded
```

**Event flow (Mapper):**
```
User types query → setMapQuery
User hits Enter  → handleMap()
  → setMapLoading(true)
  → startFakeProgress(setMapStep)   (setTimeout chain, visual only)
  → fetch POST /map
  → on success: setMapResponse(data), clearFakeProgress()
  → on error:   setMapError(message), clearFakeProgress()
User clicks IdeaCard → setSelectedMapIndex(i)
User clicks EvidenceDrawer → rendered inline (no extra state needed)
User votes → FeedbackButtons: local optimistic state + POST /api/feedback
```

---

## 6. Animations & Motion

All transitions use **Framer Motion** (`framer-motion` package, already installed).

| Element | Animation |
|---------|-----------|
| Mode tab active indicator | `layoutId="activeModeTab"` spring slide |
| Results list appearance | `motion.div` with `fade-up` keyframe (CSS) |
| IdeaCard expansion | `AnimatePresence` + height transition |
| Sidebar query panel swap | `slide-in` CSS keyframe on mount |
| EvidenceDrawer open | translate-X slide from right |
| FrontierCards | staggered `motion.div` with delay × index |

---

## 7. CSS Design Tokens (globals.css)

All colours, spacing, and shadows are CSS custom properties:

```css
/* Surface layers */
--s0: hsl(220 13% 6%)    /* deepest background */
--s1: hsl(220 12% 9%)
--s2: hsl(220 10% 13%)   /* card borders */

/* Text hierarchy */
--t1: hsl(220 20% 96%)
--t2: hsl(220 15% 75%)
--t3: hsl(220 12% 52%)
--t4: hsl(220 10% 35%)

/* Accent (indigo) */
--accent:     hsl(248 85% 65%)
--accent-bg:  hsl(248 85% 65% / 0.08)
--accent-dim: hsl(248 70% 55% / 0.05)

/* Leap colours */
--near:  hsl(142 72% 55%)   /* Adjacent Possible */
--mid:   hsl(38  95% 60%)   /* Stretch Leap */
--far:   hsl(270 80% 65%)   /* Frontier Leap */

/* Borders */
--b1: hsl(220 12% 16%)
```
