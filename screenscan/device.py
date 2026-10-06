"""Compute device selection: CUDA on NVIDIA, MPS on Apple silicon, otherwise CPU."""

import os

import torch


def pick() -> str:
    """SCREENSCAN_DEVICE=cuda|mps|cpu overrides auto-detection."""
    if forced := os.environ.get("SCREENSCAN_DEVICE"):
        return forced
    if torch.cuda.is_available():
        return "cuda"
    if torch.backends.mps.is_available():
        return "mps"
    return "cpu"


DEVICE = pick()


def half(preferred: torch.dtype) -> torch.dtype:
    """`preferred` on CUDA, float16 on MPS (bfloat16 support there is patchy), float32 on CPU."""
    return {"cuda": preferred, "mps": torch.float16}.get(DEVICE, torch.float32)
