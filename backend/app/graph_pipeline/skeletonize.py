"""
Skeletonization: convert binary road mask → 1px centerline skeleton.

Pipeline:
1. Morphological closing to fill small gaps in the mask.
2. scikit-image skeletonize (Zhang-Suen thinning).
3. Prune short spurious branches (< MIN_BRANCH_PX pixels).
"""
import logging
from typing import Tuple

import numpy as np
from scipy import ndimage
from skimage.morphology import skeletonize, remove_small_objects, binary_closing, disk

logger = logging.getLogger(__name__)

MIN_BRANCH_PX = 10   # prune skeleton branches shorter than this
CLOSE_RADIUS   = 3   # morphological closing radius to bridge small gaps


def mask_to_skeleton(mask: np.ndarray) -> np.ndarray:
    """
    Convert a binary road mask (H, W, uint8) to a 1px skeleton.

    Args:
        mask: Binary numpy array (values 0 or 1).

    Returns:
        skeleton: Boolean numpy array (H, W).
    """
    if mask.dtype != bool:
        binary = mask.astype(bool)
    else:
        binary = mask.copy()

    logger.info(f"Skeletonizing mask: shape={mask.shape}, road_px={binary.sum()}")

    # 1. Close small gaps (e.g., under cars or shadows)
    binary = binary_closing(binary, disk(CLOSE_RADIUS))

    # 2. Remove tiny isolated specks
    binary = remove_small_objects(binary, min_size=50)

    # 3. Skeletonize
    skel = skeletonize(binary)

    # 4. Prune short spurs
    skel = _prune_skeleton(skel, min_branch_length=MIN_BRANCH_PX)

    logger.info(f"Skeleton produced: {skel.sum()} centerline pixels")
    return skel


def _prune_skeleton(skel: np.ndarray, min_branch_length: int = MIN_BRANCH_PX) -> np.ndarray:
    """
    Remove skeleton branches shorter than `min_branch_length` pixels.
    Endpoints are detected as skeleton pixels with exactly 1 neighbour in a 3×3 window.
    """
    from skimage.measure import label

    result = skel.copy()
    changed = True

    while changed:
        changed = False
        # Count 8-connected neighbours for each skeleton pixel
        kernel = np.ones((3, 3), dtype=np.uint8)
        kernel[1, 1] = 0
        neighbour_count = ndimage.convolve(result.astype(np.uint8), kernel, mode="constant")

        # Endpoints: skeleton pixels with exactly 1 neighbour
        endpoints = result & (neighbour_count == 1)

        if not endpoints.any():
            break

        # Label connected components of the skeleton
        labeled, _ = label(result, connectivity=2, return_num=True)

        ep_labels = set(labeled[endpoints].flatten()) - {0}

        for lbl in ep_labels:
            component = labeled == lbl
            component_skel = result & component
            if component_skel.sum() < min_branch_length:
                # Only prune if it doesn't disconnect the skeleton
                test = result & ~component_skel
                if _is_still_connected(result, test):
                    result[component_skel] = False
                    changed = True

    return result


def _is_still_connected(original: np.ndarray, pruned: np.ndarray) -> bool:
    """
    Heuristic: if pruning removes < 5% of skeleton pixels, assume it's OK
    (full connectivity check is too expensive inside the pruning loop).
    """
    return pruned.sum() >= 0.95 * original.sum()
