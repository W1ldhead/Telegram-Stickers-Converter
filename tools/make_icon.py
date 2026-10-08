"""Рисует иконку программы: assets/icon.ico (16–256 px) и assets/icon.png."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parent.parent
S = 1024  # рисуем крупно, потом уменьшаем


def main() -> None:
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))

    # Фон: скруглённый квадрат с вертикальным градиентом
    grad = Image.new("RGBA", (S, S))
    top, bottom = (124, 77, 255), (0, 176, 255)
    gd = ImageDraw.Draw(grad)
    for y in range(S):
        t = y / (S - 1)
        gd.line([(0, y), (S, y)], fill=tuple(int(a + (b - a) * t) for a, b in zip(top, bottom)) + (255,))
    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).rounded_rectangle([40, 40, S - 40, S - 40], radius=220, fill=255)
    img.paste(grad, (0, 0), mask)

    # Наклейка: белый квадрат с отогнутым правым нижним углом
    m, r, fold = 230, 120, 230
    x0, y0, x1, y1 = m, m, S - m, S - m
    sticker = Image.new("L", (S, S), 0)
    sd = ImageDraw.Draw(sticker)
    sd.rounded_rectangle([x0, y0, x1, y1], radius=r, fill=255)
    sd.polygon([(x1 - fold, y1 + 10), (x1 + 10, y1 + 10), (x1 + 10, y1 - fold)], fill=0)

    shadow = sticker.filter(ImageFilter.GaussianBlur(28)).point(lambda v: v * 0.35)
    img.paste((20, 10, 60, 255), (0, 24), shadow)
    img.paste((255, 255, 255, 255), (0, 0), sticker)

    d = ImageDraw.Draw(img)
    # Отогнутый уголок
    d.polygon([(x1 - fold, y1), (x1, y1 - fold), (x1 - fold + 30, y1 - fold + 30)], fill=(206, 214, 236, 255))

    # Значок «плей»
    cx, cy, h = S // 2 - 10, S // 2 - 20, 300
    d.polygon([(cx - h * 0.38, cy - h / 2), (cx - h * 0.38, cy + h / 2), (cx + h * 0.5, cy)],
              fill=(124, 77, 255, 255))

    assets = ROOT / "assets"
    assets.mkdir(exist_ok=True)
    big = img.resize((256, 256), Image.LANCZOS)
    big.save(assets / "icon.png")
    big.save(assets / "icon.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print("Готово:", assets / "icon.ico")


if __name__ == "__main__":
    main()
