"""Meeting notes plugin for Ergos.

Records both mic (You) and system audio (Others) via PipeWire, transcribes
each separately with Whisper, merges with speaker attribution, and saves
as structured Obsidian meeting notes.

Two-phase flow:
1. "note meetings" → start two pw-record processes (mic + sink monitor)
2. "save meeting notes" → stop, transcribe both, merge, extract, save markdown

During recording, normal Ergos conversation continues (handle_input returns False).
"""

import asyncio
import logging
import os
import re
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from collections.abc import Callable
from typing import Optional, TYPE_CHECKING

from ergos.llm.types import GenerationConfig
from ergos.plugins.base import BasePlugin

if TYPE_CHECKING:
    from ergos.stt.transcriber import WhisperTranscriber

logger = logging.getLogger(__name__)

__all__ = ["MeetingNotesPlugin"]

# Phrases to START recording
ACTIVATION_PHRASES = [
    "note meetings",
    "note meeting",
    "record meeting",
    "record the meeting",
    "start meeting notes",
    "start recording",
]

# Phrases to STOP recording and save
SAVE_PHRASES = [
    "save meeting notes",
    "save notes",
    "save the notes",
    "stop recording",
    "stop meeting",
    "done meeting",
]

_EXTRACTION_PROMPT = """\
Below is a meeting transcript between "You" (the user) and "Others" (remote participants).
Timestamps are in [M:SS] format. Extract structured meeting notes.
Attribute action items to specific speakers where possible.

Output EXACTLY this format with no extra text:

SUMMARY: one sentence summarizing the meeting
ACTION ITEMS:
- task — @speaker
DECISIONS:
- decision made
TOPICS:
- topic: brief detail

If a section has nothing, write NONE on a single line after the header.

TRANSCRIPT:
{transcript}"""


def _parse_section(text: str, header: str) -> list[str]:
    """Parse a section from the LLM extraction output."""
    pattern = rf"^{re.escape(header)}:\s*$"
    match = re.search(pattern, text, re.MULTILINE)
    if not match:
        return []

    rest = text[match.end():]
    next_header = re.search(r"^[A-Z][A-Z ]+:\s*$", rest, re.MULTILINE)
    section_text = rest[:next_header.start()] if next_header else rest
    section_text = section_text.strip()

    if section_text.upper() == "NONE" or not section_text:
        return []

    items = []
    for line in section_text.split("\n"):
        line = line.strip()
        if line.startswith("- "):
            items.append(line[2:].strip())
        elif line and line != "NONE":
            items.append(line)
    return items


def _parse_extraction(text: str) -> dict:
    """Parse the full LLM extraction output into sections."""
    summary_match = re.search(r"^SUMMARY:\s*(.+)$", text, re.MULTILINE)
    summary = summary_match.group(1).strip() if summary_match else ""

    return {
        "summary": summary,
        "action_items": _parse_section(text, "ACTION ITEMS"),
        "decisions": _parse_section(text, "DECISIONS"),
        "topics": _parse_section(text, "TOPICS"),
    }


def _merge_transcripts(
    you_segments: list[tuple[float, float, str]],
    others_segments: list[tuple[float, float, str]],
) -> str:
    """Merge two speaker streams into a chronological transcript.

    Args:
        you_segments: (start, end, text) from mic recording.
        others_segments: (start, end, text) from system audio recording.

    Returns:
        Chronologically merged transcript with speaker labels.
    """
    entries: list[tuple[float, str, str]] = []
    for start, _end, text in you_segments:
        entries.append((start, "You", text))
    for start, _end, text in others_segments:
        entries.append((start, "Others", text))
    entries.sort(key=lambda x: x[0])

    lines = []
    for start, speaker, text in entries:
        mins = int(start // 60)
        secs = int(start % 60)
        lines.append(f"[{mins}:{secs:02d}] {speaker}: {text}")
    return "\n".join(lines)


def _build_markdown(sections: dict, dt: datetime) -> str:
    """Build Obsidian-compatible markdown from parsed sections."""
    date_str = dt.strftime("%Y-%m-%d")
    title_date = dt.strftime("%B %-d, %Y")

    lines = [
        "---",
        f"date: {date_str}",
        "tags: [meeting]",
        "---",
        f"# Meeting Notes — {title_date}",
        "",
        "## Summary",
        sections.get("summary", "") or "No summary available.",
        "",
        "## Action Items",
    ]

    action_items = sections.get("action_items", [])
    if action_items:
        for item in action_items:
            lines.append(f"- [ ] {item}")
    else:
        lines.append("No action items.")

    lines.append("")
    lines.append("## Decisions")
    decisions = sections.get("decisions", [])
    if decisions:
        for item in decisions:
            lines.append(f"- {item}")
    else:
        lines.append("No decisions recorded.")

    lines.append("")
    lines.append("## Discussion Topics")
    topics = sections.get("topics", [])
    if topics:
        for item in topics:
            lines.append(f"- {item}")
    else:
        lines.append("No topics recorded.")

    lines.append("")
    return "\n".join(lines)


def _write_notes(vault_path: str, markdown: str, dt: datetime) -> Path:
    """Write markdown to the vault Meetings directory."""
    vault = Path(os.path.expanduser(vault_path))
    meetings_dir = vault / "Meetings"
    meetings_dir.mkdir(parents=True, exist_ok=True)

    filename = f"Meeting-{dt.strftime('%Y-%m-%d-%H%M')}.md"
    filepath = meetings_dir / filename
    filepath.write_text(markdown, encoding="utf-8")
    return filepath


def _get_sink_monitor() -> str | None:
    """Get the default PipeWire/PulseAudio sink monitor source name."""
    try:
        result = subprocess.run(
            ["pactl", "get-default-sink"],
            capture_output=True, text=True, timeout=5,
        )
        sink = result.stdout.strip()
        if sink:
            return f"{sink}.monitor"
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return None


def _get_default_source() -> str | None:
    """Get the default PipeWire/PulseAudio mic source name."""
    try:
        result = subprocess.run(
            ["pactl", "get-default-source"],
            capture_output=True, text=True, timeout=5,
        )
        source = result.stdout.strip()
        if source:
            return source
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return None


def _start_pw_record(target: str, output_path: str) -> subprocess.Popen:
    """Start a pw-record process capturing from a target source."""
    return subprocess.Popen(
        [
            "pw-record",
            "--target", target,
            "--rate", "16000",
            "--channels", "1",
            "--format", "s16",
            output_path,
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _stop_process(proc: subprocess.Popen) -> None:
    """Terminate a subprocess gracefully."""
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()


class MeetingNotesPlugin(BasePlugin):
    """Plugin that records mic + system audio and saves structured meeting notes."""

    def __init__(self) -> None:
        super().__init__()
        self._vault_path: str = "~/Documents/ObsidianVault"
        self._transcriber: Optional["WhisperTranscriber"] = None
        self._broadcast_recording: Optional[Callable] = None
        self._mic_process: Optional[subprocess.Popen] = None
        self._chrome_process: Optional[subprocess.Popen] = None
        self._mic_audio_path: Optional[str] = None
        self._chrome_audio_path: Optional[str] = None

    @property
    def name(self) -> str:
        return "meeting_notes"

    @property
    def activation_phrases(self) -> list[str]:
        return ACTIVATION_PHRASES

    def should_activate(self, text: str) -> bool:
        text_lower = text.lower()
        return any(phrase in text_lower for phrase in ACTIVATION_PHRASES)

    def set_transcriber(self, transcriber: "WhisperTranscriber") -> None:
        """Inject the Whisper transcriber for audio file transcription."""
        self._transcriber = transcriber

    def set_vault_path(self, path: str) -> None:
        """Set the Obsidian vault path."""
        self._vault_path = path

    def set_broadcast_recording(self, callback: Callable) -> None:
        """Inject callback to broadcast recording status to clients."""
        self._broadcast_recording = callback

    async def handle_input(self, text: str) -> bool:
        """Handle input: start recording or save notes."""
        text_lower = text.lower()

        # If not yet recording, start capture
        if not self._is_active:
            await self.activate()
            await self._start_recording()
            return True

        # Check for save/stop command
        if any(phrase in text_lower for phrase in SAVE_PHRASES):
            await self._save_notes()
            return True

        # Pass through to normal Ergos conversation during recording
        return False

    async def _start_recording(self) -> None:
        """Start two pw-record subprocesses: mic + system audio."""
        if self._transcriber is None:
            await self._speak_text("Meeting notes transcription is not configured.")
            await self.deactivate()
            return

        monitor = _get_sink_monitor()
        mic_source = _get_default_source()

        if monitor is None or mic_source is None:
            await self._speak_text(
                "Could not find your audio devices. "
                "Make sure PipeWire is running."
            )
            await self.deactivate()
            return

        # Create temp files
        fd1, self._mic_audio_path = tempfile.mkstemp(
            suffix=".wav", prefix="ergos_meeting_mic_"
        )
        os.close(fd1)
        fd2, self._chrome_audio_path = tempfile.mkstemp(
            suffix=".wav", prefix="ergos_meeting_chrome_"
        )
        os.close(fd2)

        try:
            self._mic_process = _start_pw_record(mic_source, self._mic_audio_path)
            self._chrome_process = _start_pw_record(monitor, self._chrome_audio_path)
        except FileNotFoundError:
            await self._speak_text("pw-record is not installed. Install PipeWire tools.")
            await self.deactivate()
            return

        logger.info(
            f"Meeting recording started: mic={self._mic_audio_path} "
            f"chrome={self._chrome_audio_path}"
        )

        if self._broadcast_recording:
            await self._broadcast_recording(True)

        await self._speak_text(
            "Meeting recording started. I'm capturing both your mic and system audio. "
            "Say save meeting notes when you're done."
        )

    async def _save_notes(self) -> None:
        """Stop recording, transcribe both streams, merge, extract, save."""
        # Stop both recordings
        if self._mic_process is not None:
            _stop_process(self._mic_process)
            self._mic_process = None
        if self._chrome_process is not None:
            _stop_process(self._chrome_process)
            self._chrome_process = None

        mic_path = self._mic_audio_path
        chrome_path = self._chrome_audio_path

        # Check we have at least one recording
        has_mic = mic_path and Path(mic_path).exists() and Path(mic_path).stat().st_size > 1000
        has_chrome = chrome_path and Path(chrome_path).exists() and Path(chrome_path).stat().st_size > 1000

        if not has_mic and not has_chrome:
            await self._speak_text("The recording was too short to transcribe.")
            await self._cleanup_and_deactivate()
            return

        await self._speak_text("Saving your meeting notes. Transcribing audio, one moment.")

        try:
            loop = asyncio.get_running_loop()

            # Transcribe both audio files with timestamps
            you_segments: list[tuple[float, float, str]] = []
            others_segments: list[tuple[float, float, str]] = []

            if has_mic:
                you_segments = await loop.run_in_executor(
                    None, self._transcriber.transcribe_file_segments, mic_path
                )
            if has_chrome:
                others_segments = await loop.run_in_executor(
                    None, self._transcriber.transcribe_file_segments, chrome_path
                )

            if not you_segments and not others_segments:
                await self._speak_text("Couldn't make out any speech in the recording.")
                await self._cleanup_and_deactivate()
                return

            # Merge into speaker-attributed transcript
            transcript = _merge_transcripts(you_segments, others_segments)

            # Truncate very long transcripts for LLM context
            if len(transcript) > 4000:
                transcript = transcript[-4000:]

            # LLM extraction
            prompt = _EXTRACTION_PROMPT.format(transcript=transcript)
            gen_config = GenerationConfig(max_tokens=500, temperature=0.3)
            result = await loop.run_in_executor(
                None, self._llm.generate, prompt, gen_config
            )

            # Parse and build markdown
            sections = _parse_extraction(result.text)
            dt = datetime.now()
            markdown = _build_markdown(sections, dt)

            # Write file
            filepath = await loop.run_in_executor(
                None, _write_notes, self._vault_path, markdown, dt
            )
            logger.info(f"Meeting notes saved to {filepath}")
            await self._speak_text("Meeting notes saved.")

        except Exception as e:
            logger.error(f"Failed to save meeting notes: {e}", exc_info=True)
            await self._speak_text("Sorry, I couldn't save the meeting notes.")

        await self._cleanup_and_deactivate()

    async def _cleanup_and_deactivate(self) -> None:
        """Clean up temp files and deactivate."""
        for path in (self._mic_audio_path, self._chrome_audio_path):
            if path:
                try:
                    Path(path).unlink(missing_ok=True)
                except Exception:
                    pass
        self._mic_audio_path = None
        self._chrome_audio_path = None
        await self.deactivate()

    async def deactivate(self) -> None:
        """Stop any running recordings and clean up."""
        for proc in (self._mic_process, self._chrome_process):
            if proc is not None:
                _stop_process(proc)
        self._mic_process = None
        self._chrome_process = None
        self._is_active = False

        if self._broadcast_recording:
            await self._broadcast_recording(False)
