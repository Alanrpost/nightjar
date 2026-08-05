"""Generate app icon (ICO + PNG preview) — bind rune Gebo+Ansuz on black circle.

Reference: Gebo X crossed diagonals, Ansuz branches emerge from the upper-right
arm of the X going to the right (sharing that arm as the Ansuz staff).
"""

from pathlib import Path

from PIL import Image, ImageDraw

ASSETS = Path(__file__).parent / "app" / "assets"
SIZES = [16, 24, 32, 40, 48, 64, 96, 128, 256]

SS = 8  # supersampling


def draw_icon(size: int) -> Image.Image:
    S = size * SS
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    c = S / 2
    r = S * 0.46
    d.ellipse([c - r, c - r, c + r, c + r], fill="#111111")

    sw = max(SS * 2, int(S * 0.048))

    def pt(x: float, y: float):
        return (x * S, y * S)

    def line(x0, y0, x1, y1):
        d.line([pt(x0, y0), pt(x1, y1)], fill="white", width=sw)
        cap_r = sw // 2
        for px, py in [pt(x0, y0), pt(x1, y1)]:
            d.ellipse([px - cap_r, py - cap_r, px + cap_r, py + cap_r], fill="white")

    import math

    # ── Gebo ᚷ — X ───────────────────────────────────────────────────────────
    # Arm A: bottom-left → top-right  (also serves as Ansuz staff)
    ax0, ay0 = 0.18, 0.84
    ax1, ay1 = 0.84, 0.18
    line(ax0, ay0, ax1, ay1)

    # Arm B: top-left → bottom-right
    line(0.18, 0.18, 0.84, 0.84)

    # ── Ansuz ᚨ — two branches from Arm A going upper-right ──────────────────
    # 32° above horizontal, end points reach close to circle edge
    angle_deg = 32
    branch_len = 0.22
    bx = math.cos(math.radians(angle_deg)) * branch_len
    by = math.sin(math.radians(angle_deg)) * branch_len

    # Upper branch: 72% along Arm A (high on upper-right arm)
    t1 = 0.72
    p1x = ax0 + t1 * (ax1 - ax0)
    p1y = ay0 + t1 * (ay1 - ay0)
    line(p1x, p1y, p1x + bx, p1y - by)

    # Lower branch: 47% along Arm A (near the X crossing)
    t2 = 0.47
    p2x = ax0 + t2 * (ax1 - ax0)
    p2y = ay0 + t2 * (ay1 - ay0)
    line(p2x, p2y, p2x + bx, p2y - by)

    return img.resize((size, size), Image.LANCZOS)


def main():
    ASSETS.mkdir(parents=True, exist_ok=True)

    images = {s: draw_icon(s) for s in SIZES}

    ico_path = ASSETS / "icon.ico"
    images[SIZES[0]].save(
        ico_path,
        format="ICO",
        sizes=[(s, s) for s in SIZES],
        append_images=[images[s] for s in SIZES[1:]],
    )
    print(f"Saved {ico_path}")

    for size in [256, 48, 32, 16]:
        png_path = ASSETS / f"icon_{size}.png"
        images[size].save(png_path, format="PNG")
        print(f"Saved {png_path}")


if __name__ == "__main__":
    main()
