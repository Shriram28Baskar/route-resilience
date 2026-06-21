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
        if file.filename.lower().endswith(('.tif', '.tiff')):
            import rasterio
            from rasterio.io import MemoryFile
            with MemoryFile(contents) as memfile:
                with memfile.open() as src:
                    image = src.read()[:3]
                    image = np.transpose(image, (1, 2, 0))
                    image_np = image.astype(np.uint8)
        else:
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
        
        if file.filename.lower().endswith(('.tif', '.tiff')):
            import rasterio
            from rasterio.io import MemoryFile
            with MemoryFile(contents) as memfile:
                with memfile.open() as src:
                    image_16bit = src.read()[:3].astype(np.float32)
                    image_16bit = np.transpose(image_16bit, (1, 2, 0))
                    
                    # For the model (scrambled modulo-256 via rasterio)
                    model_image_np = image_16bit.astype(np.uint8)
                    
                    # For visual (properly scaled to 0-255 for humans)
                    v_min = image_16bit.min()
                    v_max = image_16bit.max()
                    visual_image_np = ((image_16bit - v_min) / (v_max - v_min + 1e-5) * 255).astype(np.uint8)
        else:
            visual_image = Image.open(io.BytesIO(contents)).convert("RGB")
            visual_image_np = np.array(visual_image)
            model_image_np = visual_image_np
            
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Cannot parse image: {exc}")

    try:
        overlay = generate_gradcam(model_image_np, visual_image_np, target_class=target_class)
    except Exception as exc:
        logger.exception("Explainability failed")
        raise HTTPException(status_code=500, detail=f"Explain error: {exc}")

    return JSONResponse({
        "overlay_b64": _encode_rgb(overlay),
        "method": "grad-cam",
        "target_class": target_class,
    })


import io as _io
import base64 as _base64
import numpy as _np
from PIL import Image as _Image
from fastapi import UploadFile, File


@router.post("/change-detect")
async def change_detect(
    pre_image: UploadFile = File(..., description="Pre-disaster satellite tile (RGB PNG/JPG)"),
    post_image: UploadFile = File(..., description="Post-disaster satellite tile (RGB PNG/JPG, same AOI)"),
):
    """
    Detect road damage by comparing pre- and post-disaster satellite images.

    Returns:
    - damage_mask_png_b64: base64 PNG of detected damage pixels
    - severity_map_png_b64: base64 PNG of severity heatmap
    - severity: overall label (CRITICAL/HIGH/MODERATE/MINIMAL)
    - damage_percentage: fraction of road area affected
    - estimated_affected_km: rough road length estimate
    - band_diffs: per-band change statistics
    """
    from app.ml.change_detection import detect_road_damage, damage_result_to_serializable

    try:
        pre_bytes = await pre_image.read()
        post_bytes = await post_image.read()

        pre_np = _np.array(_Image.open(_io.BytesIO(pre_bytes)).convert("RGB"))
        post_np = _np.array(_Image.open(_io.BytesIO(post_bytes)).convert("RGB"))

        # Resize post to match pre if different sizes
        if pre_np.shape != post_np.shape:
            post_pil = _Image.fromarray(post_np).resize((pre_np.shape[1], pre_np.shape[0]))
            post_np = _np.array(post_pil)

        result = detect_road_damage(pre_np, post_np)
        return damage_result_to_serializable(result)
    except Exception as exc:
        from fastapi import HTTPException
        raise HTTPException(status_code=422, detail=f"Image processing failed: {exc}")
