import os
import sys
import json
import time
import hashlib
import requests
from pathlib import Path
from dotenv import load_dotenv

# Reconfigure stdout/stderr to UTF-8 to support unicode characters on Windows
if sys.stdout.encoding != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        pass
if sys.stderr.encoding != "utf-8":
    try:
        sys.stderr.reconfigure(encoding="utf-8")
    except AttributeError:
        pass

load_dotenv()

# LLM calls handled by the shared provider chain in llm.py
from llm import call_llm_chain

# ── Cache ─────────────────────────────────────────────────────────────────────

CACHE_DIR = Path(__file__).parent / "cache"
CACHE_DIR.mkdir(exist_ok=True)
CACHE_TTL_SECONDS = 60 * 60 * 6  # 6 hours


def _cache_key(technology: str) -> str:
    return hashlib.sha1(technology.lower().strip().encode()).hexdigest()


def _load_cache(technology: str) -> list | None:
    key = _cache_key(technology)
    
    # 1. Try SQLite database cache
    try:
        from database import SessionLocal, PrecomputedAdjacency
        db = SessionLocal()
        try:
            cached = db.query(PrecomputedAdjacency).filter_by(seed_hash=key).first()
            if cached:
                print(f"  [DB cache hit] Returning cached results for '{technology}'")
                return json.loads(cached.idea_json)
        finally:
            db.close()
    except Exception as e:
        print(f"  [DB cache check failed] {e}")

    # 2. Fallback to file cache
    path = CACHE_DIR / f"{key}.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        age = time.time() - data.get("ts", 0)
        if age > CACHE_TTL_SECONDS:
            path.unlink(missing_ok=True)
            return None
        print(f"  [file cache hit] Returning cached results for '{technology}'")
        return data["results"]
    except Exception:
        return None


def _save_cache(technology: str, results: list) -> None:
    key = _cache_key(technology)
    
    # 1. Save to SQLite database cache
    try:
        from database import SessionLocal, PrecomputedAdjacency
        db = SessionLocal()
        try:
            existing = db.query(PrecomputedAdjacency).filter_by(seed_hash=key).first()
            if existing:
                existing.idea_json = json.dumps(results, ensure_ascii=False)
            else:
                new_cache = PrecomputedAdjacency(
                    seed_hash=key,
                    idea_json=json.dumps(results, ensure_ascii=False),
                    engines_used="semantic,concept,llm"
                )
                db.add(new_cache)
            db.commit()
            print(f"  [DB cache write success] Cached '{technology}'")
        finally:
            db.close()
    except Exception as e:
        print(f"  [DB cache write failed] {e}")

    # 2. Save to file cache
    path = CACHE_DIR / f"{key}.json"
    try:
        path.write_text(
            json.dumps({"ts": time.time(), "technology": technology, "results": results}, ensure_ascii=False),
            encoding="utf-8",
        )
    except Exception as e:
        print(f"  [file cache write failed] {e}")


# (LLM helpers removed — all LLM calls route through call_llm_chain from llm.py)


def parse_json_response(raw: str) -> list | dict | None:
    """
    Robustly parse a JSON response from the LLM.
    Handles: markdown fences (```json, ```JSON, ```), object wrappers,
    uppercase fences, and trailing whitespace.
    Returns the parsed object, or None on failure.
    """
    raw = raw.strip()

    # Strip markdown fences (case-insensitive)
    if raw.lower().startswith("```json"):
        raw = raw[7:]
    elif raw.startswith("```"):
        raw = raw[3:]
    if raw.endswith("```"):
        raw = raw[:-3]
    raw = raw.strip()

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"    JSON parse failed: {e}")
        print(f"    Raw (first 500 chars): {raw[:500]}")
        return None

    # If the model accidentally wrapped the array in an object, unwrap it
    if isinstance(parsed, dict):
        for key in ("results", "fields", "data", "evaluations", "items"):
            if key in parsed and isinstance(parsed[key], list):
                return parsed[key]

    return parsed


# ── 1. Fetch papers ───────────────────────────────────────────────────────────

def fetch_papers_openalex(technology: str, limit: int = 20) -> list[dict]:
    """Fetch papers from OpenAlex with progressive year-range widening."""
    import datetime
    url = "https://api.openalex.org/works"
    current_year = datetime.datetime.now().year
    headers = {"User-Agent": "mailto:info@example.com (Adjacency Mapper Client)"}

    # Try progressively wider year windows: 5yr → 10yr → all-time
    for years_back in (5, 10, None):
        params: dict = {"search": technology, "per_page": limit}
        if years_back:
            params["filter"] = f"publication_year:{current_year - years_back}-{current_year}"
        try:
            resp = requests.get(url, params=params, headers=headers, timeout=12)
            resp.raise_for_status()
            results = resp.json().get("results", [])
            if not results:
                continue

            papers = []
            for work in results:
                inverted = work.get("abstract_inverted_index") or {}
                words = {}
                for word, positions in inverted.items():
                    for pos in positions:
                        words[pos] = word
                abstract = " ".join(words[p] for p in sorted(words)) if words else ""

                concepts = work.get("concepts", [])
                papers.append({
                    "title": work.get("title", ""),
                    "abstract": abstract,
                    "year": work.get("publication_year"),
                    "citationCount": work.get("cited_by_count", 0),
                    "fieldsOfStudy": [c.get("display_name") for c in concepts if c.get("display_name")],
                })
            print(f"  Found {len(papers)} papers via OpenAlex (window: {'all-time' if not years_back else f'{years_back}yr'})")
            return papers
        except requests.RequestException as e:
            print(f"  OpenAlex request failed: {e}")
            continue
    return []


def fetch_papers(technology: str, limit: int = 20) -> list[dict]:
    """
    Fetch papers with a robust multi-strategy approach:
    1. Semantic Scholar (no sort param — avoid 400 errors; no year filter to avoid empty returns)
    2. Semantic Scholar with expanded query
    3. OpenAlex fallback with progressive year widening
    Handles 429 rate limits with backoff.
    Always returns at least an empty list — pipeline degrades gracefully.
    """
    url = "https://api.semanticscholar.org/graph/v1/paper/search"
    base_params = {
        "query": technology,
        "limit": limit,
        "fields": "title,abstract,fieldsOfStudy,year,citationCount",
    }

    for attempt in range(3):
        try:
            resp = requests.get(url, params=base_params, timeout=12)
            if resp.status_code == 429:
                wait = 2 ** (attempt + 1)  # 2s, 4s, 8s
                print(f"  S2 rate limited (attempt {attempt+1}), waiting {wait}s...")
                time.sleep(wait)
                continue
            if resp.status_code == 400:
                # Bad request — likely unsupported param, skip S2
                print("  S2 returned 400, skipping to OpenAlex...")
                break
            resp.raise_for_status()
            papers = resp.json().get("data", [])
            # Accept papers with OR without abstracts — we'll handle missing abstracts downstream
            if papers:
                with_abs = [p for p in papers if p.get("abstract")]
                print(f"  Found {len(papers)} papers via S2 ({len(with_abs)} with abstracts)")
                return papers
        except requests.RequestException as e:
            print(f"  S2 attempt {attempt+1} failed: {e}")
            time.sleep(1)

    print("  Falling back to OpenAlex...")
    return fetch_papers_openalex(technology, limit)


# ── 2. Generate specific candidate fields from abstracts ──────────────────────

# Coarse top-level labels that are too broad to be useful
GENERIC_FIELDS_TO_SKIP = {
    "Computer Science", "Mathematics", "Physics", "Engineering",
    "Science", "Research", "Technology", "Social Sciences",
    "Philosophy", "Art", "History", "Biology", "Chemistry",
    "Medicine", "Economics", "Psychology",
}


def extract_coarse_fields(papers: list[dict]) -> list[str]:
    """Pull unique fieldsOfStudy labels, skipping generic ones."""
    seen = set()
    result = []
    for paper in papers:
        for f in paper.get("fieldsOfStudy") or []:
            label = f if isinstance(f, str) else (f.get("category") if isinstance(f, dict) else None)
            if label and label not in GENERIC_FIELDS_TO_SKIP and label not in seen:
                seen.add(label)
                result.append(label)
    return result


def generate_specific_fields(technology: str, papers: list[dict]) -> list[str]:
    """
    Use Groq to generate specific subfield/application candidates.
    Works with papers (extracts from abstracts) OR without papers
    (falls back to LLM knowledge about the technology).
    Forces the model to name fields where the technology is ABSENT today.
    """
    # Build context from papers that have abstracts
    papers_with_abs = [p for p in papers if p.get("abstract")]

    if papers_with_abs:
        abstracts = "\n\n".join(
            f"- [{p.get('year', '?')}] {p.get('title', 'Untitled')}: {(p.get('abstract') or '')[:400]}"
            for p in papers_with_abs[:12]
        )
        paper_context = f"Recent papers on this topic:\n{abstracts}\n\n"
        instruction = f"Based on these papers AND your own knowledge of {technology},"
    elif papers:
        # Have papers but no abstracts — use just titles
        titles = "\n".join(f"- {p.get('title', 'Untitled')} ({p.get('year', '?')})" for p in papers[:15])
        paper_context = f"Recent papers on this topic (titles only):\n{titles}\n\n"
        instruction = f"Based on these paper titles AND your own knowledge of {technology},"
    else:
        # No papers at all — rely purely on LLM knowledge
        paper_context = ""
        instruction = f"Using your knowledge of {technology},"
        print("  No papers found — using LLM knowledge only for field generation.")

    prompt = (
        f"Technology: {technology}\n\n"
        f"{paper_context}"
        f"{instruction} identify 14 specific fields where '{technology}' is NOT YET widely applied "
        f"but could plausibly solve a concrete, named problem.\n\n"
        f"STRICT RULES:\n"
        f"1. Each entry MUST name a specific sub-problem, NOT a broad domain.\n"
        f"   BAD: 'Medicine' or 'Healthcare' or 'Biology'\n"
        f"   GOOD: 'post-surgical adhesion prediction in minimally invasive surgery'\n"
        f"2. The field must currently LACK significant {technology} adoption — not just have room for improvement.\n"
        f"3. Each entry must be a distinct domain. No synonyms or near-duplicates.\n"
        f"4. Mix practical industries (manufacturing, agriculture, legal) with scientific niches.\n\n"
        f"Respond ONLY with a JSON list of strings. No markdown, no explanation.\n"
        f'Example: ["field one", "field two", "field three"]'
    )

    print("  Generating specific candidate fields...")
    raw = call_llm_chain(
        prompt=prompt,
        system_instruction="You are a cross-disciplinary research strategist. Respond only with a raw JSON list of strings. No markdown, no explanations.",
        temperature=0.6,
    )

    if not raw:
        return []

    parsed = parse_json_response(raw)
    if isinstance(parsed, list):
        fields = [str(f) for f in parsed if isinstance(f, str)]
        print(f"  Generated {len(fields)} specific candidate fields")
        return fields

    print("  Could not parse specific fields — continuing with coarse fields only.")
    return []


def build_candidate_fields(technology: str, papers: list[dict]) -> list[str]:
    """
    Combine coarse fields from metadata with specific fields from abstracts.
    Specific fields come first (higher quality), coarse supplement if needed.
    """
    coarse = extract_coarse_fields(papers)
    specific = generate_specific_fields(technology, papers)

    seen = set()
    combined = []
    for f in specific + coarse:
        f_lower = f.lower()
        if f_lower not in seen:
            seen.add(f_lower)
            combined.append(f)

    result = combined[:15]
    print(f"  Final candidate fields ({len(result)}): {result}")
    return result


# ── 3. Evaluate fields in batch ───────────────────────────────────────────────

EVAL_SYSTEM_PROMPT = """You are an expert in technology transfer and cross-disciplinary innovation assessment.
Evaluate whether a given technology could be valuably applied to each listed target field.

Respond ONLY with a valid JSON array — no preamble, no markdown, no explanation.

Each array item must have exactly this structure:
{
  "field": "<field name>",
  "why": "<one specific sentence: what named problem in this field could this technology solve>",
  "blocker": "<one sentence: the single most likely reason this field has not adopted it yet>",
  "leap": "<one of: near | mid | far>",
  "adoption_urgency": <integer 0-100>,
  "feasibility_now": <integer 0-100>,
  "confidence": <integer 0-100>
}

Scoring definitions:
- leap: 'near' = obvious fit, low conceptual distance, existing tools transfer directly.
        'mid' = requires real adaptation or new tooling.
        'far' = speculative frontier, requires 5+ years of research.
- adoption_urgency: how transformative would adoption be for this field RIGHT NOW (100 = field-changing, 0 = marginal).
- feasibility_now: how technically and practically feasible is adoption with TODAY's tools (100 = ready today, 0 = impossible without major breakthroughs).
- confidence: your certainty in this assessment (100 = very confident, 0 = highly speculative).

Critical rules:
- Be honest and specific. Weak fits should score low on urgency OR feasibility.
- NEVER give identical scores to different fields — differentiate meaningfully.
- Name the specific bottleneck or problem in 'why', not a generic benefit.
- 'near' fields should score higher on feasibility_now (>60). 'far' fields may score lower (<40)."""


def evaluate_fields_batch(technology: str, fields: list[str]) -> list[dict]:
    """Evaluate all candidate fields in a single Groq call."""
    prompt = (
        f"Technology: {technology}\n"
        f"Target fields to evaluate: {json.dumps(fields)}\n\n"
        f"Evaluate each field against the criteria. Return a JSON array with one object per field. "
        f"Ensure scores are meaningfully differentiated — no two fields should have identical urgency AND feasibility."
    )

    print(f"  Sending batch evaluation for {len(fields)} fields...")
    raw = call_llm_chain(
        prompt=prompt,
        system_instruction=EVAL_SYSTEM_PROMPT,
        temperature=0.3,
    )

    if not raw:
        return []

    parsed = parse_json_response(raw)
    if isinstance(parsed, list):
        print(f"  Received evaluations for {len(parsed)} fields")
        return parsed

    print("  Could not parse batch evaluation response.")
    return []


# ── 4. Score and rank ─────────────────────────────────────────────────────────

LEAP_ORDER = {"near": 0, "mid": 1, "far": 2}


def compute_score(result: dict) -> float:
    """
    Weighted score: urgency matters more than feasibility.
    Confidence adjusts the score slightly — lower confidence dampens extreme scores.

    High urgency + low feasibility  = interesting but hard (still surfaces it)
    Low urgency  + high feasibility = easy but not worth building toward
    """
    try:
        urgency = int(result.get("adoption_urgency", 0))
    except (ValueError, TypeError):
        urgency = 0
    try:
        feasibility = int(result.get("feasibility_now", 0))
    except (ValueError, TypeError):
        feasibility = 0
    try:
        confidence = int(result.get("confidence", 70))
    except (ValueError, TypeError):
        confidence = 70

    raw_score = (0.6 * urgency) + (0.4 * feasibility)
    # Confidence as a mild dampener: at confidence=100 -> multiplier=1.0, at 0 -> multiplier=0.7
    confidence_mult = 0.7 + 0.3 * (confidence / 100.0)
    return raw_score * confidence_mult


def rank_results(results: list[dict], top_k: int) -> list[dict]:
    """Sort by weighted score; use leap closeness as tiebreaker."""
    scored = []
    for r in results:
        r["_score"] = compute_score(r)
        scored.append(r)
    return sorted(
        scored,
        key=lambda r: (r["_score"], -LEAP_ORDER.get(r.get("leap", "far"), 2)),
        reverse=True,
    )[:top_k]


# ── 5. Main pipeline ──────────────────────────────────────────────────────────

def _is_fallback_result(results: list) -> bool:
    """Return True if results look like the hardcoded fallback — not real LLM output."""
    if not results:
        return True
    if len(results) == 1:
        r = results[0]
        title = str(r.get("title", ""))
        rationale = str(r.get("novelty_rationale", ""))
        if "Bio-Informatics" in title or "transfer learning methods" in rationale:
            return True
    return False


def map_adjacent_possible(technology: str, top_k: int = 10, use_cache: bool = True, force_refresh: bool = False) -> list[dict]:
    print(f"\n── Mapping adjacent possible for: '{technology}' ──\n")

    # Check cache first (skipped on force_refresh to allow live re-query)
    if use_cache and not force_refresh:
        cached = _load_cache(technology)
        if cached is not None:
            return cached[:top_k]

    print("Step 1: Fetching papers...")
    papers = fetch_papers(technology)
    paper_context = []
    if papers:
        for p in papers[:12]:
            paper_context.append(f"Title: {p.get('title')}\nAbstract: {p.get('abstract', '')[:300]}")
    
    papers_str = "\n\n".join(paper_context) if paper_context else "None"

    print("\nStep 2: Resolving conceptual gaps...")
    from database import SessionLocal
    from concept_walker import find_conceptual_gaps
    db = SessionLocal()
    gaps_str = "None"
    try:
        # Resolve concepts if any
        concepts_found = []
        if papers:
            for p in papers:
                if p.get("fieldsOfStudy"):
                    concepts_found.extend(p.get("fieldsOfStudy"))
        
        seed_concept = concepts_found[0] if concepts_found else "Computer Science"
        gaps = find_conceptual_gaps(seed_concept, db, limit=5)
        gaps_str = ", ".join(gaps) if gaps else "None"
    finally:
        db.close()

    print("\nStep 3: Evaluating and synthesizing adjacent fields...")
    from llm import call_llm_with_validation
    from schemas.idea_output import AdjacentIdea
    
    variables = {
        "seed_text": technology,
        "list_of_papers": papers_str,
        "conceptual_gaps": gaps_str
    }

    try:
        results = call_llm_with_validation(
            template_name="adjacent_synthesis",
            variables=variables,
            schema=AdjacentIdea,
            is_list=True,
            temperature=0.7
        )
    except Exception as e:
        print(f"LLM synthesis failed: {e}. Falling back to default ideas.")
        results = [
            {
                "title": f"Applied {technology} in Bio-Informatics",
                "description": "Applies the core concepts to sequence analysis.",
                "novelty_rationale": "Applies transfer learning methods.",
                "confidence": 75
            }
        ]

    # Save to cache — only if results are real (not the hardcoded fallback)
    if use_cache and results and not _is_fallback_result(results):
        _save_cache(technology, results)

    return results[:top_k]


# ── 6. Entry point ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    technology = input("Enter a technology or method to map: ").strip()
    if not technology:
        technology = "transformer architecture"

    results = map_adjacent_possible(technology, top_k=10)

    output_file = "results.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump({"technology": technology, "results": results}, f, indent=2, ensure_ascii=False)
    print(f"\nResults saved to {output_file}")
