# -*- coding: utf-8 -*-
"""
ブロックのアイコンを生成する（Pillow 使用）。

ローカルの Minecraft assets が見つかる場合は models/blockstates/textures を読んで実テクスチャを使う。
見つからない環境では、素材ごとの色とドット模様で 16x16 のテクスチャを自前生成してフォールバックする。
形（階段・ハーフ・塀・ドア等）ごとに見た目を変えて区別しやすくする。
"""

import zlib

from PIL import Image, ImageChops, ImageDraw

import blockdata as bd

try:
    import minecraft_assets
except Exception:
    minecraft_assets = None

TPX = 16  # テクスチャ解像度


# ---------------------------------------------------------------------------
# 色ユーティリティ
# ---------------------------------------------------------------------------
def _clamp(v):
    return 0 if v < 0 else (255 if v > 255 else int(v))


def _mul(rgb, f):
    return (_clamp(rgb[0] * f), _clamp(rgb[1] * f), _clamp(rgb[2] * f))


def _bright(im, f):
    if f == 1.0:
        return im
    r, g, b, a = im.split()
    lut = [_clamp(i * f) for i in range(256)]
    return Image.merge('RGBA', (r.point(lut), g.point(lut), b.point(lut), a))


def _rng(*parts):
    seed = zlib.crc32(('|'.join(str(p) for p in parts)).encode('utf-8'))
    state = [seed & 0xFFFFFFFF]

    def nxt():
        state[0] = (1103515245 * state[0] + 12345) & 0x7FFFFFFF
        return state[0]
    return nxt


# ---------------------------------------------------------------------------
# テクスチャ種別
# ---------------------------------------------------------------------------
def _tex_style(base):
    if 'glass' in base:
        return 'glass'
    if base.endswith('planks') or base == 'bamboo_mosaic':
        return 'planks'
    if (base.endswith('_log') or base.endswith('_stem') or base.endswith('_wood')
            or base.endswith('_hyphae') or base in ('bamboo_block', 'stripped_bamboo_block')):
        return 'log'
    if base.endswith('_leaves'):
        return 'leaves'
    if 'cobble' in base:
        return 'cobble'
    if ('brick' in base) or ('tile' in base):
        return 'bricks'
    if base.endswith('_wool') or base.endswith('_carpet'):
        return 'wool'
    if 'concrete_powder' in base:
        return 'sand'
    if 'concrete' in base:
        return 'concrete'
    if 'terracotta' in base:
        return 'terracotta'
    if 'froglight' in base:
        return 'glow'
    if 'copper' in base:
        return 'metal'
    if 'quartz' in base or base == 'calcite':
        return 'smooth'
    if 'sand' in base:  # sand / sandstone
        return 'sand'
    if 'deepslate' in base or 'blackstone' in base or 'basalt' in base:
        return 'stone'
    if ('stone' in base or 'andesite' in base or 'diorite' in base or 'granite' in base
            or 'tuff' in base or 'prismarine' in base or 'purpur' in base
            or 'dripstone' in base or 'cinnabar' in base):
        return 'stone'
    if base.endswith('_bed'):
        return 'wool'
    return 'solid'


# ---------------------------------------------------------------------------
# 16x16 テクスチャ生成
# ---------------------------------------------------------------------------
def _noise(px, base, amt, rnd, holes=None):
    im = Image.new('RGBA', (px, px), base + (255,))
    pa = im.load()
    for y in range(px):
        for x in range(px):
            n = (rnd() % (2 * amt + 1)) - amt
            c = (_clamp(base[0] + n), _clamp(base[1] + n), _clamp(base[2] + n), 255)
            pa[x, y] = c
    return im


def _make_texture(style, color, key, top=False):
    px = TPX
    rnd = _rng(style, color, 'top' if top else 'side')

    if style == 'planks':
        im = _noise(px, color, 10, rnd)
        d = ImageDraw.Draw(im)
        seam = _mul(color, 0.6)
        for y in (0, 4, 8, 12, px - 1):
            d.line([(0, y), (px - 1, y)], fill=seam + (255,))
        # 板ごとに縦継ぎ目をずらす
        for i, y in enumerate((0, 4, 8, 12)):
            sx = (i * 7) % px
            d.line([(sx, y), (sx, y + 3)], fill=seam + (255,))
        return im

    if style == 'log':
        if top:
            im = _noise(px, _mul(color, 1.08), 6, rnd)
            d = ImageDraw.Draw(im)
            ring = _mul(color, 0.7)
            for r in (6, 4, 2):
                d.ellipse([(8 - r, 8 - r), (8 + r, 8 + r)], outline=ring + (255,))
            return im
        im = _noise(px, color, 8, rnd)
        d = ImageDraw.Draw(im)
        bark = _mul(color, 0.62)
        for x in (2, 7, 11, 14):
            d.line([(x, 0), (x, px - 1)], fill=bark + (255,))
        d.line([(0, 0), (px - 1, 0)], fill=bark + (255,))
        d.line([(0, px - 1), (px - 1, px - 1)], fill=bark + (255,))
        return im

    if style == 'leaves':
        im = _noise(px, color, 22, rnd)
        pa = im.load()
        for _ in range(26):
            x = rnd() % px
            y = rnd() % px
            pa[x, y] = _mul(color, 0.55) + (255,)
        return im

    if style == 'cobble':
        mortar = _mul(color, 0.5)
        im = Image.new('RGBA', (px, px), mortar + (255,))
        d = ImageDraw.Draw(im)
        blobs = [(1, 1, 7, 6), (9, 1, 14, 5), (1, 8, 5, 14), (7, 7, 14, 11),
                 (6, 12, 14, 14), (0, 6, 4, 7)]
        for (x0, y0, x1, y1) in blobs:
            f = 0.8 + (rnd() % 40) / 100.0
            d.rounded_rectangle([x0, y0, x1, y1], radius=1, fill=_mul(color, f) + (255,))
        return im

    if style == 'bricks':
        mortar = _mul(color, 1.25)
        im = Image.new('RGBA', (px, px), mortar + (255,))
        d = ImageDraw.Draw(im)
        rows = [0, 4, 8, 12]
        for i, y in enumerate(rows):
            off = 0 if i % 2 == 0 else 4
            for x in range(-off, px, 8):
                f = 0.85 + (rnd() % 30) / 100.0
                d.rectangle([x + 1, y + 1, x + 7, y + 3], fill=_mul(color, f) + (255,))
        return im

    if style == 'glass':
        im = Image.new('RGBA', (px, px), (color[0], color[1], color[2], 70))
        d = ImageDraw.Draw(im)
        frame = (_clamp(color[0] + 40), _clamp(color[1] + 40), _clamp(color[2] + 40), 255)
        d.rectangle([0, 0, px - 1, px - 1], outline=frame, width=1)
        d.line([(2, 12), (12, 2)], fill=(255, 255, 255, 150))
        return im

    if style == 'wool':
        im = _noise(px, color, 12, rnd)
        pa = im.load()
        for _ in range(18):
            x = rnd() % px
            y = rnd() % px
            pa[x, y] = _mul(color, 1.18) + (255,)
        return im

    if style == 'sand':
        return _noise(px, color, 14, rnd)

    if style == 'concrete':
        return _noise(px, color, 5, rnd)

    if style == 'terracotta':
        im = _noise(px, color, 8, rnd)
        d = ImageDraw.Draw(im)
        d.rectangle([0, 0, px - 1, px - 1], outline=_mul(color, 0.8) + (255,))
        return im

    if style == 'metal':
        im = _noise(px, color, 7, rnd)
        d = ImageDraw.Draw(im)
        for _ in range(5):
            x = rnd() % px
            y = rnd() % px
            d.point((x, y), fill=_mul(color, 1.2) + (255,))
        return im

    if style == 'smooth':
        return _noise(px, color, 4, rnd)

    if style == 'glow':
        im = _noise(px, color, 10, rnd)
        pa = im.load()
        for _ in range(20):
            x = rnd() % px
            y = rnd() % px
            pa[x, y] = (255, 255, 230, 255)
        return im

    if style == 'stone':
        return _noise(px, color, 11, rnd)

    return _noise(px, color, 6, rnd)  # solid


_TEX_CACHE = {}


def using_minecraft_assets():
    return bool(minecraft_assets and minecraft_assets.available())


def minecraft_assets_label():
    if not minecraft_assets:
        return ''
    return minecraft_assets.root_label()


def _asset_texture(base, top=False, face=None):
    if not minecraft_assets:
        return None
    try:
        return minecraft_assets.get_block_texture(base, top=top, face=face)
    except Exception:
        return None


def _texture(base, color, top=False, face=None):
    key = (base, color, top, face, using_minecraft_assets())
    if key not in _TEX_CACHE:
        tex = _asset_texture(base, top=top, face=face)
        if tex is None:
            tex = _make_texture(_tex_style(base), color, base, top)
        _TEX_CACHE[key] = tex
    return _TEX_CACHE[key]


def block_texture_image(bid, top=False, face=None):
    base = bd.strip_ns(bid)
    return _texture(base, bd.base_color(bid), top=top, face=face).copy()


# ---------------------------------------------------------------------------
# アイソメトリック投影
# ---------------------------------------------------------------------------
def _proj(x, y, z, S):
    a = S * 0.40
    b = S * 0.20
    c = S * 0.40
    return (S * 0.5 + (x - z) * a, S * 0.42 + (x + z) * b - y * c)


def _paste_face(canvas, tex, O, u, v, outline=True):
    px = tex.width
    ux, uy = u
    vx, vy = v
    Ox, Oy = O
    detM = (ux * vy - vx * uy) / (px * px)
    if abs(detM) < 1e-6:
        return
    a = (vy / px) / detM
    b = (-vx / px) / detM
    d = (-uy / px) / detM
    e = (ux / px) / detM
    c = -(a * Ox + b * Oy)
    f = -(d * Ox + e * Oy)
    warped = tex.transform(canvas.size, Image.AFFINE, (a, b, c, d, e, f), resample=Image.NEAREST)
    mask = Image.new('L', canvas.size, 0)
    poly = [(Ox, Oy), (Ox + ux, Oy + uy), (Ox + ux + vx, Oy + uy + vy), (Ox + vx, Oy + vy)]
    ImageDraw.Draw(mask).polygon(poly, fill=255)
    if warped.mode == 'RGBA':
        alpha = warped.getchannel('A')
        if alpha.getextrema() != (255, 255):
            mask = ImageChops.multiply(mask, alpha)
    canvas.paste(warped, (0, 0), mask)
    if outline:
        ImageDraw.Draw(canvas, 'RGBA').polygon(poly, outline=(0, 0, 0, 55))


def _iso_box(canvas, box, face, top, S):
    x0, y0, z0, x1, y1, z1 = box
    P = lambda x, y, z: _proj(x, y, z, S)
    topf = _bright(top, 1.0)
    leftf = _bright(face, 0.80)
    rightf = _bright(face, 0.62)
    # TOP (y=y1)
    A = P(x0, y1, z0)
    B = P(x1, y1, z0)
    D = P(x0, y1, z1)
    _paste_face(canvas, topf, A, (B[0] - A[0], B[1] - A[1]), (D[0] - A[0], D[1] - A[1]))
    # LEFT (z=z1)
    Dl = P(x0, y1, z1)
    Cl = P(x1, y1, z1)
    Hl = P(x0, y0, z1)
    _paste_face(canvas, leftf, Dl, (Cl[0] - Dl[0], Cl[1] - Dl[1]), (Hl[0] - Dl[0], Hl[1] - Dl[1]))
    # RIGHT (x=x1)
    Br = P(x1, y1, z0)
    Cr = P(x1, y1, z1)
    Fr = P(x1, y0, z0)
    _paste_face(canvas, rightf, Br, (Cr[0] - Br[0], Cr[1] - Br[1]), (Fr[0] - Br[0], Fr[1] - Br[1]))


def _flat(canvas, tex, box01, S):
    x0, y0, x1, y1 = box01
    w = max(1, int((x1 - x0) * S))
    h = max(1, int((y1 - y0) * S))
    t = tex.resize((w, h), Image.NEAREST)
    canvas.alpha_composite(t, (int(x0 * S), int(y0 * S)))
    ImageDraw.Draw(canvas, 'RGBA').rectangle(
        [int(x0 * S), int(y0 * S), int(x0 * S) + w - 1, int(y0 * S) + h - 1],
        outline=(0, 0, 0, 70))


# ---------------------------------------------------------------------------
# メイン
# ---------------------------------------------------------------------------
def render_block_image(bid, size=48):
    S = size
    base = bd.strip_ns(bid)
    img = Image.new('RGBA', (S, S), (0, 0, 0, 0))
    try:
        shape = bd.shape_of(bid)
        color = bd.base_color(bid)
        face = _texture(base, color, top=False)
        top = _texture(base, color, top=True)
        d = ImageDraw.Draw(img, 'RGBA')

        if shape == 'slab':
            _iso_box(img, (0, 0, 0, 1, 0.5, 1), face, top, S)
        elif shape == 'stairs':
            _iso_box(img, (0, 0.5, 0, 1, 1, 0.5), face, top, S)   # 奥の段（先に描く）
            _iso_box(img, (0, 0, 0, 1, 0.5, 1), face, top, S)     # 手前の段
        elif shape == 'carpet':
            _iso_box(img, (0.02, 0, 0.02, 0.98, 0.06, 0.98), face, top, S)
        elif shape == 'wall':
            _iso_box(img, (0.30, 0, 0.30, 0.70, 1, 0.70), face, top, S)
        elif shape == 'fence':
            _iso_box(img, (0.40, 0, 0.40, 0.60, 1, 0.60), face, top, S)
        elif shape == 'shulker':
            _iso_box(img, (0.04, 0, 0.04, 0.96, 0.9, 0.96), face, top, S)
        elif shape == 'log':
            _iso_box(img, (0, 0, 0, 1, 1, 1), face, top, S)
        elif shape in ('planks', 'glass', 'block'):
            _iso_box(img, (0, 0, 0, 1, 1, 1), face, top, S)
        elif shape == 'bed':
            _iso_box(img, (0.0, 0, 0.0, 1.0, 0.36, 1.0), face, top, S)
            # 枕
            px0, py0 = _proj(0.0, 0.36, 0.0, S)
            d.rectangle([px0, py0 - S * 0.16, px0 + S * 0.34, py0 - S * 0.02],
                        fill=(245, 245, 245, 255), outline=(0, 0, 0, 60))
        elif shape == 'fence_gate':
            col = color
            d.rectangle([S * 0.20, S * 0.18, S * 0.30, S * 0.86], fill=_mul(col, 0.9) + (255,),
                        outline=(0, 0, 0, 90))
            d.rectangle([S * 0.70, S * 0.18, S * 0.80, S * 0.86], fill=_mul(col, 0.9) + (255,),
                        outline=(0, 0, 0, 90))
            d.rectangle([S * 0.30, S * 0.34, S * 0.70, S * 0.44], fill=_mul(col, 1.05) + (255,))
            d.rectangle([S * 0.30, S * 0.58, S * 0.70, S * 0.68], fill=_mul(col, 1.05) + (255,))
        elif shape == 'pane':
            _flat(img, face, (0.42, 0.08, 0.58, 0.92), S)
        elif shape == 'door':
            _flat(img, face, (0.28, 0.05, 0.72, 0.95), S)
            d.rectangle([S * 0.33, S * 0.10, S * 0.67, S * 0.45], outline=_mul(color, 0.55) + (255,))
            d.rectangle([S * 0.33, S * 0.52, S * 0.67, S * 0.90], outline=_mul(color, 0.55) + (255,))
            d.ellipse([S * 0.60, S * 0.48, S * 0.65, S * 0.53], fill=_mul(color, 0.4) + (255,))
        elif shape == 'trapdoor':
            _flat(img, face, (0.12, 0.16, 0.88, 0.84), S)
            for yy in (0.34, 0.5, 0.66):
                d.line([(S * 0.12, S * yy), (S * 0.88, S * yy)], fill=_mul(color, 0.55) + (255,))
        elif shape == 'sign':
            _flat(img, face, (0.16, 0.12, 0.84, 0.58), S)
            d.line([(S * 0.5, S * 0.58), (S * 0.5, S * 0.9)], fill=_mul(color, 0.7) + (255,), width=max(2, S // 18))
        elif shape == 'button':
            _iso_box(img, (0.36, 0, 0.40, 0.64, 0.16, 0.60), face, top, S)
        elif shape == 'plate':
            _iso_box(img, (0.12, 0, 0.12, 0.88, 0.10, 0.88), face, top, S)
        elif shape == 'candle':
            d.rectangle([S * 0.44, S * 0.42, S * 0.56, S * 0.82], fill=color + (255,), outline=(0, 0, 0, 80))
            d.ellipse([S * 0.46, S * 0.30, S * 0.54, S * 0.44], fill=(255, 196, 84, 255))
            d.ellipse([S * 0.48, S * 0.26, S * 0.52, S * 0.34], fill=(255, 240, 170, 255))
        elif shape == 'banner':
            d.rectangle([S * 0.30, S * 0.10, S * 0.70, S * 0.16], fill=(120, 120, 120, 255))
            _flat(img, face, (0.30, 0.14, 0.70, 0.84), S)
        else:
            _iso_box(img, (0, 0, 0, 1, 1, 1), face, top, S)
    except Exception:
        # 失敗時は単純なベベル四角
        d = ImageDraw.Draw(img, 'RGBA')
        col = bd.base_color(bid)
        d.rounded_rectangle([S * 0.12, S * 0.12, S * 0.88, S * 0.88], radius=4,
                            fill=col + (255,), outline=_mul(col, 0.55) + (255,))
    return img
