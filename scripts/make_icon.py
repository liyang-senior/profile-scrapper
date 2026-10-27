"""Convert project-root icon.png into a multi-size Windows .ico for PyInstaller.

icon.png may be RGB with a white/gray studio background — that background is
removed so only the logo remains on a transparent canvas.
"""
from collections import deque
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
PNG = ROOT / "icon.png"
ICO = ROOT / "assets" / "icon.ico"
SIZES = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]


def _is_background(r: int, g: int, b: int) -> bool:
    """True for white / light-gray backdrop (not cyan/blue logo pixels)."""
    mx = max(r, g, b)
    mn = min(r, g, b)
    # Bright and nearly colorless (= gray/white), not saturated logo colors.
    return mx >= 185 and (mx - mn) <= 30


def _remove_background(img: Image.Image) -> Image.Image:
    """Flood-fill white/gray background from the corners → transparent."""
    img = img.convert("RGBA")
    w, h = img.size
    px = img.load()

    visited = [[False] * w for _ in range(h)]
    q: deque = deque()
    for x, y in ((0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1)):
        q.append((x, y))

    while q:
        x, y = q.popleft()
        if x < 0 or y < 0 or x >= w or y >= h or visited[y][x]:
            continue
        r, g, b, a = px[x, y]
        if not _is_background(r, g, b):
            continue
        visited[y][x] = True
        px[x, y] = (0, 0, 0, 0)
        q.append((x + 1, y))
        q.append((x - 1, y))
        q.append((x, y + 1))
        q.append((x, y - 1))

    # Soften anti-aliased fringe still stuck to the removed background.
    for y in range(h):
        for x in range(w):
            r, g, b, a = px[x, y]
            if a == 0:
                continue
            if _is_background(r, g, b):
                # Isolated leftover backdrop inside/around logo.
                px[x, y] = (0, 0, 0, 0)
                continue
            # Fade near-white fringe pixels that touch logo edges.
            mx = max(r, g, b)
            mn = min(r, g, b)
            if mx >= 200 and (mx - mn) <= 40:
                fade = max(0, min(255, int(255 * (1 - (mx - 200) / 55.0))))
                if fade < 40:
                    px[x, y] = (0, 0, 0, 0)
                else:
                    px[x, y] = (r, g, b, fade)

    return img


def _square_rgba(img: Image.Image) -> Image.Image:
    """Center the image on a transparent square canvas."""
    img = img.convert("RGBA")
    side = max(img.size)
    canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    canvas.paste(img, ((side - img.width) // 2, (side - img.height) // 2), img)
    return canvas


def main() -> None:
    if not PNG.exists():
        raise SystemExit(f"Missing {PNG} — copy icon.png into the project folder.")

    cleaned = _remove_background(Image.open(PNG))
    master = _square_rgba(cleaned).resize((256, 256), Image.Resampling.LANCZOS)

    images = [master.resize((w, h), Image.Resampling.LANCZOS) for w, h in SIZES]

    ICO.parent.mkdir(parents=True, exist_ok=True)
    try:
        images[-1].save(
            ICO,
            format="ICO",
            sizes=SIZES,
            append_images=images[:-1],
            bitmap_format="png",
        )
    except TypeError:
        images[-1].save(ICO, format="ICO", sizes=SIZES, append_images=images[:-1])

    check = images[-1]
    transparent = sum(1 for (_r, _g, _b, a) in check.getdata() if a == 0)
    total = check.width * check.height
    print(
        f"Wrote {ICO} from {PNG.name} "
        f"(transparent {transparent}/{total} pixels, {100 * transparent // total}%)"
    )


if __name__ == "__main__":
    main()
