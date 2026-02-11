#!/usr/bin/env python3
"""Generate simple placeholder PNG icons for the Chrome extension.

Run: python scripts/generate_icons.py
Requires: pip install Pillow  (optional – falls back to raw PNG creation)
"""

from pathlib import Path
import struct
import zlib

ICONS_DIR = Path(__file__).resolve().parent.parent / "extension" / "icons"
SIZES = [16, 48, 128]

# Colours (RGBA)
BG = (99, 102, 241, 255)       # indigo-500
CHECK = (255, 255, 255, 255)   # white


def create_minimal_png(size: int) -> bytes:
    """Create a minimal solid-colour PNG (no Pillow needed)."""
    # IHDR
    width = size
    height = size
    bit_depth = 8
    colour_type = 2  # RGB

    def make_chunk(chunk_type: bytes, data: bytes) -> bytes:
        chunk = chunk_type + data
        crc = struct.pack(">I", zlib.crc32(chunk) & 0xFFFFFFFF)
        return struct.pack(">I", len(data)) + chunk + crc

    ihdr_data = struct.pack(">IIBBBBB", width, height, bit_depth, colour_type, 0, 0, 0)
    ihdr = make_chunk(b"IHDR", ihdr_data)

    # IDAT – raw image data (filter=0 per row)
    raw_rows = b""
    for _ in range(height):
        raw_rows += b"\x00"  # filter byte
        for _ in range(width):
            raw_rows += bytes(BG[:3])
    compressed = zlib.compress(raw_rows)
    idat = make_chunk(b"IDAT", compressed)

    iend = make_chunk(b"IEND", b"")

    return b"\x89PNG\r\n\x1a\n" + ihdr + idat + iend


def main():
    ICONS_DIR.mkdir(parents=True, exist_ok=True)

    try:
        from PIL import Image, ImageDraw

        for size in SIZES:
            img = Image.new("RGBA", (size, size), BG)
            draw = ImageDraw.Draw(img)
            # Draw a simple checkmark
            cx, cy = size // 2, size // 2
            r = size // 3
            draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=BG)
            # checkmark lines
            lw = max(1, size // 10)
            draw.line(
                [(cx - r // 2, cy), (cx - r // 6, cy + r // 3), (cx + r // 2, cy - r // 3)],
                fill=CHECK,
                width=lw,
            )
            path = ICONS_DIR / f"icon{size}.png"
            img.save(path)
            print(f"Created {path}")
    except ImportError:
        print("Pillow not available – creating solid-colour placeholders")
        for size in SIZES:
            path = ICONS_DIR / f"icon{size}.png"
            path.write_bytes(create_minimal_png(size))
            print(f"Created {path}")


if __name__ == "__main__":
    main()
