# -*- coding: utf-8 -*-
"""
.litematic（Litematica の設計図 = gzip 圧縮 NBT）と
バニラ Structure NBT（.nbt）の読み書きと素材変換。

変換は各リージョンの BlockStatePalette の Name を書き換えるだけで行う。
ブロック状態（向き等の Properties）・配置データ(BlockStates)・タイルエンティティ
（看板の文字やチェストの中身）はそのまま保持される。
"""

import os

import nbtlib
from nbtlib import String

import blockdata as bd


class Conversion:
    """1 つの素材の変換候補（UI の 1 行に対応）。"""
    def __init__(self, source, target, candidates, count):
        self.source = source          # 例 'minecraft:jungle_trapdoor'
        self.target = target          # 例 'oak_trapdoor'（名前空間なし）。None=変換しない
        self.candidates = candidates  # 候補 base id のリスト
        self.count = count            # パレット上の variant 数


def load(path):
    """litematic / structure nbt を読み込んで nbtlib の File を返す。"""
    return nbtlib.load(path)


def is_litematic(nbt):
    return hasattr(nbt, 'get') and 'Regions' in nbt


def is_structure_nbt(nbt):
    return hasattr(nbt, 'get') and all(k in nbt for k in ('size', 'palette', 'blocks'))


def _vec3(value):
    if value is None:
        return None
    try:
        if hasattr(value, 'get') and all(k in value for k in ('x', 'y', 'z')):
            return int(value.get('x')), int(value.get('y')), int(value.get('z'))
    except Exception:
        pass
    try:
        return int(value[0]), int(value[1]), int(value[2])
    except Exception:
        return None


def _palette_index_at(longs, bits, mask, idx):
    bit = idx * bits
    li = bit >> 6
    if li >= len(longs):
        return 0
    off = bit & 63
    value = (longs[li] >> off) & mask
    overflow = off + bits - 64
    if overflow > 0 and li + 1 < len(longs):
        value |= (longs[li + 1] & ((1 << overflow) - 1)) << (bits - overflow)
        value &= mask
    return value


def _region_palette_counts(reg):
    palette = reg.get('BlockStatePalette', [])
    counts = [0] * len(palette)
    states = reg.get('BlockStates', [])
    size = _vec3(reg.get('Size'))
    if len(palette) == 0:
        return []
    if len(states) == 0 or not size:
        return [(str(entry['Name']), 1) for entry in palette]
    sx, sy, sz = abs(int(size[0])), abs(int(size[1])), abs(int(size[2]))
    total = sx * sy * sz
    if total <= 0:
        return [(str(entry['Name']), 1) for entry in palette]
    bits = max(2, (len(palette) - 1).bit_length())
    mask = (1 << bits) - 1
    longs = [int(v) & 0xffffffffffffffff for v in states]
    for idx in range(total):
        pi = _palette_index_at(longs, bits, mask, idx)
        if 0 <= pi < len(counts):
            counts[pi] += 1
    return [(str(entry['Name']), counts[i]) for i, entry in enumerate(palette)]


def _structure_palette_counts(nbt):
    palette = nbt.get('palette', [])
    blocks = nbt.get('blocks', [])
    if len(palette) == 0:
        return []
    counts = [0] * len(palette)
    for block in blocks:
        try:
            state = int(block.get('state', 0))
        except Exception:
            continue
        if 0 <= state < len(counts):
            counts[state] += 1
    return [(str(entry['Name']), counts[i]) for i, entry in enumerate(palette)]


def _iter_palette_counts(nbt):
    if is_litematic(nbt):
        for reg in nbt['Regions'].values():
            for item in _region_palette_counts(reg):
                yield item
        return
    if is_structure_nbt(nbt):
        for item in _structure_palette_counts(nbt):
            yield item


def scan(nbt):
    """
    変換対象になりうる素材を検出して Conversion のリストを返す。
    同じブロック（向き違い）はまとめて 1 件にする。
    """
    counts = {}    # source(full id) -> variant 数
    order = []
    for name, count in _iter_palette_counts(nbt):
        if bd.is_convertible(name):
            if name not in counts:
                counts[name] = 0
                order.append(name)
            counts[name] += count

    convs = []
    for src in order:
        tgt = bd.default_target(src)
        cands = bd.candidates_for(src)
        convs.append(Conversion(src, tgt, cands, counts[src]))

    # 種類別 → 名前順で見やすく並べる
    fam_rank = {'wood': 0, 'stone': 1, 'glass': 2, 'dye': 3, 'copper': 4, 'froglight': 5}
    convs.sort(key=lambda c: (fam_rank.get(bd.family_of(c.source), 9), c.source))
    return convs


def scan_all(nbt):
    """
    パレットの全ブロックを走査し、(変換できるもの, 変換できないもの) を返す。
    変換できないもの = [(full_id, variant数), ...]（air は除外）。
    """
    conv_counts = {}
    conv_order = []
    other_counts = {}
    other_order = []
    for name, count in _iter_palette_counts(nbt):
        if bd.is_convertible(name):
            if name not in conv_counts:
                conv_counts[name] = 0
                conv_order.append(name)
            conv_counts[name] += count
        else:
            if bd.strip_ns(name) == 'air':
                continue
            if name not in other_counts:
                other_counts[name] = 0
                other_order.append(name)
            other_counts[name] += count

    convs = []
    for src in conv_order:
        convs.append(Conversion(src, bd.default_target(src),
                                bd.candidates_for(src), conv_counts[src]))
    fam_rank = {'wood': 0, 'stone': 1, 'glass': 2, 'dye': 3, 'copper': 4, 'froglight': 5}
    convs.sort(key=lambda c: (fam_rank.get(bd.family_of(c.source), 9), c.source))

    others = sorted(((n, other_counts[n]) for n in other_order),
                    key=lambda t: bd.strip_ns(t[0]))
    return convs, others


def apply(nbt, mapping):
    """
    mapping: { source_full_id : target_base_id }（target が None / source と同じものは無視）
    パレットの Name を書き換える。書き換えた palette entry 数を返す。
    """
    changed = 0
    if is_litematic(nbt):
        palettes = (reg['BlockStatePalette'] for reg in nbt['Regions'].values())
    elif is_structure_nbt(nbt):
        palettes = (nbt['palette'],)
    else:
        palettes = ()
    for palette in palettes:
        for entry in palette:
            name = str(entry['Name'])
            tgt = mapping.get(name)
            if not tgt:
                continue
            if tgt == bd.strip_ns(name):
                continue
            entry['Name'] = String(bd.with_ns(tgt))
            if tgt not in bd.candidates_for(name):
                entry.pop('Properties', None)
            changed += 1
    return changed


def palette_size(nbt):
    if is_litematic(nbt):
        return sum(len(r['BlockStatePalette']) for r in nbt['Regions'].values())
    if is_structure_nbt(nbt):
        return len(nbt.get('palette', []))
    return 0


def total_blocks(nbt):
    try:
        total = int(nbt.get('Metadata', {}).get('TotalBlocks', 0))
        if total:
            return total
    except Exception:
        pass
    if is_structure_nbt(nbt):
        return len(nbt.get('blocks', []))
    return 0


def save(nbt, path):
    """gzip 圧縮 NBT として保存。"""
    nbt.save(path, gzipped=True)


def default_output_path(src_path):
    """入力の隣に『_変換』を付けた出力パスを作る。"""
    d = os.path.dirname(src_path)
    base = os.path.basename(src_path)
    stem, ext = os.path.splitext(base)
    if not ext:
        ext = '.litematic'
    return os.path.join(d, '%s_変換%s' % (stem, ext))


def convert_file(src_path, out_path, mapping):
    """
    便利関数: 読み込み → 変換 → 保存。
    パレット長は変えないので BlockStates の再パックは不要。
    戻り値: 書き換えた palette entry 数。
    """
    nbt = load(src_path)
    before = palette_size(nbt)
    changed = apply(nbt, mapping)
    after = palette_size(nbt)
    assert before == after, 'palette size changed unexpectedly'
    save(nbt, out_path)
    return changed
