"""
Training script for road segmentation model.

Usage:
    python -m app.ml.train \
        --data-dir /path/to/tiles \
        --epochs 50 \
        --batch-size 8 \
        --variant unet \
        --encoder resnet50
"""
import argparse
import os
import logging
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import Dataset, DataLoader, random_split
from PIL import Image

from app.ml.model import build_model
from app.ml.augmentations import get_train_transforms, get_val_transforms

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


# ── Dataset ───────────────────────────────────────────────────────────────────

class RoadDataset(Dataset):
    """
    Expects directory structure:
        data-dir/
            images/  *.png | *.jpg | *.tif
            masks/   *.png  (binary, same stem as image)
    """

    def __init__(self, data_dir: str, transform=None):
        self.data_dir = Path(data_dir)
        self.image_dir = self.data_dir / "images"
        self.mask_dir  = self.data_dir / "masks"
        
        # Only keep stems where BOTH an image AND a mask exist
        mask_stems = {p.stem for p in self.mask_dir.iterdir() if p.suffix == ".png"}
        self.stems = sorted(
            p.stem
            for p in self.image_dir.iterdir()
            if p.suffix in {".png", ".jpg", ".tif", ".tiff"}
            and p.stem in mask_stems
        )
        
        self.transform = transform
        logger.info(f"Dataset: {len(self.stems)} matched image-mask pairs "
                    f"(from {sum(1 for _ in self.image_dir.iterdir())} images, "
                    f"{len(mask_stems)} masks)")

    def __len__(self):
        return len(self.stems)

    def __getitem__(self, idx):
        import rasterio
        stem = self.stems[idx]
        
        # Find image file
        for ext in [".png", ".jpg", ".tif", ".tiff"]:
            img_path = self.image_dir / f"{stem}{ext}"
            if img_path.exists():
                break

        mask_path = self.mask_dir / f"{stem}.png"
        
        # Use rasterio for TIF, PIL for others
        if img_path.suffix in {".tif", ".tiff"}:
            with rasterio.open(img_path) as src:
                image = src.read()[:3] # first 3 bands -> (3, H, W)
                image = np.transpose(image, (1, 2, 0)) # -> (H, W, 3)
                image = image.astype(np.uint8)
        else:
            image = np.array(Image.open(img_path).convert("RGB"))
            
        mask  = np.array(Image.open(mask_path).convert("L"))
        mask  = (mask > 127).astype(np.float32)

        if self.transform:
            augmented = self.transform(image=image, mask=mask)
            image, mask = augmented["image"], augmented["mask"]

        # Convert to tensors
        if not isinstance(image, torch.Tensor):
            image = torch.from_numpy(image.transpose(2, 0, 1)).float() / 255.0
        if not isinstance(mask, torch.Tensor):
            mask  = torch.from_numpy(mask).float()
            
        # Ensure mask has a channel dimension [1, H, W]
        if mask.ndim == 2:
            mask = mask.unsqueeze(0)

        return image, mask.float()


# ── Loss ──────────────────────────────────────────────────────────────────────

class DiceBCELoss(nn.Module):
    def __init__(self, bce_weight=0.5):
        super().__init__()
        self.bce = nn.BCEWithLogitsLoss()
        self.bce_weight = bce_weight

    def forward(self, logits, targets):
        bce_loss = self.bce(logits, targets)
        prob = torch.sigmoid(logits)
        intersection = (prob * targets).sum()
        dice_loss = 1 - (2 * intersection + 1) / (prob.sum() + targets.sum() + 1)
        return self.bce_weight * bce_loss + (1 - self.bce_weight) * dice_loss


# ── Metrics ───────────────────────────────────────────────────────────────────

def compute_iou(pred_mask, true_mask, threshold=0.5):
    pred = (pred_mask > threshold).float()
    intersection = (pred * true_mask).sum()
    union = pred.sum() + true_mask.sum() - intersection
    return (intersection / (union + 1e-8)).item()


# ── Training loop ─────────────────────────────────────────────────────────────

def train(args):
    device = "cuda" if torch.cuda.is_available() else "cpu"
    logger.info(f"Training on {device}")

    dataset = RoadDataset(args.data_dir, transform=get_train_transforms(args.tile_size))
    val_size = max(1, int(0.15 * len(dataset)))
    train_size = len(dataset) - val_size
    train_ds, val_ds = random_split(dataset, [train_size, val_size])
    val_ds.dataset.transform = get_val_transforms(args.tile_size)

    train_loader = DataLoader(train_ds, batch_size=args.batch_size, shuffle=True, num_workers=0, pin_memory=True)
    val_loader   = DataLoader(val_ds,   batch_size=args.batch_size, shuffle=False, num_workers=0, pin_memory=True)

    model = build_model(variant=args.variant, encoder=args.encoder, weights="imagenet").to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=1e-4)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=args.epochs)
    criterion = DiceBCELoss()

    best_iou = 0.0
    os.makedirs("data/checkpoints", exist_ok=True)

    for epoch in range(1, args.epochs + 1):
        model.train()
        train_loss = 0.0
        for images, masks in train_loader:
            images, masks = images.to(device), masks.to(device)
            optimizer.zero_grad()
            logits = model(images)
            loss = criterion(logits, masks)
            loss.backward()
            optimizer.step()
            train_loss += loss.item()

        # Validation
        model.eval()
        val_iou = 0.0
        with torch.no_grad():
            for images, masks in val_loader:
                images, masks = images.to(device), masks.to(device)
                logits = model(images)
                val_iou += compute_iou(torch.sigmoid(logits), masks)
        val_iou /= len(val_loader)

        scheduler.step()
        avg_loss = train_loss / len(train_loader)
        logger.info(f"Epoch {epoch:03d}/{args.epochs} | loss={avg_loss:.4f} | val_iou={val_iou:.4f}")

        if val_iou > best_iou:
            best_iou = val_iou
            torch.save({"model_state_dict": model.state_dict(), "epoch": epoch, "iou": val_iou},
                       "data/checkpoints/best_model.pth")
            logger.info(f"  ✓ New best checkpoint saved (IoU={best_iou:.4f})")

    logger.info(f"Training complete. Best IoU: {best_iou:.4f}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir",   default="data/spacenet_roads")
    parser.add_argument("--epochs",     type=int,   default=50)
    parser.add_argument("--batch-size", type=int,   default=8)
    parser.add_argument("--lr",         type=float, default=1e-4)
    parser.add_argument("--tile-size",  type=int,   default=512)
    parser.add_argument("--variant",    default="unet")
    parser.add_argument("--encoder",    default="resnet50")
    train(parser.parse_args())
