import os
import sys
import json
import hashlib
import logging
from datetime import datetime

# Adjust path to find backend files
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from database import SessionLocal, Paper, PrecomputedAdjacency, PrecomputedLineage, init_db
from llm import call_llm_with_validation
from schemas.idea_output import AdjacentIdea
from schemas.lineage_output import LineageNarrative, FrontierDirection
from concept_walker import find_conceptual_gaps
from vector_index import search_faiss_index
from graph import load_graph, expand_subgraph, find_bridge_papers, sort_by_year

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Core seed topics to precompute
SEED_TOPICS = [
    "attention mechanism transformer",
    "crispr cas9 gene editing",
    "quantum computing hardware",
    "thermonuclear fusion energy",
    "mrna vaccine immunotherapy",
    "large language models deep learning",
    "graphene nanotechnology",
    "solid state battery lithium",
]

def precompute_adjacency_for_topic(technology: str, db):
    """Precompute adjacent possible ideas for a tech and save to SQLite."""
    tech_hash = hashlib.sha1(technology.lower().strip().encode()).hexdigest()
    
    # Check if already precomputed
    existing = db.query(PrecomputedAdjacency).filter_by(seed_hash=tech_hash).first()
    if existing:
        logger.info(f"Adjacency already cached for '{technology}'")
        return

    logger.info(f"Precomputing Adjacent Mapper ideas for: '{technology}'...")

    db_papers = []
    # 1. FAISS top neighbors for seed embedding context
    from embeddings import generate_local_embedding
    q_emb = generate_local_embedding(technology)
    neighbors = search_faiss_index(q_emb, top_k=20)
    
    if not neighbors:
        logger.info("  FAISS index search failed or empty, falling back to database query...")
        db_papers = db.query(Paper).filter(Paper.title.like(f"%{technology}%")).limit(12).all()
        if not db_papers:
            db_papers = db.query(Paper).order_by(Paper.breakthrough_score.desc()).limit(12).all()
        neighbors = [(p.corpus_id, 1.0) for p in db_papers]
    else:
        neighbor_ids = [n[0] for n in neighbors]
        db_papers = db.query(Paper).filter(Paper.corpus_id.in_(neighbor_ids)).all()
        
    paper_context = []
    for p in db_papers:
        paper_context.append(f"Title: {p.title}\nAbstract: {(p.abstract or '')[:300]}")
    
    papers_str = "\n\n".join(paper_context) if paper_context else "None"

    # 2. Get gaps via Concept Walker
    # Find most common concept for the technology search
    concepts_found = []
    if db_papers:
        for p in db_papers:
            if p.fields_of_study:
                try:
                    concepts_found.extend(json.loads(p.fields_of_study))
                except Exception:
                    pass
    
    seed_concept = concepts_found[0] if concepts_found else "Computer Science"
    gaps = find_conceptual_gaps(seed_concept, db, limit=5)
    gaps_str = ", ".join(gaps) if gaps else "None"

    # 3. Call LLM adjacent synthesis prompt with Pydantic validation
    variables = {
        "seed_text": technology,
        "list_of_papers": papers_str,
        "conceptual_gaps": gaps_str
    }

    try:
        ideas = call_llm_with_validation(
            template_name="adjacent_synthesis",
            variables=variables,
            schema=AdjacentIdea,
            is_list=True,
            temperature=0.7
        )

        new_cache = PrecomputedAdjacency(
            seed_hash=tech_hash,
            idea_json=json.dumps(ideas, ensure_ascii=False),
            engines_used="semantic,concept,llm",
            created_at=datetime.utcnow()
        )
        db.add(new_cache)
        db.commit()
        logger.info(f"✓ Cached Adjacent Mapper ideas for '{technology}'")
    except Exception as e:
        logger.error(f"Failed to precompute ideas for '{technology}': {e}")
        db.rollback()


def precompute_lineage_for_topic(query: str, db):
    """Precompute lineage chain, narrative, and prediction for a query."""
    query_hash = hashlib.sha1(query.lower().strip().encode()).hexdigest()
    
    existing = db.query(PrecomputedLineage).filter_by(query_hash=query_hash).first()
    if existing:
        logger.info(f"Lineage already cached for '{query}'")
        return

    logger.info(f"Precomputing Lineage Tracer for: '{query}'...")

    # 1. Retrieve seeds using local query embedding
    from embeddings import generate_local_embedding
    q_emb = generate_local_embedding(query)
    neighbors = search_faiss_index(q_emb, top_k=20)
    db_papers = []
    
    if not neighbors:
        logger.info("  FAISS index search failed or empty, falling back to database query...")
        db_papers = db.query(Paper).filter(Paper.title.like(f"%{query}%")).limit(12).all()
        if not db_papers:
            db_papers = db.query(Paper).order_by(Paper.breakthrough_score.desc()).limit(12).all()
        neighbors = [(p.corpus_id, 1.0) for p in db_papers]
    else:
        neighbor_ids = [n[0] for n in neighbors]
        db_papers = db.query(Paper).filter(Paper.corpus_id.in_(neighbor_ids)).all()
    seed_ids = [n[0] for n in neighbors]

    # 2. Subgraph expansion
    graph = load_graph(db)
    subgraph_nodes = expand_subgraph(graph, seed_ids, max_hops=3, max_nodes=200)

    # 3. Find bridge papers
    bridge_ids = find_bridge_papers(
        graph,
        subgraph_nodes,
        seeds=set(seed_ids),
        top_k=8,
    )

    bridge_papers_db = db.query(Paper).filter(Paper.corpus_id.in_(bridge_ids)).all()
    year_map = {p.corpus_id: (p.year or 9999) for p in bridge_papers_db}

    # 4. Temporal sort
    sorted_ids = sort_by_year(graph, bridge_ids, known_years=year_map)
    sorted_ids = [cid for cid in sorted_ids if cid in year_map][:8]

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
        })

    if not chain_papers:
        logger.warning(f"No chronological chain for query '{query}'")
        return

    # 5. Build prompts & LLM call narrative
    papers_str_list = []
    for i, p in enumerate(chain_papers):
        papers_str_list.append(
            f"[{i+1}] ({p['year']}) corpus_id={p['corpus_id']}\n"
            f"   Title: {p['title']}\n"
            f"   Abstract: {p['abstract'][:300]}"
        )
    papers_str = "\n\n".join(papers_str_list)

    # Resolve transition leaps automatically from graph connections
    transitions = []
    for i in range(len(sorted_ids) - 1):
        transitions.append(f"{sorted_ids[i]} -> {sorted_ids[i+1]}")
    transitions_str = "\n".join(transitions)

    # Lineage narrative LLM call
    try:
        narrative_res = call_llm_with_validation(
            template_name="lineage_narrative",
            variables={"list_of_papers": papers_str, "transitions": transitions_str},
            schema=LineageNarrative,
            is_list=False,
            temperature=0.2
        )
        
        # Frontier prediction LLM call
        pivotal_id = narrative_res.get("pivotal_paper_id")
        pivotal_paper = paper_by_id.get(pivotal_id, chain_papers[0])
        
        recent_edge_papers = "\n".join([f"- {p['title']} ({p['year']})" for p in chain_papers[-3:]])
        
        frontier_res = call_llm_with_validation(
            template_name="frontier_prediction",
            variables={
                "narrative": narrative_res.get("narrative"),
                "pivotal_title": pivotal_paper.get("title") if isinstance(pivotal_paper, dict) else pivotal_paper.title,
                "pivotal_year": pivotal_paper.get("year") if isinstance(pivotal_paper, dict) else pivotal_paper.year,
                "list_of_papers": recent_edge_papers
            },
            schema=FrontierDirection,
            is_list=True,
            temperature=0.7
        )

        # Build edge list for frontend graph visualisation
        edge_list = []
        for src in sorted_ids:
            for tgt in sorted_ids:
                if tgt in graph.neighbors(src):
                    edge_list.append({"source": src, "target": tgt})

        trace_data = {
            "query": query,
            "chain": chain_papers,
            "narrative": narrative_res.get("narrative", ""),
            "transitions": narrative_res.get("transitions", []),
            "pivotal_paper_id": narrative_res.get("pivotal_paper_id"),
            "frontier": frontier_res,
            "edges": edge_list,
        }

        new_cache = PrecomputedLineage(
            query_hash=query_hash,
            chain_json=json.dumps(trace_data, ensure_ascii=False),
            narrative=narrative_res.get("narrative"),
            frontier_json=json.dumps(frontier_res, ensure_ascii=False),
            created_at=datetime.utcnow()
        )
        db.add(new_cache)
        db.commit()
        logger.info(f"✓ Cached Lineage Tracer for '{query}'")

    except Exception as e:
        logger.error(f"Failed to precompute lineage for '{query}': {e}")
        db.rollback()


def run_precomputations():
    init_db()
    db = SessionLocal()
    try:
        for topic in SEED_TOPICS:
            precompute_adjacency_for_topic(topic, db)
            precompute_lineage_for_topic(topic, db)
    finally:
        db.close()
    logger.info("Precomputation seeding finished!")

if __name__ == "__main__":
    run_precomputations()
