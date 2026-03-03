"""VRAM monitoring and orchestration utilities for Ergos v2.

Provides GPU memory tracking, model registration, and budget checking
to ensure all v2 models (STT, LLM, TTS, Vision) fit within available VRAM.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

try:
    import torch
except ImportError:
    torch = None  # type: ignore[assignment]


@dataclass
class VRAMSnapshot:
    """Point-in-time snapshot of GPU VRAM usage.

    Attributes:
        total_mb: Total GPU VRAM in megabytes.
        used_mb: Currently used VRAM in megabytes.
        free_mb: Currently free VRAM in megabytes.
        utilization_pct: VRAM utilization as a percentage (0-100).
    """

    total_mb: float
    used_mb: float
    free_mb: float
    utilization_pct: float


@dataclass
class ModelVRAMProfile:
    """Estimated VRAM usage for a single model.

    Attributes:
        model_name: Unique identifier for the model (e.g. "whisper-small").
        estimated_mb: Expected VRAM usage in megabytes.
        category: Model category: "stt", "llm", "tts", or "vision".
    """

    model_name: str
    estimated_mb: float
    category: str


class VRAMMonitor:
    """Track and manage GPU VRAM allocation across all Ergos models.

    Maintains a registry of model VRAM estimates and compares them
    against available GPU memory to prevent out-of-memory errors.

    Usage::

        monitor = VRAMMonitor()
        monitor.register_model("whisper-small", 1024.0, "stt")
        monitor.register_model("qwen3-8b", 5324.8, "llm")

        fits, total_mb, available_mb = monitor.budget_check()
        if not fits:
            raise RuntimeError(f"Models require {total_mb}MB but only {available_mb}MB available")

        snap = monitor.snapshot()
        print(f"GPU: {snap.used_mb:.0f}/{snap.total_mb:.0f}MB used ({snap.utilization_pct:.1f}%)")
    """

    def __init__(self, vram_budget_mb: float = 16384.0) -> None:
        """Initialize the VRAM monitor.

        Args:
            vram_budget_mb: Total VRAM budget in megabytes. Defaults to 16384 (16GB)
                            matching the RTX 5080 hardware target.
        """
        self._vram_budget_mb = vram_budget_mb
        self._models: dict[str, ModelVRAMProfile] = {}

    @property
    def registered_models(self) -> dict[str, ModelVRAMProfile]:
        """Return the registry of registered model profiles."""
        return dict(self._models)

    def snapshot(self) -> VRAMSnapshot:
        """Query current GPU VRAM usage.

        Returns a VRAMSnapshot with current memory statistics.
        Returns a zero-usage snapshot when no GPU is available or
        when torch is not installed — does not raise.

        Returns:
            VRAMSnapshot with current VRAM statistics, or zeros if no GPU.
        """
        if torch is None:
            logger.debug("torch not available, returning zero VRAM snapshot")
            return VRAMSnapshot(total_mb=0.0, used_mb=0.0, free_mb=0.0, utilization_pct=0.0)

        try:
            if not torch.cuda.is_available():
                logger.debug("CUDA not available, returning zero VRAM snapshot")
                return VRAMSnapshot(total_mb=0.0, used_mb=0.0, free_mb=0.0, utilization_pct=0.0)

            # mem_get_info returns (free_bytes, total_bytes)
            free_bytes, total_bytes = torch.cuda.mem_get_info()
            total_mb = total_bytes / (1024 * 1024)
            free_mb = free_bytes / (1024 * 1024)
            used_mb = total_mb - free_mb
            utilization_pct = (used_mb / total_mb * 100.0) if total_mb > 0 else 0.0

            return VRAMSnapshot(
                total_mb=total_mb,
                used_mb=used_mb,
                free_mb=free_mb,
                utilization_pct=utilization_pct,
            )
        except Exception as e:
            logger.warning("Failed to query VRAM: %s", e)
            return VRAMSnapshot(total_mb=0.0, used_mb=0.0, free_mb=0.0, utilization_pct=0.0)

    def register_model(self, name: str, estimated_mb: float, category: str) -> None:
        """Register a model with its expected VRAM usage.

        Args:
            name: Unique model identifier (e.g. "whisper-small", "qwen3-8b").
            estimated_mb: Expected VRAM usage in megabytes.
            category: Model category: "stt", "llm", "tts", or "vision".
        """
        profile = ModelVRAMProfile(
            model_name=name,
            estimated_mb=estimated_mb,
            category=category,
        )
        self._models[name] = profile
        logger.debug("Registered model '%s': %.0fMB (%s)", name, estimated_mb, category)

    def unregister_model(self, name: str) -> None:
        """Remove a model from the registry.

        Does nothing if the model is not registered.

        Args:
            name: Model identifier to remove.
        """
        if name in self._models:
            del self._models[name]
            logger.debug("Unregistered model '%s'", name)

    def budget_check(
        self, headroom_mb: float = 4000.0
    ) -> tuple[bool, float, float]:
        """Check whether registered models fit within the VRAM budget.

        Args:
            headroom_mb: Reserved VRAM for KV cache, OS, and overhead. Default 4000 MB.

        Returns:
            Tuple of (fits, total_estimated_mb, available_mb) where:
              - fits: True if total estimated VRAM <= (budget - headroom)
              - total_estimated_mb: Sum of all registered model estimates
              - available_mb: Effective budget after subtracting headroom
        """
        total_estimated = sum(
            (p.estimated_mb for p in self._models.values()), 0.0
        )
        available = self._vram_budget_mb - headroom_mb
        fits = total_estimated <= available
        return fits, total_estimated, available

    def report(self) -> dict:
        """Generate a summary report of VRAM usage and model registry.

        Returns:
            Dict with keys:
              - "models": dict of model_name -> profile as dict
              - "gpu": current VRAMSnapshot as dict
              - "budget_mb": configured VRAM budget
              - "total_estimated_mb": sum of all registered model estimates
        """
        snap = self.snapshot()
        total_estimated = sum(
            (p.estimated_mb for p in self._models.values()), 0.0
        )

        return {
            "models": {
                name: {
                    "model_name": p.model_name,
                    "estimated_mb": p.estimated_mb,
                    "category": p.category,
                }
                for name, p in self._models.items()
            },
            "gpu": {
                "total_mb": snap.total_mb,
                "used_mb": snap.used_mb,
                "free_mb": snap.free_mb,
                "utilization_pct": snap.utilization_pct,
            },
            "budget_mb": self._vram_budget_mb,
            "total_estimated_mb": total_estimated,
        }
