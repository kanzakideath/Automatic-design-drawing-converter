# -*- coding: utf-8 -*-
"""
設計図素材変換ツール  -  GUI

.litematic をドラッグ&ドロップ（またはクリックで選択）すると、素材を自動検出し、
「置き換える素材」と「置き換えできない素材」を画像・日本語名つきで一覧表示する。
置き換え先はクリックして候補から選び直せる。「開始」で新しいファイルを生成する。
ライト／ダークのテーマ切替に対応。
"""

import os
import sys
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    _HAS_DND = True
except Exception:
    _HAS_DND = False

from PIL import ImageTk

import blockdata as bd
import converter
import icons

APP_TITLE = '設計図素材変換ツール'
KEEP = '__keep__'

CATEGORY_LABELS = [
    ('recommended', 'おすすめ（同じ形）'),
    ('wood', '木材'),
    ('stone', '石・建材'),
    ('glass', 'ガラス'),
    ('color', '色付き'),
    ('copper', '銅'),
    ('redstone', 'レッドストーン'),
    ('utility', '機能・作業'),
    ('natural', '自然・地形'),
    ('plant', '植物'),
    ('light', '光源'),
    ('ore', '鉱石・金属'),
    ('decoration', '装飾'),
    ('other', 'その他'),
    ('all', 'すべて'),
]
CATEGORY_BY_LABEL = {label: key for key, label in CATEGORY_LABELS}
CATEGORY_NAME = {key: label for key, label in CATEGORY_LABELS}


def block_category(bid):
    base = bd.strip_ns(bid)
    fam = bd.family_of(base)
    if fam == 'wood':
        return 'wood'
    if fam == 'stone':
        return 'stone'
    if fam == 'glass':
        return 'glass'
    if fam == 'dye':
        return 'color'
    if fam == 'copper' or 'copper' in base:
        return 'copper'
    if fam == 'froglight':
        return 'light'

    if (base.endswith(('_log', '_wood', '_stem', '_hyphae', '_planks', '_leaves', '_sapling'))
            or base.startswith('stripped_') or base.startswith(('oak_', 'spruce_', 'birch_', 'jungle_', 'acacia_',
                                                                 'dark_oak_', 'mangrove_', 'cherry_', 'pale_oak_',
                                                                 'bamboo_', 'crimson_', 'warped_'))):
        return 'wood'
    if 'glass' in base:
        return 'glass'
    if any(base.endswith('_' + form) for form in (
            'wool', 'carpet', 'bed', 'concrete', 'concrete_powder', 'terracotta',
            'glazed_terracotta', 'candle', 'shulker_box', 'banner', 'wall_banner')):
        return 'color'
    if any(k in base for k in ('redstone', 'piston', 'observer', 'repeater', 'comparator', 'rail',
                               'target', 'lever', 'button', 'pressure_plate', 'tripwire', 'daylight_detector',
                               'sculk_sensor', 'crafter', 'dispenser', 'dropper', 'hopper')):
        return 'redstone'
    if any(k in base for k in ('stone', 'slate', 'tuff', 'granite', 'diorite', 'andesite', 'sandstone',
                               'blackstone', 'basalt', 'quartz', 'brick', 'prismarine', 'purpur',
                               'calcite', 'dripstone', 'cobble', 'tile')):
        return 'stone'
    if any(k in base for k in ('ore', 'raw_', 'iron', 'gold', 'diamond', 'emerald', 'lapis',
                               'netherite', 'coal_block', 'amethyst', 'copper_block')):
        return 'ore'
    if any(k in base for k in ('torch', 'lantern', 'lamp', 'light', 'glowstone', 'sea_lantern',
                               'shroomlight', 'magma_block', 'fire', 'candle')):
        return 'light'
    if any(k in base for k in ('chest', 'barrel', 'furnace', 'crafting_table', 'anvil', 'table',
                               'beacon', 'brewing_stand', 'cauldron', 'loom', 'stonecutter',
                               'cartography', 'grindstone', 'lectern', 'composter', 'bell', 'bed')):
        return 'utility'
    if any(k in base for k in ('dirt', 'grass', 'sand', 'gravel', 'clay', 'mud', 'snow', 'ice',
                               'water', 'lava', 'nylium', 'netherrack', 'soul_', 'end_stone',
                               'obsidian', 'moss', 'rooted', 'podzol', 'mycelium')):
        return 'natural'
    if any(k in base for k in ('flower', 'mushroom', 'grass', 'fern', 'vine', 'leaves', 'sapling',
                               'kelp', 'coral', 'bush', 'roots', 'wart', 'cactus', 'sugar_cane',
                               'bamboo', 'pumpkin', 'melon', 'hay_block')):
        return 'plant'
    if any(k in base for k in ('sign', 'painting', 'pot', 'skull', 'head', 'banner', 'carpet',
                               'bookshelf', 'decorated_pot', 'chain', 'bars', 'door', 'trapdoor',
                               'fence', 'wall', 'stairs', 'slab')):
        return 'decoration'
    return 'other'

LIGHT = {
    'BG': '#f3f4f6', 'CARD': '#ffffff', 'ROW_ALT': '#f7f8fa', 'TEXT': '#1f2430',
    'MUTED': '#6b7280', 'ACCENT': '#2d6cdf', 'ACCENT_DK': '#1f4fb0', 'BORDER': '#d9dce3',
    'DROP_BG': '#eaf0fb', 'DROP_FG': '#1f4fb0', 'TARGET_BG': '#eef6ee', 'KEEP_BG': '#eeeeee',
    'BADGE_BG': '#e8edf7', 'BADGE_FG': '#1f4fb0', 'NBADGE_BG': '#ececf0', 'NBADGE_FG': '#6b7280',
    'HOVER': '#dceaff', 'REC_BG': '#fff7e6', 'BTN_BG': '#e5e7eb',
}
DARK = {
    'BG': '#1e1f25', 'CARD': '#26272f', 'ROW_ALT': '#2b2d36', 'TEXT': '#e8eaed',
    'MUTED': '#9aa0aa', 'ACCENT': '#4f86f7', 'ACCENT_DK': '#3b6fd0', 'BORDER': '#3a3d47',
    'DROP_BG': '#23304a', 'DROP_FG': '#bcd0f5', 'TARGET_BG': '#243a2c', 'KEEP_BG': '#33353d',
    'BADGE_BG': '#2f3850', 'BADGE_FG': '#bcd0f5', 'NBADGE_BG': '#34363f', 'NBADGE_FG': '#9aa0aa',
    'HOVER': '#33425e', 'REC_BG': '#3b3520', 'BTN_BG': '#3a3d47',
}
C = dict(LIGHT)   # 現在のパレット


class App:
    def __init__(self, root):
        self.root = root
        self.dark = False
        self.icon_cache = {}
        self.src_path = None
        self.loaded_nbt = None
        self.convs = []
        self.others = []
        self.rows = []
        self.overrides = {}        # source_full_id -> target_base / KEEP
        self._wheel_target = None
        self._regid2file = {}
        self._info_text = 'ファイル未選択'
        self._drop_text = self._default_drop_text()
        self._vnote_text = '（読み込み時に自動判定）'
        self._build_ui()
        if len(sys.argv) > 1 and os.path.isfile(sys.argv[1]):
            self.root.after(120, lambda: self.load_file(sys.argv[1]))

    # ------------------------------------------------------------------ icons
    def get_icon(self, bid, size=44):
        key = (bid, size)
        if key not in self.icon_cache:
            self.icon_cache[key] = ImageTk.PhotoImage(icons.render_block_image(bid, size))
        return self.icon_cache[key]

    def _default_drop_text(self):
        return ('ここに .litematic ファイルをドラッグ&ドロップ\nまたはクリックして選択'
                if _HAS_DND else 'ここをクリックして .litematic を選択')

    # --------------------------------------------------------------------- UI
    def _build_ui(self):
        self.root.title(APP_TITLE)
        self.root.configure(bg=C['BG'])
        self.root.geometry('900x740')
        self.root.minsize(780, 600)

        # ヘッダ（タイトル + テーマ切替）
        header = tk.Frame(self.root, bg=C['BG'])
        header.pack(fill='x', padx=18, pady=(14, 4))
        toprow = tk.Frame(header, bg=C['BG'])
        toprow.pack(fill='x')
        tk.Label(toprow, text=APP_TITLE, bg=C['BG'], fg=C['TEXT'],
                 font=('Yu Gothic UI', 17, 'bold')).pack(side='left')
        self.theme_btn = tk.Button(toprow, text=self._theme_label(), command=self.toggle_theme,
                                   bg=C['BTN_BG'], fg=C['TEXT'], relief='flat',
                                   font=('Yu Gothic UI', 9), padx=10, pady=4, cursor='hand2')
        self.theme_btn.pack(side='right')
        tk.Label(header, text='設計図(.litematic)の素材を、入手しやすい一般的な素材へ置き換えます。',
                 bg=C['BG'], fg=C['MUTED'], font=('Yu Gothic UI', 10)).pack(anchor='w')

        # ドロップゾーン
        self.drop = tk.Label(self.root, text=self._drop_text, bg=C['DROP_BG'], fg=C['DROP_FG'],
                             font=('Yu Gothic UI', 12, 'bold'), relief='ridge', bd=2,
                             padx=10, pady=20, cursor='hand2')
        self.drop.pack(fill='x', padx=18, pady=(4, 8))
        self.drop.bind('<Button-1>', lambda e: self.choose_file())
        if _HAS_DND:
            self.drop.drop_target_register(DND_FILES)
            self.drop.dnd_bind('<<Drop>>', self.on_drop)

        # バージョン選択
        vrow = tk.Frame(self.root, bg=C['BG'])
        vrow.pack(fill='x', padx=20, pady=(2, 0))
        tk.Label(vrow, text='対象バージョン:', bg=C['BG'], fg=C['TEXT'],
                 font=('Yu Gothic UI', 9, 'bold')).pack(side='left')
        regs = bd.available_registries()
        self._regid2file = {}
        labels = []
        for r in regs:
            mem = r.get('members', [r['id']])
            label = r['id'] if len(mem) == 1 else '%s (%s〜)' % (r['id'], mem[0])
            self._regid2file[label] = r['file']
            labels.append(label)
        cur = bd.active_registry()
        cur_label = next((l for l, f in self._regid2file.items() if f == bd.ACTIVE_FILE),
                         labels[0] if labels else '')
        self.version_var = tk.StringVar(value=cur_label)
        self.version_combo = ttk.Combobox(vrow, textvariable=self.version_var, values=labels,
                                          state='readonly', width=20, font=('Yu Gothic UI', 9))
        self.version_combo.pack(side='left', padx=(6, 8))
        self.version_combo.bind('<<ComboboxSelected>>', self.on_version_change)
        self.version_note = tk.Label(vrow, text=self._vnote_text, bg=C['BG'], fg=C['MUTED'],
                                     font=('Yu Gothic UI', 8))
        self.version_note.pack(side='left')

        # ファイル情報
        self.info = tk.Label(self.root, text=self._info_text, bg=C['BG'], fg=C['MUTED'],
                             font=('Yu Gothic UI', 9), anchor='w', justify='left')
        self.info.pack(fill='x', padx=20, pady=(0, 2))

        # 見出し
        self.heading = tk.Label(self.root, text='', bg=C['BG'], fg=C['TEXT'],
                                font=('Yu Gothic UI', 12, 'bold'), anchor='w')
        self.heading.pack(fill='x', padx=20, pady=(4, 0))
        tk.Label(self.root,
                 text='※ 初期状態では入手しやすい素材へ自動変換します。'
                      ' 置き換え先をクリックするとカテゴリ/検索から全ブロックを選べます。',
                 bg=C['BG'], fg=C['MUTED'], font=('Yu Gothic UI', 8), anchor='w',
                 justify='left').pack(fill='x', padx=20, pady=(0, 4))

        # スクロール可能リスト
        body = tk.Frame(self.root, bg=C['BG'])
        body.pack(fill='both', expand=True, padx=18, pady=(2, 6))
        self.canvas = tk.Canvas(body, bg=C['CARD'], highlightthickness=1,
                                highlightbackground=C['BORDER'])
        self.canvas.pack(side='left', fill='both', expand=True)
        sb = tk.Scrollbar(body, orient='vertical', command=self.canvas.yview)
        sb.pack(side='right', fill='y')
        self.canvas.configure(yscrollcommand=sb.set)
        self.list_frame = tk.Frame(self.canvas, bg=C['CARD'])
        self._win = self.canvas.create_window((0, 0), window=self.list_frame, anchor='nw')
        self.list_frame.bind('<Configure>',
                             lambda e: self.canvas.configure(scrollregion=self.canvas.bbox('all')))
        self.canvas.bind('<Configure>',
                         lambda e: self.canvas.itemconfigure(self._win, width=e.width))
        self._bind_wheel(self.canvas, self.canvas)

        # フッタ
        footer = tk.Frame(self.root, bg=C['BG'])
        footer.pack(fill='x', padx=18, pady=(2, 14))
        self.start_btn = tk.Button(footer, text='開始（変換して新規ファイルを生成）',
                                   command=self.do_convert, bg=C['ACCENT'], fg='white',
                                   activebackground=C['ACCENT_DK'], activeforeground='white',
                                   font=('Yu Gothic UI', 12, 'bold'), relief='flat',
                                   padx=16, pady=10, cursor='hand2',
                                   state='normal' if self.convs else 'disabled')
        self.start_btn.pack(side='right')
        self.reset_btn = tk.Button(footer, text='別のファイル', command=self.reset,
                                   bg=C['BTN_BG'], fg=C['TEXT'], relief='flat',
                                   font=('Yu Gothic UI', 10), padx=12, pady=8, cursor='hand2',
                                   state='normal' if self.src_path else 'disabled')
        self.reset_btn.pack(side='right', padx=(0, 8))
        self.status_lbl = tk.Label(footer, text='', bg=C['BG'], fg=C['MUTED'],
                                   font=('Yu Gothic UI', 9), anchor='w')
        self.status_lbl.pack(side='left')

        self._build_rows()

    def _theme_label(self):
        return '☀ ライトモード' if self.dark else '🌙 ダークモード'

    # --------------------------------------------------------------- theme
    def toggle_theme(self):
        global C
        self.dark = not self.dark
        C = dict(DARK if self.dark else LIGHT)
        for w in self.root.winfo_children():
            w.destroy()
        self._build_ui()
        if self.loaded_nbt is not None:
            self.version_note.configure(text=self._vnote_text)
            self.info.configure(text=self._info_text)
            self.drop.configure(text=self._drop_text)
            self._rescan()

    # --------------------------------------------------------------- wheel
    def _bind_wheel(self, widget, target_canvas):
        widget.bind('<Enter>', lambda e: setattr(self, '_wheel_target', target_canvas))
        if not getattr(self, '_wheel_bound', False):
            self.root.bind_all('<MouseWheel>', self._on_wheel)
            self._wheel_bound = True

    def _on_wheel(self, e):
        c = self._wheel_target
        if c is not None:
            try:
                c.yview_scroll(int(-e.delta / 120), 'units')
            except tk.TclError:
                self._wheel_target = None

    # --------------------------------------------------------------- file io
    def choose_file(self):
        path = filedialog.askopenfilename(
            title='設計図ファイルを選択',
            filetypes=[('Litematica 設計図', '*.litematic'), ('すべて', '*.*')])
        if path:
            self.load_file(path)

    def on_drop(self, event):
        try:
            paths = self.root.tk.splitlist(event.data)
        except Exception:
            paths = [event.data.strip('{}')]
        if paths:
            self.load_file(paths[0])

    def load_file(self, path):
        if not os.path.isfile(path):
            messagebox.showerror(APP_TITLE, 'ファイルが見つかりません:\n%s' % path)
            return
        try:
            nbt = converter.load(path)
        except Exception as e:
            messagebox.showerror(APP_TITLE,
                                 '読み込みに失敗しました。\n.litematic 形式ですか？\n\n%s' % e)
            return

        self.src_path = path
        self.loaded_nbt = nbt
        self.overrides = {}

        dv = None
        try:
            dv = int(nbt.get('MinecraftDataVersion'))
        except Exception:
            dv = None
        f = bd.file_for_dataversion(dv)
        if f:
            bd.set_active_file(f)
            for label, file in self._regid2file.items():
                if file == f:
                    self.version_var.set(label)
                    break
            reg = bd.active_registry()
            if reg:
                self._vnote_text = '自動判定: %s（DataVersion %s）' % (reg['id'], dv)
                self.version_note.configure(text=self._vnote_text)

        try:
            md = nbt.get('Metadata', {})
            name = str(md.get('Name', ''))
            total = int(md.get('TotalBlocks', 0))
            self._info_text = ('ファイル: %s\n設計図名: %s   /  総ブロック: %s   /  パレット: %d 種'
                               % (os.path.basename(path), name or '(無名)', total,
                                  converter.palette_size(nbt)))
        except Exception:
            self._info_text = 'ファイル: %s' % os.path.basename(path)
        self.info.configure(text=self._info_text)

        self._drop_text = ('読み込み完了: %s\n（別のファイルに変えるにはクリック/ドロップ）'
                           % os.path.basename(path))
        self.drop.configure(text=self._drop_text)
        self._rescan()
        self.reset_btn.configure(state='normal')

    def _rescan(self):
        if self.loaded_nbt is None:
            return
        self.convs, self.others = converter.scan_all(self.loaded_nbt)
        self._build_rows()
        self.start_btn.configure(state='normal' if self.convs else 'disabled')

    def on_version_change(self, event=None):
        label = self.version_var.get()
        f = self._regid2file.get(label)
        if f and f != bd.ACTIVE_FILE:
            bd.set_active_file(f)
            reg = bd.active_registry()
            if reg:
                self._vnote_text = '手動選択: %s' % reg['id']
                self.version_note.configure(text=self._vnote_text)
            self._rescan()

    def reset(self):
        self.src_path = None
        self.loaded_nbt = None
        self.convs = []
        self.others = []
        self.overrides = {}
        self._info_text = 'ファイル未選択'
        self._drop_text = self._default_drop_text()
        self._vnote_text = '（読み込み時に自動判定）'
        self._build_rows()
        self.start_btn.configure(state='disabled')
        self.reset_btn.configure(state='disabled')
        self.info.configure(text=self._info_text)
        self.heading.configure(text='')
        self.status_lbl.configure(text='')
        self.drop.configure(text=self._drop_text)
        self.version_note.configure(text=self._vnote_text)

    # --------------------------------------------------------------- rows
    def _build_rows(self):
        for w in self.list_frame.winfo_children():
            w.destroy()
        self.rows = []

        if not self.convs and not self.others:
            self.heading.configure(text='以下の素材を置き換えます')
            tk.Label(self.list_frame,
                     text='ファイルを読み込むと、ここに素材が表示されます。',
                     bg=C['CARD'], fg=C['MUTED'], font=('Yu Gothic UI', 10), pady=40).pack(fill='x')
            return

        self.heading.configure(text='自動で置き換える素材 %d 種類 ／ そのままの素材 %d 種類'
                               % (len(self.convs), len(self.others)))

        idx = 0
        if self.convs:
            self._section('▼ 自動で置き換える素材（クリックで変換先を変更できます）', C['ACCENT'])
        for conv in self.convs:
            self._make_row(idx, conv)
            idx += 1

        if self.others:
            self._section('▼ そのままの素材（必要ならクリックで置き換えできます）', C['MUTED'])
            for bid, count in self.others:
                self._make_nonconv_row(idx, bid, count)
                idx += 1

    def _section(self, text, color):
        f = tk.Frame(self.list_frame, bg=C['CARD'])
        f.pack(fill='x', pady=(10, 2))
        tk.Label(f, text=text, bg=C['CARD'], fg=color,
                 font=('Yu Gothic UI', 10, 'bold')).pack(anchor='w', padx=12)
        self._bind_wheel(f, self.canvas)

    def _name_block(self, parent, bid, bgc):
        fr = tk.Frame(parent, bg=bgc)
        tk.Label(fr, text=bd.jp_name(bid), bg=bgc, fg=C['TEXT'],
                 font=('Yu Gothic UI', 11), anchor='w', justify='left',
                 wraplength=230).pack(anchor='w', fill='x')
        tk.Label(fr, text=bd.strip_ns(bid), bg=bgc, fg=C['MUTED'],
                 font=('Consolas', 8), anchor='w', justify='left',
                 wraplength=230).pack(anchor='w', fill='x')
        return fr

    def _make_row(self, idx, conv):
        bgc = C['CARD'] if idx % 2 == 0 else C['ROW_ALT']
        row = tk.Frame(self.list_frame, bg=bgc, pady=6, padx=10)
        row.pack(fill='x')
        row.grid_columnconfigure(2, weight=1, minsize=220)
        row.grid_columnconfigure(5, weight=1, minsize=280)
        self._bind_wheel(row, self.canvas)

        fam = bd.family_of(conv.source)
        tk.Label(row, text=bd.JP_FAMILY.get(fam, ''), bg=C['BADGE_BG'], fg=C['BADGE_FG'],
                 font=('Yu Gothic UI', 8, 'bold'), width=5, padx=2).grid(
                     row=0, column=0, sticky='w', padx=(0, 8))

        si = self.get_icon(bd.strip_ns(conv.source))
        sl = tk.Label(row, image=si, bg=bgc)
        sl.image = si
        sl.grid(row=0, column=1, sticky='w')
        self._name_block(row, conv.source, bgc).grid(
            row=0, column=2, sticky='ew', padx=(6, 8))
        if conv.count > 1:
            tk.Label(row, text='×%d' % conv.count, bg=bgc, fg=C['MUTED'],
                     font=('Yu Gothic UI', 8)).grid(row=0, column=3, sticky='w', padx=(0, 4))

        tk.Label(row, text='→', bg=bgc, fg=C['MUTED'],
                 font=('Yu Gothic UI', 14, 'bold')).grid(row=0, column=4, padx=8)

        target_btn = tk.Button(row, compound='left', bg=C['TARGET_BG'], fg=C['TEXT'],
                               relief='groove', bd=1, anchor='w', justify='left',
                               wraplength=260,
                               font=('Yu Gothic UI', 10), cursor='hand2', padx=6, pady=4)
        target_btn.grid(row=0, column=5, sticky='ew')
        tk.Label(row, text='▼ 変更', bg=bgc, fg=C['ACCENT'],
                 font=('Yu Gothic UI', 8)).grid(row=0, column=6, sticky='w', padx=(8, 0))

        # 以前の選択（override）を、現バージョンで有効なら復元
        ov = self.overrides.get(conv.source)
        if ov is not None and (ov == KEEP or bd.is_valid_block(ov)):
            target = ov
        else:
            target = conv.target
        rowdata = {'conv': conv, 'target': target, 'btn': target_btn, 'bg': bgc}
        target_btn.configure(command=lambda r=rowdata: self.open_picker(r))
        self.rows.append(rowdata)
        self._refresh_target(rowdata)

    def _make_nonconv_row(self, idx, bid, count):
        bgc = C['CARD'] if idx % 2 == 0 else C['ROW_ALT']
        row = tk.Frame(self.list_frame, bg=bgc, pady=5, padx=10)
        row.pack(fill='x')
        row.grid_columnconfigure(2, weight=1, minsize=220)
        row.grid_columnconfigure(5, weight=1, minsize=280)
        self._bind_wheel(row, self.canvas)
        tk.Label(row, text='任意', bg=C['NBADGE_BG'], fg=C['NBADGE_FG'],
                 font=('Yu Gothic UI', 8, 'bold'), width=5, padx=2).grid(
                      row=0, column=0, sticky='w', padx=(0, 8))
        ic = self.get_icon(bd.strip_ns(bid))
        il = tk.Label(row, image=ic, bg=bgc)
        il.image = ic
        il.grid(row=0, column=1, sticky='w')
        self._name_block(row, bid, bgc).grid(row=0, column=2, sticky='ew', padx=(6, 8))
        if count > 1:
            tk.Label(row, text='×%d' % count, bg=bgc, fg=C['MUTED'],
                     font=('Yu Gothic UI', 8)).grid(row=0, column=3, sticky='w', padx=(0, 4))
        tk.Label(row, text='→', bg=bgc, fg=C['MUTED'],
                 font=('Yu Gothic UI', 14, 'bold')).grid(row=0, column=4, padx=8)

        target_btn = tk.Button(row, compound='left', bg=C['KEEP_BG'], fg=C['MUTED'],
                               relief='groove', bd=1, anchor='w', justify='left',
                               wraplength=260,
                               font=('Yu Gothic UI', 10), cursor='hand2', padx=6, pady=4)
        target_btn.grid(row=0, column=5, sticky='ew')
        tk.Label(row, text='▼ 変更', bg=bgc, fg=C['ACCENT'],
                 font=('Yu Gothic UI', 8)).grid(row=0, column=6, sticky='w', padx=(8, 0))

        conv = converter.Conversion(bid, bd.strip_ns(bid), [], count)
        ov = self.overrides.get(bid)
        target = ov if (ov is not None and (ov == KEEP or bd.is_valid_block(ov))) else KEEP
        rowdata = {'conv': conv, 'target': target, 'btn': target_btn, 'bg': bgc}
        target_btn.configure(command=lambda r=rowdata: self.open_picker(r))
        self.rows.append(rowdata)
        self._refresh_target(rowdata)

    def _refresh_target(self, rowdata):
        btn = rowdata['btn']
        tgt = rowdata['target']
        if tgt == KEEP:
            icon = self.get_icon(bd.strip_ns(rowdata['conv'].source))
            btn.configure(image=icon, text=' 変換しない', bg=C['KEEP_BG'], fg=C['MUTED'])
        else:
            icon = self.get_icon(tgt)
            btn.configure(image=icon, text=' ' + bd.jp_name(tgt), bg=C['TARGET_BG'], fg=C['TEXT'])
        btn.image = icon

    # --------------------------------------------------------------- picker
    def open_picker(self, rowdata):
        conv = rowdata['conv']
        top = tk.Toplevel(self.root)
        top.title('置き換え先を選ぶ')
        top.configure(bg=C['BG'])
        top.geometry('760x660')
        top.minsize(620, 500)
        top.transient(self.root)
        top.grab_set()

        tk.Label(top, text='「%s」の置き換え先' % bd.jp_name(conv.source),
                 bg=C['BG'], fg=C['TEXT'], font=('Yu Gothic UI', 12, 'bold'),
                 wraplength=720, justify='left').pack(anchor='w', padx=14, pady=(12, 2), fill='x')
        tk.Label(top, text='カテゴリを選ぶか、ID/日本語名で検索して変換先を選択します。',
                 bg=C['BG'], fg=C['MUTED'], font=('Yu Gothic UI', 9)).pack(anchor='w', padx=14)

        controls = tk.Frame(top, bg=C['BG'])
        controls.pack(fill='x', padx=14, pady=(10, 4))
        tk.Label(controls, text='カテゴリ', bg=C['BG'], fg=C['TEXT'],
                 font=('Yu Gothic UI', 9)).pack(side='left')
        cat_var = tk.StringVar(value=CATEGORY_NAME['recommended'])
        cat_box = ttk.Combobox(controls, textvariable=cat_var,
                               values=[label for _, label in CATEGORY_LABELS],
                               state='readonly', width=22, font=('Yu Gothic UI', 9))
        cat_box.pack(side='left', padx=(6, 14))
        tk.Label(controls, text='検索', bg=C['BG'], fg=C['TEXT'],
                 font=('Yu Gothic UI', 9)).pack(side='left')
        search_var = tk.StringVar()
        search_entry = tk.Entry(controls, textvariable=search_var, font=('Yu Gothic UI', 10),
                                bg=C['CARD'], fg=C['TEXT'], insertbackground=C['TEXT'],
                                relief='solid', bd=1)
        search_entry.pack(side='left', fill='x', expand=True, padx=(6, 0))

        count_lbl = tk.Label(top, text='', bg=C['BG'], fg=C['MUTED'], font=('Yu Gothic UI', 8),
                             anchor='w')
        count_lbl.pack(fill='x', padx=14, pady=(0, 2))

        body = tk.Frame(top, bg=C['BG'])
        body.pack(fill='both', expand=True, padx=12, pady=8)
        cv = tk.Canvas(body, bg=C['CARD'], highlightthickness=1, highlightbackground=C['BORDER'])
        cv.pack(side='left', fill='both', expand=True)
        sb = tk.Scrollbar(body, orient='vertical', command=cv.yview)
        sb.pack(side='right', fill='y')
        cv.configure(yscrollcommand=sb.set)
        inner = tk.Frame(cv, bg=C['CARD'])
        win = cv.create_window((0, 0), window=inner, anchor='nw')
        inner.bind('<Configure>', lambda e: cv.configure(scrollregion=cv.bbox('all')))
        cv.bind('<Configure>', lambda e: cv.itemconfigure(win, width=e.width))
        self._bind_wheel(cv, cv)

        def choose(value):
            rowdata['target'] = value
            self.overrides[rowdata['conv'].source] = value
            self._refresh_target(rowdata)
            top.destroy()
            self._wheel_target = self.canvas

        all_blocks = bd.all_blocks()

        def items_for_selection():
            q = search_var.get().strip().lower()
            selected = CATEGORY_BY_LABEL.get(cat_var.get(), 'recommended')
            if q:
                pool = all_blocks
            elif selected == 'recommended':
                pool = conv.candidates or [bd.strip_ns(conv.source)]
            elif selected == 'all':
                pool = all_blocks
            else:
                pool = [b for b in all_blocks if block_category(b) == selected]

            seen = set()
            items = []
            for b in pool:
                base = bd.strip_ns(b)
                if base in seen:
                    continue
                seen.add(base)
                if q and q not in base.lower() and q not in bd.jp_name(base).lower():
                    continue
                items.append(base)
            return items

        def rebuild_list(*_):
            for child in inner.winfo_children():
                child.destroy()
            self._picker_item(inner, '変換しない（そのまま）', bd.strip_ns(conv.source),
                              lambda: choose(KEEP), keep=True)
            items = items_for_selection()
            for cand in items:
                self._picker_item(inner, bd.jp_name(cand), cand, (lambda c=cand: choose(c)),
                                  recommended=(cand == conv.target))
            count_lbl.configure(text='表示: %d件 / 全ブロック: %d件' % (len(items), len(all_blocks)))
            cv.yview_moveto(0)

        cat_box.bind('<<ComboboxSelected>>', rebuild_list)
        search_var.trace_add('write', rebuild_list)
        rebuild_list()
        search_entry.focus_set()

    def _picker_item(self, parent, label, icon_id, cmd, keep=False, recommended=False):
        bgc = C['REC_BG'] if recommended else (C['KEEP_BG'] if keep else C['CARD'])
        f = tk.Frame(parent, bg=bgc, padx=8, pady=4, cursor='hand2')
        f.pack(fill='x')
        ic = self.get_icon(icon_id, 38)
        il = tk.Label(f, image=ic, bg=bgc)
        il.image = ic
        il.pack(side='left')
        txt = tk.Frame(f, bg=bgc)
        txt.pack(side='left', padx=8, fill='x', expand=True)
        suffix = '  ← おすすめ' if recommended else ''
        name_lbl = tk.Label(txt, text=label + suffix, bg=bgc, fg=(C['MUTED'] if keep else C['TEXT']),
                            font=('Yu Gothic UI', 10), anchor='w', justify='left',
                            wraplength=350)
        name_lbl.pack(anchor='w', fill='x')
        id_lbl = tk.Label(txt, text=bd.strip_ns(icon_id), bg=bgc, fg=C['MUTED'],
                          font=('Consolas', 8), anchor='w', justify='left', wraplength=350)
        id_lbl.pack(anchor='w', fill='x')
        for w in (f, il, txt, name_lbl, id_lbl):
            w.bind('<Button-1>', lambda e: cmd())
            w.bind('<Enter>', lambda e, ff=f: self._hover(ff, True, bgc))
            w.bind('<Leave>', lambda e, ff=f: self._hover(ff, False, bgc))

    def _hover(self, frame, on, base):
        col = C['HOVER'] if on else base
        frame.configure(bg=col)
        for ch in frame.winfo_children():
            try:
                ch.configure(bg=col)
                for gc in ch.winfo_children():
                    gc.configure(bg=col)
            except tk.TclError:
                pass

    # --------------------------------------------------------------- convert
    def do_convert(self):
        if not self.src_path:
            return
        mapping = {}
        for r in self.rows:
            t = r['target']
            if t == KEEP or t == bd.strip_ns(r['conv'].source):
                continue
            mapping[r['conv'].source] = t
        if not mapping:
            messagebox.showinfo(APP_TITLE, '変換する素材がありません（すべて「変換しない」になっています）。')
            return

        default_out = converter.default_output_path(self.src_path)
        out = filedialog.asksaveasfilename(
            title='変換後のファイルの保存先', initialdir=os.path.dirname(default_out),
            initialfile=os.path.basename(default_out), defaultextension='.litematic',
            filetypes=[('Litematica 設計図', '*.litematic')])
        if not out:
            return
        if os.path.abspath(out) == os.path.abspath(self.src_path):
            messagebox.showwarning(APP_TITLE, '元のファイルとは別の名前で保存してください。')
            return
        try:
            changed = converter.convert_file(self.src_path, out, mapping)
        except Exception as e:
            messagebox.showerror(APP_TITLE, '変換に失敗しました:\n%s' % e)
            return

        self.status_lbl.configure(text='完了: ' + os.path.basename(out))
        if messagebox.askyesno(
                APP_TITLE,
                '変換が完了しました。\n\n置き換えた素材: %d 種類\n出力ファイル:\n%s\n\n'
                'フォルダを開きますか？' % (len(mapping), out)):
            try:
                os.startfile(os.path.dirname(out))
            except Exception:
                pass


def _selftest(out_path):
    groups = set(id(g) for g in bd.ID2GROUP.values())
    regs = bd.available_registries()
    report = 'registries=%d (%s) active=%s VALID=%s groups=%d convertible=%d jp=%s' % (
        len(regs), ','.join(r['id'] for r in regs), bd.ACTIVE_FILE,
        None if bd.VALID is None else len(bd.VALID), len(groups),
        sum(1 for k in bd.ID2GROUP if bd.is_convertible(k)),
        bd.jp_name('stone_brick_slab'))
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(report)


def main():
    if len(sys.argv) >= 3 and sys.argv[1] == '--selftest':
        _selftest(sys.argv[2])
        return
    root = TkinterDnD.Tk() if _HAS_DND else tk.Tk()
    try:
        root.tk.call('tk', 'scaling', 1.2)
    except Exception:
        pass
    from dashboard_app import DashboardApp
    app = DashboardApp(root)
    if len(sys.argv) > 1 and os.path.isfile(sys.argv[1]):
        root.after(120, lambda: app.load_file(sys.argv[1]))
    root.mainloop()


if __name__ == '__main__':
    main()
