#!/usr/bin/env python3
"""Generates the Yatesium logo assets in branding/.

The files mirror paths in the Chromium source tree. build.py copies them over
the Chromium originals. To use your own artwork, replace the files in
branding/ (keep names and pixel sizes) instead of running this script.

Requires Pillow. Usage: make_branding.py [output dir]
"""

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

TOP = (20, 150, 160)
BOTTOM = (22, 72, 110)
WHITE = (255, 255, 255, 255)
SS = 8  # supersampling factor


def mark(size):
    """Rounded square with a vertical gradient and a white Y."""
    n = size * SS
    gradient = Image.new('RGBA', (n, n))
    draw = ImageDraw.Draw(gradient)
    for y in range(n):
        t = y / (n - 1)
        draw.line([(0, y), (n, y)],
                  fill=tuple(round(a + (b - a) * t)
                             for a, b in zip(TOP, BOTTOM)) + (255, ))
    mask = Image.new('L', (n, n), 0)
    pad = n * 0.04
    ImageDraw.Draw(mask).rounded_rectangle(
        [pad, pad, n - pad, n - pad], radius=n * 0.22, fill=255)
    image = Image.new('RGBA', (n, n), (0, 0, 0, 0))
    image.paste(gradient, (0, 0), mask)

    draw = ImageDraw.Draw(image)
    width = round(n * 0.13)
    center = (n * 0.5, n * 0.53)
    for end in ((n * 0.27, n * 0.24), (n * 0.73, n * 0.24), (n * 0.5, n * 0.80)):
        draw.line([end, center], fill=WHITE, width=width)
        r = width / 2
        draw.ellipse([end[0] - r, end[1] - r, end[0] + r, end[1] + r],
                     fill=WHITE)
    r = width / 2
    draw.ellipse([center[0] - r, center[1] - r, center[0] + r, center[1] + r],
                 fill=WHITE)
    return image.resize((size, size), Image.LANCZOS)


def wordmark(width, height, color):
    scale = 4
    image = Image.new('RGBA', (width * scale, height * scale), (0, 0, 0, 0))
    font = None
    for name in ('DejaVuSans.ttf', 'segoeui.ttf', 'arial.ttf'):
        try:
            font = ImageFont.truetype(name, round(height * scale * 0.74))
            break
        except OSError:
            continue
    if font is None:
        sys.exit('No usable TrueType font found for the wordmark.')
    draw = ImageDraw.Draw(image)
    box = draw.textbbox((0, 0), 'Yatesium', font=font)
    x = (image.width - (box[2] - box[0])) / 2 - box[0]
    y = (image.height - (box[3] - box[1])) / 2 - box[1]
    draw.text((x, y), 'Yatesium', font=font, fill=color)
    return image.resize((width, height), Image.LANCZOS)


SVG = '''<svg viewBox="0 0 256 256" xmlns="http://www.w3.org/2000/svg">
<defs><linearGradient id="g" x1="0" y1="0" x2="0" y2="1">
<stop offset="0" stop-color="#1496a0"/><stop offset="1" stop-color="#16486e"/>
</linearGradient></defs>
<rect x="10" y="10" width="236" height="236" rx="56" fill="url(#g)"/>
<path d="M69 61 128 136 187 61M128 136V205" fill="none" stroke="#fff"
 stroke-width="33" stroke-linecap="round" stroke-linejoin="round"/>
</svg>
'''


def main():
    out = Path(sys.argv[1] if len(sys.argv) > 1 else
               Path(__file__).resolve().parent.parent / 'branding')
    theme = out / 'chrome' / 'app' / 'theme'
    pngs = {
        'chromium/product_logo_16.png': 16,
        'chromium/product_logo_24.png': 24,
        'chromium/product_logo_48.png': 48,
        'chromium/product_logo_64.png': 64,
        'chromium/product_logo_128.png': 128,
        'chromium/product_logo_256.png': 256,
        'chromium/win/tiles/Logo.png': 600,
        'chromium/win/tiles/SmallLogo.png': 176,
        'default_100_percent/chromium/product_logo_16.png': 16,
        'default_100_percent/chromium/product_logo_32.png': 32,
        'default_200_percent/chromium/product_logo_16.png': 32,
        'default_200_percent/chromium/product_logo_32.png': 64,
    }
    for rel, size in pngs.items():
        path = theme / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        mark(size).save(path)

    ico = theme / 'chromium' / 'win' / 'chromium.ico'
    sizes = (16, 24, 32, 48, 64, 256)
    frames = [mark(s) for s in sizes]
    frames[-1].save(ico, format='ICO', sizes=[(s, s) for s in sizes],
                    append_images=frames[:-1])

    (theme / 'chromium' / 'product_logo.svg').write_text(SVG, encoding='utf-8',
                                                         newline='\n')

    for scale, folder in ((1, 'default_100_percent'), (2, 'default_200_percent')):
        base = theme / folder / 'chromium'
        wordmark(97 * scale, 22 * scale,
                 (95, 99, 104, 255)).save(base / 'product_logo_name_22.png')
        wordmark(97 * scale, 22 * scale,
                 WHITE).save(base / 'product_logo_name_22_white.png')
    print('Wrote branding assets to', out)


if __name__ == '__main__':
    main()
