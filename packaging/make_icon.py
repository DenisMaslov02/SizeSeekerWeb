"""Draws the SizeSeekerWeb icon (PNG for the web UI/tray, ICO for exe/installer).

Run: python packaging/make_icon.py
"""

from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
SIZE = 512


def draw() -> Image.Image:
    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((16, 16, SIZE - 16, SIZE - 16), radius=110, fill=(37, 99, 235, 255))
    # bar chart (green / cyan / red like the original's thresholds)
    base = 400
    for x, height, color in ((96, 120, (34, 197, 94)), (170, 200, (34, 184, 214)), (244, 280, (240, 82, 82))):
        d.rounded_rectangle((x, base - height, x + 54, base), radius=12, fill=color + (255,))
    # magnifier
    cx, cy, r = 330, 230, 92
    d.ellipse((cx - r, cy - r, cx + r, cy + r), outline=(255, 255, 255, 255), width=30)
    d.line((cx + 62, cy + 62, 440, 440), fill=(255, 255, 255, 255), width=40)
    d.ellipse((440 - 20, 440 - 20, 440 + 20, 440 + 20), fill=(255, 255, 255, 255))
    return img


def main() -> None:
    img = draw()
    img.resize((256, 256), Image.LANCZOS).save(ROOT / "sizeseekerweb" / "static" / "icon.png")
    img.save(ROOT / "packaging" / "icon.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print("icons written")


if __name__ == "__main__":
    main()
