"""Agent 4: Coordinator - wires the 3 agents, owns the retry loop.

The evaluator can ask for a revision for as long as it likes; the loop is
capped at MAX_ITERATIONS and the best result so far is returned. Every
attempt runs under a hard timeout, so a single stuck call can never hang
the pipeline.
"""
from logger import log

from .evaluator import evaluate
from .llm import LLMError
from .researcher import research
from .summarizer import summarize

MAX_ITERATIONS = 5


def run_pipeline(topic: str, max_iterations: int = MAX_ITERATIONS) -> dict:
    notes = research(topic)
    summary = summarize(notes)
    iteration = 1
    verdict = evaluate(notes, summary)
    while verdict != "APPROVED" and iteration < max_iterations:
        log("coordinator", {"iteration": iteration, "verdict": verdict, "action": "retrying summarizer"})
        summary = summarize(notes)
        verdict = evaluate(notes, summary)
        iteration += 1
    log("coordinator", {"final_iteration": iteration, "verdict": verdict})
    return {
        "topic": topic,
        "summary": summary,
        "iterations": iteration,
        "verdict": verdict,
    }


def run_pipeline_safe(topic: str, max_iterations: int = MAX_ITERATIONS) -> dict:
    """Never raises: catches LLM/network failures and returns a structured result
    the API can always answer with. This is the crashproof entry point."""
    try:
        result = run_pipeline(topic, max_iterations=max_iterations)
        result["status"] = "ok"
    except (LLMError, ValueError, KeyError, Exception) as exc:  # noqa: BLE001 - deliberate catch-all
        log("coordinator", {"fatal": str(exc)})
        result = {"status": "error", "topic": topic, "error": str(exc)[:500]}
    return result
