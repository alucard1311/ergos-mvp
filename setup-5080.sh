#!/bin/bash
# Ergos setup for Ubuntu 24.04 + RTX 5080
# Usage:
#   Part 1: bash setup-5080.sh prepare   (installs drivers, reboots)
#   Part 2: bash setup-5080.sh install    (after reboot, sets up ergos)
set -euo pipefail

REPO="git@github.com:alucard1311/ergos-mvp.git"
ERGOS_DIR="$HOME/ergos"

prepare() {
    echo "=== Part 1: System + NVIDIA Drivers ==="

    sudo apt update && sudo apt upgrade -y

    # System dependencies
    sudo apt install -y \
        git python3.12 python3.12-venv python3-pip \
        portaudio19-dev libsndfile1 ffmpeg \
        build-essential cmake curl

    # NVIDIA drivers (570 series for RTX 5080)
    sudo apt install -y nvidia-driver-570

    echo ""
    echo "=== Drivers installed. Rebooting in 5 seconds... ==="
    echo "After reboot, run: bash setup-5080.sh install"
    sleep 5
    sudo reboot
}

install() {
    echo "=== Part 2: Ergos Setup ==="

    # Verify GPU
    echo "Checking GPU..."
    nvidia-smi || { echo "ERROR: nvidia-smi failed. Did you reboot after Part 1?"; exit 1; }
    echo ""

    # Install CUDA toolkit
    sudo apt install -y nvidia-cuda-toolkit

    # Clone repo
    if [ ! -d "$ERGOS_DIR" ]; then
        echo "Cloning ergos..."
        git clone "$REPO" "$ERGOS_DIR"
    else
        echo "Ergos directory exists, pulling latest..."
        cd "$ERGOS_DIR" && git pull
    fi

    cd "$ERGOS_DIR"

    # Python venv
    echo "Creating virtual environment..."
    python3.12 -m venv .venv
    source .venv/bin/activate
    pip install --upgrade pip

    # Install ergos with orpheus extra
    echo "Installing ergos + dependencies..."
    pip install -e ".[orpheus]"

    # llama-cpp-python with CUDA support
    echo "Installing llama-cpp-python with CUDA..."
    CMAKE_ARGS="-DGGML_CUDA=on" pip install llama-cpp-python --force-reinstall --no-cache-dir

    # onnxruntime with CUDA
    echo "Installing onnxruntime-gpu..."
    pip install onnxruntime-gpu

    # sounddevice for local audio testing
    pip install sounddevice

    # Pre-download models
    echo "Pre-downloading Whisper model..."
    python -c "from faster_whisper import WhisperModel; WhisperModel('small.en', device='cuda', compute_type='int8')"

    # Verify
    echo ""
    echo "=== Running tests ==="
    python -m pytest tests/unit/ -q

    echo ""
    echo "=== Orpheus TTS test ==="
    python test_markup.py

    echo ""
    echo "========================================="
    echo " Ergos setup complete!"
    echo " GPU: $(nvidia-smi --query-gpu=name --format=csv,noheader)"
    echo " VRAM: $(nvidia-smi --query-gpu=memory.total --format=csv,noheader)"
    echo ""
    echo " To test voice: python test_local.py"
    echo " To start:      source .venv/bin/activate && ergos start"
    echo "========================================="
}

case "${1:-}" in
    prepare) prepare ;;
    install) install ;;
    *)
        echo "Usage: bash setup-5080.sh [prepare|install]"
        echo "  prepare  - Install system deps + NVIDIA drivers (reboots)"
        echo "  install  - Set up ergos (run after reboot)"
        ;;
esac
