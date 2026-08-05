"""
AI4Papers OG Image Generator
=============================
Generates a 1200x630 Open Graph / Twitter Card image and saves it to
View/public/og-image.png (or a custom --out path).

Usage
-----
    # First-time generation (from any directory):
    python Sever/scripts/generate_og_image.py

    # Overwrite an existing file:
    python Sever/scripts/generate_og_image.py --force

    # Custom output path:
    python Sever/scripts/generate_og_image.py --out /path/to/og-image.png

Requirements
------------
    Pillow >= 10.4 (already in Sever/requirements.txt)
    Run with the project's virtualenv active.

Notes
-----
    After running, the next `npm run build` inside View/ will copy
    og-image.png from public/ into dist/ automatically.
    To replace with a proper design, just overwrite the file — no code change needed.
"""

from __future__ import annotations

import argparse
import math
import os
import sys
from pathlib import Path
from typing import Optional

from PIL import Image, ImageDraw, ImageFont

# ---------------------------------------------------------------------------
# Layout constants
# ---------------------------------------------------------------------------

W, H = 1200, 630

# Background gradient: top → bottom (dark navy)
BG_TOP = (11, 17, 32)
BG_BOTTOM = (22, 35, 58)

# Accent glow (blue)
ACCENT_COLOR = (59, 130, 246)
ACCENT_ALPHA = 80  # 0–255, used on RGBA layer

# Text colors
WHITE = (255, 255, 255)
LIGHT_GRAY = (180, 195, 220)
DIM_GRAY = (100, 120, 150)
BLUE_TEXT = (96, 165, 250)

# Separator line
SEP_COLOR = (59, 130, 246)
SEP_HEIGHT = 4

# Padding / margins
PAD_X = 80
PAD_Y = 70

# ---------------------------------------------------------------------------
# Font paths (ordered by preference)
# ---------------------------------------------------------------------------

_FONT_CANDIDATES = [
    # Windows – Microsoft YaHei (supports Chinese)
    r"C:/Windows/Fonts/msyhbd.ttc",
    r"C:/Windows/Fonts/msyh.ttc",
    r"C:/Windows/Fonts/simhei.ttf",
    # Linux – Noto CJK
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.otc",
    "/usr/share/fonts/opentype/noto/NotoSansCJKsc-Bold.otf",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/noto-cjk/NotoSansCJKsc-Bold.otf",
    # macOS
    "/System/Library/Fonts/PingFang.ttc",
    "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
]

_cjk_available: Optional[bool] = None  # cached after first _load_font call


def _load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    """Return the best available TrueType font at the given size.

    Sets the module-level ``_cjk_available`` flag on first call so callers
    can decide whether to show Chinese or English text.
    """
    global _cjk_available
    for path in _FONT_CANDIDATES:
        if os.path.isfile(path):
            try:
                font = ImageFont.truetype(path, size)
                if _cjk_available is None:
                    _cjk_available = True
                return font
            except Exception:
                continue
    if _cjk_available is None:
        _cjk_available = False
    return ImageFont.load_default()


# ---------------------------------------------------------------------------
# Drawing helpers
# ---------------------------------------------------------------------------

def _gradient_background(w: int, h: int) -> Image.Image:
    """Create a vertical gradient background image (RGB)."""
    img = Image.new("RGB", (w, h))
    px = img.load()
    for y in range(h):
        t = y / (h - 1)
        r = int(BG_TOP[0] + (BG_BOTTOM[0] - BG_TOP[0]) * t)
        g = int(BG_TOP[1] + (BG_BOTTOM[1] - BG_TOP[1]) * t)
        b = int(BG_TOP[2] + (BG_BOTTOM[2] - BG_TOP[2]) * t)
        for x in range(w):
            px[x, y] = (r, g, b)  # type: ignore[index]
    return img


def _draw_accent_glow(img: Image.Image) -> Image.Image:
    """Paint a soft circular glow in the bottom-right corner."""
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    cx, cy = int(img.width * 0.88), int(img.height * 0.78)
    radius = 320
    for r in range(radius, 0, -4):
        alpha = int(ACCENT_ALPHA * math.exp(-2.5 * (1 - r / radius)))
        draw.ellipse(
            [cx - r, cy - r, cx + r, cy + r],
            fill=(*ACCENT_COLOR, alpha),
        )
    base = img.convert("RGBA")
    merged = Image.alpha_composite(base, overlay)
    return merged.convert("RGB")


def _draw_grid_dots(img: Image.Image) -> Image.Image:
    """Subtle dot grid texture for depth."""
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    spacing = 40
    dot_r = 1
    for y in range(0, img.height, spacing):
        for x in range(0, img.width, spacing):
            draw.ellipse(
                [x - dot_r, y - dot_r, x + dot_r, y + dot_r],
                fill=(255, 255, 255, 18),
            )
    base = img.convert("RGBA")
    merged = Image.alpha_composite(base, overlay)
    return merged.convert("RGB")


def _text_width(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont) -> int:
    bbox = draw.textbbox((0, 0), text, font=font)
    return bbox[2] - bbox[0]


# ---------------------------------------------------------------------------
# Main render
# ---------------------------------------------------------------------------

def render(out_path: Path, force: bool = False) -> None:
    if out_path.exists() and not force:
        print(
            f"[generate_og_image] '{out_path}' already exists. "
            "Pass --force to overwrite.",
            file=sys.stderr,
        )
        sys.exit(1)

    # --- Background ---
    img = _gradient_background(W, H)
    img = _draw_accent_glow(img)
    img = _draw_grid_dots(img)
    draw = ImageDraw.Draw(img)

    # --- Pre-load fonts at various sizes ---
    font_brand = _load_font(88, bold=True)
    font_sub = _load_font(38)
    font_feature = _load_font(30)
    font_domain = _load_font(26)

    use_cn = bool(_cjk_available)

    # --- Brand name ---
    brand = "AI4Papers"
    brand_x, brand_y = PAD_X, PAD_Y
    draw.text((brand_x, brand_y), brand, font=font_brand, fill=WHITE)

    # Measure brand height for separator placement
    brand_bbox = draw.textbbox((brand_x, brand_y), brand, font=font_brand)
    brand_h = brand_bbox[3] - brand_bbox[1]

    sep_y = brand_y + brand_h + 18
    sep_x2 = W - PAD_X
    draw.rectangle([brand_x, sep_y, sep_x2, sep_y + SEP_HEIGHT], fill=SEP_COLOR)

    # --- Tagline ---
    tagline = "免费 AI 论文工作流平台" if use_cn else "Free AI Paper Workflow Platform"
    tagline_y = sep_y + SEP_HEIGHT + 22
    draw.text((brand_x, tagline_y), tagline, font=font_sub, fill=BLUE_TEXT)

    # --- Feature bullets ---
    if use_cn:
        features = [
            "· 每日 arXiv 论文智能推荐 & 中文结构化摘要",
            "· 多论文对比分析 · 跨文献深度研究",
            "· 知识库 · 灵感工作台 · PDF 双语对照阅读",
        ]
    else:
        features = [
            "· Daily arXiv digest with AI scoring & Chinese summaries",
            "· Cross-paper comparison · Deep multi-doc research",
            "· Knowledge base · Inspiration workbench · Bilingual PDF",
        ]

    feat_y = tagline_y + 80
    line_gap = 52
    for feat in features:
        draw.text((brand_x, feat_y), feat, font=font_feature, fill=LIGHT_GRAY)
        feat_y += line_gap

    # --- Bottom-right domain ---
    domain = "ai4papers.com"
    dom_w = _text_width(draw, domain, font_domain)
    draw.text(
        (W - PAD_X - dom_w, H - PAD_Y - 10),
        domain,
        font=font_domain,
        fill=DIM_GRAY,
    )

    # --- Thin top stripe ---
    draw.rectangle([0, 0, W, 3], fill=SEP_COLOR)

    # --- Save ---
    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(str(out_path), format="PNG", optimize=True)

    size_kb = out_path.stat().st_size // 1024
    print(f"[generate_og_image] Saved: {out_path}  ({W}x{H}, {size_kb} KB)")


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def _default_out() -> Path:
    """Resolve repo-relative default output path regardless of cwd."""
    script_dir = Path(__file__).resolve().parent          # Sever/scripts/
    repo_root = script_dir.parent.parent                  # project root
    return repo_root / "View" / "public" / "og-image.png"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate the AI4Papers OG / Twitter Card image (1200×630 PNG)."
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Output path (default: View/public/og-image.png relative to repo root)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite the file if it already exists",
    )
    args = parser.parse_args()

    out = args.out if args.out is not None else _default_out()
    render(out_path=out, force=args.force)


if __name__ == "__main__":
    main()
