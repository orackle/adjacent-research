"""
chain.py — Temporal RAG synthesis for intellectual lineage tracing.

Given a user query, this module:
  1. Retrieves seed papers via dense retrieval (embedding similarity).
  2. Expands a citation subgraph (BFS, 3 hops).
  3. Detects bridge papers (high hub score in subgraph).
  4. Sorts bridge papers chronologically.
  5. Synthesises a narrative "intellectual lineage" via Gemini.
  6. Returns structured chain data + frontier predictions.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Optional

import google.generativeai as genai

from database import SessionLocal, Paper, CitationEdge
from graph import CitationGraph, load_graph, expand_subgraph, find_bridge_papers, sort_by_year

logger = logging.getLogger(__name__)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _cosine_similarity(v1: list[float], v2: list[float]) -> float:
    if not v1 or not v2:
        return 0.0
    dot = sum(x * y for x, y in zip(v1, v2))
    mag1 = sum(x * x for x in v1) ** 0.5
    mag2 = sum(x * x for x in v2) ** 0.5
    if mag1 * mag2 == 0:
        return 0.0
    return dot / (mag1 * mag2)


from embeddings import generate_local_embedding

def _embed_query(query: str, api_key: str) -> list[float]:
    return generate_local_embedding(query)


def _fetch_seed_papers(query: str, api_key: str, db, top_k: int = 30) -> list[Paper]:
    """Dense retrieval from SQLite — returns top_k most similar papers."""
    q_emb = _embed_query(query, api_key)
    if not q_emb:
        # Fallback: return most cited papers
        return db.query(Paper).order_by(Paper.citation_count.desc()).limit(top_k).all()

    from vector_index import search_faiss_index
    faiss_results = search_faiss_index(q_emb, top_k=top_k)
    
    if not faiss_results:
        return db.query(Paper).order_by(Paper.citation_count.desc()).limit(top_k).all()

    candidate_ids = [item[0] for item in faiss_results]
    papers_map = {p.corpus_id: p for p in db.query(Paper).filter(Paper.corpus_id.in_(candidate_ids)).all()}
    return [papers_map[cid] for cid in candidate_ids if cid in papers_map]


def _enrich_citation_edges(seed_ids: list[str], api_key: Optional[str], db) -> None:
    """
    Fetch references for seed papers from OpenAlex and insert
    any missing citation edges into the DB on the fly.
    This keeps the graph populated without a full re-ingestion.
    """
    import urllib.parse
    import requests

    for corpus_id in seed_ids[:10]:  # Limit live fetches to avoid rate limits
        existing = db.query(CitationEdge).filter_by(source_corpus_id=corpus_id).first()
        if existing:
            continue  # Already have edges for this paper

        paper = db.query(Paper).filter_by(corpus_id=corpus_id).first()
        if not paper:
            continue

        headers = {"User-Agent": "mailto:info@example.com (Adjacency Mapper Client)"}
        url = None

        if corpus_id.startswith("https://openalex.org/") or corpus_id.startswith("W"):
            work_id = corpus_id
            if not work_id.startswith("https://"):
                work_id = f"https://openalex.org/{work_id}"
            url = f"https://api.openalex.org/works/{work_id}"
        elif paper.doi:
            url = f"https://api.openalex.org/works/https://doi.org/{paper.doi.strip()}"
        elif paper.arxiv_id:
            clean_arxiv = paper.arxiv_id.strip()
            if not clean_arxiv.startswith("arXiv:"):
                clean_arxiv = f"arXiv:{clean_arxiv}"
            url = f"https://api.openalex.org/works?filter=arxiv:{clean_arxiv}"
        else:
            encoded_title = urllib.parse.quote(paper.title)
            url = f"https://api.openalex.org/works?search={encoded_title}&per_page=1"

        try:
            resp = requests.get(url, headers=headers, timeout=10)
            if resp.status_code == 429:
                time.sleep(2)
                resp = requests.get(url, headers=headers, timeout=10)
            if not resp.ok:
                continue

            data = resp.json()
            if "results" in data:
                results = data.get("results", [])
                if not results:
                    continue
                work = results[0]
            else:
                work = data

            referenced_works = work.get("referenced_works", [])
            source_year = paper.year

            new_edges = []
            for ref_id in referenced_works:
                if not ref_id or ref_id == corpus_id:
                    continue
                new_edges.append(
                    CitationEdge(
                        source_corpus_id=corpus_id,
                        target_corpus_id=ref_id,
                        source_year=source_year,
                    )
                )

            if new_edges:
                try:
                    db.bulk_save_objects(new_edges)
                    db.commit()
                    logger.info(f"Inserted {len(new_edges)} citation edges for {corpus_id} from OpenAlex")
                except Exception:
                    db.rollback()

            time.sleep(0.2)  # Polite delay
        except Exception as e:
            logger.warning(f"Edge fetch failed for {corpus_id}: {e}")


# ── Narrative synthesis ───────────────────────────────────────────────────────

_NARRATIVE_SYSTEM = """You are an expert science historian and AI researcher.
You will be given a sequence of research papers in chronological order that represent
an intellectual lineage — how ideas built on each other over time.

Your task:
1. Write a compelling 3-5 sentence narrative that explains HOW each paper built on the
   previous one, forming a causal chain of ideas. Be specific about mechanisms, not vague.
2. Identify the single most pivotal "bridge" paper — the one that changed the direction
   most dramatically.
3. Name the key conceptual leap made at each step (one short phrase per transition).

Respond with ONLY a JSON object in this exact shape:
{
  "narrative": "<string: 3-5 sentence story of the intellectual chain>",
  "pivotal_paper_id": "<corpus_id of the most pivotal bridge paper>",
  "transitions": [
    {"from_id": "<id>", "to_id": "<id>", "leap": "<short phrase>"},
    ...
  ]
}"""


def _build_synthesis_prompt(papers_in_order: list[dict]) -> str:
    lines = []
    for i, p in enumerate(papers_in_order):
        lines.append(
            f"[{i+1}] ({p.get('year', '?')}) corpus_id={p['corpus_id']}\n"
            f"   Title: {p['title']}\n"
            f"   Abstract: {(p.get('abstract') or '')[:350]}"
        )
    return "\n\n".join(lines)


def synthesise_narrative(
    papers_in_order: list[dict],
    api_key: str,
) -> dict:
    """Call LLM with validation to generate the lineage narrative and transitions."""
    if not papers_in_order:
        return {
            "narrative": "The selected papers trace a clear progression of ideas over time.",
            "pivotal_paper_id": "",
            "transitions": [],
        }

    from llm import call_llm_with_validation
    from schemas.lineage_output import LineageNarrative

    papers_str = _build_synthesis_prompt(papers_in_order)
    transitions = []
    for i in range(len(papers_in_order) - 1):
        transitions.append(f"{papers_in_order[i]['corpus_id']} -> {papers_in_order[i+1]['corpus_id']}")
    transitions_str = "\n".join(transitions)

    try:
        return call_llm_with_validation(
            template_name="lineage_narrative",
            variables={"list_of_papers": papers_str, "transitions": transitions_str},
            schema=LineageNarrative,
            is_list=False,
            temperature=0.2
        )
    except Exception as e:
        logger.error(f"Narrative synthesis failed: {e}")
        return {
            "narrative": "These papers form a key intellectual chain in this research area.",
            "pivotal_paper_id": papers_in_order[0]["corpus_id"],
            "transitions": [],
        }


# ── Frontier prediction ───────────────────────────────────────────────────────

def predict_frontier(narrative: str, topic: str, api_key: str) -> list[dict]:
    """Call LLM with validation to predict 3 frontier directions based on the narrative."""
    from llm import call_llm_with_validation
    from schemas.lineage_output import FrontierDirection

    try:
        return call_llm_with_validation(
            template_name="frontier_prediction",
            variables={
                "narrative": narrative,
                "pivotal_title": "Pivotal Paper",
                "pivotal_year": "N/A",
                "list_of_papers": f"Related research on topic: {topic}"
            },
            schema=FrontierDirection,
            is_list=True,
            temperature=0.7
        )
    except Exception as e:
        logger.error(f"Frontier prediction failed: {e}")
        return []


# ── Main pipeline ─────────────────────────────────────────────────────────────

def trace_lineage(
    query: str,
    gemini_api_key: str,
    s2_api_key: Optional[str] = None,
    max_chain_papers: int = 8,
) -> dict:
    """
    Full pipeline: query → seed retrieval → graph expansion → bridge detection
    → temporal sort → narrative synthesis → frontier prediction.

    Returns a structured dict ready to be JSON-serialised and sent to the frontend.
    """
    db = SessionLocal()
    try:
        logger.info(f"[trace] query='{query}'")

        # Step 0: Check database cache
        import hashlib
        from database import PrecomputedLineage
        query_hash = hashlib.sha1(query.lower().strip().encode()).hexdigest()
        cached = db.query(PrecomputedLineage).filter_by(query_hash=query_hash).first()
        if cached:
            logger.info(f"[trace cache hit] returning cached trace for '{query}'")
            return json.loads(cached.chain_json)

        # Step 1: Dense retrieval for seeds
        seeds = _fetch_seed_papers(query, gemini_api_key, db, top_k=20)
        seed_ids = [p.corpus_id for p in seeds]
        logger.info(f"[trace] {len(seeds)} seed papers retrieved")

        # Step 2: Enrich citation edges from S2 for seeds we don't have yet
        _enrich_citation_edges(seed_ids, s2_api_key, db)

        # Step 3: Load graph and expand subgraph
        graph = load_graph(db)
        subgraph_nodes = expand_subgraph(graph, seed_ids, max_hops=3, max_nodes=200)
        logger.info(f"[trace] subgraph has {len(subgraph_nodes)} nodes")

        # Step 4: Find bridge papers
        bridge_ids = find_bridge_papers(
            graph,
            subgraph_nodes,
            seeds=set(seed_ids),
            top_k=max_chain_papers + 5,
        )

        # Step 5: Fetch Paper objects for bridge papers (must exist in DB)
        bridge_papers_db = (
            db.query(Paper)
            .filter(Paper.corpus_id.in_(bridge_ids))
            .all()
        )
        year_map = {p.corpus_id: (p.year or 9999) for p in bridge_papers_db}

        # Step 6: Temporal sort
        sorted_ids = sort_by_year(graph, bridge_ids, known_years=year_map)
        sorted_ids = [cid for cid in sorted_ids if cid in year_map][:max_chain_papers]

        # Build ordered paper dicts for synthesis
        paper_by_id = {p.corpus_id: p for p in bridge_papers_db}
        chain_papers = []
        for cid in sorted_ids:
            p = paper_by_id.get(cid)
            if not p:
                continue
            chain_papers.append({
                "corpus_id": p.corpus_id,
                "title": p.title,
                "abstract": p.abstract or "",
                "year": p.year,
                "citation_count": p.citation_count or 0,
                "cd_index": p.cd_index,
                "novelty_score": p.novelty_score,
                "breakthrough_score": p.breakthrough_score,
                "arxiv_id": p.arxiv_id,
                "doi": p.doi,
            })

        logger.info(f"[trace] {len(chain_papers)} bridge papers in chain")

        if not chain_papers:
            return {
                "query": query,
                "chain": [],
                "narrative": "Not enough connected papers found in the database. Try running ingestion first.",
                "transitions": [],
                "pivotal_paper_id": None,
                "frontier": [],
            }

        # Step 7: Narrative synthesis
        synthesis = synthesise_narrative(chain_papers, gemini_api_key)

        # Step 8: Frontier prediction
        frontier = predict_frontier(synthesis.get("narrative", ""), query, gemini_api_key)

        # Step 9: Build edge list for frontend graph visualisation
        edge_list = []
        for src in sorted_ids:
            for tgt in sorted_ids:
                if tgt in graph.neighbors(src):
                    edge_list.append({"source": src, "target": tgt})

        return {
            "query": query,
            "chain": chain_papers,
            "narrative": synthesis.get("narrative", ""),
            "transitions": synthesis.get("transitions", []),
            "pivotal_paper_id": synthesis.get("pivotal_paper_id"),
            "frontier": frontier,
            "edges": edge_list,
        }

    finally:
        db.close()
