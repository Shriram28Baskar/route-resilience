"""
Inference pipeline: load model, preprocess tile, run forward pass, post-process.
Supports single-resolution and multi-resolution late fusion.
"""
import os
import logging
from functools import lru_cache
from typing import Tuple, List, Optional

import numpy as np
import torch
import torch.nn.functional as F
from PIL import Image

from app.ml.model import build_model, load_checkpoint

logger = logging.getLogger(__name__)

TILE_SIZE = int(os.getenv("TILE_SIZE", 512))
CHECKPOINT = os.getenv("MODEL_CHECKPOINT", "data/checkpoints/best_model.pth")
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"

# ImageNet normalization
MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
STD  = np.array([0.229, 0.224, 0.225], dtype=np.float32)


@lru_cache(maxsize=1)
def _get_model():
    """Load and cache the inference model (singleton)."""
    model = build_model(
        variant=os.getenv("MODEL_VARIANT", "unet"),
        encoder=os.getenv("MODEL_ENCODER", "resnet50"),
        weights=None,  # will be loaded from checkpoint
    )
    model = load_checkpoint(model, CHECKPOINT, device=DEVICE)
    model.to(DEVICE).eval()
    return model


def preprocess(image_np: np.ndarray, tile_size: int = TILE_SIZE) -> torch.Tensor:
    """
    Resize, normalize, and convert an HxWxC uint8 RGB numpy array to
    a (1, 3, H, W) float32 tensor.
    """
    img = Image.fromarray(image_np).resize((tile_size, tile_size), Image.BILINEAR)
    arr = np.array(img, dtype=np.float32) / 255.0
    arr = (arr - MEAN) / STD
    tensor = torch.from_numpy(arr.transpose(2, 0, 1)).unsqueeze(0)  # (1, 3, H, W)
    return tensor.to(DEVICE)


def postprocess(logits: torch.Tensor, original_size: Tuple[int, int]) -> Tuple[np.ndarray, np.ndarray]:
    """
    Convert model output logits → binary mask + confidence map at original_size.

    Returns:
        mask:       uint8 (H, W) binary road mask {0, 1}
        confidence: float32 (H, W) probability in [0, 1]
    """
    prob = torch.sigmoid(logits.squeeze())  # (H, W)
    prob_resized = F.interpolate(
        prob.unsqueeze(0).unsqueeze(0),
        size=original_size,
        mode="bilinear",
        align_corners=False,
    ).squeeze().cpu().numpy()

    mask = (prob_resized > 0.5).astype(np.uint8)
    return mask, prob_resized.astype(np.float32)


def run_inference(image_np: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """
    End-to-end inference on a single RGB tile.

    Returns:
        (binary_mask, confidence_map) as numpy arrays at input resolution.
    """
    h, w = image_np.shape[:2]
    tensor = preprocess(image_np)

    with torch.no_grad():
        logits = _get_model()(tensor)  # (1, 1, TILE_SIZE, TILE_SIZE)

    return postprocess(logits, (h, w))


def fuse_predictions(probability_maps: List[np.ndarray], weights: Optional[List[float]] = None) -> Tuple[np.ndarray, np.ndarray]:
    """
    Multi-resolution late fusion: weighted average of aligned probability maps.

    Args:
        probability_maps: List of float32 arrays aligned to the same spatial extent.
        weights: Per-map weights (uniform if None).

    Returns:
        (binary_mask, fused_confidence)
    """
    if not probability_maps:
        raise ValueError("No probability maps to fuse")

    if weights is None:
        weights = [1.0 / len(probability_maps)] * len(probability_maps)

    target_shape = probability_maps[0].shape
    fused = np.zeros(target_shape, dtype=np.float32)

    for pmap, w in zip(probability_maps, weights):
        if pmap.shape != target_shape:
            pmap_resized = np.array(
                Image.fromarray(pmap).resize((target_shape[1], target_shape[0]), Image.BILINEAR)
            )
        else:
            pmap_resized = pmap
        fused += w * pmap_resized

    mask = (fused > 0.5).astype(np.uint8)
    return mask, fused
