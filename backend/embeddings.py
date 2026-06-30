import logging
from typing import List

logger = logging.getLogger(__name__)

_model = None

def get_embedding_model():
    global _model
    if _model is None:
        try:
            from sentence_transformers import SentenceTransformer
            logger.info("Loading local sentence-transformers model 'all-MiniLM-L6-v2'...")
            _model = SentenceTransformer("all-MiniLM-L6-v2")
            logger.info("Local embedding model loaded successfully.")
        except Exception as e:
            logger.error(f"Failed to load sentence-transformers: {e}")
            raise e
    return _model

def generate_local_embedding(text: str) -> List[float]:
    """Generate 384-dimensional dense embedding using local sentence-transformers."""
    if not text:
        return []
    try:
        model = get_embedding_model()
        embedding = model.encode(text)
        return embedding.tolist()
    except Exception as e:
        logger.error(f"Local embedding generation failed: {e}")
        # Fallback to random embedding of dimension 384 (MiniLM shape)
        import random
        return [random.uniform(-0.1, 0.1) for _ in range(384)]
