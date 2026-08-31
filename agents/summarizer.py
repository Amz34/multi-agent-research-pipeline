"""Agent 2: Summarizer - notes -> structured JSON {title, keyPoints[], takeaway}."""
from logger import log

from .llm import chat, extract_json

SYSTEM = (
    "You are a precise summarizer. You turn raw research notes into a strict JSON object. "
    "Respond with ONLY valid JSON, no markdown fences, no commentary."
)

USER_TEMPLATE = (
    'Read these research notes and produce a JSON object with exactly this shape: '
    '{{ "title": string, "keyPoints": string[], "takeaway": string }}. '
    "Return exactly 3 key points. Respond with ONLY the JSON.\n\nResearch notes:\n{notes}"
)


def summarize(notes: str) -> dict:
    text = chat(
        [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": USER_TEMPLATE.format(notes=notes[:12000])},
        ],
        max_tokens=800,
    )
    summary = extract_json(text)
    # minimal schema guardrail
    summary.setdefault("title", "")
    summary.setdefault("keyPoints", [])
    summary.setdefault("takeaway", "")
    log("summarizer", {"input_chars": len(notes), "output": summary})
    return summary
