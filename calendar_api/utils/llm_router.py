import requests
import json
import re
from django.conf import settings

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

    # Need to add SSH connection is available
    # If not available, try building a local port forward to the remote Ollama server

    local_forward_port = settings.LOCAL_FORWARD_PORT
    url = f"http://127.0.0.1:{local_forward_port}/api/generate"

    combined_prompt = f"System Instruction:\n{system_prompt}\n\nUser Question:\n{user_question}"
    
    payload = {
        "model": "llama3.1:latest",
        # "system": system_prompt,
        "prompt": combined_prompt,
        "stream": False,
        "format": "json",
        "options": {
            "temperature": 0.0
        }
    }

    # Tight timeout so it drops down to Tier 3 rapidly if the VPN link goes dark
    res = requests.post(url, json=payload, timeout=15.0)
    if res.status_code != 200:
        raise RuntimeError(f"Remote Ollama node error: {res.text}")
        
    raw_text = res.json()['response'].strip()
    
    if raw_text.startswith("```json"):
        raw_text = raw_text.replace("```json", "", 1).rstrip("```").strip()
    elif raw_text.startswith("```"):
        raw_text = raw_text.replace("```", "", 1).rstrip("```").strip()

    return raw_text

def query_tier3_local_ollama(system_prompt: str, user_question: str) -> str:
    """Tier 3: Local Offline System Contingency Layer (Active Development Target)"""
    url = settings.OLLAMA_API_URL

    if not url.endswith('/api/generate'):
        url = url.rstrip('/') + '/api/generate'

    combined_prompt = f"System Instruction:\n{system_prompt}\n\nUser Question:\n{user_question}"
    
    # Format rules mapping specifically for Ollama's direct endpoints
    payload = {
        "model": "qwen2.5:1.5b",
        # "system": system_prompt,
        "prompt": combined_prompt,
        "stream": False,
        # "format": "json",
        "options": {
            "temperature": 0.0
        }
    }
    
    # 3. Pull the text content out of the structural message nested dictionary
    res = requests.post(url, json=payload, timeout=120.0)
    if res.status_code != 200:
        raise RuntimeError(f"Ollama local node error: {res.text}")
    
    raw_text = res.json()['response'].strip()

    if raw_text.startswith("```json"):
        raw_text = raw_text.replace("```json", "", 1).rstrip("```").strip()
    elif raw_text.startswith("```"):
        raw_text = raw_text.replace("```", "", 1).rstrip("```").strip()

    return raw_text

def cascade_llm_router(system_prompt: str, user_question: str) -> dict:
    """
    Sequentially cascades query processing traffic down the infrastructure hierarchy.
    Gracefully handles errors or environment omission to reach the active offline target.
    """
    # ----------------------------------------------------
    # ATTEMPT TIER 1: Cloud API Node
    # ----------------------------------------------------
    try:
        print("Route Context -> Attempting Tier 1: Gemini Cloud API...")
        raw_response = query_tier1_gemini(system_prompt, user_question)
        print(f"[LLM Router] Tier 1 successfully retrieved raw text: {raw_response[:100]}...")

        return json.loads(raw_response.strip())
    except json.JSONDecodeError as jde:
        print(f"[LLM Router Error] Failed to parse JSON from Tier 1. Raw output: {raw_response}")
        return {"error": f"JSON parse error: {jde}"} 
    except Exception as e:
        print(f"Tier 1 Bypassed / Offline")

    # ----------------------------------------------------
    # ATTEMPT TIER 2: Private Remote Server VM Node
    # ----------------------------------------------------
    try:
        print("Route Context -> Attempting Tier 2: Remote GPU Server...")
        raw_response = query_tier2_remote_gpu(system_prompt, user_question)
        print(f"[LLM Router] Tier 2 successfully retrieved raw text: {raw_response[:100]}...")

        return json.loads(raw_response.strip())
    except json.JSONDecodeError as jde:
        print(f"[LLM Router Error] Failed to parse JSON from Tier 2. Raw output: {raw_response}")
        return {"error": f"JSON parse error: {jde}"} 
    except Exception as e:
        print(f"Tier 2 Failure Reason: {type(e).__name__} - {str(e)}")
        print(f"Tier 2 Bypassed / Offline")

    # ----------------------------------------------------
    # ATTEMPT TIER 3: Local Laptop Node
    # ----------------------------------------------------
    try:
        print("Route Context -> Executing Tier 3: Local Ollama Core Node Engine...")
        raw_response = query_tier3_local_ollama(system_prompt, user_question)
        print(f"[LLM Router] Tier 3 successfully retrieved raw text: {raw_response[:100]}...")

        return json.loads(raw_response.strip())
    except json.JSONDecodeError as jde:
        print(f"[LLM Router Error] Failed to parse JSON from Tier 3. Raw output: {raw_response}")
        return {"error": f"JSON parse error: {jde}"}    
    except Exception as e:
        print(f"\n[LLM ROUTER CRASH DETAIL] Tier 3 Failed to Parse JSON String. Reason: {e}")
        if 'raw_response' in locals():
            print(f"Raw text generated by Qwen was: {raw_response}\n")

        return {"error": f"Critical: All AI layers processing limits exhausted. Details: {e}"}
    