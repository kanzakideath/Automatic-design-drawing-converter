# -*- coding: utf-8 -*-
"""
設計図素材変換ツール - ブロックの種類データ / 変換ルール（全素材対応版）

実際のゲーム本体(26.2)から抽出した有効ブロックID一覧(data/blocks_26.2.txt)を基準に、
「同じ形（stairs/slab/wall/planks/…）で素材だけ違うブロック」を 1 つのグループにまとめる。
各グループ内は入手difficulty（難易度）の昇順に並べ、いちばん入手しやすいものを既定の置き換え先にする。

著作物（テクスチャ等）は一切含まない。色はアイコン用の自前近似値。
ブロックIDは機能的な識別子（レジストリ名）であり、それ自体は創作表現ではない。
"""

import os
import sys
import json
import zlib


# ---------------------------------------------------------------------------
# 有効ブロックID一覧の読み込み（バンドルされた data/blocks_*.txt）
# ---------------------------------------------------------------------------
def _resource_dir():
    if getattr(sys, 'frozen', False):
        return os.path.join(sys._MEIPASS, 'data')          # PyInstaller 同梱
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')


def _read_block_file(fname):
    if not fname:
        return None
    try:
        with open(os.path.join(_resource_dir(), fname), encoding='utf-8') as f:
            return set(line.strip() for line in f if line.strip())
    except OSError:
        return None


def _load_versions():
    try:
        with open(os.path.join(_resource_dir(), 'versions.json'), encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return None


_VERSIONS = _load_versions()
REGISTRIES = (_VERSIONS or {}).get('registries', [])      # 新しい順
_BY_VERSION = (_VERSIONS or {}).get('by_version', {})

VALID = None            # 現在有効なブロックID集合
ID2GROUP = {}           # 現在有効なグループ表
ACTIVE_FILE = None


def _ok(bid):
    return VALID is None or bid in VALID


# ---------------------------------------------------------------------------
# 名前空間ヘルパ
# ---------------------------------------------------------------------------
def strip_ns(bid):
    return bid[len('minecraft:'):] if bid.startswith('minecraft:') else bid


def is_vanilla(bid):
    return (':' not in bid) or bid.startswith('minecraft:')


def with_ns(base):
    return 'minecraft:' + base


# ---------------------------------------------------------------------------
# 素材リストと難易度
# ---------------------------------------------------------------------------
# 木材（入手しやすい順）
WOOD_ORDER = ['oak', 'birch', 'spruce', 'jungle', 'acacia', 'dark_oak',
              'bamboo', 'mangrove', 'cherry', 'pale_oak', 'crimson', 'warped']
WOOD_DIFF = {m: i for i, m in enumerate(WOOD_ORDER)}
WOOD_DIFF['bamboo_mosaic'] = WOOD_DIFF['bamboo']

# 染料色（白＝最易→以降ざっくり入手しやすい順）
DYE_ORDER = ['white', 'light_gray', 'gray', 'black', 'red', 'yellow', 'orange',
             'blue', 'green', 'brown', 'pink', 'lime', 'light_blue', 'cyan',
             'purple', 'magenta']
DYES = DYE_ORDER
DYE_DIFF = {c: i for i, c in enumerate(DYE_ORDER)}

# 木の各「形」 -> ブロックID
WOOD_PLANK_FORMS = ['planks', 'stairs', 'slab', 'fence', 'fence_gate', 'door',
                    'trapdoor', 'button', 'pressure_plate', 'sign', 'wall_sign',
                    'hanging_sign', 'wall_hanging_sign']


def wood_form_map(m):
    d = {}
    for f in WOOD_PLANK_FORMS:
        d[f] = '%s_%s' % (m, f)
    if m in ('crimson', 'warped'):
        d['log'] = '%s_stem' % m
        d['wood'] = '%s_hyphae' % m
        d['stripped_log'] = 'stripped_%s_stem' % m
        d['stripped_wood'] = 'stripped_%s_hyphae' % m
    elif m == 'bamboo':
        d['log'] = 'bamboo_block'
        d['stripped_log'] = 'stripped_bamboo_block'
    else:
        d['log'] = '%s_log' % m
        d['wood'] = '%s_wood' % m
        d['stripped_log'] = 'stripped_%s_log' % m
        d['stripped_wood'] = 'stripped_%s_wood' % m
        d['leaves'] = '%s_leaves' % m
        d['sapling'] = '%s_sapling' % m
    return d


# 石系の難易度（小さいほど入手しやすい）。既定は cobblestone(0)。
def diff_stone(s):
    table = {
        'cobblestone': 0,
        'stone': 1, 'cobbled_deepslate': 1, 'granite': 1, 'diorite': 1,
        'andesite': 1, 'tuff': 1, 'deepslate': 1,
        'smooth_stone': 1,
        'mossy_cobblestone': 2, 'sandstone': 2, 'red_sandstone': 2,
        'stone_brick': 2,
    }
    if s in table:
        return table[s]
    if 'cobblestone' in s:
        return 2
    if s.startswith('polished_') and ('blackstone' not in s):
        return 3
    if 'stone_brick' in s:                       # mossy_/cracked_/chiseled_
        return 3
    if 'deepslate' in s:
        return 3
    if 'sandstone' in s:
        return 3
    if 'tuff' in s:
        return 3
    if 'basalt' in s or s in ('calcite', 'dripstone_block', 'dripstone'):
        return 3
    if 'mud_brick' in s or s == 'bricks' or s == 'brick' or 'resin' in s:
        return 4
    if 'blackstone' in s:
        return 4
    if 'nether_brick' in s:
        return 4
    if 'quartz' in s:
        return 4
    if 'prismarine' in s:
        return 5
    if 'purpur' in s:
        return 5
    if 'end_stone' in s:
        return 5
    return 6                                       # 未知素材は候補末尾（既定にしない）


WOOD_STEMS = set(WOOD_ORDER) | {'bamboo_mosaic'}

# 石系の「フル（立方体）ブロック」の追加候補（stairs等から導けない装飾フルブロック）
EXTRA_STONE_BLOCKS = [
    'stone', 'smooth_stone',
    'chiseled_stone_bricks', 'cracked_stone_bricks', 'mossy_stone_bricks',
    'sandstone', 'chiseled_sandstone', 'cut_sandstone', 'smooth_sandstone',
    'red_sandstone', 'chiseled_red_sandstone', 'cut_red_sandstone', 'smooth_red_sandstone',
    'quartz_block', 'chiseled_quartz_block', 'quartz_pillar', 'quartz_bricks', 'smooth_quartz',
    'deepslate', 'cobbled_deepslate', 'polished_deepslate', 'chiseled_deepslate',
    'cracked_deepslate_bricks', 'cracked_deepslate_tiles',
    'blackstone', 'gilded_blackstone', 'polished_blackstone',
    'chiseled_polished_blackstone', 'cracked_polished_blackstone_bricks',
    'tuff', 'polished_tuff', 'chiseled_tuff', 'chiseled_tuff_bricks',
    'basalt', 'polished_basalt', 'smooth_basalt', 'calcite', 'dripstone_block',
    'purpur_block', 'purpur_pillar', 'prismarine_bricks', 'dark_prismarine',
    'bricks',
]


# ---------------------------------------------------------------------------
# グループの構築
# ---------------------------------------------------------------------------
class Group:
    __slots__ = ('family', 'form', 'members', 'default')

    def __init__(self, family, form, members):
        self.family = family
        self.form = form
        self.members = members          # 難易度昇順の base id 列
        self.default = members[0]


ID2GROUP = {}


def _register(group):
    if len(group.members) < 2:
        return
    for m in group.members:
        ID2GROUP.setdefault(m, group)


def _pick_block(stem):
    for cand in (stem, stem + 's', stem + '_block'):
        if _ok(cand):
            return cand
    return None


def _copper_base(b):
    x = b
    if x.startswith('waxed_'):
        x = x[6:]
    for ox in ('exposed_', 'weathered_', 'oxidized_'):
        if x.startswith(ox):
            x = x[len(ox):]
            break
    if x == 'copper':          # exposed_copper 等の素ブロックは copper_block 扱い
        x = 'copper_block'
    return x


def _copper_diff(b):
    d = 0
    x = b
    if x.startswith('waxed_'):
        d += 1
        x = x[6:]
    if x.startswith('exposed_'):
        d += 2
    elif x.startswith('weathered_'):
        d += 3
    elif x.startswith('oxidized_'):
        d += 4
    return d


def _build():
    # ---- 木材 ----
    maps = {m: wood_form_map(m) for m in WOOD_ORDER}
    maps['bamboo_mosaic'] = {'planks': 'bamboo_mosaic',
                             'slab': 'bamboo_mosaic_slab',
                             'stairs': 'bamboo_mosaic_stairs'}
    wood_mats = WOOD_ORDER + ['bamboo_mosaic']
    byform = {}
    for m in wood_mats:
        for fk, bid in maps[m].items():
            if _ok(bid):
                byform.setdefault(fk, []).append((WOOD_DIFF[m], bid))
    for fk, lst in byform.items():
        lst.sort(key=lambda x: x[0])
        _register(Group('wood', fk, [b for _, b in lst]))

    # ---- 石系 stairs / slab / wall ----
    stone_stems = set()
    for form in ('stairs', 'slab', 'wall'):
        suf = '_' + form
        mats = set()
        if VALID:
            for b in VALID:
                if b.endswith(suf):
                    stem = b[:-len(suf)]
                    if stem in WOOD_STEMS or 'copper' in stem:
                        continue
                    mats.add(stem)
        mats = sorted(mats, key=lambda s: (diff_stone(s), s))
        if mats:
            stone_stems.update(mats)
            _register(Group('stone', form, [s + suf for s in mats]))

    # ---- 石系 フルブロック ----
    block_members = []
    seen = set()
    cand_stems = sorted(stone_stems, key=lambda s: (diff_stone(s), s))
    for stem in cand_stems:
        blk = _pick_block(stem)
        if blk and blk not in seen:
            seen.add(blk)
            block_members.append((diff_stone(stem), blk))
    for extra in EXTRA_STONE_BLOCKS:
        if _ok(extra) and extra not in seen:
            seen.add(extra)
            block_members.append((diff_stone(extra), extra))
    block_members.sort(key=lambda x: x[0])
    if block_members:
        _register(Group('stone', 'block', [b for _, b in block_members]))

    # ---- 銅（酸化/蝋引き → 素の銅）----
    if VALID:
        groups = {}
        for b in VALID:
            if 'copper' in b:
                groups.setdefault(_copper_base(b), []).append(b)
        for base, ids in groups.items():
            if base not in ids or len(ids) < 2:
                continue
            ids = sorted(ids, key=lambda x: (_copper_diff(x), x))
            ids.remove(base)
            ids.insert(0, base)
            _register(Group('copper', base, ids))

    # ---- 染料色の装飾ブロック ----
    dye_forms = ['wool', 'carpet', 'bed', 'concrete', 'concrete_powder',
                 'terracotta', 'glazed_terracotta', 'candle', 'shulker_box',
                 'banner', 'wall_banner']
    plain = {'terracotta': 'terracotta', 'candle': 'candle', 'shulker_box': 'shulker_box'}
    for form in dye_forms:
        members = []
        pl = plain.get(form)
        if pl and _ok(pl):
            members.append((-1, pl))
        for c in DYES:
            bid = '%s_%s' % (c, form)
            if _ok(bid):
                members.append((DYE_DIFF[c], bid))
        members.sort(key=lambda x: x[0])
        _register(Group('dye', form, [b for _, b in members]))

    # ---- ガラス ----
    blk = []
    if _ok('glass'):
        blk.append((-1, 'glass'))
    for c in DYES:
        bid = '%s_stained_glass' % c
        if _ok(bid):
            blk.append((DYE_DIFF[c], bid))
    if _ok('tinted_glass'):
        blk.append((99, 'tinted_glass'))
    blk.sort(key=lambda x: x[0])
    _register(Group('glass', 'glass', [b for _, b in blk]))

    pane = []
    if _ok('glass_pane'):
        pane.append((-1, 'glass_pane'))
    for c in DYES:
        bid = '%s_stained_glass_pane' % c
        if _ok(bid):
            pane.append((DYE_DIFF[c], bid))
    pane.sort(key=lambda x: x[0])
    _register(Group('glass', 'glass_pane', [b for _, b in pane]))

    # ---- フロッグライト（色違い → 既定 ochre）----
    frog = [f for f in ('ochre_froglight', 'verdant_froglight', 'pearlescent_froglight')
            if _ok(f)]
    if len(frog) >= 2:
        _register(Group('froglight', 'froglight', frog))


def set_active_file(fname):
    """指定の data/blocks_*.txt を有効レジストリにして全グループを再構築する。"""
    global VALID, ID2GROUP, ACTIVE_FILE
    VALID = _read_block_file(fname)
    ID2GROUP = {}
    _build()
    ACTIVE_FILE = fname


def available_registries():
    """[{id, data_version, file, count, members}, ...]（新しい順）"""
    return list(REGISTRIES)


def file_for_dataversion(dv):
    """設計図の MinecraftDataVersion から最適なレジストリのファイル名を返す。"""
    if dv is not None and str(dv) in _BY_VERSION:
        return _BY_VERSION[str(dv)]
    if dv is not None:
        le = [r for r in REGISTRIES if r['data_version'] <= dv]
        if le:
            return max(le, key=lambda r: r['data_version'])['file']
    return REGISTRIES[0]['file'] if REGISTRIES else None


def active_registry():
    for r in REGISTRIES:
        if r['file'] == ACTIVE_FILE:
            return r
    return None


# 初期化: 最新レジストリ（無ければ data 内の任意の blocks_*.txt）で構築
if REGISTRIES:
    set_active_file(REGISTRIES[0]['file'])
else:
    import glob as _glob
    _f = _glob.glob(os.path.join(_resource_dir(), 'blocks_*.txt'))
    set_active_file(os.path.basename(_f[0]) if _f else None)


# ---------------------------------------------------------------------------
# 公開API
# ---------------------------------------------------------------------------
def get_group(bid):
    if not is_vanilla(bid):
        return None
    return ID2GROUP.get(strip_ns(bid))


def family_of(bid):
    g = get_group(bid)
    return g.family if g else None


def default_target(bid):
    g = get_group(bid)
    return g.default if g else None


def candidates_for(bid):
    g = get_group(bid)
    return list(g.members) if g else []


def is_valid_block(bid):
    base = strip_ns(bid)
    return VALID is None or base in VALID


def all_blocks():
    """現在の対象バージョンで使える全ブロックID(base id)を名前順で返す。"""
    if VALID is None:
        return sorted(ID2GROUP.keys())
    return sorted(VALID)


def is_convertible(bid):
    g = get_group(bid)
    if not g:
        return False
    return g.default != strip_ns(bid)


# ---------------------------------------------------------------------------
# アイコン用: 形と色
# ---------------------------------------------------------------------------
def shape_of(bid):
    base = strip_ns(bid)
    if base.endswith('_slab'):
        return 'slab'
    if base.endswith('_stairs'):
        return 'stairs'
    if base.endswith('_trapdoor'):
        return 'trapdoor'
    if base.endswith('_door'):
        return 'door'
    if base.endswith('_fence_gate'):
        return 'fence_gate'
    if base.endswith('_fence'):
        return 'fence'
    if base.endswith('_wall'):
        return 'wall'
    if base.endswith('_glass_pane') or base == 'glass_pane':
        return 'pane'
    if base.endswith('glass'):
        return 'glass'
    if base.endswith('_bed'):
        return 'bed'
    if base.endswith('_carpet'):
        return 'carpet'
    if base.endswith('_wall_sign') or base.endswith('_hanging_sign') or base.endswith('_sign'):
        return 'sign'
    if base.endswith('_button'):
        return 'button'
    if base.endswith('_pressure_plate'):
        return 'plate'
    if base.endswith('_candle') or base == 'candle':
        return 'candle'
    if base.endswith('shulker_box'):
        return 'shulker'
    if base.endswith('_banner') or base.endswith('_wall_banner'):
        return 'banner'
    if base.endswith('froglight'):
        return 'block'
    if (base.endswith('_log') or base.endswith('_stem') or base.endswith('_wood')
            or base.endswith('_hyphae') or base in ('bamboo_block', 'stripped_bamboo_block')):
        return 'log'
    if base.endswith('_planks') or base == 'bamboo_mosaic':
        return 'planks'
    return 'block'


_WOOD_C = {
    'oak': (165, 133, 79), 'spruce': (107, 79, 46), 'birch': (196, 178, 123),
    'jungle': (160, 115, 80), 'acacia': (167, 89, 47), 'dark_oak': (66, 44, 21),
    'mangrove': (122, 53, 47), 'cherry': (227, 178, 174), 'pale_oak': (222, 213, 196),
    'bamboo': (193, 167, 86), 'crimson': (126, 59, 81), 'warped': (43, 104, 99),
}
_DYE_C = {
    'white': (233, 236, 236), 'orange': (240, 118, 19), 'magenta': (198, 79, 189),
    'light_blue': (58, 175, 217), 'yellow': (248, 198, 39), 'lime': (112, 185, 25),
    'pink': (237, 141, 172), 'gray': (62, 68, 71), 'light_gray': (142, 142, 134),
    'cyan': (21, 137, 145), 'purple': (121, 42, 172), 'blue': (53, 57, 157),
    'brown': (114, 71, 40), 'green': (84, 109, 27), 'red': (160, 39, 34),
    'black': (20, 21, 25),
}


def base_color(bid):
    base = strip_ns(bid)

    if base in ('glass', 'glass_pane'):
        return (181, 217, 225)
    if base == 'tinted_glass':
        return (42, 38, 47)
    if base.endswith('_stained_glass_pane') or base.endswith('_stained_glass'):
        return _DYE_C.get(base.split('_stained_glass')[0], (181, 217, 225))

    # 染料色
    for form in ('glazed_terracotta', 'concrete_powder', 'wall_banner', 'shulker_box',
                 'terracotta', 'concrete', 'candle', 'banner', 'carpet', 'wool', 'bed'):
        suf = '_' + form
        if base.endswith(suf):
            c = base[:-len(suf)]
            if c in _DYE_C:
                return _DYE_C[c]
    if base == 'terracotta':
        return (152, 94, 68)

    # 木材
    for m, col in _WOOD_C.items():
        if base == m or base.startswith(m + '_') or base.startswith('stripped_' + m):
            return col

    # 銅
    if 'copper' in base:
        if 'oxidized' in base:
            return (82, 162, 132)
        if 'weathered' in base:
            return (108, 156, 118)
        if 'exposed' in base:
            return (161, 125, 99)
        return (224, 132, 94)

    # フロッグライト
    if base == 'ochre_froglight':
        return (216, 196, 122)
    if base == 'verdant_froglight':
        return (146, 175, 110)
    if base == 'pearlescent_froglight':
        return (214, 178, 196)

    # 石・地形ほか（キーワード）
    kw = [
        ('deepslate', (72, 72, 76)), ('blackstone', (44, 40, 46)),
        ('basalt', (80, 78, 84)), ('red_sandstone', (190, 102, 47)),
        ('sandstone', (219, 207, 163)), ('quartz', (235, 229, 222)),
        ('purpur', (170, 116, 170)), ('prismarine', (99, 152, 137)),
        ('calcite', (223, 221, 216)), ('dripstone', (140, 110, 95)),
        ('tuff', (108, 108, 100)), ('granite', (149, 103, 85)),
        ('diorite', (188, 188, 190)), ('andesite', (136, 137, 137)),
        ('mossy', (104, 118, 88)), ('nether_brick', (44, 22, 26)),
        ('resin', (220, 120, 30)), ('cinnabar', (150, 40, 40)),
        ('sulfur', (208, 196, 70)), ('brick', (150, 96, 80)),
        ('stone', (130, 130, 130)), ('cobble', (127, 127, 127)),
    ]
    for k, col in kw:
        if k in base:
            return col

    extra = {
        'water': (60, 110, 200), 'lava': (216, 110, 28), 'soul_sand': (84, 64, 52),
        'soul_soil': (95, 73, 60), 'sand': (219, 207, 163), 'gravel': (130, 124, 120),
        'dirt': (134, 96, 67), 'grass_block': (110, 160, 70), 'short_grass': (110, 170, 70),
        'crafting_table': (124, 86, 51), 'hopper': (70, 72, 75), 'chest': (162, 120, 56),
    }
    if base in extra:
        return extra[base]

    h = zlib.crc32(base.encode('utf-8')) & 0xFFFFFF
    r, g, b = (h >> 16) & 255, (h >> 8) & 255, h & 255
    return ((r + 128) // 2, (g + 128) // 2, (b + 128) // 2)


# ---------------------------------------------------------------------------
# 日本語表示名
# ---------------------------------------------------------------------------
JP_FAMILY = {'wood': '木材', 'stone': '石系', 'copper': '銅', 'dye': '色付き',
             'glass': 'ガラス', 'froglight': '光源'}

_COLOR_JP = {
    'white': '白', 'orange': '橙', 'magenta': '赤紫', 'light_blue': '空色',
    'yellow': '黄', 'lime': '黄緑', 'pink': '桃', 'gray': '灰', 'light_gray': '薄灰',
    'cyan': '青緑', 'purple': '紫', 'blue': '青', 'brown': '茶', 'green': '緑',
    'red': '赤', 'black': '黒',
}
_WOOD_JP = {
    'oak': 'オーク', 'spruce': 'マツ', 'birch': 'シラカバ', 'jungle': 'ジャングル',
    'acacia': 'アカシア', 'dark_oak': 'ダークオーク', 'mangrove': 'マングローブ',
    'cherry': 'サクラ', 'pale_oak': '淡いオーク', 'bamboo': '竹',
    'crimson': 'クリムゾン', 'warped': 'ワープド', 'bamboo_mosaic': '竹細工',
}

_COLOR_JP.update({
    'white': '白色', 'orange': '橙色', 'magenta': '赤紫色', 'light_blue': '空色',
    'yellow': '黄色', 'lime': '黄緑色', 'pink': '桃色', 'gray': '灰色',
    'light_gray': '薄灰色', 'cyan': '青緑色', 'purple': '紫色', 'blue': '青色',
    'brown': '茶色', 'green': '緑色', 'red': '赤色', 'black': '黒色',
})
_PREFIX_JP = [
    ('polished_', '磨かれた'), ('smooth_', '滑らかな'), ('chiseled_', '模様入りの'),
    ('cracked_', 'ひび割れた'), ('mossy_', '苔むした'), ('cut_', '研がれた'),
    ('stripped_', '樹皮を剥いだ'), ('gilded_', '金張りの'),
    ('waxed_', '錆止めの'), ('exposed_', '風化し始めた'),
    ('weathered_', '風化した'), ('oxidized_', '酸化した'), ('infested_', '虫食いの'),
]
# 形（接尾辞）→ 日本語。長い接尾辞を先に判定する。
_FORM_JP = [
    ('_stained_glass_pane', 'の色付きガラス板'), ('_stained_glass', 'の色付きガラス'),
    ('_glazed_terracotta', 'の彩釉テラコッタ'), ('_concrete_powder', 'のコンクリートパウダー'),
    ('_wall_hanging_sign', 'の壁掛け吊り看板'), ('_hanging_sign', 'の吊り看板'),
    ('_wall_sign', 'の壁掛け看板'), ('_pressure_plate', 'の感圧板'),
    ('_fence_gate', 'のフェンスゲート'), ('_wall_banner', 'の壁掛けの旗'),
    ('_shulker_box', 'のシュルカーボックス'), ('_trapdoor', 'のトラップドア'),
    ('_fence', 'のフェンス'), ('_stairs', 'の階段'), ('_slab', 'のハーフブロック'),
    ('_button', 'のボタン'), ('_carpet', 'のカーペット'), ('_candle', 'のろうそく'),
    ('_banner', 'の旗'), ('_planks', 'の板'), ('_door', 'のドア'), ('_sign', 'の看板'),
    ('_wall', 'の塀'), ('_wool', 'の羊毛'), ('_bed', 'のベッド'), ('_log', 'の原木'),
    ('_stem', 'の幹'), ('_hyphae', 'の菌糸'), ('_wood', 'の木'), ('_leaves', 'の葉'),
    ('_sapling', 'の苗木'), ('_concrete', 'のコンクリート'), ('_terracotta', 'のテラコッタ'),
]
# 素材そのもの（形なし）
_MAT_JP = {
    'stone': '石', 'smooth_stone': '滑らかな石', 'cobblestone': '丸石',
    'mossy_cobblestone': '苔むした丸石', 'stone_brick': '石レンガ', 'stone_bricks': '石レンガ',
    'mossy_stone_brick': '苔むした石レンガ', 'granite': '花崗岩', 'diorite': '閃緑岩',
    'andesite': '安山岩', 'calcite': '方解石', 'tuff': '凝灰岩', 'tuff_brick': '凝灰岩レンガ',
    'tuff_bricks': '凝灰岩レンガ', 'deepslate': '深層岩', 'cobbled_deepslate': '深層岩の丸石',
    'deepslate_brick': '深層岩レンガ', 'deepslate_bricks': '深層岩レンガ',
    'deepslate_tile': '深層岩タイル', 'deepslate_tiles': '深層岩タイル',
    'sandstone': '砂岩', 'red_sandstone': '赤い砂岩', 'blackstone': '黒石',
    'gilded_blackstone': '金張りの黒石', 'polished_blackstone_brick': '磨かれた黒石レンガ',
    'polished_blackstone_bricks': '磨かれた黒石レンガ', 'basalt': '玄武岩',
    'quartz': 'クォーツ', 'quartz_block': 'クォーツブロック', 'quartz_brick': 'クォーツレンガ',
    'quartz_bricks': 'クォーツレンガ', 'quartz_pillar': 'クォーツの柱', 'smooth_quartz': '滑らかなクォーツ',
    'prismarine': 'プリズマリン', 'prismarine_brick': 'プリズマリンレンガ',
    'prismarine_bricks': 'プリズマリンレンガ', 'dark_prismarine': '暗いプリズマリン',
    'purpur': 'プルプァ', 'purpur_block': 'プルプァブロック', 'purpur_pillar': 'プルプァの柱',
    'brick': 'レンガ', 'bricks': 'レンガ', 'nether_brick': 'ネザーレンガ', 'nether_bricks': 'ネザーレンガ',
    'red_nether_brick': '赤いネザーレンガ', 'red_nether_bricks': '赤いネザーレンガ',
    'end_stone_brick': 'エンドストーンレンガ', 'end_stone_bricks': 'エンドストーンレンガ',
    'mud_brick': '泥レンガ', 'mud_bricks': '泥レンガ', 'resin_brick': '樹脂レンガ', 'resin_bricks': '樹脂レンガ',
    'cinnabar': '辰砂', 'cinnabar_brick': '辰砂レンガ', 'cinnabar_bricks': '辰砂レンガ',
    'sulfur': '硫黄', 'sulfur_brick': '硫黄レンガ', 'sulfur_bricks': '硫黄レンガ',
    'dripstone_block': '鍾乳石', 'dripstone': '鍾乳石',
    'glass': 'ガラス', 'tinted_glass': '遮光ガラス', 'glass_pane': 'ガラス板',
    'terracotta': 'テラコッタ',
    'copper': '銅', 'copper_block': '銅ブロック', 'cut_copper': '切り込み入りの銅',
    'chiseled_copper': '模様入りの銅', 'copper_bulb': '銅電球', 'copper_grate': '銅格子',
    'copper_chest': '銅のチェスト', 'copper_bars': '銅の鉄格子', 'copper_chain': '銅の鎖',
    'copper_lantern': '銅のランタン', 'copper_torch': '銅の松明', 'copper_golem_statue': '銅ゴーレム像',
    'candle': 'ろうそく', 'shulker_box': 'シュルカーボックス',
    'ochre_froglight': '黄土色のフロッグライト', 'verdant_froglight': '新緑色のフロッグライト',
    'pearlescent_froglight': '真珠色のフロッグライト',
    'bamboo_block': '竹ブロック', 'petrified_oak': '化石化したオーク',
    # よく使う機能/地形ブロック（置き換え不可表示用）
    'water': '水', 'lava': '溶岩', 'air': '空気', 'soul_sand': 'ソウルサンド',
    'soul_soil': 'ソウルソイル', 'soul_campfire': '魂のたき火', 'campfire': 'たき火',
    'magma_block': 'マグマブロック', 'bubble_column': '気泡の柱', 'hopper': 'ホッパー',
    'chest': 'チェスト', 'trapped_chest': 'トラップチェスト', 'crafting_table': '作業台',
    'furnace': 'かまど', 'sand': '砂', 'red_sand': '赤い砂', 'gravel': '砂利', 'dirt': '土',
    'coarse_dirt': '粗い土', 'grass_block': '草ブロック', 'short_grass': '草', 'tall_grass': '背の高い草',
    'dirt_path': '土の道', 'clay': '粘土', 'obsidian': '黒曜石', 'glowstone': 'グロウストーン',
    'sea_lantern': 'シーランタン', 'redstone_block': 'レッドストーンブロック', 'slime_block': 'スライムブロック',
    'honey_block': 'ハチミツブロック', 'iron_block': '鉄ブロック', 'gold_block': '金ブロック',
    'note_block': '音符ブロック', 'bookshelf': '本棚', 'ice': '氷', 'packed_ice': '氷塊',
    'snow_block': '雪ブロック', 'pumpkin': 'カボチャ', 'melon': 'スイカ', 'hay_block': '干し草の俵',
    'bricks_block': 'レンガ',
}

_MAT_JP.update({
    'activator_rail': 'アクティベーターレール',
    'barrel': '樽',
    'redstone': 'レッドストーンダスト',
    'powered_rail': 'パワードレール',
    'detector_rail': 'ディテクターレール',
    'rail': 'レール',
    'wither_rose': 'ウィザーローズ',
    'comparator': 'レッドストーンコンパレーター',
    'redstone_comparator': 'レッドストーンコンパレーター',
    'redstone_torch': 'レッドストーントーチ',
    'redstone_wall_torch': '壁付けレッドストーントーチ',
    'redstone_wire': 'レッドストーンダスト',
    'lever': 'レバー',
    'observer': 'オブザーバー',
    'repeater': 'レッドストーンリピーター',
    'redstone_repeater': 'レッドストーンリピーター',
    'composter': 'コンポスター',
    'sticky_piston': '粘着ピストン',
    'piston': 'ピストン',
    'piston_head': 'ピストンヘッド',
    'moving_piston': '動くピストン',
    'dropper': 'ドロッパー',
    'dispenser': 'ディスペンサー',
    'cauldron': '大釜',
    'water_cauldron': '水入り大釜',
    'lava_cauldron': '溶岩入り大釜',
    'powder_snow_cauldron': '粉雪入り大釜',
    'snow': '雪',
    'target': '的',
    'vine': 'ツタ',
    'lava_bucket': '溶岩入りバケツ',
    'water_bucket': '水入りバケツ',
    'bucket': 'バケツ',
    'player_head': 'プレイヤーの頭',
    'player_wall_head': '壁付けプレイヤーの頭',
    'zombie_head': 'ゾンビの頭',
    'zombie_wall_head': '壁付けゾンビの頭',
    'skeleton_skull': 'スケルトンの頭蓋骨',
    'skeleton_wall_skull': '壁付けスケルトンの頭蓋骨',
    'wither_skeleton_skull': 'ウィザースケルトンの頭蓋骨',
    'wither_skeleton_wall_skull': '壁付けウィザースケルトンの頭蓋骨',
    'creeper_head': 'クリーパーの頭',
    'creeper_wall_head': '壁付けクリーパーの頭',
    'dragon_head': 'ドラゴンの頭',
    'dragon_wall_head': '壁付けドラゴンの頭',
    'piglin_head': 'ピグリンの頭',
    'piglin_wall_head': '壁付けピグリンの頭',
    'ender_chest': 'エンダーチェスト',
    'end_portal_frame': 'エンドポータルフレーム',
    'lightning_rod': '避雷針',
    'redstone_lamp': 'レッドストーンランプ',
    'daylight_detector': '日照センサー',
    'tripwire_hook': 'トリップワイヤーフック',
    'sculk_sensor': 'スカルクセンサー',
    'calibrated_sculk_sensor': '調律されたスカルクセンサー',
    'crafter': 'クラフター',
    'beacon': 'ビーコン',
    'anvil': '金床',
    'chipped_anvil': '欠けた金床',
    'damaged_anvil': '壊れかけの金床',
    'brewing_stand': '醸造台',
    'enchanting_table': 'エンチャントテーブル',
    'cartography_table': '製図台',
    'smithing_table': '鍛冶台',
    'fletching_table': '矢細工台',
    'grindstone': '砥石',
    'stonecutter': '石切台',
    'loom': '機織り機',
    'lectern': '書見台',
    'bell': '鐘',
    'campfire': '焚き火',
    'soul_campfire': '魂の焚き火',
    'chain': '鎖',
    'iron_bars': '鉄格子',
    'ladder': 'はしご',
    'scaffolding': '足場',
    'warped_button': '歪んだボタン',
    'warped_trapdoor': '歪んだトラップドア',
    'warped_fence_gate': '歪んだフェンスゲート',
    'warped_door': '歪んだドア',
    'warped_sign': '歪んだ看板',
    'warped_hanging_sign': '歪んだ吊り看板',
    'crimson_button': '真紅のボタン',
    'crimson_trapdoor': '真紅のトラップドア',
    'crimson_fence_gate': '真紅のフェンスゲート',
    'crimson_door': '真紅のドア',
    'crimson_sign': '真紅の看板',
    'crimson_hanging_sign': '真紅の吊り看板',
})

_TOKEN_JP = {
    'block': 'ブロック', 'bricks': 'レンガ', 'brick': 'レンガ', 'tiles': 'タイル', 'tile': 'タイル',
    'pillar': '柱', 'chiseled': '模様入り', 'cracked': 'ひび割れた', 'polished': '磨かれた',
    'smooth': '滑らかな', 'cut': '研がれた', 'mossy': '苔むした', 'stripped': '樹皮を剥いだ',
    'waxed': '錆止めされた', 'exposed': '風化し始めた', 'weathered': '風化した', 'oxidized': '酸化した',
    'stairs': '階段', 'slab': 'ハーフブロック', 'wall': '塀', 'fence': 'フェンス',
    'gate': 'ゲート', 'door': 'ドア', 'trapdoor': 'トラップドア', 'button': 'ボタン',
    'pressure': '感圧', 'plate': '板', 'sign': '看板', 'hanging': '吊り', 'leaves': '葉',
    'sapling': '苗木', 'log': '原木', 'wood': '木', 'stem': '幹', 'hyphae': '菌糸',
    'glass': 'ガラス', 'pane': '板', 'stained': '色付き', 'concrete': 'コンクリート',
    'powder': 'パウダー', 'terracotta': 'テラコッタ', 'glazed': '彩釉',
    'wool': '羊毛', 'carpet': 'カーペット', 'candle': 'ろうそく', 'banner': '旗',
    'shulker': 'シュルカー', 'box': 'ボックス', 'ore': '鉱石', 'raw': '原石',
    'deepslate': '深層岩', 'stone': '石', 'blackstone': '黒石', 'sandstone': '砂岩',
    'sand': '砂', 'red': '赤い', 'blue': '青い', 'green': '緑の', 'yellow': '黄色の',
    'white': '白色の', 'black': '黒色の', 'gray': '灰色の', 'light': '薄い',
    'dark': '暗い', 'pink': '桃色の', 'purple': '紫色の', 'cyan': '青緑色の',
    'lime': '黄緑色の', 'orange': '橙色の', 'magenta': '赤紫色の', 'brown': '茶色の',
    'iron': '鉄', 'gold': '金', 'copper': '銅', 'diamond': 'ダイヤモンド', 'emerald': 'エメラルド',
    'lapis': 'ラピスラズリ', 'coal': '石炭', 'quartz': 'クォーツ', 'nether': 'ネザー',
    'redstone': 'レッドストーン', 'wire': 'ダスト', 'torch': 'トーチ',
    'head': '頭', 'skull': '頭蓋骨', 'cauldron': '大釜', 'lava': '溶岩', 'water': '水',
    'powder': '粉', 'snow': '雪', 'piston': 'ピストン', 'moving': '動く',
    'end': 'エンド', 'sea': 'シー', 'lantern': 'ランタン', 'glowstone': 'グロウストーン',
    'froglight': 'フロッグライト', 'prismarine': 'プリズマリン', 'purpur': 'プルプァ',
    'basalt': '玄武岩', 'calcite': '方解石', 'tuff': '凝灰岩', 'dripstone': '鍾乳石',
    'granite': '花崗岩', 'diorite': '閃緑岩', 'andesite': '安山岩', 'obsidian': '黒曜石',
}


def _token_fallback_jp(mat):
    parts = [p for p in mat.split('_') if p]
    if not parts:
        return mat
    translated = []
    known = 0
    i = 0
    while i < len(parts):
        two = '_'.join(parts[i:i + 2])
        if two in _MAT_JP:
            translated.append(_MAT_JP[two])
            known += 2
            i += 2
            continue
        token = parts[i]
        if token in _TOKEN_JP:
            translated.append(_TOKEN_JP[token])
            known += 1
        else:
            translated.append(token)
        i += 1
    return ''.join(translated) if known else mat


def jp_material(mat):
    if mat in _MAT_JP:
        return _MAT_JP[mat]
    if mat in _WOOD_JP:
        return _WOOD_JP[mat]
    for c in DYES:
        if mat == c:
            return _COLOR_JP[c]
        if mat.startswith(c + '_'):
            return _COLOR_JP[c] + jp_material(mat[len(c) + 1:])
    if mat.endswith('_bricks'):
        return jp_material(mat[:-7]) + 'レンガ'
    for pre, jp in _PREFIX_JP:
        if mat.startswith(pre):
            return jp + jp_material(mat[len(pre):])
    return _token_fallback_jp(mat)


def jp_name(bid):
    """ブロックIDを分かりやすい日本語名にする。"""
    base = strip_ns(bid)
    if base in _MAT_JP:
        return _MAT_JP[base]
    for suf, jp in _FORM_JP:
        if base.endswith(suf):
            return jp_material(base[:-len(suf)]) + jp
    return jp_material(base)


def display_name(bid):
    return strip_ns(bid)
