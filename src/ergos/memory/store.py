"""MemoryStore for cross-session memory persistence.

Provides load/save/prune/budget operations over a JSON-backed list of MemoryEntry.
Also provides extraction helpers for parsing LLM output and formatting conversation
history for memory extraction.

Following the kitchen plugin pattern from src/ergos/plugins/kitchen/memory.py.
"""

import json
import logging
from dataclasses import asdict
from pathlib import Path
from typing import Optional

from .types import MemoryEntry

logger = logging.getLogger(__name__)

# Storage path for cross-session memory
MEMORY_PATH = Path.home() / ".ergos" / "memory.json"

# Max entries injected into prompt per session
MEMORY_BUDGET = 15

# Max entries to store before pruning
MEMORY_MAX_STORED = 100

# Valid categories extracted from conversation
_VALID_CATEGORIES = {"preference", "fact", "moment"}

# Prompt template for extracting memorable information from conversation history
EXTRACTION_PROMPT = (
    "Review this conversation and extract facts worth remembering about the user.\n"
    "Conversation: {history}\n"
    "Extract 0-5 memorable items. For each, write one clear sentence and categorize it.\n"
    "Categories: preference (likes/dislikes/habits), fact (personal info), moment (notable exchange or joke).\n"
    "Only extract genuinely useful or memorable information -- skip trivial exchanges.\n"
    "Format: CATEGORY: sentence\n"
    "If nothing memorable occurred, respond with: NOTHING"
)


class MemoryStore:
    """Manages persistence of cross-session memory entries.

    Stores data as JSON at ~/.ergos/memory.json by default.
    """

    def __init__(self, storage_path: Optional[Path] = None) -> None:
        """Initialize memory store.

        Args:
            storage_path: Custom path to memory.json file (uses default if None).
        """
        self._path = storage_path or MEMORY_PATH

    def load(self) -> list[MemoryEntry]:
        """Load memory entries from disk.

        Returns:
            List of MemoryEntry objects, or empty list if file missing or parse error.
        """
        if not self._path.exists():
            logger.debug("No existing memory file at %s", self._path)
            return []

        try:
            data = json.loads(self._path.read_text())
            entries = []
            for item in data:
                entries.append(
                    MemoryEntry(
                        content=item["content"],
                        category=item["category"],
                        timestamp=item["timestamp"],
                        access_count=item.get("access_count", 0),
                    )
                )
            logger.info("Loaded %d memory entries from %s", len(entries), self._path)
            return entries
        except Exception as e:
            logger.warning("Failed to load memory from %s: %s, returning empty", self._path, e)
            return []

    def save(self, entries: list[MemoryEntry]) -> None:
        """Save memory entries to disk.

        Args:
            entries: List of MemoryEntry objects to persist.
        """
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            data = [asdict(entry) for entry in entries]
            self._path.write_text(json.dumps(data, indent=2))
            logger.info("Saved %d memory entries to %s", len(entries), self._path)
        except Exception as e:
            logger.error("Failed to save memory to %s: %s", self._path, e)

    def get_budget(self, entries: list[MemoryEntry], n: int = MEMORY_BUDGET) -> list[MemoryEntry]:
        """Return the top N most recent entries, incrementing their access_count.

        Args:
            entries: Full list of memory entries.
            n: Maximum number of entries to return (default: MEMORY_BUDGET=15).

        Returns:
            Up to n entries sorted by recency (most recent first), with access_count incremented.
        """
        sorted_entries = sorted(entries, key=lambda e: e.timestamp, reverse=True)
        selected = sorted_entries[:n]
        for entry in selected:
            entry.access_count += 1
        return selected

    def prune(self, entries: list[MemoryEntry], max_size: int = MEMORY_MAX_STORED) -> list[MemoryEntry]:
        """Drop lowest-scored entries when over max_size cap.

        Scoring formula: 0.7 * normalized_timestamp + 0.3 * normalized_access_count
        Higher score = more likely to survive pruning.

        Args:
            entries: Full list of memory entries.
            max_size: Maximum entries to retain (default: MEMORY_MAX_STORED=100).

        Returns:
            List of at most max_size entries, keeping highest-scored ones.
        """
        if len(entries) <= max_size:
            return entries

        # Normalize timestamps to [0, 1] range
        timestamps = [e.timestamp for e in entries]
        min_ts = min(timestamps)
        max_ts = max(timestamps)
        ts_range = max_ts - min_ts if max_ts != min_ts else 1.0

        # Normalize access_counts to [0, 1] range
        access_counts = [e.access_count for e in entries]
        min_ac = min(access_counts)
        max_ac = max(access_counts)
        ac_range = max_ac - min_ac if max_ac != min_ac else 1.0

        def score(entry: MemoryEntry) -> float:
            norm_ts = (entry.timestamp - min_ts) / ts_range
            norm_ac = (entry.access_count - min_ac) / ac_range
            return 0.7 * norm_ts + 0.3 * norm_ac

        sorted_by_score = sorted(entries, key=score, reverse=True)
        return sorted_by_score[:max_size]


def parse_extraction_result(text: str) -> list[MemoryEntry]:
    """Parse LLM extraction output into MemoryEntry objects.

    Expected format:
        CATEGORY: sentence
        CATEGORY: sentence
        ...
    Or simply: NOTHING

    Args:
        text: Raw LLM output from extraction prompt.

    Returns:
        List of MemoryEntry objects, or empty list if "NOTHING" or no valid lines.
    """
    if text.strip().upper() == "NOTHING":
        return []

    entries = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if ": " not in line:
            continue
        category, _, content = line.partition(": ")
        category = category.lower().strip()
        content = content.strip()
        if category not in _VALID_CATEGORIES:
            continue
        if not content:
            continue
        entries.append(MemoryEntry(content=content, category=category))

    return entries


def format_history_for_extraction(messages: list) -> Optional[str]:
    """Format conversation history for the extraction prompt.

    Args:
        messages: List of Message-like objects with .role and .content attributes.
                  If fewer than 4 messages, returns None (skip extraction).

    Returns:
        Formatted string with USER:/ASSISTANT: prefixes, or None if too short.
    """
    if len(messages) < 4:
        return None

    # Cap at last 20 messages
    recent = messages[-20:]

    lines = []
    for msg in recent:
        role_label = "USER" if msg.role == "user" else "ASSISTANT"
        lines.append(f"{role_label}: {msg.content}")

    return "\n".join(lines)
