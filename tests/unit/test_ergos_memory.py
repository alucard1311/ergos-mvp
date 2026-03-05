"""Unit tests for Ergos cross-session memory module.

Tests MemoryStore CRUD, prune, budget, and extraction parsing.
"""

import time
from pathlib import Path

import pytest

from ergos.memory.types import MemoryEntry
from ergos.memory.store import (
    MemoryStore,
    parse_extraction_result,
    format_history_for_extraction,
    MEMORY_BUDGET,
    MEMORY_MAX_STORED,
)
from ergos.llm.processor import Message


class TestMemoryEntry:
    """Tests for MemoryEntry dataclass defaults."""

    def test_defaults(self):
        """MemoryEntry with content and category has auto timestamp and access_count=0."""
        before = time.time()
        entry = MemoryEntry("likes coffee", "preference")
        after = time.time()

        assert entry.content == "likes coffee"
        assert entry.category == "preference"
        assert before <= entry.timestamp <= after
        assert entry.access_count == 0


class TestMemoryStore:
    """Tests for MemoryStore load, save, prune, and budget operations."""

    def test_load_empty(self, tmp_path):
        """load() returns empty list when memory.json does not exist."""
        store = MemoryStore(storage_path=tmp_path / "memory.json")
        result = store.load()
        assert result == []

    def test_roundtrip(self, tmp_path):
        """save() + load() round-trips preserve all MemoryEntry fields."""
        storage_path = tmp_path / "memory.json"
        store = MemoryStore(storage_path=storage_path)

        entries = [
            MemoryEntry(content="likes dark coffee", category="preference", timestamp=1000.0, access_count=3),
            MemoryEntry(content="works at a startup", category="fact", timestamp=2000.0, access_count=1),
            MemoryEntry(content="laughed at recursive joke", category="moment", timestamp=3000.0, access_count=0),
        ]

        store.save(entries)
        loaded = store.load()

        assert len(loaded) == 3
        for original, loaded_entry in zip(entries, loaded):
            assert loaded_entry.content == original.content
            assert loaded_entry.category == original.category
            assert loaded_entry.timestamp == original.timestamp
            assert loaded_entry.access_count == original.access_count

    def test_prune(self, tmp_path):
        """prune() with 110 entries returns exactly 100, dropping 10 oldest."""
        store = MemoryStore(storage_path=tmp_path / "memory.json")

        # Create 110 entries with distinct timestamps; oldest first
        entries = [
            MemoryEntry(content=f"entry {i}", category="fact", timestamp=float(i), access_count=0)
            for i in range(110)
        ]

        pruned = store.prune(entries, max_size=100)

        assert len(pruned) == 100
        # The 10 oldest (timestamp 0..9) should be dropped
        remaining_timestamps = {e.timestamp for e in pruned}
        for i in range(10):
            assert float(i) not in remaining_timestamps, f"Oldest entry {i} should have been pruned"

    def test_prune_respects_access_count(self, tmp_path):
        """Entries with higher access_count survive pruning over same-age but lower access_count."""
        store = MemoryStore(storage_path=tmp_path / "memory.json")

        # Create 101 entries all with the same timestamp (same age).
        # 100 entries have access_count=0; the special entry has access_count=10.
        # When pruning to 100, the frequently-accessed entry should survive.
        entries = [
            MemoryEntry(content=f"common {i}", category="fact", timestamp=1000.0, access_count=0)
            for i in range(100)
        ]
        # Same timestamp but higher access_count -- should survive pruning
        high_access = MemoryEntry(content="high access same age", category="fact", timestamp=1000.0, access_count=10)
        entries.append(high_access)

        pruned = store.prune(entries, max_size=100)

        assert len(pruned) == 100
        # The high-access entry should survive because its normalized access_count score is higher
        contents = [e.content for e in pruned]
        assert "high access same age" in contents, "High access_count entry should survive pruning over same-age entries"

    def test_budget(self, tmp_path):
        """get_budget() with 20 entries returns exactly 15, most recent first."""
        store = MemoryStore(storage_path=tmp_path / "memory.json")

        entries = [
            MemoryEntry(content=f"entry {i}", category="fact", timestamp=float(i), access_count=0)
            for i in range(20)
        ]

        budget = store.get_budget(entries, n=15)

        assert len(budget) == 15
        # Should be sorted by recency (highest timestamp first)
        timestamps = [e.timestamp for e in budget]
        assert timestamps == sorted(timestamps, reverse=True)
        # Most recent entry should be first (timestamp 19)
        assert budget[0].timestamp == 19.0

    def test_budget_fewer_than_n(self, tmp_path):
        """get_budget() with 5 entries returns all 5 when n=15."""
        store = MemoryStore(storage_path=tmp_path / "memory.json")

        entries = [
            MemoryEntry(content=f"entry {i}", category="fact", timestamp=float(i), access_count=0)
            for i in range(5)
        ]

        budget = store.get_budget(entries, n=15)

        assert len(budget) == 5

    def test_budget_increments_access_count(self, tmp_path):
        """get_budget() increments access_count on returned entries."""
        store = MemoryStore(storage_path=tmp_path / "memory.json")

        entries = [
            MemoryEntry(content=f"entry {i}", category="fact", timestamp=float(i), access_count=0)
            for i in range(5)
        ]

        budget = store.get_budget(entries, n=3)

        # All returned entries should have access_count incremented
        for entry in budget:
            assert entry.access_count == 1, f"Expected access_count=1, got {entry.access_count}"


class TestMemoryExtraction:
    """Tests for parse_extraction_result and format_history_for_extraction."""

    def test_parse_categories(self):
        """parse_extraction_result correctly categorizes preference, fact, moment."""
        text = (
            "preference: likes dark coffee\n"
            "fact: works at a startup\n"
            "moment: laughed at the recursive joke"
        )
        results = parse_extraction_result(text)

        assert len(results) == 3

        assert results[0].category == "preference"
        assert results[0].content == "likes dark coffee"

        assert results[1].category == "fact"
        assert results[1].content == "works at a startup"

        assert results[2].category == "moment"
        assert results[2].content == "laughed at the recursive joke"

    def test_parse_nothing(self):
        """parse_extraction_result returns empty list for 'NOTHING'."""
        result = parse_extraction_result("NOTHING")
        assert result == []

    def test_parse_mixed_case(self):
        """parse_extraction_result lowercases category."""
        result = parse_extraction_result("Preference: prefers tea")
        assert len(result) == 1
        assert result[0].category == "preference"
        assert result[0].content == "prefers tea"

    def test_skip_short_history(self):
        """format_history_for_extraction returns None for fewer than 4 messages."""
        messages = [
            Message(role="user", content="Hello"),
            Message(role="assistant", content="Hi there!"),
            Message(role="user", content="Bye"),
        ]
        result = format_history_for_extraction(messages)
        assert result is None

    def test_format_history(self):
        """format_history_for_extraction returns formatted string with USER/ASSISTANT prefixes."""
        messages = [
            Message(role="user", content="Hello"),
            Message(role="assistant", content="Hi there!"),
            Message(role="user", content="How are you?"),
            Message(role="assistant", content="I'm doing great!"),
            Message(role="user", content="Tell me a joke"),
            Message(role="assistant", content="Why did the chicken cross the road?"),
        ]
        result = format_history_for_extraction(messages)

        assert result is not None
        assert "USER: Hello" in result
        assert "ASSISTANT: Hi there!" in result
        assert "USER: How are you?" in result
        assert "ASSISTANT: I'm doing great!" in result
