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
from nbtlib.tag import ByteArray, Compound, Int

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


def _schem_tag(nbt):
    if not hasattr(nbt, 'get'):
        return None
    nested = nbt.get('Schematic')
    if hasattr(nested, 'get'):
        return nested
    return nbt


def _schem_blocks_tag(nbt):
    schem = _schem_tag(nbt)
    if not hasattr(schem, 'get'):
        return None
    blocks = schem.get('Blocks')
    if hasattr(blocks, 'get'):
        return blocks
    return schem


def is_sponge_schem(nbt):
    schem = _schem_tag(nbt)
    blocks = _schem_blocks_tag(nbt)
    if not hasattr(schem, 'get') or not hasattr(blocks, 'get'):
        return False
    has_size = all(k in schem for k in ('Width', 'Height', 'Length'))
    has_data = 'Data' in blocks or 'BlockData' in blocks
    return has_size and 'Palette' in blocks and has_data


def schem_dimensions(nbt):
    schem = _schem_tag(nbt)
    if not hasattr(schem, 'get'):
        return None
    try:
        return int(schem['Width']), int(schem['Height']), int(schem['Length'])
    except Exception:
        return None


def _parse_schem_state(raw):
    raw = str(raw)
    if '[' not in raw or not raw.endswith(']'):
        return raw, {}
    name, prop_text = raw[:-1].split('[', 1)
    props = {}
    for part in prop_text.split(','):
        if '=' not in part:
            continue
        key, value = part.split('=', 1)
        props[key] = value
    return name, props


def _format_schem_state(name, props):
    if not props:
        return str(name)
    return '%s[%s]' % (name, ','.join('%s=%s' % (k, v) for k, v in props.items()))


def schem_palette_entries(nbt):
    blocks = _schem_blocks_tag(nbt)
    if not hasattr(blocks, 'get'):
        return []
    palette = blocks.get('Palette', {})
    entries = []
    for raw, idx in palette.items():
        try:
            state_id = int(idx)
        except Exception:
            continue
        name, props = _parse_schem_state(raw)
        entries.append((state_id, str(raw), name, props))
    entries.sort(key=lambda item: item[0])
    return entries


def _decode_varints(data, total=None):
    if data is None:
        return []
    raw = [int(b) & 0xff for b in data]
    out = []
    i = 0
    while i < len(raw) and (total is None or len(out) < total):
        value = 0
        shift = 0
        while True:
            if i >= len(raw):
                break
            b = raw[i]
            i += 1
            value |= (b & 0x7f) << shift
            if not (b & 0x80):
                out.append(value)
                break
            shift += 7
            if shift > 35:
                out.append(0)
                break
    if total is not None and len(out) < total:
        out.extend([0] * (total - len(out)))
    return out


def _encode_varints(values):
    data = []
    for value in values:
        value = max(0, int(value))
        while True:
            b = value & 0x7f
            value >>= 7
            if value:
                data.append(b | 0x80)
            else:
                data.append(b)
                break
    return ByteArray([b if b < 128 else b - 256 for b in data])


def schem_block_ids(nbt):
    blocks = _schem_blocks_tag(nbt)
    dims = schem_dimensions(nbt)
    if not hasattr(blocks, 'get') or not dims:
        return []
    total = int(dims[0]) * int(dims[1]) * int(dims[2])
    return _decode_varints(blocks.get('Data', blocks.get('BlockData')), total)


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


def _schem_palette_counts(nbt):
    entries = schem_palette_entries(nbt)
    if not entries:
        return []
    max_id = max(item[0] for item in entries)
    counts = [0] * (max_id + 1)
    for state_id in schem_block_ids(nbt):
        if 0 <= state_id < len(counts):
            counts[state_id] += 1
    names = {state_id: name for state_id, _raw, name, _props in entries}
    return [(names.get(i, 'minecraft:air'), counts[i]) for i in range(len(counts)) if i in names]


def _iter_palette_counts(nbt):
    if is_litematic(nbt):
        for reg in nbt['Regions'].values():
            for item in _region_palette_counts(reg):
                yield item
        return
    if is_structure_nbt(nbt):
        for item in _structure_palette_counts(nbt):
            yield item
        return
    if is_sponge_schem(nbt):
        for item in _schem_palette_counts(nbt):
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
    if is_sponge_schem(nbt):
        return _apply_schem(nbt, mapping)
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


def _apply_schem(nbt, mapping):
    blocks = _schem_blocks_tag(nbt)
    if not hasattr(blocks, 'get'):
        return 0
    entries = schem_palette_entries(nbt)
    if not entries:
        return 0

    old_to_new_state = {}
    changed = 0
    for old_id, raw, name, props in entries:
        tgt = mapping.get(name)
        if tgt and tgt != bd.strip_ns(name):
            new_name = bd.with_ns(tgt)
            new_props = props if tgt in bd.candidates_for(name) else {}
            new_state = _format_schem_state(new_name, new_props)
            changed += 1
        else:
            new_state = raw
        old_to_new_state[old_id] = new_state

    if not changed:
        return 0

    state_to_new_id = {}
    old_to_new_id = {}
    for old_id, _raw, _name, _props in entries:
        new_state = old_to_new_state[old_id]
        if new_state not in state_to_new_id:
            state_to_new_id[new_state] = len(state_to_new_id)
        old_to_new_id[old_id] = state_to_new_id[new_state]

    block_ids = schem_block_ids(nbt)
    remapped = [old_to_new_id.get(state_id, 0) for state_id in block_ids]
    new_palette = Compound()
    for state, idx in state_to_new_id.items():
        new_palette[state] = Int(idx)
    blocks['Palette'] = new_palette
    data_key = 'Data' if 'Data' in blocks else 'BlockData'
    blocks[data_key] = _encode_varints(remapped)
    return changed


def palette_size(nbt):
    if is_litematic(nbt):
        return sum(len(r['BlockStatePalette']) for r in nbt['Regions'].values())
    if is_structure_nbt(nbt):
        return len(nbt.get('palette', []))
    if is_sponge_schem(nbt):
        return len(schem_palette_entries(nbt))
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
    if is_sponge_schem(nbt):
        return sum(count for name, count in _schem_palette_counts(nbt)
                   if bd.strip_ns(name) not in ('air', 'cave_air', 'void_air'))
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
    if not is_sponge_schem(nbt):
        assert before == after, 'palette size changed unexpectedly'
    save(nbt, out_path)
    return changed
