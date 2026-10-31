#!/usr/bin/env python3
"""Prepare summer-school photos for the gallery and print their HTML.

For each source photo this script
  * applies the EXIF orientation,
  * converts embedded color profiles (e.g. Display P3 from phones) to sRGB,
  * drops all metadata (EXIF incl. GPS location, XMP, ICC),
  * writes static/img/gallery/<year>/<name>.jpg         (long edge 2048 px)
     and static/img/gallery/<year>/thumbs/<name>.jpg  (short edge 600 px),
  * prints one <figure> per photo, ready to paste into pages/photos.html.

Usage (from the repository root):
  python3 tools/add_photos.py --year 2026 --city Princeton \
      [--featured NAME] [--featured NAME] PHOTO [PHOTO ...]

<name> is the lower-cased source file name without extension. Photos marked
with --featured (by <name>) get class "is-featured" and span 2x2 grid cells.
Figures are printed in the order the photos are given.
Requires Pillow (with ImageCms, included in standard Pillow wheels).
"""
import argparse
import html
import io
import re
import sys
from pathlib import Path

from PIL import Image, ImageCms, ImageOps

FULL_LONG_EDGE = 2048
THUMB_SHORT_EDGE = 600
FULL_QUALITY = 82
THUMB_QUALITY = 80
SRGB = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB"))
REPO = Path(__file__).resolve().parent.parent


def load_srgb(path: Path) -> Image.Image:
    im = Image.open(path)
    # Decode JPEGs at a reduced scale when possible (much faster for 45 MP files).
    im.draft("RGB", (FULL_LONG_EDGE, FULL_LONG_EDGE))
    icc = im.info.get("icc_profile")
    im = ImageOps.exif_transpose(im)
    if im.mode not in ("RGB", "L"):
        im = im.convert("RGB")
    if icc:
        src = ImageCms.ImageCmsProfile(io.BytesIO(icc))
        im = ImageCms.profileToProfile(im, src, SRGB, renderingIntent=0, outputMode="RGB")
    return im.convert("RGB")


def resized(im: Image.Image, long_edge=None, short_edge=None) -> Image.Image:
    w, h = im.size
    if long_edge:
        s = long_edge / max(w, h)
    else:
        s = short_edge / min(w, h)
    if s >= 1:
        return im.copy()
    return im.resize((round(w * s), round(h * s)), Image.LANCZOS)


def save(im: Image.Image, path: Path, quality: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # No exif/icc_profile arguments: the output carries no metadata at all.
    im.save(path, "JPEG", quality=quality, optimize=True, progressive=True)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--year", required=True, help="edition year, e.g. 2026")
    ap.add_argument("--city", required=True, help="host city for the caption, e.g. Princeton")
    ap.add_argument("--featured", action="append", default=[], metavar="NAME",
                    help="name of a photo to show as a 2x2 tile (repeatable)")
    ap.add_argument("photos", nargs="+", type=Path)
    args = ap.parse_args()

    out_dir = REPO / "static" / "img" / "gallery" / args.year
    caption = f"ICCP {args.year} Summer School · {args.city}"
    figures = []
    for src in args.photos:
        name = re.sub(r"[^a-z0-9_-]+", "-", src.stem.lower()).strip("-")
        im = load_srgb(src)
        full = resized(im, long_edge=FULL_LONG_EDGE)
        thumb = resized(im, short_edge=THUMB_SHORT_EDGE)
        save(full, out_dir / f"{name}.jpg", FULL_QUALITY)
        save(thumb, out_dir / "thumbs" / f"{name}.jpg", THUMB_QUALITY)
        rel = f"./static/img/gallery/{args.year}"
        cls = "gallery-item is-featured" if name in args.featured else "gallery-item"
        figures.append(
            f'<figure class="{cls}" data-src="{rel}/{name}.jpg" data-caption="{html.escape(caption)}" tabindex="0" onclick="openPhotoModal(this)">\n'
            f'\t<img src="{rel}/thumbs/{name}.jpg" alt="Photo from the {html.escape(caption.replace(" · ", ", "))}" '
            f'width="{thumb.width}" height="{thumb.height}" loading="lazy">\n'
            f"</figure>"
        )
        print(f"{src.name} -> {name}.jpg ({full.width}x{full.height}), thumbs/{name}.jpg ({thumb.width}x{thumb.height})",
              file=sys.stderr)
    missing = set(args.featured) - {re.sub(r"[^a-z0-9_-]+", "-", p.stem.lower()).strip("-") for p in args.photos}
    if missing:
        print(f"warning: --featured names not found: {', '.join(sorted(missing))}", file=sys.stderr)
    print("\n".join(figures))
    return 0


if __name__ == "__main__":
    sys.exit(main())
