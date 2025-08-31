#!/usr/bin/env python3
"""
Create a small animated GIF for upload testing.

Outputs: scripts/test_anim.gif
"""
from __future__ import annotations

from PIL import Image, ImageDraw
from pathlib import Path


def create_gif(path: Path):
    frames = []
    size = (120, 120)
    colors = [(255,0,0), (0,255,0), (0,128,255), (255,165,0)]
    for i, color in enumerate(colors):
        img = Image.new('RGB', size, color)
        d = ImageDraw.Draw(img)
        d.rectangle([10+i*5, 10, 60+i*5, 60], outline=(255,255,255), width=3)
        d.text((15, 80), f"Frame {i+1}", fill=(255,255,255))
        frames.append(img)
    frames[0].save(
        path,
        save_all=True,
        append_images=frames[1:],
        duration=300,
        loop=0,
        optimize=True,
        disposal=2,
    )


if __name__ == '__main__':
    out = Path(__file__).resolve().parent / 'test_anim.gif'
    create_gif(out)
    print("Created:", out)

