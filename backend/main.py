import os
import sys
import time
import json
import random
import logging
import threading
from flask import Flask, request, jsonify
from flask_cors import CORS

# Local imports
from dotenv import load_dotenv
load_dotenv()

from database import init_db, SessionLocal, Paper
from novelty import GEMINI_API_KEY
from scripts.ingest_papers import run_ingestion

import google.generativeai as genai

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
# Enable CORS for Next.js frontend
CORS(app)

@app.before_request
def initialize():
    # Run once to ensure db is initialized
    if not hasattr(app, "_db_initialized"):
        logger.info("Initializing SQLite database...")
        init_db()
        app._db_initialized = True

def cosine_similarity(v1: list, v2: list) -> float:
    if not v1 or not v2:
        return 0.0
    dot_product = sum(x * y for x, y in zip(v1, v2))
    magnitude_v1 = sum(x * x for x in v1) ** 0.5
    magnitude_v2 = sum(x * x for x in v2) ** 0.5
    if magnitude_v1 * magnitude_v2 == 0:
        return 0.0
    return dot_product / (magnitude_v1 * magnitude_v2)

def are_titles_similar(t1: str, t2: str, threshold: float = 0.6) -> bool:
    import re
    def get_clean_words(text):
        words = re.findall(r'\b\w+\b', text.lower())
        stopwords = {
            'a', 'an', 'the', 'and', 'of', 'in', 'for', 'to', 'with', 'on', 'at', 'by', 'from', 'using', 'based',
            'potential', 'potentialities', 'challenges', 'clinical', 'advance', 'advances', 'progress', 'novel'
        }
        cleaned = []
        for w in words:
            if w in stopwords:
                continue
            # Simple stemming for plurals (e.g. vaccines -> vaccine, methods -> method)
            if len(w) > 3 and w.endswith('s'):
                w = w[:-1]
            cleaned.append(w)
        return set(cleaned)

    words1 = get_clean_words(t1)
    words2 = get_clean_words(t2)
    
    if not words1 or not words2:
        return False
        
    intersection = words1.intersection(words2)
    union = words1.union(words2)
    return (len(intersection) / len(union)) > threshold

from embeddings import generate_local_embedding

def generate_query_embedding(text: str) -> list:
    return generate_local_embedding(text)

def generate_llm_explanations(title: str, abstract: str) -> tuple:
    """Generate breakthrough one-liner and context summary using Gemini."""
    default_one_liner = f"Introduces a groundbreaking framework for solving key constraints in {title}."
    default_context = "**Problem Posed:** General bottleneck in state-of-the-art systems.\n\n**Solution Proposed:** Custom methodology that enhances performance."

    if not GEMINI_API_KEY:
        return (default_one_liner, default_context)

    try:
        model = genai.GenerativeModel("gemini-2.5-flash")
        
        # 1. One-liner
        prompt_one_liner = f"""You are an expert research communicator. Given a paper's title and abstract, write a single, punchy sentence that explains why this paper is considered groundbreaking. Mention the key innovation or finding.

Paper: "{title}"
Abstract: "{abstract}"

Breakthrough reason:"""
        res_one = model.generate_content(prompt_one_liner)
        one_liner_text = getattr(res_one, 'text', None)
        one_liner = one_liner_text.strip().strip('"') if one_liner_text else default_one_liner

        # 2. Context summary (Problem and Solution)
        prompt_context = f"""Write a concise two-part analysis of this paper based on its title and abstract:
1. Start with the label "**Problem Posed:** " followed by 1-2 sentences explaining the specific bottleneck or problem the paper addresses.
2. Follow with the label "**Solution Proposed:** " followed by 1-2 sentences explaining how this paper solves it.

Do not include any other text or headers.

Paper: "{title}"
Abstract: "{abstract}" """
        res_context = model.generate_content(prompt_context)
        context_text = getattr(res_context, 'text', None)
        context = context_text.strip() if context_text else default_context

        return one_liner, context
    except Exception as e:
        logger.error(f"Error generating Gemini explanations: {e}")
        return (default_one_liner, default_context)

def rerank_with_gemini(query: str, candidates: list) -> list:
    """Use Gemini to re-rank the top candidates for relevance."""
    if not GEMINI_API_KEY or not candidates:
        return candidates[:10]
    try:
        model = genai.GenerativeModel("gemini-2.5-flash")
        items = []
        for idx, p in enumerate(candidates):
            items.append(f"[{idx}] Title: {p.title}\nAbstract: {(p.abstract or '')[:300]}")
            
        papers_str = "\n\n".join(items)
        prompt = f"""You are an expert research ranker. Rate the relevance of these papers to the search query "{query}".
Respond ONLY with a JSON list of indices in order of relevance (most relevant first), e.g. [3, 0, 1, 2]. Do not include any other text.

PAPERS:
{papers_str}"""
        
        res = model.generate_content(prompt)
        # Guard: res.text can be None if response was blocked/filtered
        res_text = getattr(res, 'text', None)
        if not res_text:
            logger.warning("Gemini rerank returned empty/blocked response; using FAISS order.")
            return candidates[:10]
        text = res_text.strip()
        
        # Extract indices
        import re
        match = re.search(r"\[\s*\d+\s*(?:,\s*\d+\s*)*\]", text)
        if match:
            indices = json.loads(match.group())
            ranked = []
            for idx in indices:
                if 0 <= idx < len(candidates):
                    ranked.append(candidates[idx])
            # Append remaining ones
            for c in candidates:
                if c not in ranked:
                    ranked.append(c)
            return ranked[:10]
    except Exception as e:
        logger.error(f"Failed to rerank with Gemini: {e}")
    return candidates[:10]

def _live_fallback_search(topic: str, k: int) -> list:
    """
    When the local FAISS index has no relevant papers for a topic,
    fetch live results from OpenAlex and arXiv, format them as lightweight
    result dicts (without DB scores), and return them.
    """
    from scripts.ingest_papers import fetch_openalex_papers, fetch_arxiv_papers
    logger.info(f"No local results for '{topic}' — falling back to live OpenAlex/arXiv search.")

    oa_papers = fetch_openalex_papers(topic, limit=k * 3)
    ax_papers = fetch_arxiv_papers(topic, max_results=k * 2)

    seen_titles: set = set()
    merged = []
    for p in oa_papers + ax_papers:
        norm = (p.get("title") or "").strip().lower()
        if norm and norm not in seen_titles:
            seen_titles.add(norm)
            merged.append(p)

    results = []
    for p in merged[:k]:
        ext = p.get("externalIds") or {}
        results.append({
            "corpus_id": p.get("paperId", ""),
            "doi": ext.get("DOI"),
            "arxiv_id": ext.get("ArXiv"),
            "title": p.get("title", "Untitled"),
            "abstract": p.get("abstract", ""),
            "year": p.get("year"),
            "fields_of_study": p.get("fieldsOfStudy") or [],
            "citation_count": p.get("citationCount", 0),
            "citation_velocity": p.get("citationVelocity", 0.0),
            "influential_citation_count": p.get("influentialCitationCount", 0),
            "cd_index": None,
            "novelty_score": None,
            "breakthrough_score": None,
            "citation_velocity_percentile": 0.0,
            "cd_index_percentile": 0.0,
            "one_line_reason": None,
            "context_summary": None,
            "final_score": p.get("citationVelocity", 0.0),
            "live_result": True,  # flag so frontend can show a badge
        })
    return results


@app.route("/search", methods=["POST"])
def search_papers():
    start_time = time.time()
    req = request.get_json() or {}
    
    topic = req.get("topic", "")
    k = int(req.get("k", 5))
    w_velocity = float(req.get("w_velocity", 0.4))
    w_novelty = float(req.get("w_novelty", 0.3))
    w_cd = float(req.get("w_cd", 0.3))
    
    logger.info(f"Received search request for topic: {topic}")
    
    if not topic:
        return jsonify([])
        
    # 1. Embed query
    query_emb = generate_query_embedding(topic)
    
    # Fetch all papers with embeddings
    db = SessionLocal()
    try:
        papers = db.query(Paper).filter(Paper.embedding != None).all()
            
        # 2. Dense retrieval via local FAISS index
        from vector_index import search_faiss_index
        faiss_results = search_faiss_index(query_emb, top_k=20)

        # Check if FAISS results are meaningful (score > 0.3 cosine similarity)
        RELEVANCE_THRESHOLD = 0.3
        strong_faiss = [(cid, score) for cid, score in faiss_results if score >= RELEVANCE_THRESHOLD] if faiss_results else []
        
        top_candidates = []
        if strong_faiss:
            candidate_ids = [item[0] for item in strong_faiss]
            papers_map = {p.corpus_id: p for p in db.query(Paper).filter(Paper.corpus_id.in_(candidate_ids)).all()}
            top_candidates = [papers_map[cid] for cid in candidate_ids if cid in papers_map]
        
        # If no papers in DB at all OR no relevant local results → live fallback
        if not papers or not top_candidates:
            logger.info(f"Triggering live fallback for topic='{topic}' (papers_in_db={len(papers) if papers else 0}, strong_faiss={len(strong_faiss)})")
            live_results = _live_fallback_search(topic, k)
            duration = time.time() - start_time
            logger.info(f"Live fallback search completed in {duration:.3f}s with {len(live_results)} results")
            return jsonify(live_results)
            
        # 3. Re-rank using Gemini
        candidates = rerank_with_gemini(topic, top_candidates)
        
        # 4. Apply custom user weights to compute final score
        results = []
        for p in candidates:
            novelty = p.novelty_score if p.novelty_score is not None else 0.5
            final_score = (
                w_velocity * p.citation_velocity_percentile +
                w_novelty * (novelty * 100.0) +
                w_cd * p.cd_index_percentile
            )
            
            # 5. Populate/cache LLM explanations on the fly if missing or outdated format
            if not p.one_line_reason or not p.context_summary or "**Problem Posed:**" not in p.context_summary:
                logger.info(f"Generating explanations for: {p.title}")
                one_liner, context = generate_llm_explanations(p.title, p.abstract or "")
                p.one_line_reason = one_liner
                p.context_summary = context
                db.add(p)
                db.commit()
                
            fields_study = []
            if p.fields_of_study:
                try:
                    fields_study = json.loads(p.fields_of_study)
                except Exception:
                    pass
                    
            results.append({
                "corpus_id": p.corpus_id,
                "doi": p.doi,
                "arxiv_id": p.arxiv_id,
                "title": p.title,
                "abstract": p.abstract,
                "year": p.year,
                "fields_of_study": fields_study,
                "citation_count": p.citation_count,
                "citation_velocity": p.citation_velocity,
                "influential_citation_count": p.influential_citation_count,
                "cd_index": p.cd_index,
                "novelty_score": novelty,
                "breakthrough_score": p.breakthrough_score or 0.0,
                "citation_velocity_percentile": p.citation_velocity_percentile,
                "cd_index_percentile": p.cd_index_percentile,
                "one_line_reason": p.one_line_reason,
                "context_summary": p.context_summary,
                "final_score": final_score
            })
            
        # Sort descending by final weighted score
        results.sort(key=lambda x: x["final_score"], reverse=True)
        
        # Deduplicate/diversity filter to remove near-duplicate titles
        diverse_results = []
        for r in results:
            is_redundant = False
            for selected in diverse_results:
                if are_titles_similar(r["title"], selected["title"], threshold=0.55):
                    is_redundant = True
                    break
            if not is_redundant:
                diverse_results.append(r)
                if len(diverse_results) == k:
                    break
                    
        results = diverse_results
        
        duration = time.time() - start_time
        logger.info(f"Search query processed in {duration:.3f}s")
        
        return jsonify(results)
    finally:
        db.close()

@app.route("/internal/run_ingestion", methods=["POST"])
def trigger_ingestion():
    """Trigger database ingestion asynchronously."""
    thread = threading.Thread(target=run_ingestion)
    thread.start()
    return jsonify({"status": "Ingestion triggered in background."})


@app.route("/internal/ingest_edges", methods=["POST"])
def trigger_edge_ingestion():
    """Trigger citation edge ingestion for existing papers (graph layer population)."""
    from scripts.ingest_papers import ingest_citation_edges

    def run_edges():
        db = SessionLocal()
        try:
            from database import Paper
            all_ids = [p.corpus_id for p in db.query(Paper.corpus_id).all()]
            s2_key = os.environ.get("S2_API_KEY")
            ingest_citation_edges(db, all_ids, s2_api_key=s2_key)
        finally:
            db.close()

    thread = threading.Thread(target=run_edges)
    thread.start()
    return jsonify({"status": "Citation edge ingestion triggered in background."})


@app.route("/map", methods=["POST"])
def map_adjacent():
    """Run the adjacent-possible mapper for a given technology."""
    req = request.get_json() or {}
    technology = req.get("technology", "").strip()
    top_k = int(req.get("top_k", 10))
    use_cache = bool(req.get("use_cache", True))

    if not technology:
        return jsonify({"error": "technology field is required"}), 400

    try:
        from mapper import map_adjacent_possible
        results = map_adjacent_possible(technology, top_k=top_k, use_cache=use_cache)
        return jsonify({"technology": technology, "results": results})
    except Exception as e:
        logger.error(f"Mapper failed for '{technology}': {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/trace", methods=["POST"])
def trace_lineage_endpoint():
    """Trace the intellectual lineage of a query through the citation graph."""
    req = request.get_json() or {}
    query = req.get("query", "").strip()
    max_chain = int(req.get("max_chain", 8))

    if not query:
        return jsonify({"error": "query field is required"}), 400

    if not GEMINI_API_KEY:
        return jsonify({"error": "GEMINI_API_KEY not configured"}), 500

    try:
        from chain import trace_lineage
        s2_key = os.environ.get("S2_API_KEY")
        result = trace_lineage(
            query=query,
            gemini_api_key=GEMINI_API_KEY,
            s2_api_key=s2_key,
            max_chain_papers=max_chain,
        )
        return jsonify(result)
    except Exception as e:
        logger.error(f"Trace failed for '{query}': {e}")
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
