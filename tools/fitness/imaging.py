"""Deterministic post-processing of generated character images.

* Near-black becomes exactly #000 so the image edge disappears on the canvas.
* Everything is reduced to grayscale ink, except each character's signature item
  (e.g. blue shorts), re-tinted to its exact hex with the original shading.
* Red tendon glows are not baked in; scenes draw them as a separate layer.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from .common import TEMPLATES


PROCESS_VERSION = 2
BLACK_POINT, WHITE_POINT = 0.085, 0.97


def rgb(hex_colour: str) -> np.ndarray:
    value = hex_colour.lstrip("#")
    return np.array([int(value[i:i + 2], 16) for i in (0, 2, 4)], dtype=np.float32) / 255


def _hue(a: np.ndarray, mx: np.ndarray, delta: np.ndarray) -> np.ndarray:
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    safe = np.maximum(delta, 1e-6)
    hue = np.where(mx == r, ((g - b) / safe) % 6, np.where(mx == g, (b - r) / safe + 2, (r - g) / safe + 4))
    return hue * 60


def signature_mask(a: np.ndarray, hex_colour: str, window: float = 26) -> np.ndarray:
    """Soft mask of saturated pixels whose hue is near the signature colour (wraps at red)."""
    mx, mn = a.max(-1), a.min(-1)
    delta = mx - mn
    sat = np.where(mx > 0, delta / np.maximum(mx, 1e-6), 0)
    target = rgb(hex_colour)[None, None, :]
    t_mx, t_mn = target.max(-1), target.min(-1)
    target_hue = float(_hue(target, t_mx, t_mx - t_mn)[0, 0])
    distance = np.abs((_hue(a, mx, delta) - target_hue + 180) % 360 - 180)
    raw = (distance <= window) & (sat > 0.45) & (mx > 0.25)
    image = Image.fromarray((raw * 255).astype(np.uint8)).filter(ImageFilter.MedianFilter(5)).filter(ImageFilter.MaxFilter(3))
    return np.asarray(image.filter(ImageFilter.GaussianBlur(1.1))).astype(np.float32) / 255


def process(raw: Path, output: Path, signature_hexes: list[str]) -> dict:
    """Grayscale ink on pure black; each signature colour region re-tinted to its exact hex."""
    a = np.asarray(Image.open(raw).convert("RGB")).astype(np.float32) / 255
    luminance = a[..., 0] * 0.299 + a[..., 1] * 0.587 + a[..., 2] * 0.114
    ink = np.clip((luminance - BLACK_POINT) / (WHITE_POINT - BLACK_POINT), 0, 1)
    ink = np.where(ink < 0.025, 0, ink)
    result = np.repeat(ink[..., None], 3, axis=-1)
    fractions, warnings = {}, []
    for hex_colour in signature_hexes:
        mask = signature_mask(a, hex_colour)
        hard = mask > 0.5
        reference = np.percentile(luminance[hard], 92) if hard.sum() > 50 else 1.0
        shade = np.clip(luminance / max(reference, 1e-3), 0, 1) ** 0.85
        tinted = rgb(hex_colour)[None, None, :] * shade[..., None]
        result = result * (1 - mask[..., None]) + tinted * mask[..., None]
        fractions[hex_colour] = round(float(hard.mean()), 4)
        if hard.mean() < 0.002:
            warnings.append(f"signature colour {hex_colour} not detected; check the image or regenerate")
    result = np.where(luminance[..., None] < BLACK_POINT * 0.6, 0, result)
    output.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray((np.clip(result, 0, 1) * 255).round().astype(np.uint8)).save(output, optimize=True)
    border = np.concatenate([luminance[:8].ravel(), luminance[-8:].ravel(), luminance[:, :8].ravel(), luminance[:, -8:].ravel()])
    if border.mean() > 0.06:
        warnings.append("raw background is not near-black at the edges; check for a visible frame")
    height, width = luminance.shape
    return {"width": width, "height": height, "signature_fraction": fractions, "warnings": warnings}


def _font(size: int):
    try:
        font = ImageFont.truetype(str(TEMPLATES / "fonts/Montserrat-Variable.ttf"), size)
        try:
            font.set_variation_by_axes([800])
        except (OSError, AttributeError):
            pass
        return font
    except OSError:
        return ImageFont.load_default()


def contact_sheet(items: list[tuple[str, Path, list[dict]]], output: Path, palette: dict, thumb_height: int = 640,
                  grid: bool = False, columns: int = 4) -> Path:
    """Grid of images with labels, optional normalized tendon ellipses and a 10% coordinate grid."""
    thumbs = []
    for label, path, tendons in items:
        image = Image.open(path).convert("RGB")
        scale = thumb_height / image.height
        image = image.resize((max(1, round(image.width * scale)), thumb_height), Image.LANCZOS)
        draw = ImageDraw.Draw(image)
        if grid:  # lines every 0.1 so layout.json fractions can be read off directly
            small = _font(14)
            for step in range(1, 10):
                x, y = step * image.width / 10, step * image.height / 10
                draw.line([(x, 0), (x, image.height)], fill=(200, 40, 40), width=1)
                draw.line([(0, y), (image.width, y)], fill=(200, 40, 40), width=1)
                draw.text((x + 2, 2), f".{step}", fill=(255, 90, 90), font=small)
                draw.text((2, y + 2), f".{step}", fill=(255, 90, 90), font=small)
        for tendon in tendons:
            cx, cy = tendon["x"] * image.width, tendon["y"] * image.height
            rx = tendon.get("rx") or tendon.get("r", 0.04)
            ry = tendon.get("ry") or rx
            draw.ellipse([cx - rx * image.width, cy - ry * image.width, cx + rx * image.width, cy + ry * image.width],
                         outline=palette["highlight"], width=4)
        thumbs.append((label, image))
    columns = min(columns, len(thumbs)) or 1
    rows = (len(thumbs) + columns - 1) // columns
    cell_w = max(t.width for _, t in thumbs) + 24
    cell_h = thumb_height + 70
    sheet = Image.new("RGB", (columns * cell_w, rows * cell_h), (24, 24, 24))
    draw = ImageDraw.Draw(sheet)
    font = _font(30)
    for index, (label, thumb) in enumerate(thumbs):
        x, y = (index % columns) * cell_w + 12, (index // columns) * cell_h + 12
        sheet.paste(thumb, (x, y))
        draw.text((x, y + thumb_height + 12), label, fill=(255, 255, 255), font=font)
    output.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output)
    return output
