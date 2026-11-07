#!/usr/bin/env python3
"""画挂件自己的形象（原创，MIT）。

跑：python tools/make_assets.py
产出：
  assets/whale.png   512×512 透明底，圆角构图，桌面上直接用
  assets/dot.png      96×96  极简模式的圆点

不依赖任何第三方素材，纯 PIL 几何绘制，放大 4 倍再降采样做抗锯齿。
"""

import os

from PIL import Image, ImageDraw, ImageFilter

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(HERE, "assets")

S = 512
K = 4  # 超采样倍数
W = S * K

BODY_TOP = (42, 143, 208)
BODY_BOTTOM = (23, 96, 152)
BELLY = (222, 237, 247)
FIN = (30, 114, 170)
EYE = (12, 32, 48)
SPOUT = (198, 228, 244)


def lerp(a, b, t):
    return tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(3))


def gradient(size, top, bottom):
    img = Image.new("RGBA", (size, size))
    d = ImageDraw.Draw(img)
    for y in range(size):
        d.line([(0, y), (size, y)], fill=lerp(top, bottom, y / max(1, size - 1)) + (255,))
    return img


def rounded_mask(size, radius):
    m = Image.new("L", (size, size), 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, size - 1, size - 1], radius=radius, fill=255)
    return m


def _rot_ellipse(cx, cy, rx, ry, deg, fill=(255, 255, 255, 255)):
    """在 W×W 的画布上画一个绕中心旋转的椭圆（单独一层再转，边缘才顺）。"""
    size = int(max(rx, ry) * 2.6)
    layer = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    ImageDraw.Draw(layer).ellipse(
        [size / 2 - rx, size / 2 - ry, size / 2 + rx, size / 2 + ry], fill=fill
    )
    layer = layer.rotate(deg, resample=Image.BICUBIC, expand=False)
    out = Image.new("RGBA", (W, W), (0, 0, 0, 0))
    out.paste(layer, (int(cx - size / 2), int(cy - size / 2)), layer)
    return out


def whale():
    img = Image.new("RGBA", (W, W), (0, 0, 0, 0))
    mask = Image.new("L", (W, W), 0)
    ImageDraw.Draw(mask).ellipse(
        [int(W * 0.12), int(W * 0.25), int(W * 0.70), int(W * 0.75)], fill=255
    )

    # 尾巴：一个连着的燕尾（两片三角，根部贴着身体）
    tail = Image.new("L", (W, W), 0)
    td = ImageDraw.Draw(tail)
    td.polygon([
        (int(W * 0.655), int(W * 0.470)),
        (int(W * 0.900), int(W * 0.300)),
        (int(W * 0.808), int(W * 0.500)),
        (int(W * 0.905), int(W * 0.700)),
        (int(W * 0.655), int(W * 0.548)),
    ], fill=255)
    td.ellipse([int(W * (0.808 - 0.020)), int(W * (0.500 - 0.020)),
                int(W * (0.808 + 0.020)), int(W * (0.500 + 0.020))], fill=255)
    _np = __import__("numpy")
    mask = Image.fromarray(_np.maximum(_np.array(mask), _np.array(tail)))

    img.paste(gradient(W, BODY_TOP, BODY_BOTTOM), (0, 0), mask)

    # 肚皮
    belly = Image.new("L", (W, W), 0)
    ImageDraw.Draw(belly).ellipse(
        [int(W * 0.15), int(W * 0.50), int(W * 0.70), int(W * 0.82)], fill=255
    )
    belly = Image.composite(belly, Image.new("L", (W, W), 0), mask)
    belly = belly.filter(ImageFilter.GaussianBlur(int(W * 0.008)))
    img.paste(Image.new("RGBA", (W, W), BELLY + (255,)), (0, 0), belly.point(lambda v: int(v * 0.72)))

    d = ImageDraw.Draw(img)

    # 眼睛 + 高光
    ex, ey, er = int(W * 0.255), int(W * 0.425), int(W * 0.028)
    d.ellipse([ex - er, ey - er, ex + er, ey + er], fill=EYE + (255,))
    hr = max(2, er // 3)
    d.ellipse([ex - hr + er // 3, ey - hr - er // 4, ex + hr + er // 3, ey + hr - er // 4],
              fill=(255, 255, 255, 235))

    # 腮红
    d.ellipse([int(W * 0.305), int(W * 0.487), int(W * 0.352), int(W * 0.530)],
              fill=(255, 150, 160, 80))

    # 喷水
    for cx, cy, r in ((0.245, 0.185, 0.017), (0.285, 0.122, 0.011), (0.325, 0.165, 0.008)):
        d.ellipse([int(W * (cx - r)), int(W * (cy - r)), int(W * (cx + r)), int(W * (cy + r))],
                  fill=SPOUT + (185,))

    return img.resize((S, S), Image.LANCZOS)


def dot():
    s = 96 * K
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    # 外圈柔光
    glow = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.ellipse([0, 0, s - 1, s - 1], fill=BODY_TOP + (90,))
    glow = glow.filter(ImageFilter.GaussianBlur(s * 0.06))
    img = Image.alpha_composite(img, glow)
    d = ImageDraw.Draw(img)
    pad = int(s * 0.22)
    d.ellipse([pad, pad, s - pad, s - pad], fill=BODY_TOP + (255,))
    d.ellipse([int(s * 0.36), int(s * 0.30), int(s * 0.56), int(s * 0.44)],
              fill=(255, 255, 255, 90))
    return img.resize((96, 96), Image.LANCZOS)


def main():
    os.makedirs(OUT, exist_ok=True)
    w = whale()
    w.save(os.path.join(OUT, "whale.png"))
    dot().save(os.path.join(OUT, "dot.png"))
    print("写好：assets/whale.png, assets/dot.png")
    # 顺带留一份 SVG 轮廓，方便你自己改
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {S} {S}">
  <defs><linearGradient id="b" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0" stop-color="#2a8fd0"/><stop offset="1" stop-color="#176098"/>
  </linearGradient></defs>
  <ellipse cx="212" cy="258" rx="164" ry="138" fill="url(#b)"/>
  <path d="M360 236 L474 140 L462 268 L506 318 L372 306 Z" fill="url(#b)"/>
  <ellipse cx="228" cy="330" rx="56" ry="48" fill="#1e72aa"/>
  <ellipse cx="230" cy="352" rx="150" ry="80" fill="#deedf7" opacity="0.9"/>
  <circle cx="125" cy="218" r="15" fill="#0c2030"/>
  <circle cx="130" cy="213" r="5" fill="#fff" opacity="0.9"/>
  <circle cx="160" cy="252" r="10" fill="#ff96a0" opacity="0.28"/>
</svg>
"""
    with open(os.path.join(OUT, "whale.svg"), "w", encoding="utf-8") as f:
        f.write(svg)
    print("写好：assets/whale.svg")


if __name__ == "__main__":
    main()
