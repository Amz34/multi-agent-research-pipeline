"""Agent 1: Researcher - deterministic search + page fetch -> raw notes."""
from logger import log

from .search import research_notes


def research(topic: str) -> str:
    notes = research_notes(topic)
    log("researcher", {"topic": topic, "notes_chars": len(notes), "notes": notes})
    return notes
