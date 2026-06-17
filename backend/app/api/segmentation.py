"""
/segment  — road segmentation endpoints.
POST /segment          → run inference on an uploaded tile
POST /segment/explain  → return Grad-CAM / SHAP overlay for a tile
"""
import io
import base64
import logging
from typing import Optional

import numpy as np
from fastapi import APIRouter, File, UploadFile, HTTPException
from fastapi.responses import JSONResponse
from PIL import Image

from app.ml.inference import run_inference, fuse_predictions
from app.ml.explain import generate_gradcam

logger = logging.getLogger(__name__)
router = APIRouter()


def _encode_mask(mask: np.ndarray) -> str:
    """Encode a binary uint8 mask as a base64 PNG string."""
    img = Image.fromarray((mask * 255).astype(np.uint8), mode="L")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


def _encode_rgb(image_np: np.ndarray) -> str:
    """Encode an RGB uint8 image as a base64 PNG string."""
    img = Image.fromarray(image_np.astype(np.uint8), mode="RGB")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


@router.post("/")
async def segment_tile(file: UploadFile = File(...)):
    """
    Accept a satellite image tile (RGB PNG/JPEG/GeoTIFF) and return:
    - binary road mask (base64 PNG)
    - confidence map (base64 PNG)
    - model IoU on internal validation set (if cached)
    """
    try:
        contents = await file.read()
        image = Image.open(io.BytesIO(contents)).convert("RGB")
        image_np = np.array(image)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Cannot parse image: {exc}")

    try:
        mask, confidence = run_inference(image_np)
    except Exception as exc:
        logger.exception("Inference failed")
        raise HTTPException(status_code=500, detail=f"Inference error: {exc}")

    return JSONResponse({
        "mask_b64": _encode_mask(mask),
        "confidence_b64": _encode_mask(confidence),
        "tile_size": list(image_np.shape[:2]),
        "road_pixel_ratio": float(mask.mean()),
    })


@router.post("/explain")
async def explain_tile(file: UploadFile = File(...), target_class: Optional[int] = 1):
    """
    Return a Grad-CAM saliency overlay highlighting which regions drove
    the road segmentation prediction.
    """
    try:
        contents = await file.read()
        image = Image.open(io.BytesIO(contents)).convert("RGB")
        image_np = np.array(image)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Cannot parse image: {exc}")

    try:
        overlay = generate_gradcam(image_np, target_class=target_class)
    except Exception as exc:
        logger.exception("Explainability failed")
        raise HTTPException(status_code=500, detail=f"Explain error: {exc}")

    return JSONResponse({
        "overlay_b64": _encode_rgb(overlay),
        "method": "grad-cam",
        "target_class": target_class,
    })
