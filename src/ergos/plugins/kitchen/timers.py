"""Timer management for kitchen bot."""

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Callable, Awaitable, Optional

logger = logging.getLogger(__name__)

# Type alias for timer alert callback
TimerAlertCallback = Callable[[str], Awaitable[None]]


@dataclass
class KitchenTimer:
    """A single cooking timer with alerts.

    Provides countdown functionality with alerts at key intervals
    (1 minute, 30 seconds, and completion).
    """

    label: str
    seconds: int
    alert_callback: TimerAlertCallback
    _task: Optional[asyncio.Task] = field(default=None, repr=False)
    _cancelled: bool = field(default=False, repr=False)
    _remaining: int = field(default=0, repr=False)

    async def start(self) -> None:
        """Start the timer countdown."""
        self._remaining = self.seconds
        self._cancelled = False
        self._task = asyncio.create_task(self._run())
        logger.info(f"Timer started: {self.label} for {self.seconds} seconds")

    async def _run(self) -> None:
        """Run the timer countdown with alerts."""
        try:
            while self._remaining > 0 and not self._cancelled:
                # Alert at key intervals
                if self._remaining == 60:
                    await self.alert_callback(
                        f"One minute left on your {self.label} timer."
                    )
                elif self._remaining == 30:
                    await self.alert_callback(
                        f"30 seconds left on {self.label}."
                    )
                elif self._remaining == 10:
                    await self.alert_callback(
                        f"10 seconds left on {self.label}."
                    )

                await asyncio.sleep(1)
                self._remaining -= 1

            if not self._cancelled:
                await self.alert_callback(
                    f"Timer done! Your {self.label} is ready."
                )
                logger.info(f"Timer completed: {self.label}")

        except asyncio.CancelledError:
            logger.info(f"Timer cancelled: {self.label}")
            raise

    async def cancel(self) -> None:
        """Cancel the timer."""
        self._cancelled = True
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info(f"Timer cancelled: {self.label}")

    @property
    def remaining_seconds(self) -> int:
        """Get remaining time in seconds."""
        return self._remaining

    @property
    def remaining_formatted(self) -> str:
        """Get remaining time as formatted string."""
        minutes = self._remaining // 60
        seconds = self._remaining % 60
        if minutes > 0:
            return f"{minutes} minute{'s' if minutes != 1 else ''} and {seconds} seconds"
        return f"{seconds} seconds"

    @property
    def is_running(self) -> bool:
        """Check if timer is currently running."""
        return self._task is not None and not self._task.done() and not self._cancelled


class TimerManager:
    """Manages multiple kitchen timers.

    Allows creating, tracking, and cancelling multiple concurrent timers.
    """

    def __init__(self, alert_callback: TimerAlertCallback) -> None:
        """Initialize timer manager.

        Args:
            alert_callback: Async function called for timer alerts.
        """
        self._timers: dict[str, KitchenTimer] = {}
        self._alert_callback = alert_callback
        self._timer_counter = 0

    async def create_timer(
        self,
        duration_str: str,
        label: Optional[str] = None,
    ) -> Optional[KitchenTimer]:
        """Create and start a new timer.

        Args:
            duration_str: Duration string (e.g., "5 minutes", "30 seconds").
            label: Optional label for the timer.

        Returns:
            Created timer or None if duration couldn't be parsed.
        """
        seconds = self._parse_duration(duration_str)
        if seconds is None:
            return None

        # Generate unique label if not provided
        if label is None:
            self._timer_counter += 1
            label = f"timer {self._timer_counter}"

        timer = KitchenTimer(
            label=label,
            seconds=seconds,
            alert_callback=self._alert_callback,
        )

        self._timers[label] = timer
        await timer.start()
        return timer

    def _parse_duration(self, duration_str: str) -> Optional[int]:
        """Parse duration string to seconds.

        Args:
            duration_str: Duration string (e.g., "5 minutes", "30 seconds").

        Returns:
            Duration in seconds or None if parsing fails.
        """
        import re

        duration_lower = duration_str.lower()

        # Match number followed by unit
        match = re.search(r"(\d+)\s*(minutes?|mins?|seconds?|secs?|hours?|hrs?)?", duration_lower)
        if not match:
            return None

        num = int(match.group(1))
        unit = match.group(2) or "minutes"  # Default to minutes

        if "second" in unit or "sec" in unit:
            return num
        elif "hour" in unit or "hr" in unit:
            return num * 3600
        else:  # minutes
            return num * 60

    async def cancel_timer(self, label: str) -> bool:
        """Cancel a timer by label.

        Args:
            label: Timer label.

        Returns:
            True if timer was found and cancelled.
        """
        if label in self._timers:
            await self._timers[label].cancel()
            del self._timers[label]
            return True
        return False

    async def cancel_all(self) -> None:
        """Cancel all active timers."""
        for timer in list(self._timers.values()):
            await timer.cancel()
        self._timers.clear()

    def get_timer(self, label: str) -> Optional[KitchenTimer]:
        """Get a timer by label.

        Args:
            label: Timer label.

        Returns:
            Timer or None if not found.
        """
        return self._timers.get(label)

    @property
    def active_timers(self) -> list[KitchenTimer]:
        """Get list of active timers.

        Returns:
            List of currently running timers.
        """
        return [t for t in self._timers.values() if t.is_running]

    def get_status_summary(self) -> str:
        """Get a summary of all active timers.

        Returns:
            Human-readable status of all timers.
        """
        active = self.active_timers
        if not active:
            return "No active timers."

        lines = []
        for timer in active:
            lines.append(f"{timer.label}: {timer.remaining_formatted} remaining")
        return "\n".join(lines)
