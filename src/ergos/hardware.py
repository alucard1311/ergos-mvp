"""Hardware detection module for Ergos."""

import logging
import platform
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


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
