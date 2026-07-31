import logging
import requests
import json
from django.conf import settings

logger = logging.getLogger(__name__)

def _cleanup_llm_text(raw_text: str) -> str:
    raw_text = raw_text.strip()
    if raw_text.startswith("```json"):
        raw_text = raw_text[len("```json"):].strip()
    elif raw_text.startswith("```"):
        raw_text = raw_text[len("```"):].strip()
    return raw_text.rstrip("`").strip()

def _extract_llm_response_text(response: requests.Response) -> str:
    response.raise_for_status()
    body = response.json()
    if not isinstance(body, dict):
        raise ValueError("LLM response JSON is not an object")
    raw_text = body.get("response") or body.get("text")
    if not isinstance(raw_text, str):
        raise ValueError("LLM response missing expected text field")
    return _cleanup_llm_text(raw_text)

def query_tier1_gemini(system_prompt: str, user_question: str) -> str:
    """Tier 1: High-Speed Public Cloud API (Bypassed if key is missing)"""
    api_key = settings.GEMINI_API_KEY
    if not api_key:
        raise ValueError("Missing GEMINI_API_KEY credentials")
        
    # Modern structural API call setup
    from google import genai
    client = genai.Client(api_key=api_key)
    full_prompt = f"System Instruction:\n{system_prompt}\n\nUser Question:\n{user_question}"
    response = client.models.generate_content(
        model='gemini-2.5-flash',
        contents=full_prompt,
        config={'response_mime_type': 'application/json'}
    )
    return response.text

def query_tier2_remote_gpu(system_prompt: str, user_question: str) -> str:
    """Tier 2: Private Dedicated GPU Server Engine (Bypassed if IP is missing)"""
    remote_ip = settings.REMOTE_GPU_SERVER_IP
    if not remote_ip:
        raise ValueError("Missing REMOTE_GPU_SERVER_IP configuration")

    local_forward_port = settings.LOCAL_FORWARD_PORT
    url = f"http://127.0.0.1:{local_forward_port}/api/generate"

    combined_prompt = f"System Instruction:\n{system_prompt}\n\nUser Question:\n{user_question}"
    payload = {
        "model": "llama3.1:latest",
        "prompt": combined_prompt,
        "stream": False,
        "format": "json",
        "options": {"temperature": 0.0},
    }

    res = requests.post(url, json=payload, timeout=15.0)
    return _extract_llm_response_text(res)

def query_tier3_local_ollama(system_prompt: str, user_question: str) -> str:
    """Tier 3: Local Offline System Contingency Layer (Active Development Target)"""
    url = settings.OLLAMA_API_URL
    if not url.endswith("/api/generate"):
        url = url.rstrip("/") + "/api/generate"

    combined_prompt = f"System Instruction:\n{system_prompt}\n\nUser Question:\n{user_question}"
    payload = {
        "model": "qwen2.5:1.5b",
        "prompt": combined_prompt,
        "stream": False,
        "options": {"temperature": 0.0},
    }

    res = requests.post(url, json=payload, timeout=120.0)
    return _extract_llm_response_text(res)

def cascade_llm_router(system_prompt: str, user_question: str) -> dict:
    def _attempt_tier(tier_name: str, fn):
        try:
            logger.info("LLM Router -> Attempting %s", tier_name)
            raw_response = fn(system_prompt, user_question)
            logger.debug("LLM Router %s raw response: %s", tier_name, raw_response[:200])
            return json.loads(raw_response)
        except json.JSONDecodeError as jde:
            logger.warning("%s JSON parse error: %s", tier_name, jde)
            return {"error": f"JSON parse error: {jde}"}
        except Exception as exc:
            logger.warning("%s failed: %s", tier_name, exc)
            return None

    result = _attempt_tier("Tier 1: Gemini Cloud API", query_tier1_gemini)
    if result is not None:
        return result

    result = _attempt_tier("Tier 2: Remote GPU Server", query_tier2_remote_gpu)
    if result is not None:
        return result

    result = _attempt_tier("Tier 3: Local Ollama Core", query_tier3_local_ollama)
    if result is not None:
        return result

    return {"error": "Critical: All AI layers exhausted."}
