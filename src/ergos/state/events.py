"""State change events for the conversation state machine."""

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Callable, Awaitable


class ConversationState(Enum):
    """
    State of the conversation.

    This is the single source of truth for conversation state.
    The audio pipeline reads from this rather than maintaining its own state.
    """
    IDLE = "idle"  # Not in conversation
    LISTENING = "listening"  # Receiving audio, waiting for speech
    PROCESSING = "processing"  # Processing speech (STT → LLM)
    SPEAKING = "speaking"  # Playing TTS output


@dataclass
class StateChangeEvent:
    """
    An event representing a state transition.

    Emitted whenever the state machine successfully transitions
    from one state to another.
    """
    previous_state: ConversationState
    new_state: ConversationState
    timestamp: float = field(default_factory=time.time)
    metadata: Optional[dict] = None

    def __str__(self) -> str:
        return f"{self.previous_state.value} → {self.new_state.value}"


# Type alias for state change callbacks
StateChangeCallback = Callable[[StateChangeEvent], Awaitable[None]]
