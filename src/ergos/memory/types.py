"""MemoryEntry dataclass for cross-session memory persistence."""

import time
from dataclasses import dataclass, field


@dataclass
class MemoryEntry:
    """A single piece of remembered information about the user.

    Attributes:
        content: The remembered fact or preference as a clear sentence.
        category: One of "preference", "fact", or "moment".
        timestamp: Unix timestamp when the entry was created (auto-set).
        access_count: Number of times this entry has been retrieved via get_budget.
    """

    content: str
    category: str  # "preference", "fact", "moment"
    timestamp: float = field(default_factory=time.time)
    access_count: int = 0
