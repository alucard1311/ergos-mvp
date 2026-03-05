"""Tests for the meeting notes plugin (pure functions + activation logic)."""

from datetime import datetime

import pytest

from ergos.plugins.meeting_notes import (
    MeetingNotesPlugin,
    SAVE_PHRASES,
    _build_markdown,
    _merge_transcripts,
    _parse_extraction,
    _write_notes,
)


class TestMergeTranscripts:
    def test_interleaves_chronologically(self):
        you = [(0.0, 2.0, "Hello everyone"), (5.0, 7.0, "Let's get started")]
        others = [(2.5, 4.5, "Hi, good morning"), (8.0, 10.0, "Sounds good")]
        result = _merge_transcripts(you, others)

        lines = result.split("\n")
        assert len(lines) == 4
        assert lines[0] == "[0:00] You: Hello everyone"
        assert lines[1] == "[0:02] Others: Hi, good morning"
        assert lines[2] == "[0:05] You: Let's get started"
        assert lines[3] == "[0:08] Others: Sounds good"

    def test_only_you(self):
        you = [(0.0, 3.0, "Just me talking")]
        result = _merge_transcripts(you, [])
        assert "[0:00] You: Just me talking" in result

    def test_only_others(self):
        others = [(1.0, 4.0, "Remote speaker")]
        result = _merge_transcripts([], others)
        assert "[0:01] Others: Remote speaker" in result

    def test_empty_both(self):
        assert _merge_transcripts([], []) == ""

    def test_timestamp_formatting(self):
        you = [(65.0, 70.0, "After one minute")]
        result = _merge_transcripts(you, [])
        assert "[1:05] You: After one minute" in result

    def test_long_meeting_timestamps(self):
        others = [(3661.0, 3665.0, "One hour in")]
        result = _merge_transcripts([], others)
        assert "[61:01] Others: One hour in" in result


class TestParseExtraction:
    def test_full_output(self):
        text = """\
SUMMARY: We discussed the new feature rollout plan.
ACTION ITEMS:
- Build the API endpoint — @You
- Write tests — @Others
DECISIONS:
- Use REST instead of GraphQL
TOPICS:
- API design: decided on REST endpoints
- Timeline: targeting next sprint"""

        result = _parse_extraction(text)
        assert result["summary"] == "We discussed the new feature rollout plan."
        assert len(result["action_items"]) == 2
        assert "Build the API endpoint — @You" in result["action_items"]
        assert "Write tests — @Others" in result["action_items"]
        assert len(result["decisions"]) == 1
        assert len(result["topics"]) == 2

    def test_none_sections(self):
        text = """\
SUMMARY: Quick chat, nothing actionable.
ACTION ITEMS:
NONE
DECISIONS:
NONE
TOPICS:
- Catch-up: general status update"""

        result = _parse_extraction(text)
        assert result["summary"] == "Quick chat, nothing actionable."
        assert result["action_items"] == []
        assert result["decisions"] == []
        assert len(result["topics"]) == 1

    def test_empty_output(self):
        result = _parse_extraction("")
        assert result["summary"] == ""
        assert result["action_items"] == []
        assert result["decisions"] == []
        assert result["topics"] == []

    def test_missing_sections(self):
        text = "SUMMARY: Just a summary, nothing else."
        result = _parse_extraction(text)
        assert result["summary"] == "Just a summary, nothing else."
        assert result["action_items"] == []


class TestBuildMarkdown:
    def test_full_sections(self):
        sections = {
            "summary": "Discussed the launch plan.",
            "action_items": ["Deploy to staging — @You", "Update docs — @Others"],
            "decisions": ["Go with blue theme"],
            "topics": ["Launch date: next Monday"],
        }
        dt = datetime(2026, 3, 5, 14, 30)
        md = _build_markdown(sections, dt)

        assert "date: 2026-03-05" in md
        assert "tags: [meeting]" in md
        assert "# Meeting Notes — March 5, 2026" in md
        assert "Discussed the launch plan." in md
        assert "- [ ] Deploy to staging — @You" in md
        assert "- [ ] Update docs — @Others" in md
        assert "- Go with blue theme" in md
        assert "- Launch date: next Monday" in md

    def test_empty_sections(self):
        sections = {
            "summary": "",
            "action_items": [],
            "decisions": [],
            "topics": [],
        }
        dt = datetime(2026, 3, 5, 14, 30)
        md = _build_markdown(sections, dt)

        assert "No summary available." in md
        assert "No action items." in md
        assert "No decisions recorded." in md
        assert "No topics recorded." in md


class TestWriteNotes:
    def test_writes_file(self, tmp_path):
        vault_path = str(tmp_path / "vault")
        dt = datetime(2026, 3, 5, 14, 30)
        md = "# Test Meeting\nSome content."

        filepath = _write_notes(vault_path, md, dt)

        assert filepath.exists()
        assert filepath.name == "Meeting-2026-03-05-1430.md"
        assert filepath.parent.name == "Meetings"
        assert filepath.read_text() == md

    def test_creates_directories(self, tmp_path):
        vault_path = str(tmp_path / "deep" / "vault")
        dt = datetime(2026, 1, 15, 9, 0)

        filepath = _write_notes(vault_path, "content", dt)
        assert filepath.exists()
        assert filepath.parent.exists()


class TestShouldActivate:
    def test_start_phrases(self):
        plugin = MeetingNotesPlugin()
        assert plugin.should_activate("note meetings") is True
        assert plugin.should_activate("Note Meetings") is True
        assert plugin.should_activate("record meeting") is True
        assert plugin.should_activate("record the meeting") is True
        assert plugin.should_activate("start meeting notes") is True
        assert plugin.should_activate("start recording") is True

    def test_save_phrases_do_not_activate(self):
        """Save phrases should NOT trigger activation — they stop recording."""
        plugin = MeetingNotesPlugin()
        for phrase in SAVE_PHRASES:
            assert plugin.should_activate(phrase) is False, f"'{phrase}' should not activate"

    def test_non_activation(self):
        plugin = MeetingNotesPlugin()
        assert plugin.should_activate("what's the weather") is False
        assert plugin.should_activate("tell me a joke") is False

    def test_plugin_name(self):
        plugin = MeetingNotesPlugin()
        assert plugin.name == "meeting_notes"
