import os
import re
import logging

logger = logging.getLogger(__name__)


def score_novelty(abstract: str, prior_abstracts: str) -> float:
    """
    Score the novelty of a new abstract relative to prior abstracts.
    Routes through the shared LLM chain (Gemini → Groq → OpenRouter → …)
    so it survives any single provider's rate-limit.
    Returns a float between 0.0 and 1.0.
    """
    if not abstract:
        return 0.5

    prompt = (
        "You are an AI research evaluator. You will be shown a NEW paper abstract "
        "and a set of PRIOR paper abstracts from the same field. Rate the novelty of "
        "the new work on a continuous scale from 0 to 1, where 0 means it is completely "
        "derivative or obvious, and 1 means it introduces a radically new problem, method, "
        "or result that significantly departs from prior work. Only respond with a number.\n\n"
        f"NEW ABSTRACT:\n{abstract}\n\n"
        f"PRIOR ABSTRACTS:\n{prior_abstracts}"
    )

    try:
        from llm import call_llm_chain
        text = call_llm_chain(prompt, temperature=0.1)
        if not text:
            logger.warning("All LLM providers unavailable for novelty scoring. Using fallback 0.65.")
            return 0.65

        match = re.search(r"[-+]?\d*\.\d+|\d+", text)
        if match:
            score = float(match.group())
            return max(0.0, min(1.0, score))
        return 0.5

    except Exception as e:
        logger.error(f"Error during novelty scoring: {e}")
        return 0.5
