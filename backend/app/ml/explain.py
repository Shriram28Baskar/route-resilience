"""
Explainability: Grad-CAM implementation for road segmentation models.
Returns a heatmap overlay aligned to the input image.
"""
import logging
from typing import Optional

import numpy as np
import torch
import torch.nn.functional as F
import cv2

from app.ml.inference import _get_model, preprocess, DEVICE

logger = logging.getLogger(__name__)


class GradCAM:
    """
    Gradient-weighted Class Activation Mapping for segmentation models.
    Hooks into the final convolutional layer to capture activations + gradients.
    """

    def __init__(self, model: torch.nn.Module, target_layer_name: Optional[str] = None):
        self.model = model
        self.activations = None
        self.gradients = None
        self._hook_handles = []

        layer = self._find_target_layer(model, target_layer_name)
        if layer is not None:
            self._hook_handles.append(layer.register_forward_hook(self._save_activation))
            self._hook_handles.append(layer.register_full_backward_hook(self._save_gradient))
        else:
            logger.warning("Could not find target layer for Grad-CAM — returning blank overlay")

    def _find_target_layer(self, model, name):
        """Auto-detect the last Conv2d layer if name not specified."""
        last_conv = None
        for n, m in model.named_modules():
            if isinstance(m, torch.nn.Conv2d):
                if name is None or name in n:
                    last_conv = m
        return last_conv

    def _save_activation(self, module, input, output):
        self.activations = output.detach()

    def _save_gradient(self, module, grad_input, grad_output):
        self.gradients = grad_output[0].detach()

    def generate(self, input_tensor: torch.Tensor) -> np.ndarray:
        """
        Generate a Grad-CAM heatmap for the given input.

        Returns: float32 numpy array in [0, 1] of shape (H, W).
        """
        self.model.zero_grad()
        output = self.model(input_tensor)   # (1, 1, H, W)

        # For binary segmentation: backprop through mean predicted road probability
        road_score = torch.sigmoid(output).mean()
        road_score.backward()

        if self.activations is None or self.gradients is None:
            logger.warning("Grad-CAM hooks not triggered — returning uniform heatmap")
            return np.ones(input_tensor.shape[-2:], dtype=np.float32) * 0.5

        # Global average pool gradients over spatial dims → channel weights
        weights = self.gradients.mean(dim=(2, 3), keepdim=True)  # (1, C, 1, 1)
        cam = (weights * self.activations).sum(dim=1, keepdim=True)  # (1, 1, H, W)
        cam = F.relu(cam).squeeze().cpu().numpy()

        # Normalize to [0, 1]
        cam_min, cam_max = cam.min(), cam.max()
        if cam_max > cam_min:
            cam = (cam - cam_min) / (cam_max - cam_min)
        else:
            cam = np.zeros_like(cam)

        return cam.astype(np.float32)

    def remove_hooks(self):
        for h in self._hook_handles:
            h.remove()


def generate_gradcam(image_np: np.ndarray, target_class: int = 1) -> np.ndarray:
    """
    Generate a Grad-CAM overlay for the given RGB tile.

    Returns:
        uint8 RGB overlay image (H, W, 3) — Jet colormap on the original image.
    """
    h, w = image_np.shape[:2]
    model = _get_model()
    model.eval()

    input_tensor = preprocess(image_np)
    input_tensor.requires_grad_(True)

    cam_gen = GradCAM(model)

    try:
        cam = cam_gen.generate(input_tensor)
    finally:
        cam_gen.remove_hooks()

    # Resize CAM to original image dimensions
    cam_resized = cv2.resize(cam, (w, h), interpolation=cv2.INTER_LINEAR)

    # Apply jet colormap
    heatmap = cv2.applyColorMap((cam_resized * 255).astype(np.uint8), cv2.COLORMAP_JET)
    heatmap_rgb = cv2.cvtColor(heatmap, cv2.COLOR_BGR2RGB)

    # Overlay on original image
    overlay = cv2.addWeighted(image_np.astype(np.uint8), 0.55, heatmap_rgb, 0.45, 0)
    return overlay
