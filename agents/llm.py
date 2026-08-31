"""LLM wrapper: DeepSeek (OpenAI-compatible) with crashproof behaviour.

- exponential backoff + jitter on 429 / 5xx / network errors
- hard timeout on every call
- JSON extraction guardrails (markdown fences, stray prose)
"""
import json
import os
import random
import re
import time
from pathlib import Path

import httpx
from dotenv import load_dotenv

# Portable env loading: repo-local .env first, then infra fallback (our server).
load_dotenv(Path(__file__).resolve().parent.parent / ".env", override=False)
if Path("/home/ubuntu/.hermes/.env").exists():
    load_dotenv("/home/ubuntu/.hermes/.env", override=False)

DEEPSEEK_URL = os.environ.get("DEEPSEEK_URL", "https://api.deepseek.com/chat/completions")
MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")
API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")


class LLMError(RuntimeError):
    pass


def chat(messages, max_tokens=1000, temperature=0.3, timeout=60, retries=3):
    """One LLM call with retry/backoff. Returns the assistant message text."""
    if not API_KEY:
        raise LLMError(
            "DEEPSEEK_API_KEY not found. Copy .env.example to .env and add your key."
        )
    payload = {
        "model": MODEL,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "stream": False,
    }
    headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}
    attempt = 0
    while True:
        attempt += 1
        try:
            with httpx.Client(timeout=timeout) as client:
                resp = client.post(DEEPSEEK_URL, json=payload, headers=headers)
            if resp.status_code == 200:
                data = resp.json()
                msg = data["choices"][0]["message"]
                content = (msg.get("content") or "").strip()
                if not content and msg.get("reasoning_content"):
                    # Reasoning models (deepseek-v4-flash) can hit the token cap
                    # inside the thinking phase - fall back to what we have.
                    content = (msg.get("reasoning_content") or "").strip()
                return content
            if resp.status_code in (429, 500, 502, 503, 529):
                if attempt > retries:
                    raise LLMError(f"LLM retries exhausted after {attempt} attempts (HTTP {resp.status_code})")
                backoff = min(2 ** (attempt - 1), 30) * (1 + random.random() * 0.5)
                time.sleep(backoff)
                continue
            raise LLMError(f"LLM HTTP {resp.status_code}: {resp.text[:300]}")
        except (httpx.TimeoutException, httpx.ConnectError, httpx.ReadError) as exc:
            if attempt > retries:
                raise LLMError(f"LLM network error after {attempt} attempts: {exc}") from exc
            time.sleep(min(2 ** (attempt - 1), 15) * (1 + random.random() * 0.5))


def extract_json(text):
    """Robustly pull a JSON object out of model output."""
    if not text:
        raise ValueError("empty model output")
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise ValueError(f"no JSON object in model output: {text[:200]!r}")
    return json.loads(text[start : end + 1])
