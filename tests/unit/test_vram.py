"""Unit tests for VRAM monitoring module."""

from unittest.mock import MagicMock, patch

import pytest

from ergos.core.vram import ModelVRAMProfile, VRAMMonitor, VRAMSnapshot


class TestVRAMSnapshot:
    """Tests for VRAMSnapshot dataclass."""

    def test_snapshot_fields(self):
        """VRAMSnapshot stores total_mb, used_mb, free_mb, utilization_pct."""
        snap = VRAMSnapshot(
            total_mb=16384.0,
            used_mb=4096.0,
            free_mb=12288.0,
            utilization_pct=25.0,
        )
        assert snap.total_mb == 16384.0
        assert snap.used_mb == 4096.0
        assert snap.free_mb == 12288.0
        assert snap.utilization_pct == 25.0


class TestModelVRAMProfile:
    """Tests for ModelVRAMProfile dataclass."""

    def test_profile_fields(self):
        """ModelVRAMProfile stores model_name, estimated_mb, category."""
        profile = ModelVRAMProfile(
            model_name="whisper-small",
            estimated_mb=1024.0,
            category="stt",
        )
        assert profile.model_name == "whisper-small"
        assert profile.estimated_mb == 1024.0
        assert profile.category == "stt"

    def test_profile_categories(self):
        """ModelVRAMProfile accepts stt/llm/tts/vision categories."""
        for cat in ("stt", "llm", "tts", "vision"):
            p = ModelVRAMProfile(model_name="m", estimated_mb=100.0, category=cat)
            assert p.category == cat


class TestVRAMMonitor:
    """Tests for VRAMMonitor class."""

    def test_init_default_budget(self):
        """VRAMMonitor initializes with 16384 MB default budget."""
        monitor = VRAMMonitor()
        assert monitor._vram_budget_mb == 16384.0

    def test_init_custom_budget(self):
        """VRAMMonitor accepts custom budget."""
        monitor = VRAMMonitor(vram_budget_mb=8192.0)
        assert monitor._vram_budget_mb == 8192.0

    def test_empty_registered_models(self):
        """VRAMMonitor starts with no registered models."""
        monitor = VRAMMonitor()
        assert len(monitor.registered_models) == 0

    def test_snapshot_with_gpu(self):
        """VRAMMonitor.snapshot() returns correct data when GPU is available.

        torch.cuda.mem_get_info returns (free_bytes, total_bytes).
        """
        total_bytes = 16 * 1024 ** 3  # 16 GB
        free_bytes = 12 * 1024 ** 3   # 12 GB free -> 4 GB used

        with patch("ergos.core.vram.torch") as mock_torch:
            mock_torch.cuda.is_available.return_value = True
            mock_torch.cuda.mem_get_info.return_value = (free_bytes, total_bytes)

            monitor = VRAMMonitor()
            snap = monitor.snapshot()

        assert snap.total_mb == pytest.approx(16384.0, rel=1e-3)
        assert snap.free_mb == pytest.approx(12288.0, rel=1e-3)
        assert snap.used_mb == pytest.approx(4096.0, rel=1e-3)
        assert snap.utilization_pct == pytest.approx(25.0, rel=1e-3)

    def test_snapshot_no_gpu(self):
        """VRAMMonitor.snapshot() returns zero snapshot when no GPU is available."""
        with patch("ergos.core.vram.torch") as mock_torch:
            mock_torch.cuda.is_available.return_value = False

            monitor = VRAMMonitor()
            snap = monitor.snapshot()

        assert snap.total_mb == 0.0
        assert snap.used_mb == 0.0
        assert snap.free_mb == 0.0
        assert snap.utilization_pct == 0.0

    def test_snapshot_no_torch(self):
        """VRAMMonitor.snapshot() returns zero snapshot when torch is not installed."""
        with patch("ergos.core.vram.torch", None):
            monitor = VRAMMonitor()
            snap = monitor.snapshot()

        assert snap.total_mb == 0.0
        assert snap.used_mb == 0.0

    def test_register_model(self):
        """VRAMMonitor.register_model() adds a ModelVRAMProfile."""
        monitor = VRAMMonitor()
        monitor.register_model("whisper-small", 1024.0, "stt")

        assert "whisper-small" in monitor.registered_models
        profile = monitor.registered_models["whisper-small"]
        assert profile.model_name == "whisper-small"
        assert profile.estimated_mb == 1024.0
        assert profile.category == "stt"

    def test_register_multiple_models(self):
        """VRAMMonitor can register multiple models."""
        monitor = VRAMMonitor()
        monitor.register_model("whisper-small", 1024.0, "stt")
        monitor.register_model("qwen3-8b", 5324.8, "llm")
        monitor.register_model("kokoro-82m", 512.0, "tts")

        assert len(monitor.registered_models) == 3

    def test_unregister_model(self):
        """VRAMMonitor.unregister_model() removes a model."""
        monitor = VRAMMonitor()
        monitor.register_model("whisper-small", 1024.0, "stt")
        monitor.unregister_model("whisper-small")

        assert "whisper-small" not in monitor.registered_models

    def test_unregister_nonexistent_model(self):
        """VRAMMonitor.unregister_model() does not crash on unknown model."""
        monitor = VRAMMonitor()
        # Should not raise
        monitor.unregister_model("nonexistent-model")

    def test_budget_check_fits(self):
        """VRAMMonitor.budget_check() returns True when models fit in budget."""
        monitor = VRAMMonitor(vram_budget_mb=16384.0)
        monitor.register_model("whisper-small", 1024.0, "stt")
        monitor.register_model("qwen3-8b", 5324.8, "llm")
        monitor.register_model("kokoro-82m", 512.0, "tts")

        fits, total_estimated, available = monitor.budget_check(headroom_mb=4000.0)

        assert fits is True
        assert total_estimated == pytest.approx(6860.8, rel=1e-3)
        # available = budget - headroom = 16384 - 4000 = 12384
        assert available == pytest.approx(12384.0, rel=1e-3)

    def test_budget_check_does_not_fit(self):
        """VRAMMonitor.budget_check() returns False when models exceed budget."""
        monitor = VRAMMonitor(vram_budget_mb=8192.0)
        monitor.register_model("model-a", 5000.0, "llm")
        monitor.register_model("model-b", 4000.0, "llm")

        fits, total_estimated, available = monitor.budget_check(headroom_mb=1000.0)

        assert fits is False
        assert total_estimated == pytest.approx(9000.0, rel=1e-3)
        # available = 8192 - 1000 = 7192
        assert available == pytest.approx(7192.0, rel=1e-3)

    def test_budget_check_default_headroom(self):
        """VRAMMonitor.budget_check() uses 4000 MB headroom by default."""
        monitor = VRAMMonitor(vram_budget_mb=16384.0)
        fits, total, available = monitor.budget_check()

        # No models registered, total = 0, available = 16384 - 4000 = 12384
        assert fits is True
        assert total == 0.0
        assert available == pytest.approx(12384.0, rel=1e-3)

    def test_report_structure(self):
        """VRAMMonitor.report() returns dict with models, gpu, budget_mb, total_estimated_mb."""
        monitor = VRAMMonitor(vram_budget_mb=16384.0)
        monitor.register_model("whisper-small", 1024.0, "stt")

        with patch("ergos.core.vram.torch") as mock_torch:
            mock_torch.cuda.is_available.return_value = False
            report = monitor.report()

        assert "models" in report
        assert "gpu" in report
        assert "budget_mb" in report
        assert "total_estimated_mb" in report

        assert report["budget_mb"] == 16384.0
        assert report["total_estimated_mb"] == 1024.0
        assert "whisper-small" in report["models"]
        # GPU section is a dict (serialized snapshot)
        assert isinstance(report["gpu"], dict)

    def test_report_gpu_dict_keys(self):
        """VRAMMonitor.report() gpu section has expected keys."""
        monitor = VRAMMonitor()

        with patch("ergos.core.vram.torch") as mock_torch:
            mock_torch.cuda.is_available.return_value = False
            report = monitor.report()

        gpu = report["gpu"]
        assert "total_mb" in gpu
        assert "used_mb" in gpu
        assert "free_mb" in gpu
        assert "utilization_pct" in gpu


class TestGetVramUsage:
    """Tests for hardware.py get_vram_usage() function."""

    def test_get_vram_usage_with_gpu(self):
        """get_vram_usage() returns (used_mb, total_mb) when GPU is available."""
        from ergos.hardware import get_vram_usage

        total_bytes = 16 * 1024 ** 3
        free_bytes = 10 * 1024 ** 3

        with patch("ergos.hardware.torch") as mock_torch:
            mock_torch.cuda.is_available.return_value = True
            mock_torch.cuda.mem_get_info.return_value = (free_bytes, total_bytes)

            used_mb, total_mb = get_vram_usage()

        assert total_mb == pytest.approx(16384.0, rel=1e-3)
        assert used_mb == pytest.approx(6144.0, rel=1e-3)

    def test_get_vram_usage_no_gpu(self):
        """get_vram_usage() returns (0.0, 0.0) when GPU is not available."""
        from ergos.hardware import get_vram_usage

        with patch("ergos.hardware.torch") as mock_torch:
            mock_torch.cuda.is_available.return_value = False

            used_mb, total_mb = get_vram_usage()

        assert used_mb == 0.0
        assert total_mb == 0.0

    def test_get_vram_usage_no_torch(self):
        """get_vram_usage() returns (0.0, 0.0) when torch is not installed."""
        from ergos.hardware import get_vram_usage

        with patch("ergos.hardware.torch", None):
            used_mb, total_mb = get_vram_usage()

        assert used_mb == 0.0
        assert total_mb == 0.0
