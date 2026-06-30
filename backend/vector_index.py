import os
import json
import logging
from typing import List, Tuple
import numpy as np
import faiss
from database import Paper

logger = logging.getLogger(__name__)

INDEX_PATH = os.path.join(os.path.dirname(__file__), "index.faiss")
IDS_PATH = os.path.join(os.path.dirname(__file__), "index_ids.json")

_faiss_index = None
_paper_ids = []

def build_faiss_index(session) -> bool:
    """Builds FAISS index from paper embeddings in DB and saves to disk."""
    try:
        logger.info("Fetching paper embeddings from database to build FAISS index...")
        papers = session.query(Paper).filter(Paper.embedding != None).all()
        if not papers:
            logger.warning("No papers with embeddings found in database.")
            return False

        embeddings = []
        ids = []
        for p in papers:
            try:
                emb = json.loads(p.embedding)
                if len(emb) == 384:
                    embeddings.append(emb)
                    ids.append(p.corpus_id)
            except Exception:
                continue

        if not embeddings:
            logger.warning("No valid 384-dimensional embeddings found.")
            return False

        # Convert to numpy float32 array
        xb = np.array(embeddings).astype('float32')
        # L2 normalize vectors for cosine similarity (Inner Product)
        faiss.normalize_L2(xb)

        # Create IndexFlatIP
        d = 384
        index = faiss.IndexFlatIP(d)
        index.add(xb)

        # Save to disk
        faiss.write_index(index, INDEX_PATH)
        with open(IDS_PATH, "w", encoding="utf-8") as f:
            json.dump(ids, f, ensure_ascii=False)

        global _faiss_index, _paper_ids
        _faiss_index = index
        _paper_ids = ids

        logger.info(f"FAISS index built successfully with {len(ids)} papers.")
        return True
    except Exception as e:
        logger.error(f"Failed to build FAISS index: {e}")
        return False

def load_faiss_index():
    """Loads FAISS index and ID mapping from disk if not already in memory."""
    global _faiss_index, _paper_ids
    if _faiss_index is not None and _paper_ids:
        return _faiss_index, _paper_ids

    if os.path.exists(INDEX_PATH) and os.path.exists(IDS_PATH):
        try:
            logger.info("Loading FAISS index from disk...")
            _faiss_index = faiss.read_index(INDEX_PATH)
            with open(IDS_PATH, "r", encoding="utf-8") as f:
                _paper_ids = json.load(f)
            logger.info(f"FAISS index loaded with {len(_paper_ids)} vectors.")
            return _faiss_index, _paper_ids
        except Exception as e:
            logger.error(f"Error loading FAISS index: {e}")
    
    return None, []

def search_faiss_index(query_emb: List[float], top_k: int = 50) -> List[Tuple[str, float]]:
    """Search FAISS index for nearest neighbors. Returns list of (corpus_id, score)."""
    if not query_emb:
        return []

    index, ids = load_faiss_index()
    if index is None or not ids:
        logger.warning("FAISS index not loaded or empty.")
        return []

    try:
        # Format query vector
        xq = np.array([query_emb]).astype('float32')
        faiss.normalize_L2(xq)

        # Search index
        scores, indices = index.search(xq, min(top_k, len(ids)))
        
        results = []
        for score, idx in zip(scores[0], indices[0]):
            if idx != -1 and idx < len(ids):
                results.append((ids[idx], float(score)))
        return results
    except Exception as e:
        logger.error(f"FAISS search failed: {e}")
        return []
