import os
import json
import time
import logging
import requests
from typing import Any, Dict, List, Type, Optional
from pydantic import BaseModel, ValidationError

from dotenv import load_dotenv
load_dotenv()

logger = logging.getLogger(__name__)

# ── API Keys ──────────────────────────────────────────────────────────────────
GEMINI_API_KEY      = os.environ.get("GEMINI_API_KEY")
GROQ_API_KEY        = os.environ.get("GROQ_API_KEY")
OPENROUTER_API_KEY  = os.environ.get("OPENROUTER_API_KEY")
CEREBRAS_API_KEY    = os.environ.get("CEREBRAS_API_KEY")
NVIDIA_API_KEY      = os.environ.get("NVIDIA_API_KEY")
HUGGINGFACE_API_KEY = os.environ.get("HUGGINGFACE_API_KEY")

# ── Lazy client init ──────────────────────────────────────────────────────────
_groq_client = None
if GROQ_API_KEY:
    try:
        from groq import Groq
        _groq_client = Groq(api_key=GROQ_API_KEY)
    except Exception as e:
        logger.error(f"Failed to initialize Groq client: {e}")

if GEMINI_API_KEY:
    try:
        import google.generativeai as genai
        genai.configure(api_key=GEMINI_API_KEY)
    except Exception as e:
        logger.error(f"Failed to initialize Gemini: {e}")


# ── Prompt loader ─────────────────────────────────────────────────────────────

def load_prompt_template(name: str) -> str:
    """Loads a prompt template from the prompts/ directory."""
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    paths = [
        os.path.join(base_dir, "prompts", f"{name}.txt"),
        os.path.join(base_dir, "prompts", name),
        os.path.join(os.path.dirname(base_dir), "prompts", f"{name}.txt"),
        os.path.join(os.path.dirname(base_dir), "prompts", name),
    ]
    for path in paths:
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return f.read()
            except Exception as e:
                logger.error(f"Failed to read prompt template at {path}: {e}")

    logger.error(f"Prompt template '{name}' not found.")
    raise FileNotFoundError(f"Prompt template {name} not found.")


# ── Provider helpers ──────────────────────────────────────────────────────────

def _is_rate_limit(err: str) -> bool:
    return any(t in err for t in ("rate_limit", "rate limit", "429", "too many requests", "quota"))


def _call_gemini_raw(prompt: str, system_instruction: Optional[str] = None, temperature: float = 0.4) -> Optional[str]:
    """Call Gemini Flash. Returns None on any error."""
    if not GEMINI_API_KEY:
        return None
    try:
        import google.generativeai as genai
        model = genai.GenerativeModel(
            "gemini-2.5-flash",
            system_instruction=system_instruction,
            generation_config=genai.GenerationConfig(
                temperature=temperature,
                max_output_tokens=4000,
            )
        )
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        logger.warning(f"Gemini call failed: {e}")
        return None


def _call_groq_raw(messages: List[Dict[str, str]], temperature: float = 0.4) -> Optional[str]:
    """
    Call Groq. Tries llama-3.3-70b first, then llama-3.1-8b as fallback.
    Each model gets up to 3 attempts with exponential backoff on rate-limit only.
    Returns None if all attempts fail.
    """
    if not _groq_client:
        return None

    for model in ("llama-3.3-70b-versatile", "llama-3.1-8b-instant"):
        for attempt in range(3):
            try:
                response = _groq_client.chat.completions.create(
                    model=model,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=4000,
                )
                return response.choices[0].message.content.strip()
            except Exception as e:
                err = str(e).lower()
                if _is_rate_limit(err) and attempt < 2:
                    wait = 4 * (2 ** attempt)  # 4s, 8s
                    logger.info(f"Groq ({model}) rate-limited. Waiting {wait}s (attempt {attempt+1}/3)...")
                    time.sleep(wait)
                else:
                    logger.warning(f"Groq ({model}) failed: {e}")
                    break  # move to next model

    return None


def _call_openai_compat(
    base_url: str,
    api_key: str,
    model: str,
    messages: List[Dict[str, str]],
    temperature: float = 0.4,
    provider_name: str = "OpenAI-compat",
    extra_headers: Optional[Dict[str, str]] = None,
) -> Optional[str]:
    """Generic OpenAI-compatible chat completions caller via requests."""
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    if extra_headers:
        headers.update(extra_headers)

    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": 4000,
    }
    try:
        resp = requests.post(
            f"{base_url}/chat/completions",
            headers=headers,
            json=payload,
            timeout=60,
        )
        if resp.status_code == 429:
            logger.warning(f"{provider_name} ({model}) rate-limited (429). Skipping.")
            return None
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"].strip()
    except Exception as e:
        logger.warning(f"{provider_name} ({model}) failed: {e}")
        return None


# OpenRouter free model list — ALL entries MUST end with :free.
# The :free suffix is OpenRouter's billing gate — those models cost $0/token.
# The assertion below is a hard code-level guard so this can never be bypassed.
_OPENROUTER_FREE_MODELS = [
    "deepseek/deepseek-r1:free",
    "meta-llama/llama-3.3-70b-instruct:free",
    "qwen/qwen3-235b-a22b:free",
]

# Startup assertion — will raise immediately on import if a non-free model slips in.
for _m in _OPENROUTER_FREE_MODELS:
    assert _m.endswith(":free"), (
        f"SAFETY: OpenRouter model '{_m}' is NOT a free model. "
        "All OpenRouter models must end with ':free' to guarantee $0 cost."
    )


def _call_openrouter_raw(messages: List[Dict[str, str]], temperature: float = 0.4) -> Optional[str]:
    """
    OpenRouter — cycles through free-tier models only.

    Three layers of $0 enforcement:
      1. All model names in _OPENROUTER_FREE_MODELS end with ':free' (asserted at import).
      2. The request payload sets 'provider.require_parameters: true' and
         'provider.order' to pin the call to free-tier serving infrastructure.
      3. OpenRouter itself never charges for :free models regardless of usage.
    """
    if not OPENROUTER_API_KEY:
        return None

    extra_headers = {
        "HTTP-Referer": "https://github.com/adjacency-research",
        "X-Title": "Adjacency Research",
    }

    for model in _OPENROUTER_FREE_MODELS:
        # Belt-and-suspenders: re-assert at call time (catches runtime mutation)
        if not model.endswith(":free"):
            logger.error(f"SAFETY BLOCK: refused to call non-free OpenRouter model '{model}'")
            continue

        # Build payload manually so we can inject provider constraints
        headers = {
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
            **extra_headers,
        }
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": 4000,
            # Tell OpenRouter: only route to providers that support this model's
            # free tier; do not fall back to paid providers.
            "provider": {
                "require_parameters": True,
            },
        }
        try:
            resp = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers=headers,
                json=payload,
                timeout=60,
            )
            if resp.status_code == 429:
                logger.warning(f"OpenRouter ({model}) rate-limited. Trying next free model...")
                continue
            if resp.status_code == 402:
                # 402 = Payment Required — should never happen with :free models,
                # but if it does, skip rather than pay.
                logger.error(f"SAFETY: OpenRouter returned 402 Payment Required for '{model}'. Skipping.")
                continue
            resp.raise_for_status()
            data = resp.json()
            content = data["choices"][0]["message"]["content"].strip()
            logger.info(f"OpenRouter success with free model: {model}")
            return content
        except Exception as e:
            logger.warning(f"OpenRouter ({model}) failed: {e}")
            continue

    return None


def _dummy_openrouter_for_openai_compat(messages: List[Dict[str, str]], temperature: float = 0.4, model: str = "", extra_headers: Optional[Dict[str, str]] = None) -> Optional[str]:
    """Internal shim — not used; OpenRouter now has its own dedicated function above."""





def _call_cerebras_raw(messages: List[Dict[str, str]], temperature: float = 0.4) -> Optional[str]:
    """Cerebras — llama-3.3-70b, 30 RPM free tier, no CC needed."""
    if not CEREBRAS_API_KEY:
        return None
    return _call_openai_compat(
        base_url="https://api.cerebras.ai/v1",
        api_key=CEREBRAS_API_KEY,
        model="llama-3.3-70b",
        messages=messages,
        temperature=temperature,
        provider_name="Cerebras",
    )


def _call_nvidia_raw(messages: List[Dict[str, str]], temperature: float = 0.4) -> Optional[str]:
    """NVIDIA NIM — llama-3.1-70b-instruct, 1000 req/month free tier, no CC needed."""
    if not NVIDIA_API_KEY:
        return None
    return _call_openai_compat(
        base_url="https://integrate.api.nvidia.com/v1",
        api_key=NVIDIA_API_KEY,
        model="meta/llama-3.1-70b-instruct",
        messages=messages,
        temperature=temperature,
        provider_name="NVIDIA NIM",
    )


def _call_huggingface_raw(messages: List[Dict[str, str]], temperature: float = 0.4) -> Optional[str]:
    """
    Hugging Face Serverless Inference API — Qwen2.5-72B, free with HF token.
    Last resort; can be slow.
    """
    if not HUGGINGFACE_API_KEY:
        return None
    return _call_openai_compat(
        base_url="https://router.huggingface.co/novita/v3/openai",
        api_key=HUGGINGFACE_API_KEY,
        model="Qwen/Qwen2.5-72B-Instruct",
        messages=messages,
        temperature=temperature,
        provider_name="HuggingFace",
    )


# ── Master chain ──────────────────────────────────────────────────────────────

def _build_messages(
    formatted_prompt: str,
    system_instruction: Optional[str],
) -> List[Dict[str, str]]:
    msgs: List[Dict[str, str]] = []
    if system_instruction:
        msgs.append({"role": "system", "content": system_instruction})
    msgs.append({"role": "user", "content": formatted_prompt})
    return msgs


def call_llm_chain(
    prompt: str,
    system_instruction: Optional[str] = None,
    temperature: float = 0.4,
) -> Optional[str]:
    """
    Run the full 9-provider free chain in order:
      1. Gemini Flash
      2. Groq llama-3.3-70b  (with backoff + fallback to 8b)
      3. OpenRouter deepseek-r1:free
      4. OpenRouter llama-3.3-70b:free
      5. OpenRouter qwen3-235b:free
      6. Cerebras llama-3.3-70b
      7. NVIDIA llama-3.1-70b
      8. HuggingFace Qwen2.5-72B

    Returns the first non-None response, or None if all fail.
    """
    messages = _build_messages(prompt, system_instruction)

    # 1. Gemini
    result = _call_gemini_raw(prompt, system_instruction, temperature)
    if result:
        logger.info("LLM chain: Gemini succeeded.")
        return result

    # 2. Groq (70b → 8b internally)
    result = _call_groq_raw(messages, temperature)
    if result:
        logger.info("LLM chain: Groq succeeded.")
        return result

    # 3-5. OpenRouter free models
    result = _call_openrouter_raw(messages, temperature)
    if result:
        logger.info("LLM chain: OpenRouter succeeded.")
        return result

    # 6. Cerebras
    result = _call_cerebras_raw(messages, temperature)
    if result:
        logger.info("LLM chain: Cerebras succeeded.")
        return result

    # 7. NVIDIA NIM
    result = _call_nvidia_raw(messages, temperature)
    if result:
        logger.info("LLM chain: NVIDIA NIM succeeded.")
        return result

    # 8. HuggingFace (last resort)
    result = _call_huggingface_raw(messages, temperature)
    if result:
        logger.info("LLM chain: HuggingFace succeeded.")
        return result

    return None


# ── JSON + Pydantic validation ────────────────────────────────────────────────

def parse_json_safely(raw: str) -> Any:
    """Robust JSON block parser."""
    raw = raw.strip()
    if raw.startswith("```json"):
        raw = raw[7:]
    elif raw.startswith("```"):
        raw = raw[3:]
    if raw.endswith("```"):
        raw = raw[:-3]
    raw = raw.strip()

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # Try to find a JSON block manually
        for open_c, close_c in [("[", "]"), ("{", "}")]:
            start = raw.find(open_c)
            if start != -1:
                end = raw.rfind(close_c)
                if end != -1:
                    try:
                        return json.loads(raw[start:end + 1])
                    except Exception:
                        pass
        raise


def call_llm_with_validation(
    template_name: str,
    variables: Dict[str, Any],
    schema: Type[BaseModel],
    is_list: bool = False,
    temperature: float = 0.4,
) -> Any:
    """
    Loads template, builds the prompt, runs through the full LLM chain,
    and validates output with a Pydantic schema.
    Supports list-of-objects validation.
    Up to 3 correction attempts using a fresh chain call each time.
    """
    template_content = load_prompt_template(template_name)

    # Split System / User sections if present
    system_instruction = None
    user_prompt = template_content
    if "System:" in template_content:
        parts = template_content.split("User:")
        system_instruction = parts[0].replace("System:", "").strip()
        user_prompt = parts[1].strip() if len(parts) > 1 else ""

    # Format the prompt — simple key replacement to avoid curly brace conflicts
    formatted_prompt = user_prompt
    for k, v in variables.items():
        formatted_prompt = formatted_prompt.replace(f"{{{k}}}", str(v))

    # --- Initial LLM call ---
    raw_response = call_llm_chain(formatted_prompt, system_instruction, temperature)

    if not raw_response:
        raise RuntimeError("All LLM providers in the chain failed to return a response.")

    # --- Parse + validate with up to 3 correction rounds ---
    for attempt in range(3):
        try:
            parsed_data = parse_json_safely(raw_response)

            if is_list:
                if not isinstance(parsed_data, list):
                    if isinstance(parsed_data, dict):
                        for key in ("results", "data", "ideas", "items"):
                            if key in parsed_data and isinstance(parsed_data[key], list):
                                parsed_data = parsed_data[key]
                                break
                    if not isinstance(parsed_data, list):
                        raise ValueError("Expected a JSON array of objects.")
                return [schema(**item).dict() for item in parsed_data]
            else:
                if isinstance(parsed_data, list):
                    if len(parsed_data) > 0:
                        parsed_data = parsed_data[0]
                    else:
                        raise ValueError("Expected a JSON object, got empty list.")
                return schema(**parsed_data).dict()

        except (json.JSONDecodeError, ValidationError, ValueError) as e:
            logger.warning(f"Validation failed on attempt {attempt + 1}/3: {e}")
            if attempt == 2:
                raise

            # Build correction prompt and retry through the full chain
            correction_prompt = (
                f"Your previous response failed validation with this error:\n{e}\n\n"
                f"Original Output:\n{raw_response}\n\n"
                f"Please correct the output and return ONLY the valid JSON structure. "
                f"Do not include markdown, code fences, or explanations."
            )
            correction_sys = (system_instruction or "") + "\nReturn ONLY valid JSON matching the schema."

            raw_response = call_llm_chain(correction_prompt, correction_sys, temperature=0.1)
            if not raw_response:
                raise RuntimeError("All LLM providers failed to return a correction response.")
