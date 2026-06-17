"""
Segmentation model definitions.

Default: U-Net with ResNet-50 encoder (segmentation-models-pytorch).
Stretch: SegFormer-style Transformer backbone via the `transformers` library.
"""
import os
import logging
from typing import Literal, Optional

import torch
import torch.nn as nn

logger = logging.getLogger(__name__)

ModelVariant = Literal["unet", "deeplabv3plus", "segformer"]


def build_model(
    variant: ModelVariant = "unet",
    encoder: str = "resnet50",
    weights: Optional[str] = "imagenet",
    num_classes: int = 1,
) -> nn.Module:
    """
    Build and return a segmentation model.

    Args:
        variant: Architecture variant.
        encoder: SMP encoder name (ignored for segformer).
        weights: Pre-trained weights (imagenet or None).
        num_classes: Output channels (1 for binary road mask).

    Returns:
        PyTorch nn.Module ready for training or inference.
    """
    if variant == "segformer":
        return _build_segformer(num_classes)
    else:
        return _build_smp(variant, encoder, weights, num_classes)


def _build_smp(variant, encoder, weights, num_classes):
    try:
        import segmentation_models_pytorch as smp
    except ImportError:
        raise RuntimeError("segmentation-models-pytorch not installed. Run: pip install segmentation-models-pytorch")

    in_channels = 3  # RGB

    kwargs = dict(encoder_name=encoder, encoder_weights=weights, in_channels=in_channels, classes=num_classes)

    if variant == "unet":
        model = smp.Unet(**kwargs)
    elif variant == "deeplabv3plus":
        model = smp.DeepLabV3Plus(**kwargs)
    else:
        raise ValueError(f"Unknown SMP variant: {variant}")

    logger.info(f"Built SMP model: {variant} / encoder={encoder} / weights={weights}")
    return model


def _build_segformer(num_classes: int):
    """
    Lightweight SegFormer (MIT-b0 backbone) via HuggingFace transformers.
    Wraps SegformerForSemanticSegmentation with a thin adapter for
    (B, C, H, W) → (B, num_classes, H, W) output.
    """
    try:
        from transformers import SegformerForSemanticSegmentation, SegformerConfig
    except ImportError:
        raise RuntimeError("transformers not installed. Run: pip install transformers")

    config = SegformerConfig.from_pretrained(
        "nvidia/segformer-b0-finetuned-ade-512-512",
        num_labels=num_classes,
        ignore_mismatched_sizes=True,
    )
    model = SegformerForSemanticSegmentation(config)
    logger.info("Built SegFormer (MIT-b0) model")
    return SegFormerWrapper(model)


class SegFormerWrapper(nn.Module):
    """Thin wrapper to produce (B, num_classes, H, W) from SegFormer."""

    def __init__(self, base_model):
        super().__init__()
        self.model = base_model

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        outputs = self.model(pixel_values=x)
        logits = outputs.logits  # (B, num_classes, H/4, W/4)
        # Upsample to original resolution
        logits = nn.functional.interpolate(logits, size=x.shape[-2:], mode="bilinear", align_corners=False)
        return logits


def load_checkpoint(model: nn.Module, checkpoint_path: str, device: str = "cpu") -> nn.Module:
    """Load a saved .pth checkpoint into the model."""
    if not os.path.exists(checkpoint_path):
        logger.warning(f"Checkpoint not found at {checkpoint_path}. Using randomly initialized weights.")
        return model

    try:
        state = torch.load(checkpoint_path, map_location=device)
        model.load_state_dict(state.get("model_state_dict", state))
        logger.info(f"Loaded checkpoint from {checkpoint_path}")
    except Exception as exc:
        logger.error(f"Failed to load checkpoint from {checkpoint_path}: {exc}. "
                     f"Using randomly initialized weights instead.")
    return model
