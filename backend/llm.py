import os
import json
import time
import logging
from typing import Any, Dict, List, Type, Optional
from pydantic import BaseModel, ValidationError

from dotenv import load_dotenv
load_dotenv()

logger = logging.getLogger(__name__)

# Ensure API keys are loaded
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")

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


def load_prompt_template(name: str) -> str:
    """Loads a prompt template from the prompts/ directory."""
    # Look in backend/../prompts/ or adjacent prompts/
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


def _call_gemini_raw(prompt: str, system_instruction: Optional[str] = None, temperature: float = 0.4) -> Optional[str]:
    """Call Gemini Flash API."""
    if not GEMINI_API_KEY:
        return None
    try:
        import google.generativeai as genai
        # Format instruction
        model_name = "gemini-2.5-flash"
        model = genai.GenerativeModel(
            model_name,
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
    """Call Groq API (Llama-3.3-70b-versatile) with exponential backoff."""
    if not _groq_client:
        return None
    
    # Try llama-3.3-70b-versatile or fallback to llama-3.1-8b-instant
    model = "llama-3.3-70b-versatile"
    
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
            if ("rate_limit" in err or "429" in err) and attempt < 2:
                wait = 4 * (2 ** attempt)
                logger.info(f"Groq rate-limited. Waiting {wait}s...")
                time.sleep(wait)
            else:
                logger.warning(f"Groq call failed: {e}")
                # Try fallback smaller model
                if model == "llama-3.3-70b-versatile":
                    model = "llama-3.1-8b-instant"
                    logger.info(f"Falling back to Groq model {model}...")
                else:
                    return None
    return None


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
        start = raw.find("[")
        if start != -1:
            end = raw.rfind("]")
            if end != -1:
                try:
                    return json.loads(raw[start:end+1])
                except Exception:
                    pass
        start = raw.find("{")
        if start != -1:
            end = raw.rfind("}")
            if end != -1:
                try:
                    return json.loads(raw[start:end+1])
                except Exception:
                    pass
        raise


def call_llm_with_validation(
    template_name: str,
    variables: Dict[str, Any],
    schema: Type[BaseModel],
    is_list: bool = False,
    temperature: float = 0.4
) -> Any:
    """
    Loads template, builds the prompt, calls Gemini/Groq, and validates the output with a Pydantic schema.
    Supports list-of-objects validation.
    """
    template_content = load_prompt_template(template_name)
    
    # Split System instruction and User message if specified
    system_instruction = None
    user_prompt = template_content
    
    if "System:" in template_content:
        parts = template_content.split("User:")
        system_instruction = parts[0].replace("System:", "").strip()
        user_prompt = parts[1].strip() if len(parts) > 1 else ""

    # Format the prompt using simple key replacements to avoid curly brace conflicts in JSON examples
    formatted_prompt = user_prompt
    for k, v in variables.items():
        formatted_prompt = formatted_prompt.replace(f"{{{k}}}", str(v))
    
    raw_response = None
    # 1. Try Gemini
    raw_response = _call_gemini_raw(formatted_prompt, system_instruction, temperature)
    
    # 2. Try Groq if Gemini failed or was unavailable
    if not raw_response:
        logger.info("Gemini failed/unavailable. Falling back to Groq (Llama-3.3-70b-versatile)...")
        messages = []
        if system_instruction:
            messages.append({"role": "system", "content": system_instruction})
        messages.append({"role": "user", "content": formatted_prompt})
        raw_response = _call_groq_raw(messages, temperature)

    if not raw_response:
        raise RuntimeError("Both Gemini and Groq LLMs failed to return a response.")

    # 3. Parse and Validate
    for attempt in range(3):
        try:
            parsed_data = parse_json_safely(raw_response)
            
            if is_list:
                if not isinstance(parsed_data, list):
                    # If it's wrapped in a dict
                    if isinstance(parsed_data, dict):
                        for key in ("results", "data", "ideas", "items"):
                            if key in parsed_data and isinstance(parsed_data[key], list):
                                parsed_data = parsed_data[key]
                                break
                    if not isinstance(parsed_data, list):
                        raise ValidationError("Expected a JSON array of objects.")
                
                validated = [schema(**item).dict() for item in parsed_data]
                return validated
            else:
                if isinstance(parsed_data, list):
                    if len(parsed_data) > 0:
                        parsed_data = parsed_data[0]
                    else:
                        raise ValidationError("Expected a JSON object, got empty list.")
                validated = schema(**parsed_data).dict()
                return validated
                
        except (json.JSONDecodeError, ValidationError, ValueError) as e:
            logger.warning(f"Validation failed on attempt {attempt+1}: {e}")
            if attempt == 2:
                # Retries exhausted
                raise e
            
            # Request correction
            correction_prompt = (
                f"Your previous response failed validation with the following error:\n{e}\n\n"
                f"Original Output:\n{raw_response}\n\n"
                f"Please correct the output and return ONLY the valid JSON structure. Do not include markdown or explanations."
            )
            
            # Re-call
            messages = []
            if system_instruction:
                messages.append({"role": "system", "content": system_instruction + "\nReturn ONLY valid JSON matching the schema."})
            messages.append({"role": "user", "content": formatted_prompt})
            messages.append({"role": "assistant", "content": raw_response})
            messages.append({"role": "user", "content": correction_prompt})
            
            # Try Groq for correction to ensure structured format
            raw_response = _call_groq_raw(messages, temperature=0.1)
            if not raw_response:
                raw_response = _call_gemini_raw(correction_prompt, system_instruction, temperature=0.1)
            
            if not raw_response:
                raise RuntimeError("LLM failed to return correction response.")
