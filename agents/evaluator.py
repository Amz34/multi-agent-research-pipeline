"""Agent 3: Evaluator - is the summary grounded in the notes? APPROVED or REVISE."""
import json

from logger import log

from .llm import chat

SYSTEM = "You are a strict quality gate. You respond with exactly one word: APPROVED or REVISE."

USER_TEMPLATE = (
    "Research notes:\n{notes}\n\nSummary:\n{summary}\n\n"
    'Does the summary have 3 distinct, high-quality key points that are clearly '
    'interesting and well-developed? Respond with ONLY "APPROVED" or "REVISE".'
)


def evaluate(notes: str, summary: dict) -> str:
    text = chat(
        [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": USER_TEMPLATE.format(notes=notes[:12000], summary=json.dumps(summary, ensure_ascii=False))},
        ],
        max_tokens=600,  # reasoning model needs headroom for thinking + verdict
        temperature=0.0,
    )
    verdict = text.strip().upper().replace('"', "").replace(".", "")
    verdict = "APPROVED" if "APPROVED" in verdict else "REVISE"
    log("evaluator", {"verdict": verdict, "raw": text[:100]})
    return verdict
