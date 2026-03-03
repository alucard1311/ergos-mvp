"""Hardware detection module for Ergos."""

import logging
import platform
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

try:
    import torch
except ImportError:
    torch = None  # type: ignore[assignment]


@dataclass
class GPUInfo:
    """GPU information."""

    available: bool
    name: Optional[str] = None
    memory_gb: Optional[float] = None
    cuda_version: Optional[str] = None


@dataclass
class HardwareInfo:
    """System hardware information."""

    platform: str
    python_version: str
    gpu: GPUInfo
    recommended_device: str  # "cuda" or "cpu"


def get_vram_usage() -> tuple[float, float]:
    """Query current GPU VRAM usage.

    Returns:
        Tuple of (used_mb, total_mb). Returns (0.0, 0.0) when no GPU
        is available or when torch is not installed.
    """
    if torch is None:
        logger.debug("torch not available, returning zero VRAM usage")
        return (0.0, 0.0)

    try:
        if not torch.cuda.is_available():
            logger.debug("CUDA not available, returning zero VRAM usage")
            return (0.0, 0.0)

        # mem_get_info returns (free_bytes, total_bytes)
        free_bytes, total_bytes = torch.cuda.mem_get_info()
        total_mb = total_bytes / (1024 * 1024)
        free_mb = free_bytes / (1024 * 1024)
        used_mb = total_mb - free_mb
        return (used_mb, total_mb)
    except Exception as e:
        logger.warning("Failed to query VRAM usage: %s", e)
        return (0.0, 0.0)


def detect_gpu() -> GPUInfo:
    """Detect CUDA GPU availability and specs."""
    try:
        import torch

        if torch.cuda.is_available():
            device = torch.cuda.get_device_properties(0)
            return GPUInfo(
                available=True,
                name=device.name,
                memory_gb=round(device.total_memory / (1024**3), 1),
                cuda_version=torch.version.cuda,
            )
    except ImportError:
        logger.warning("PyTorch not installed, cannot detect GPU")
    except Exception as e:
        logger.warning(f"GPU detection failed: {e}")

    return GPUInfo(available=False)


def detect_hardware() -> HardwareInfo:
    """Detect system hardware capabilities."""
    gpu = detect_gpu()

    return HardwareInfo(
        platform=platform.platform(),
        python_version=platform.python_version(),
        gpu=gpu,
        recommended_device="cuda" if gpu.available else "cpu",
    )


def log_hardware_info(info: HardwareInfo) -> None:
    """Log hardware information for diagnostics."""
    logger.info(f"Platform: {info.platform}")
    logger.info(f"Python: {info.python_version}")
    if info.gpu.available:
        logger.info(
            f"GPU: {info.gpu.name} ({info.gpu.memory_gb}GB, CUDA {info.gpu.cuda_version})"
        )
    else:
        logger.info("GPU: Not available (using CPU)")
    logger.info(f"Recommended device: {info.recommended_device}")
