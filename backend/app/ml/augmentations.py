"""
Albumentations-based augmentation pipelines.
Includes occlusion simulation transforms:
- Tree canopy / shadow patches (CoarseDropout)
- Cloud blobs (Perlin-noise approximation via GaussianBlur + brightness)
- Vehicle clutter (small random rectangles)
- Atmospheric haze (fog simulation)
"""
import numpy as np
import albumentations as A
from albumentations.pytorch import ToTensorV2


def get_train_transforms(tile_size: int = 512) -> A.Compose:
    """Full augmentation pipeline for training (geometric + photometric + occlusion)."""
    return A.Compose([
        # Geometric
        A.RandomSizedCrop(min_max_height=(int(tile_size * 0.7), tile_size), size=(tile_size, tile_size), p=0.5),
        A.HorizontalFlip(p=0.5),
        A.VerticalFlip(p=0.5),
        A.RandomRotate90(p=0.5),
        A.ShiftScaleRotate(shift_limit=0.05, scale_limit=0.1, rotate_limit=30, p=0.5),

        # Photometric
        A.RandomBrightnessContrast(brightness_limit=0.3, contrast_limit=0.3, p=0.6),
        A.HueSaturationValue(hue_shift_limit=20, sat_shift_limit=30, val_shift_limit=20, p=0.4),
        A.CLAHE(clip_limit=4.0, tile_grid_size=(8, 8), p=0.3),
        A.GaussNoise(p=0.3),
        A.GaussianBlur(blur_limit=(3, 7), p=0.2),

        # Occlusion simulation
        _canopy_occlusion(p=0.4),
        _shadow_overlay(p=0.3),
        _cloud_blob(p=0.2),
        _vehicle_clutter(tile_size, p=0.3),

        # Normalize (ImageNet stats)
        A.Normalize(mean=(0.485, 0.456, 0.406), std=(0.229, 0.224, 0.225)),
        ToTensorV2(),
    ])


def get_val_transforms(tile_size: int = 512) -> A.Compose:
    """Minimal transforms for validation (normalize only)."""
    return A.Compose([
        A.Resize(tile_size, tile_size),
        A.Normalize(mean=(0.485, 0.456, 0.406), std=(0.229, 0.224, 0.225)),
        ToTensorV2(),
    ])


def get_occluded_test_transforms(tile_size: int = 512, occlusion_type: str = "canopy") -> A.Compose:
    """
    Create an 'occluded test set' by applying heavy occlusion to clean tiles.
    Used to compute Occlusion-Recall separately from baseline IoU.
    """
    occ_map = {
        "canopy":  _canopy_occlusion(p=1.0),
        "shadow":  _shadow_overlay(p=1.0),
        "cloud":   _cloud_blob(p=1.0),
        "vehicle": _vehicle_clutter(tile_size, p=1.0),
    }
    return A.Compose([
        A.Resize(tile_size, tile_size),
        occ_map.get(occlusion_type, _canopy_occlusion(p=1.0)),
        A.Normalize(mean=(0.485, 0.456, 0.406), std=(0.229, 0.224, 0.225)),
        ToTensorV2(),
    ])


# ── Occlusion transforms ──────────────────────────────────────────────────────

def _canopy_occlusion(p: float = 0.5) -> A.BasicTransform:
    """Simulate tree canopy occlusion with irregular dark-green patches."""
    return A.CoarseDropout(
        num_holes_range=(4, 12),
        hole_height_range=(16, 64),
        hole_width_range=(16, 64),
        fill=(34, 85, 34),          # dark green
        p=p,
    )


def _shadow_overlay(p: float = 0.4) -> A.BasicTransform:
    """Simulate cast shadows (abrupt brightness drop in random regions)."""
    return A.RandomShadow(
        shadow_roi=(0, 0, 1, 1),
        num_shadows_limit=(1, 3),
        shadow_dimension=6,
        p=p,
    )


def _cloud_blob(p: float = 0.2) -> A.BasicTransform:
    """Simulate cloud/haze occlusion with random bright white patches + blur."""
    return A.OneOf([
        A.RandomFog(fog_coef_range=(0.3, 0.6), alpha_coef=0.1, p=1.0),
        A.CoarseDropout(
            num_holes_range=(1, 4), 
            hole_height_range=(64, 128), 
            hole_width_range=(64, 128),
            fill=220,  # white-ish cloud
            p=1.0,
        ),
    ], p=p)


def _vehicle_clutter(tile_size: int, p: float = 0.3) -> A.BasicTransform:
    """Simulate vehicle clutter (small rectangles of various colors)."""
    return A.CoarseDropout(
        num_holes_range=(10, 30),
        hole_height_range=(2, max(4, tile_size // 64)),
        hole_width_range=(4, max(8, tile_size // 32)),
        fill=0,
        p=p,
    )
