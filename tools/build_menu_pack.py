"""Собирает брендовый ресурспак BritonLauncher.

Запуск: python tools/build_menu_pack.py
Результат: assets/BritonMenu.zip

Нужен Pillow (pip install pillow). В сборку лаунчера уже кладётся готовый zip.
"""

from __future__ import annotations

import io
import json
import math
import os
import random
import zipfile

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

try:
    import numpy as np
except Exception:  # pragma: no cover
    np = None

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_ZIP = os.path.join(ROOT, "assets", "BritonMenu.zip")

SIZE = 512
GLOW = (150, 22, 44)
TOP = (8, 3, 11)
BOTTOM = (30, 6, 16)

FONT_CANDIDATES = [
    r"C:\Windows\Fonts\impact.ttf",
    r"C:\Windows\Fonts\bahnschrift.ttf",
    r"C:\Windows\Fonts\arialbd.ttf",
    r"C:\Windows\Fonts\segoeuib.ttf",
]

SPLASHES = [
    "BritonLauncher!",
    "Сайт внутри!",
    "Красное море!",
    "100% стиль!",
    "Модов не мерено!",
    "Fabric внутри!",
    "Играй с друзьями!",
    "Сделано с любовью!",
    "Костя одобряет!",
    "Офлайн — тоже игра!",
    "Нажми «Играть»!",
    "Больше RAM!",
    "Привет с сайта!",
    "Тема Red Sea!",
    "Скины, моды, шейдеры!",
    "Не забудь про RAM!",
    "Лаунчер мечты!",
    "Без лишних кнопок!",
    "Твой ник в углу!",
    "Код с сайта!",
    "Обновляйся вовремя!",
    "Шейдеры включай!",
    "Тут красиво!",
    "Проверь моды!",
    "Собери сборку!",
    "Пиксели в порядке!",
    "Ещё один блок!",
    "Крипер не пройдёт!",
    "Британский стиль!",
    "Всё будет огонь!",
]


def _font(size: int) -> ImageFont.FreeTypeFont:
    for path in FONT_CANDIDATES:
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def _vertical_gradient() -> Image.Image:
    if np is not None:
        t = np.linspace(0.0, 1.0, SIZE, dtype=np.float32)[:, None]
        top = np.array(TOP, dtype=np.float32)
        bottom = np.array(BOTTOM, dtype=np.float32)
        arr = top[None, None, :] + (bottom - top)[None, None, :] * t[:, :, None]
        arr = np.repeat(arr, SIZE, axis=1)
        return Image.fromarray(arr.clip(0, 255).astype("uint8"), "RGB")

    img = Image.new("RGB", (SIZE, SIZE))
    px = img.load()
    for y in range(SIZE):
        t = y / (SIZE - 1)
        col = tuple(int(TOP[i] + (BOTTOM[i] - TOP[i]) * t) for i in range(3))
        for x in range(SIZE):
            px[x, y] = col
    return img


def _cube(draw: ImageDraw.ImageDraw, cx: float, cy: float, s: float) -> None:
    """Рисует тёмный изометрический блок с подсветкой граней."""
    h = s * 0.5
    w = s * 0.87
    top = [(cx, cy - s), (cx + w, cy - h), (cx, cy), (cx - w, cy - h)]
    left = [(cx - w, cy - h), (cx, cy), (cx, cy + h), (cx - w, cy + h - 1)]
    right = [(cx + w, cy - h), (cx, cy), (cx, cy + h), (cx + w, cy + h - 1)]
    draw.polygon(top, fill=(44, 10, 18, 210), outline=(220, 55, 70, 90))
    draw.polygon(left, fill=(24, 5, 11, 220), outline=(200, 40, 55, 70))
    draw.polygon(right, fill=(34, 7, 14, 220), outline=(220, 55, 70, 70))


def _panorama(seed: int, gx: float, gy: float, strength: float = 1.0) -> Image.Image:
    rnd = random.Random(seed)
    base = _vertical_gradient().convert("RGB")

    if np is not None:
        yy, xx = np.mgrid[0:SIZE, 0:SIZE].astype(np.float32)
        dx = (xx - gx * SIZE) / SIZE
        dy = (yy - gy * SIZE) / SIZE
        dist = np.sqrt(dx * dx + dy * dy)
        glow = np.exp(-((dist * 3.1) ** 2)) * strength
        glow2 = np.exp(-((dist * 6.6) ** 2)) * 0.45 * strength
        add = (glow + glow2)[:, :, None] * np.array(GLOW, dtype=np.float32)
        arr = np.asarray(base, dtype=np.float32) + add
        base = Image.fromarray(arr.clip(0, 255).astype("uint8"), "RGB")

    layer = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)

    # Туман у горизонта.
    horizon = int(SIZE * rnd.uniform(0.66, 0.74))
    for i in range(70):
        y = horizon - 45 + i
        alpha = int(46 * (1 - abs(i - 35) / 35))
        draw.line((0, y, SIZE, y), fill=(170, 35, 55, max(0, alpha)))

    # Дальние горы.
    far = [(0, SIZE)]
    x = 0
    while x < SIZE:
        x += rnd.randint(26, 62)
        far.append((x, horizon - rnd.randint(0, 52)))
    far += [(SIZE, SIZE)]
    draw.polygon(far, fill=(13, 4, 10, 245))

    # Ближние горы.
    near = [(0, SIZE)]
    x = 0
    while x < SIZE:
        x += rnd.randint(34, 90)
        near.append((x, horizon + rnd.randint(8, 34) - rnd.randint(0, 22)))
    near += [(SIZE, SIZE)]
    draw.polygon(near, fill=(7, 2, 6, 255))

    # Парящие блоки над горизонтом.
    for _ in range(rnd.randint(4, 7)):
        cx = rnd.uniform(0.08, 0.92) * SIZE
        cy = rnd.uniform(0.12, horizon / SIZE - 0.10) * SIZE
        _cube(draw, cx, cy, rnd.uniform(9, 22))

    layer = layer.filter(ImageFilter.GaussianBlur(0.7))
    base = Image.alpha_composite(base.convert("RGBA"), layer).convert("RGB")

    # Диагональные «осколки» — низкая прозрачность, края остаются тёмными.
    shards = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    sdraw = ImageDraw.Draw(shards)
    for _ in range(3):
        cx = rnd.uniform(0.2, 0.8) * SIZE
        cy = rnd.uniform(0.15, 0.5) * SIZE
        width = rnd.uniform(0.25, 0.55) * SIZE
        height = rnd.uniform(0.03, 0.08) * SIZE
        angle = rnd.uniform(-0.6, 0.6)
        points = []
        for px, py in ((-width / 2, -height / 2), (width / 2, -height / 2), (width / 2, height / 2), (-width / 2, height / 2)):
            rx = px * math.cos(angle) - py * math.sin(angle)
            ry = px * math.sin(angle) + py * math.cos(angle)
            points.append((cx + rx, cy + ry))
        sdraw.polygon(points, fill=(220, 40, 60, rnd.randint(10, 22)))

    shards = shards.filter(ImageFilter.GaussianBlur(8))
    base = Image.alpha_composite(base.convert("RGBA"), shards).convert("RGB")

    # Звёзды.
    stars = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    st = ImageDraw.Draw(stars)
    for _ in range(110):
        x = rnd.randint(0, SIZE - 1)
        y = rnd.randint(0, max(1, int(horizon * 0.92)))
        if rnd.random() < 0.55 and abs(x - gx * SIZE) < SIZE * 0.28 and abs(y - gy * SIZE) < SIZE * 0.28:
            continue
        r = rnd.choice((1, 1, 1, 2))
        a = rnd.randint(40, 130)
        st.ellipse((x, y, x + r, y + r), fill=(255, 220, 225, a))
    base = Image.alpha_composite(base.convert("RGBA"), stars).convert("RGB")

    # Мягкий шум, чтобы градиент не был «пластиковым».
    if np is not None:
        noise = np.random.default_rng(seed).normal(0, 3.2, (SIZE, SIZE, 1))
        arr = np.asarray(base, dtype=np.float32) + noise
        base = Image.fromarray(arr.clip(0, 255).astype("uint8"), "RGB")

    # Виньетка по краям: стыки кубов остаются тёмными и незаметными.
    if np is not None:
        yy, xx = np.mgrid[0:SIZE, 0:SIZE].astype(np.float32)
        edge = np.minimum(np.minimum(xx, SIZE - 1 - xx), np.minimum(yy, SIZE - 1 - yy)) / (SIZE * 0.20)
        edge = np.clip(edge, 0.0, 1.0)
        mult = 0.50 + 0.50 * edge
        arr = np.asarray(base, dtype=np.float32) * mult[:, :, None]
        base = Image.fromarray(arr.clip(0, 255).astype("uint8"), "RGB")

    return base

    # Мягкий шум, чтобы градиент не был «пластиковым».
    if np is not None:
        noise = np.random.default_rng(seed).normal(0, 3.2, (SIZE, SIZE, 1))
        arr = np.asarray(base, dtype=np.float32) + noise
        base = Image.fromarray(arr.clip(0, 255).astype("uint8"), "RGB")

    # Виньетка по краям: стыки кубов остаются тёмными и незаметными.
    if np is not None:
        yy, xx = np.mgrid[0:SIZE, 0:SIZE].astype(np.float32)
        edge = np.minimum(np.minimum(xx, SIZE - 1 - xx), np.minimum(yy, SIZE - 1 - yy)) / (SIZE * 0.20)
        edge = np.clip(edge, 0.0, 1.0)
        mult = 0.50 + 0.50 * edge
        arr = np.asarray(base, dtype=np.float32) * mult[:, :, None]
        base = Image.fromarray(arr.clip(0, 255).astype("uint8"), "RGB")

    return base


def _logo() -> Image.Image:
    img = Image.new("RGBA", (1024, 256), (0, 0, 0, 0))
    font = _font(170)
    text = "BRITON"
    draw = ImageDraw.Draw(img)

    widths = []
    for ch in text:
        bbox = draw.textbbox((0, 0), ch, font=font)
        widths.append(bbox[2] - bbox[0])
    total = sum(widths)
    target = 982
    spacing = (target - total) / (len(text) - 1) if len(text) > 1 else 0

    bbox = draw.textbbox((0, 0), text, font=font)
    text_h = bbox[3] - bbox[1]
    top = max(2, int((128 - text_h) / 2) - bbox[1])

    x = (1024 - target) / 2
    for ch, w in zip(text, widths):
        draw.text((x, top), ch, font=font, fill=(255, 255, 255, 255), stroke_width=3, stroke_fill=(255, 255, 255, 255))
        x += w + spacing

    mask = img.getchannel("A")

    shadow = Image.new("RGBA", img.size, (0, 0, 0, 0))
    sdraw = ImageDraw.Draw(shadow)
    sdraw.bitmap((0, 7), mask, fill=(70, 4, 14, 210))
    shadow = shadow.filter(ImageFilter.GaussianBlur(8))

    grad = Image.new("RGBA", img.size, (0, 0, 0, 0))
    for row in range(256):
        t = row / 255
        r = int(255 - 8 * t)
        g = int(248 - 40 * t)
        b = int(250 - 46 * t)
        for col in range(1024):
            grad.putpixel((col, row), (r, g, b, 255))
    text_layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    text_layer.paste(grad, (0, 0), mask)

    out = Image.new("RGBA", img.size, (0, 0, 0, 0))
    out = Image.alpha_composite(out, shadow)
    out = Image.alpha_composite(out, text_layer)
    return out


def _edition() -> Image.Image:
    img = Image.new("RGBA", (512, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    font = _font(33)
    text = "LAUNCHER EDITION"
    spacing = 5
    widths = [draw.textlength(ch, font=font) for ch in text]
    total = sum(widths) + spacing * (len(text) - 1)
    x = (512 - total) / 2
    for ch, w in zip(text, widths):
        draw.text((x, 14), ch, font=font, fill=(235, 60, 70, 255))
        x += w + spacing
    return img


def _icon() -> Image.Image:
    img = Image.new("RGBA", (128, 128), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle((2, 2, 126, 126), radius=26, fill=(18, 6, 12, 255), outline=(225, 29, 46, 255), width=5)
    font = _font(92)
    bbox = draw.textbbox((0, 0), "B", font=font)
    x = (128 - (bbox[2] - bbox[0])) // 2 - bbox[0]
    y = (128 - (bbox[3] - bbox[1])) // 2 - bbox[1] - 4
    draw.text((x, y), "B", font=font, fill=(255, 255, 255, 255))
    return img


def _png_bytes(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def build() -> str:
    os.makedirs(os.path.dirname(OUT_ZIP), exist_ok=True)
    meta = {
        "pack": {
            "pack_format": 15,
            "supported_formats": [15, 99],
            "min_format": [15, 0],
            "max_format": 99,
            "description": "§cBritonLauncher§r — кастомное меню",
        }
    }

    glow_positions = [
        (0.50, 0.52, 1.00),
        (0.72, 0.48, 0.85),
        (0.50, 0.50, 0.95),
        (0.28, 0.50, 0.85),
        (0.50, 0.34, 0.75),
        (0.50, 0.68, 0.75),
    ]

    logo = _logo()
    edition = _edition()

    with zipfile.ZipFile(OUT_ZIP, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        z.writestr("pack.mcmeta", json.dumps(meta, ensure_ascii=False, indent=2))
        z.writestr("pack.png", _png_bytes(_icon()))
        z.writestr("assets/minecraft/textures/gui/title/minecraft.png", _png_bytes(logo))
        z.writestr("assets/minecraft/textures/gui/title/minceraft.png", _png_bytes(logo))
        z.writestr("assets/minecraft/textures/gui/title/edition.png", _png_bytes(edition))
        z.writestr("assets/minecraft/texts/splashes.txt", "\n".join(SPLASHES) + "\n")
        for i, (gx, gy, strength) in enumerate(glow_positions):
            img = _panorama(1000 + i, gx, gy, strength)
            z.writestr(f"assets/minecraft/textures/gui/title/background/panorama_{i}.png", _png_bytes(img))

    return OUT_ZIP


if __name__ == "__main__":
    path = build()
    print("built", path, os.path.getsize(path), "bytes")
