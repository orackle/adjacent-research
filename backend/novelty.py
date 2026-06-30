import os
import re
import google.generativeai as genai

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
else:
    print("WARNING: GEMINI_API_KEY is not set. Novelty scoring will run in fallback mock mode.")

def score_novelty(abstract: str, prior_abstracts: str) -> float:
    """
    Score the novelty of a new abstract relative to prior abstracts using Gemini 1.5 Flash.
    Returns a float between 0.0 and 1.0.
    """
    if not abstract:
        return 0.5

    if not GEMINI_API_KEY:
        # Mock mode fallback
        return 0.65

    prompt = f"""You are an AI research evaluator. You will be shown a NEW paper abstract and a set of PRIOR paper abstracts from the same field. Rate the novelty of the new work on a continuous scale from 0 to 1, where 0 means it is completely derivative or obvious, and 1 means it introduces a radically new problem, method, or result that significantly departs from prior work. Only respond with a number.

NEW ABSTRACT:
{abstract}

PRIOR ABSTRACTS:
{prior_abstracts}"""

    try:
        model = genai.GenerativeModel("gemini-2.5-flash")
        response = model.generate_content(prompt)
        text = response.text.strip()
        
        # Extract floating point number from the output
        match = re.search(r"[-+]?\d*\.\d+|\d+", text)
        if match:
            score = float(match.group())
            # Normalize/clamp score to [0, 1]
            return max(0.0, min(1.0, score))
        return 0.5
    except Exception as e:
        print(f"Error calling Gemini API for novelty score: {e}")
        return 0.5
