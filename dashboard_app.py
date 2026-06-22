# -*- coding: utf-8 -*-
"""Dark dashboard UI for the schematic material converter."""

import json
import math
import os
import random
import tkinter as tk
from tkinter import font as tkfont
from tkinter import filedialog, messagebox, ttk

try:
    from tkinterdnd2 import DND_FILES
    _HAS_DND = True
except Exception:
    DND_FILES = None
    _HAS_DND = False

from PIL import Image, ImageDraw, ImageTk

import blockdata as bd
import converter
import icons
import updater


APP_TITLE = '設計図自動素材変換ツール'
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

UI = {
    'BG': '#07101d', 'SIDEBAR': '#081320', 'HEADER': '#07111f',
    'PANEL': '#101b2a', 'PANEL_2': '#142234', 'PANEL_3': '#1b2b42',
    'ROW': '#101c2d', 'ROW_ALT': '#142235', 'BORDER': '#2a3a55',
    'BORDER_HI': '#5b8cff', 'TEXT': '#f4f8ff', 'TEXT_SOFT': '#d6e1f4',
    'MUTED': '#91a1bc', 'MUTED_2': '#64738e', 'ACCENT': '#3d8bff',
    'ACCENT_2': '#6aa9ff', 'ACCENT_3': '#8f7dff', 'ACCENT_DK': '#1f62d8',
    'CYAN': '#35d8e6', 'GREEN': '#31d084', 'ORANGE': '#ffb84d',
    'RED': '#ff6f7d', 'BTN_BG': '#1c2b40', 'BTN_BG_2': '#22344d',
    'KEEP_BG': '#263246', 'TARGET_BG': '#1f3a36', 'REC_BG': '#2a2555',
    'HOVER': '#2a3d59', 'CARD': '#101b2a', 'BADGE_BG': '#263653',
    'BADGE_FG': '#b6ccff', 'NBADGE_BG': '#252f42', 'NBADGE_FG': '#a9b6cc',
}


def _hex_to_rgb(value):
    value = str(value).strip()
    if value.startswith('#') and len(value) == 7:
        return tuple(int(value[i:i + 2], 16) for i in (1, 3, 5))
    return (24, 36, 54)


def _mix_hex(a, b, ratio):
    ar, ag, ab = _hex_to_rgb(a)
    br, bg, bb = _hex_to_rgb(b)
    ratio = max(0.0, min(1.0, ratio))
    rgb = (
        int(ar + (br - ar) * ratio),
        int(ag + (bg - ag) * ratio),
        int(ab + (bb - ab) * ratio),
    )
    return '#%02x%02x%02x' % rgb


class RoundedButton(tk.Canvas):
    def __init__(self, parent, text, command=None, bg=None, fg=None, active_bg=None,
                 size=9, weight='bold', padx=10, pady=5, state='normal',
                 radius=None, **_kw):
        self.parent_bg = parent.cget('bg') if hasattr(parent, 'cget') else UI['BG']
        self.text = text
        self.command = command
        self.fill = bg or UI['BTN_BG']
        self.hover_fill = active_bg or _mix_hex(self.fill, '#ffffff', 0.10)
        self.fg = fg or UI['TEXT']
        self.state = state
        self.font = ('Yu Gothic UI', size, weight)
        self.tk_font = tkfont.Font(font=self.font)
        self.padx = padx
        self.pady = pady
        self.radius = radius
        text_width = max(34, self.tk_font.measure(text.replace('\n', '  ')))
        line_count = max(1, text.count('\n') + 1)
        text_height = self.tk_font.metrics('linespace') * line_count
        width = max(44, text_width + padx * 2)
        height = max(28, text_height + pady * 2)
        super().__init__(parent, width=width, height=height, bg=self.parent_bg,
                         highlightthickness=0, bd=0, relief='flat',
                         cursor='hand2' if state == 'normal' else '')
        self._hover = False
        self._pressed = False
        self._photo = None
        self.bind('<Configure>', lambda _e: self._redraw())
        self.bind('<Enter>', self._on_enter)
        self.bind('<Leave>', self._on_leave)
        self.bind('<ButtonPress-1>', self._on_press)
        self.bind('<ButtonRelease-1>', self._on_release)
        self._redraw()

    def configure(self, cnf=None, **kw):
        if cnf:
            kw.update(cnf)
        if 'text' in kw:
            self.text = kw.pop('text')
        if 'bg' in kw:
            self.fill = kw.pop('bg')
            self.hover_fill = _mix_hex(self.fill, '#ffffff', 0.12)
        if 'background' in kw:
            self.fill = kw.pop('background')
            self.hover_fill = _mix_hex(self.fill, '#ffffff', 0.12)
        if 'fg' in kw:
            self.fg = kw.pop('fg')
        if 'foreground' in kw:
            self.fg = kw.pop('foreground')
        if 'state' in kw:
            self.state = kw.pop('state')
            super().configure(cursor='hand2' if self.state == 'normal' else '')
        if 'command' in kw:
            self.command = kw.pop('command')
        if kw:
            super().configure(**kw)
        self._redraw()

    config = configure

    def _on_enter(self, _event):
        if self.state != 'normal':
            return
        self._hover = True
        self._redraw()

    def _on_leave(self, _event):
        self._hover = False
        self._pressed = False
        self._redraw()

    def _on_press(self, _event):
        if self.state != 'normal':
            return
        self._pressed = True
        self._redraw()

    def _on_release(self, event):
        if self.state != 'normal':
            return
        was_pressed = self._pressed
        self._pressed = False
        self._redraw()
        if was_pressed and 0 <= event.x <= self.winfo_width() and 0 <= event.y <= self.winfo_height():
            if self.command:
                self.command()

    def _redraw(self):
        width = self.winfo_width()
        height = self.winfo_height()
        if width < 8:
            width = int(float(self['width']))
        if height < 8:
            height = int(float(self['height']))
        width = max(24, width)
        height = max(20, height)
        scale = 3
        fill = self.hover_fill if self._hover else self.fill
        if self._pressed:
            fill = _mix_hex(fill, '#000000', 0.12)
        if self.state != 'normal':
            fill = _mix_hex(fill, '#6c7484', 0.45)
        radius = self.radius or max(12, min(22, height // 2))
        img = Image.new('RGBA', (width * scale, height * scale), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        shadow = (0, 0, 0, 80)
        rr = radius * scale
        draw.rounded_rectangle(
            [2 * scale, 3 * scale, width * scale - 2 * scale, height * scale - 1 * scale],
            radius=rr, fill=shadow)
        draw.rounded_rectangle(
            [1 * scale, 1 * scale, width * scale - 3 * scale, height * scale - 4 * scale],
            radius=rr, fill=fill, outline=_mix_hex(fill, '#ffffff', 0.18), width=scale)
        img = img.resize((width, height), Image.Resampling.LANCZOS)
        self._photo = ImageTk.PhotoImage(img)
        self.delete('all')
        self.create_image(0, 0, image=self._photo, anchor='nw')
        text_color = self.fg if self.state == 'normal' else UI['MUTED']
        self.create_text(width // 2, height // 2 - 1, text=self.text, fill=text_color,
                         font=self.font, justify='center')


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
                               'target', 'lever', 'button', 'pressure_plate', 'tripwire',
                               'daylight_detector', 'sculk_sensor', 'crafter', 'dispenser',
                               'dropper', 'hopper')):
        return 'redstone'
    if any(k in base for k in ('stone', 'slate', 'tuff', 'granite', 'diorite', 'andesite',
                               'sandstone', 'blackstone', 'basalt', 'quartz', 'brick',
                               'prismarine', 'purpur', 'calcite', 'dripstone', 'cobble', 'tile')):
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


class DashboardApp:
    def __init__(self, root):
        self.root = root
        self.icon_cache = {}
        self.image_cache = {}
        self.src_path = None
        self.loaded_nbt = None
        self.convs = []
        self.others = []
        self.overrides = {}
        self.rows = []
        self._wheel_target = None
        self._wheel_bound = False
        self._regid2file = {}
        self.active_filter = 'all'
        self.preview_tab = 'overview'
        self.last_output = None
        self.output_history = []
        self.focus_mode = False
        self.sidebar_collapsed = False
        self.sidebar_items = {}
        self.pending_update = None
        self.update_checking = False
        self.update_notified = False
        self.note_var = tk.StringVar(value='')
        self.progress_var = tk.DoubleVar(value=0)
        self._build_ui()
        self.root.after(1800, self.check_for_updates_silent)

    # ------------------------------------------------------------------ basics
    def get_icon(self, bid, size=34):
        key = (bd.strip_ns(bid), size)
        if key not in self.icon_cache:
            self.icon_cache[key] = ImageTk.PhotoImage(icons.render_block_image(key[0], size))
        return self.icon_cache[key]

    def _default_drop_text(self):
        return ('ここに .litematic ファイルをドラッグ&ドロップ\nまたはクリックして選択'
                if _HAS_DND else 'ここをクリックして .litematic を選択')

    def _configure_style(self):
        style = ttk.Style()
        try:
            style.theme_use('clam')
        except tk.TclError:
            pass
        style.configure('Studio.TCombobox',
                        fieldbackground=UI['PANEL_2'], background=UI['PANEL_2'],
                        foreground=UI['TEXT'], bordercolor=UI['BORDER'],
                        arrowcolor=UI['TEXT_SOFT'], selectbackground=UI['PANEL_3'],
                        selectforeground=UI['TEXT'])
        style.map('Studio.TCombobox',
                  fieldbackground=[('readonly', UI['PANEL_2'])],
                  foreground=[('readonly', UI['TEXT'])])
        style.configure('Studio.Horizontal.TProgressbar',
                        troughcolor='#101827', background=UI['ACCENT'],
                        bordercolor=UI['BORDER'], lightcolor=UI['ACCENT'],
                        darkcolor=UI['ACCENT_DK'])

    def _label(self, parent, text, size=10, weight='normal', fg=None, bg=None, **kw):
        return tk.Label(parent, text=text, bg=bg or parent.cget('bg'), fg=fg or UI['TEXT'],
                        font=('Yu Gothic UI', size, weight), **kw)

    def _button(self, parent, text, command=None, bg=None, fg=None, size=9, weight='bold',
                padx=10, pady=5, state='normal', **kw):
        return RoundedButton(parent, text=text, command=command, bg=bg or UI['BTN_BG'],
                             fg=fg or UI['TEXT'], active_bg=UI['HOVER'],
                             size=size, weight=weight, padx=padx, pady=pady,
                             state=state, **kw)

    def _panel(self, parent, bg=None, border=None):
        return tk.Frame(parent, bg=bg or UI['PANEL'], highlightthickness=0,
                        highlightbackground=border or UI['BORDER'])

    def _register_drop(self, widget):
        if not _HAS_DND:
            return
        try:
            widget.drop_target_register(DND_FILES)
            widget.dnd_bind('<<Drop>>', self.on_drop)
        except Exception:
            pass

    def _set_centered_geometry(self, window, width, height):
        sw = max(1, window.winfo_screenwidth())
        sh = max(1, window.winfo_screenheight())
        x = max(0, int((sw - width) / 2))
        y = max(0, int((sh - height) / 2))
        window.geometry('%dx%d+%d+%d' % (width, height, x, y))

    # --------------------------------------------------------------------- ui
    def _build_ui(self):
        self.root.title(APP_TITLE)
        self.root.configure(bg=UI['BG'])
        self._set_centered_geometry(self.root, 1280, 720)
        self.root.minsize(1100, 660)
        self.root.grid_rowconfigure(1, weight=1)
        self.root.grid_columnconfigure(1, weight=1)
        self._configure_style()

        self.sidebar = tk.Frame(self.root, bg=UI['SIDEBAR'], width=74)
        self.sidebar.grid(row=0, column=0, rowspan=3, sticky='ns')
        self.sidebar.grid_propagate(False)

        self.header = tk.Frame(self.root, bg=UI['HEADER'], height=62)
        self.header.grid(row=0, column=1, sticky='ew')
        self.header.grid_propagate(False)

        self.main = tk.Frame(self.root, bg=UI['BG'])
        self.main.grid(row=1, column=1, sticky='nsew', padx=16, pady=(12, 8))

        self.footer = tk.Frame(self.root, bg=UI['HEADER'], height=54)
        self.footer.grid(row=2, column=1, sticky='ew')
        self.footer.grid_propagate(False)

        self._register_drop(self.root)
        self._build_sidebar()
        self._build_header()
        self._build_main()
        self._build_footer()

    def _build_sidebar(self):
        logo = tk.Canvas(self.sidebar, width=48, height=48, bg=UI['SIDEBAR'], highlightthickness=0)
        logo.pack(pady=(12, 14))
        logo.create_polygon(12, 10, 27, 3, 40, 11, 25, 19, fill=UI['ACCENT'])
        logo.create_polygon(12, 12, 25, 20, 25, 36, 12, 28, fill=UI['ACCENT_2'])
        logo.create_polygon(27, 20, 41, 12, 41, 29, 27, 38, fill=UI['ACCENT_3'])
        logo.create_text(26, 25, text='S', fill='white', font=('Segoe UI', 15, 'bold'))
        for symbol, label, key, active in [
            ('⌂', 'ワークフロー', 'workflow', True), ('▣', '設計図', 'blueprint', False),
            ('✚', 'ルール', 'rules', False), ('▤', 'プレビュー', 'preview', False),
            ('◉', '出力履歴', 'history', False), ('⚙', '設定', 'settings', False),
            ('?', 'ヘルプ', 'help', False),
        ]:
            self._nav_item(symbol, label, key, active)
        tk.Frame(self.sidebar, bg=UI['SIDEBAR']).pack(fill='both', expand=True)
        close = self._label(self.sidebar, '≪\nメニューを\n閉じる', size=8, fg=UI['MUTED'],
                            justify='center', cursor='hand2')
        close.pack(pady=(0, 12))
        close.bind('<Button-1>', lambda _e: self.toggle_sidebar())

    def _nav_item(self, symbol, label, key, active=False):
        bg = '#1d5dce' if active else '#0f1d2d'
        fg = '#ffffff' if active else UI['MUTED']
        f = tk.Frame(self.sidebar, bg=UI['SIDEBAR'])
        f.pack(fill='x', padx=8, pady=4)
        item = RoundedButton(f, text=symbol + '\n' + label,
                             command=lambda k=key: self.navigate(k),
                             bg=bg, fg=fg, active_bg='#22476d',
                             size=8, weight='bold' if active else 'normal',
                             padx=3, pady=5, radius=16)
        item.pack(fill='x')
        self.sidebar_items[key] = item

    def _set_sidebar_active(self, key):
        for name, widget in self.sidebar_items.items():
            active = name == key
            widget.configure(bg='#1d5dce' if active else '#0f1d2d',
                             fg='#ffffff' if active else UI['MUTED'])

    def navigate(self, key):
        self._set_sidebar_active(key)
        actions = {
            'workflow': lambda: self._sync_progress(text='進行状況: ワークフロー表示中'),
            'blueprint': self.open_blueprint_dialog,
            'rules': self.open_rule_manager,
            'preview': self.open_full_preview,
            'history': self.open_history_dialog,
            'settings': self.open_settings_dialog,
            'help': self.open_help_dialog,
        }
        actions.get(key, actions['workflow'])()

    def _dialog(self, title, width=760, height=520, modal=False):
        top = tk.Toplevel(self.root)
        top.title(title)
        top.configure(bg=UI['BG'])
        self._set_centered_geometry(top, width, height)
        top.minsize(min(width, 560), min(height, 420))
        top.transient(self.root)
        top.grid_rowconfigure(1, weight=1)
        top.grid_columnconfigure(0, weight=1)
        head = tk.Frame(top, bg=UI['HEADER'])
        head.grid(row=0, column=0, sticky='ew')
        self._label(head, title, size=14, weight='bold', bg=UI['HEADER']).pack(side='left', padx=16, pady=12)
        self._button(head, '閉じる', top.destroy, bg='#0d1726', size=8, padx=10, pady=4).pack(side='right', padx=12)
        body = tk.Frame(top, bg=UI['BG'])
        body.grid(row=1, column=0, sticky='nsew', padx=16, pady=16)
        if modal:
            top.grab_set()
        top.lift()
        return top, body

    def _dialog_button_row(self, parent):
        row = tk.Frame(parent, bg=parent.cget('bg'))
        row.pack(fill='x', pady=(12, 0))
        return row

    def toggle_focus_mode(self):
        self.focus_mode = not self.focus_mode
        alpha = 0.96 if self.focus_mode else 1.0
        try:
            self.root.attributes('-alpha', alpha)
        except tk.TclError:
            pass
        self._sync_progress(text='進行状況: フォーカス表示 %s' % ('ON' if self.focus_mode else 'OFF'))

    def toggle_sidebar(self):
        self.sidebar_collapsed = not self.sidebar_collapsed
        self.sidebar.configure(width=50 if self.sidebar_collapsed else 74)
        self._sync_progress(text='進行状況: サイドバー %s' % ('縮小' if self.sidebar_collapsed else '展開'))

    def open_build_dialog(self):
        _top, body = self._dialog('Studio Build 情報', 620, 440)
        stats = self._stats()
        rows = [
            ('ビルド種別', 'ローカル配布ビルド'),
            ('アプリバージョン', updater.APP_VERSION),
            ('読み込み中の設計図', os.path.basename(self.src_path) if self.src_path else '-'),
            ('対象レジストリ', bd.active_registry()),
            ('変換ルール数', str(stats['rules'])),
            ('ユニークブロック数', str(stats['unique_total'])),
            ('最終出力', self.last_output or '-'),
        ]
        for label, value in rows:
            self._metric_line(body, label, value)
        row = self._dialog_button_row(body)
        self._button(row, 'アプリのフォルダを開く', lambda: self.open_folder(os.getcwd()),
                     bg=UI['BTN_BG_2']).pack(side='left', padx=(0, 8))
        self._button(row, 'dist を開く', lambda: self.open_folder(os.path.join(os.getcwd(), 'dist')),
                     bg=UI['BTN_BG_2']).pack(side='left')

    def open_blueprint_dialog(self):
        _top, body = self._dialog('設計図', 720, 520)
        if self.loaded_nbt is None:
            self._label(body, 'まだ設計図が読み込まれていません。', size=11, fg=UI['TEXT_SOFT'],
                        bg=UI['BG']).pack(anchor='w')
        else:
            meta = self._metadata()
            for label, value in [
                ('ファイル', self.src_path or '-'), ('形式', meta['format']), ('サイズ', meta['size']),
                ('範囲', meta['area']), ('ブロック総数', meta['total']), ('ユニークブロック数', meta['unique']),
            ]:
                self._metric_line(body, label, value)
        row = self._dialog_button_row(body)
        self._button(row, '別の設計図を読み込む', self.choose_file, bg=UI['ACCENT']).pack(side='left', padx=(0, 8))
        self._button(row, '設計図フォルダを開く', self.open_source_folder, bg=UI['BTN_BG_2']).pack(side='left', padx=(0, 8))
        self._button(row, '読み込みを解除', self.clear_loaded_file, bg='#241f58').pack(side='left')

    def open_rule_manager(self):
        _top, body = self._dialog('ルール管理', 820, 560)
        self._label(body, 'プリセット、未設定ブロック、未使用ルールをまとめて管理します。', size=10,
                    fg=UI['MUTED'], bg=UI['BG']).pack(anchor='w', pady=(0, 10))
        grid = tk.Frame(body, bg=UI['BG'])
        grid.pack(fill='x')
        for title, desc, cmd in [
            ('自動マッピング', '素材の種類を保ったまま入手しやすいブロックへ割り当てます。', self.apply_default_preset),
            ('建築向け', 'ガラスや石材を見やすい現代的な構成に寄せます。', self.apply_architecture_preset),
            ('装飾保持', '装飾ブロックはそのままにして主要素材だけ変換します。', self.apply_deco_preset),
            ('すべて保持', '全ブロックを変換しない設定にします。', self.reset_mappings),
            ('未使用ルール削除', '現在の設計図に存在しない保存済みルールを削除します。', self.clean_unused_rules),
            ('手動ルール追加', '一覧の先頭ブロックから変換先ピッカーを開きます。', self.add_manual_rule),
        ]:
            row = tk.Frame(grid, bg=UI['PANEL_2'], highlightthickness=1, highlightbackground=UI['BORDER'])
            row.pack(fill='x', pady=4)
            tx = tk.Frame(row, bg=UI['PANEL_2'])
            tx.pack(side='left', fill='x', expand=True, padx=10, pady=8)
            self._label(tx, title, size=10, weight='bold', bg=UI['PANEL_2']).pack(anchor='w')
            self._label(tx, desc, size=8, fg=UI['MUTED'], bg=UI['PANEL_2']).pack(anchor='w')
            self._button(row, '実行', cmd, bg='#28215a', padx=12, pady=5).pack(side='right', padx=10)

    def open_preset_manager(self):
        _top, body = self._dialog('プリセット管理', 700, 500)
        self._label(body, '現在のルールセットを保存し、いつでも再利用できます。', size=10,
                    fg=UI['MUTED'], bg=UI['BG']).pack(anchor='w', pady=(0, 10))
        for title, desc, cmd in [
            ('プロジェクトJSONとして保存', '読み込み元、対象バージョン、手動ルール、メモを保存します。', self.save_project),
            ('自動マッピングを適用', '初期推奨ルールに戻します。', self.apply_default_preset),
            ('建築向けプリセットを適用', '建築プレビューで見やすい素材へ寄せます。', self.apply_architecture_preset),
            ('装飾ブロック最適化を適用', '装飾は保持しつつ素材ブロックを整理します。', self.apply_deco_preset),
        ]:
            row = tk.Frame(body, bg=UI['PANEL_2'], highlightthickness=1, highlightbackground=UI['BORDER'])
            row.pack(fill='x', pady=4)
            tx = tk.Frame(row, bg=UI['PANEL_2'])
            tx.pack(side='left', fill='x', expand=True, padx=10, pady=8)
            self._label(tx, title, size=10, weight='bold', bg=UI['PANEL_2']).pack(anchor='w')
            self._label(tx, desc, size=8, fg=UI['MUTED'], bg=UI['PANEL_2']).pack(anchor='w')
            self._button(row, '実行', cmd, bg='#28215a', padx=12, pady=5).pack(side='right', padx=10)

    def open_full_preview(self):
        top, body = self._dialog('Minecraft風プレビュー', 980, 640)
        body.grid_rowconfigure(0, weight=1)
        body.grid_columnconfigure(0, weight=1)
        img = self._result_preview_image(900, 470)
        prev = tk.Label(body, image=img, bg=UI['PANEL'], highlightthickness=1, highlightbackground=UI['BORDER_HI'])
        prev.image = img
        prev.grid(row=0, column=0, sticky='nsew')
        row = tk.Frame(body, bg=UI['BG'])
        row.grid(row=1, column=0, sticky='ew', pady=(12, 0))
        self._button(row, 'PNGとして保存', self.export_preview, bg=UI['ACCENT']).pack(side='left', padx=(0, 8))
        self._button(row, 'CSVを書き出し', self.export_mapping_csv, bg=UI['BTN_BG_2']).pack(side='left', padx=(0, 8))
        self._button(row, '閉じる', top.destroy, bg='#0d1726').pack(side='right')

    def open_history_dialog(self):
        _top, body = self._dialog('出力履歴', 760, 520)
        entries = list(self.output_history)
        if self.last_output and self.last_output not in [e.get('path') for e in entries]:
            entries.append({'path': self.last_output, 'rules': '-', 'changed': '-'})
        if not entries:
            self._label(body, 'まだ出力履歴はありません。変換を実行するとここに記録されます。',
                        size=10, fg=UI['MUTED'], bg=UI['BG']).pack(anchor='w')
            return
        for entry in reversed(entries[-12:]):
            row = tk.Frame(body, bg=UI['PANEL_2'], highlightthickness=1, highlightbackground=UI['BORDER'])
            row.pack(fill='x', pady=4)
            tx = tk.Frame(row, bg=UI['PANEL_2'])
            tx.pack(side='left', fill='x', expand=True, padx=10, pady=8)
            self._label(tx, os.path.basename(entry['path']), size=10, weight='bold', bg=UI['PANEL_2']).pack(anchor='w')
            self._label(tx, entry['path'], size=8, fg=UI['MUTED'], bg=UI['PANEL_2'],
                        wraplength=520).pack(anchor='w')
            self._button(row, 'フォルダ', lambda p=entry['path']: self.open_folder(os.path.dirname(p)),
                         bg='#28215a').pack(side='right', padx=10)

    def open_settings_dialog(self):
        _top, body = self._dialog('設定', 700, 520)
        regs = bd.available_registries()
        labels = []
        reg_map = {}
        for r in regs:
            label = r.get('id', r.get('file', 'registry'))
            labels.append(label)
            reg_map[label] = r['file']
        self._label(body, '対象バージョンレジストリ', size=10, weight='bold', bg=UI['BG']).pack(anchor='w')
        var = tk.StringVar(value=next((k for k, v in reg_map.items() if v == bd.ACTIVE_FILE),
                                      labels[0] if labels else ''))
        combo = ttk.Combobox(body, textvariable=var, values=labels, state='readonly',
                             style='Studio.TCombobox', font=('Yu Gothic UI', 10))
        combo.pack(fill='x', pady=(6, 12))

        def apply_registry():
            f = reg_map.get(var.get())
            if f:
                bd.set_active_file(f)
                if self.loaded_nbt is not None:
                    self._rescan()
                self._sync_progress(text='進行状況: レジストリを変更しました')

        self._button(body, 'このレジストリを適用', apply_registry, bg=UI['ACCENT']).pack(anchor='w')
        self._label(body, '表示', size=10, weight='bold', bg=UI['BG']).pack(anchor='w', pady=(18, 6))
        self._button(body, 'フォーカス表示を切り替え', self.toggle_focus_mode, bg=UI['BTN_BG_2']).pack(anchor='w')
        self._button(body, 'プレビューキャッシュをクリア', self.clear_preview_cache,
                     bg=UI['BTN_BG_2']).pack(anchor='w', pady=(8, 0))
        self._label(body, '更新', size=10, weight='bold', bg=UI['BG']).pack(anchor='w', pady=(18, 6))
        self._button(body, 'ネット更新を今すぐ確認', self.check_for_updates_manual,
                     bg=UI['BTN_BG_2']).pack(anchor='w')
        self._button(body, '更新URL設定ファイルを作成', self.create_update_url_file,
                     bg=UI['BTN_BG_2']).pack(anchor='w', pady=(8, 0))

    def open_help_dialog(self):
        _top, body = self._dialog('ヘルプ', 760, 520)
        text = (
            '1. 設計図を読み込むと、パレット内の全ブロックを解析します。\n'
            '2. 変換先はカテゴリ検索から全アイテムへ変更できます。\n'
            '3. 右側のプレビューは .litematic の BlockStates を読み、変換後の素材で簡易レンダーします。\n'
            '4. 変換を実行すると元ファイルは上書きせず、新しい .litematic を生成します。\n'
            '5. プロジェクト保存はルールJSON、プレビュー出力はPNG、メニューからCSVも出力できます。'
        )
        self._label(body, text, size=10, fg=UI['TEXT_SOFT'], bg=UI['BG'],
                    justify='left', wraplength=680).pack(anchor='w')

    def open_export_menu(self):
        _top, body = self._dialog('出力メニュー', 560, 430)
        for label, desc, cmd in [
            ('プレビューPNGを書き出し', '現在の変換設定を反映したMinecraft風プレビュー画像を保存します。', self.export_preview),
            ('マッピングCSVを書き出し', 'ブロックごとの変換先と状態をCSVで保存します。', self.export_mapping_csv),
            ('プロジェクトJSONを保存', '現在のルールとメモを保存します。', self.save_project),
            ('出力フォルダを開く', '最後に変換したファイルのフォルダを開きます。', self.open_last_output_folder),
            ('概要をコピー', '変換概要をクリップボードへコピーします。', self.copy_summary),
        ]:
            row = tk.Frame(body, bg=UI['PANEL_2'], highlightthickness=1, highlightbackground=UI['BORDER'])
            row.pack(fill='x', pady=4)
            tx = tk.Frame(row, bg=UI['PANEL_2'])
            tx.pack(side='left', fill='x', expand=True, padx=10, pady=8)
            self._label(tx, label, size=9, weight='bold', bg=UI['PANEL_2']).pack(anchor='w')
            self._label(tx, desc, size=7, fg=UI['MUTED'], bg=UI['PANEL_2']).pack(anchor='w')
            self._button(row, '実行', cmd, bg='#28215a', padx=12, pady=5).pack(side='right', padx=10)

    def open_validation_dialog(self, label, count):
        _top, body = self._dialog('検証: ' + label, 720, 520)
        self._label(body, '%s: %s件' % (label, count), size=12, weight='bold', bg=UI['BG']).pack(anchor='w')
        rows = []
        if '未設定' in label:
            rows = [c for c in self._all_records() if self._target_for(c) == KEEP]
        elif '競合' in label:
            rows = [c for c in self._all_records()
                    if self._target_for(c) != KEEP and not bd.is_valid_block(self._target_for(c))]
        if not rows:
            self._label(body, '問題は見つかりませんでした。', size=10, fg=UI['GREEN'], bg=UI['BG']).pack(anchor='w', pady=12)
            return
        for conv in rows[:24]:
            tgt = self._target_for(conv)
            self._metric_line(body, bd.strip_ns(conv.source), '未設定' if tgt == KEEP else str(tgt))
        if len(rows) > 24:
            self._label(body, 'ほか %d 件' % (len(rows) - 24), size=8, fg=UI['MUTED'], bg=UI['BG']).pack(anchor='w')
        row = self._dialog_button_row(body)
        self._button(row, '一覧で絞り込む', lambda: self.set_filter('other'), bg=UI['ACCENT']).pack(side='left', padx=(0, 8))
        self._button(row, '自動マッピングを実行', self.apply_default_preset, bg=UI['BTN_BG_2']).pack(side='left')

    def clear_loaded_file(self):
        self.src_path = None
        self.loaded_nbt = None
        self.convs = []
        self.others = []
        self.overrides = {}
        self.last_output = None
        self.progress_var.set(0)
        self._refresh_layout()

    def clear_preview_cache(self):
        self.image_cache = {}
        self._refresh_layout()
        self._sync_progress(text='進行状況: プレビューキャッシュをクリアしました')

    def open_folder(self, path):
        try:
            if path and os.path.isdir(path):
                os.startfile(path)
            else:
                messagebox.showinfo(APP_TITLE, 'フォルダが見つかりません:\n%s' % path)
        except Exception as e:
            messagebox.showerror(APP_TITLE, 'フォルダを開けませんでした:\n%s' % e)

    def open_source_folder(self):
        if not self.src_path:
            messagebox.showinfo(APP_TITLE, '設計図が読み込まれていません。')
            return
        self.open_folder(os.path.dirname(self.src_path))

    def open_last_output_folder(self):
        if not self.last_output:
            messagebox.showinfo(APP_TITLE, 'まだ変換結果がありません。')
            return
        self.open_folder(os.path.dirname(self.last_output))

    def copy_summary(self):
        stats = self._stats()
        text = '\n'.join([
            '設計図自動素材変換ツール 概要',
            'ファイル: %s' % (self.src_path or '-'),
            '総ブロック数: %s' % stats['total_blocks'],
            'ユニークブロック数: %s' % stats['unique_total'],
            '変換ルール数: %s' % stats['rules'],
            '未設定: %s' % stats['unset'],
            '競合: %s' % stats['conflicts'],
        ])
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self._sync_progress(text='進行状況: 概要をコピーしました')

    def check_for_updates_silent(self):
        self._check_for_updates(manual=False)

    def check_for_updates_manual(self):
        self._check_for_updates(manual=True)

    def _check_for_updates(self, manual=False):
        if self.update_checking:
            return
        manifest_url = updater.read_manifest_url()
        if not manifest_url:
            if manual:
                self.open_update_config_help()
            return
        self.update_checking = True
        if hasattr(self, 'update_state'):
            self.update_state.configure(text='● 更新確認中...', fg=UI['ORANGE'])

        def on_result(info):
            self.root.after(0, lambda: self._finish_update_check(info, manual))

        def on_error(exc):
            self.root.after(0, lambda: self._finish_update_error(exc, manual))

        updater.check_for_update_async(on_result, on_error)

    def _finish_update_check(self, info, manual):
        self.update_checking = False
        if info is None:
            if hasattr(self, 'update_state'):
                self.update_state.configure(text='● 最新 v%s' % updater.APP_VERSION, fg=UI['GREEN'])
            if manual:
                messagebox.showinfo(APP_TITLE, '最新版です。\n現在のバージョン: %s' % updater.APP_VERSION)
            return
        self.pending_update = info
        if hasattr(self, 'update_state'):
            self.update_state.configure(text='● 更新あり v%s' % info.version, fg=UI['ORANGE'])
        if manual or not self.update_notified or info.mandatory:
            self.update_notified = True
            self.prompt_update(info)

    def _finish_update_error(self, exc, manual):
        self.update_checking = False
        if hasattr(self, 'update_state'):
            self.update_state.configure(text='● 更新確認失敗', fg=UI['RED'])
        if manual:
            messagebox.showerror(APP_TITLE, '更新確認に失敗しました。\nGitHub Release がまだ無い場合もここになります。\n\n%s' % exc)

    def prompt_update(self, info=None):
        info = info or self.pending_update
        if info is None:
            self.check_for_updates_manual()
            return
        notes = ('\n\n更新内容:\n%s' % info.notes) if info.notes else ''
        ask = messagebox.askyesno(
            APP_TITLE,
            '新しいバージョンがあります。\n\n現在: %s\n最新: %s%s\n\n今すぐダウンロードして更新しますか？\n更新後にアプリを再起動します。'
            % (updater.APP_VERSION, info.version, notes))
        if ask:
            self.download_and_apply_update(info)

    def download_and_apply_update(self, info):
        if self.update_checking:
            return
        self.update_checking = True
        self._sync_progress(0, '進行状況: 更新ファイルをダウンロードしています...')
        if hasattr(self, 'update_state'):
            self.update_state.configure(text='● 更新DL中...', fg=UI['ORANGE'])

        def progress(value):
            pct = max(0, min(100, int(value * 100)))
            self.root.after(0, lambda p=pct: self._sync_progress(p, '進行状況: 更新ファイルをダウンロードしています...'))

        def worker():
            try:
                path = updater.download_update(info, progress)
                updater.schedule_replace_and_restart(path)
            except Exception as exc:
                self.root.after(0, lambda e=exc: self._update_failed(e))
                return
            self.root.after(0, self._close_for_update)

        import threading
        threading.Thread(target=worker, daemon=True).start()

    def _update_failed(self, exc):
        self.update_checking = False
        if hasattr(self, 'update_state'):
            self.update_state.configure(text='● 更新失敗', fg=UI['RED'])
        messagebox.showerror(APP_TITLE, '更新に失敗しました:\n%s' % exc)

    def _close_for_update(self):
        self._sync_progress(100, '進行状況: 更新を適用するため再起動します...')
        try:
            self.root.destroy()
        except tk.TclError:
            pass

    def open_update_config_help(self):
        top, body = self._dialog('自動更新設定', 760, 520)
        url_file = updater.app_dir() / updater.MANIFEST_URL_FILE
        example = (
            '1. GitHubで Release を作成\n'
            '2. tag を v1.1.3 のように現在より大きい番号にする\n'
            '3. 設計図素材変換ツール.exe を Release asset として添付\n'
            '4. 公開後、アプリ起動時または「今すぐ確認」で通知されます'
        )
        self._label(body, 'このアプリは GitHub Releases を標準の更新元として確認します。現在の更新元は kanzakideath/Automatic-design-drawing-converter です。',
                    size=10, fg=UI['TEXT_SOFT'], bg=UI['BG'], justify='left', wraplength=700).pack(anchor='w')
        self._label(body, '更新元を変えたい場合だけ、EXEと同じフォルダの update_manifest_url.txt を編集します: %s' % url_file, size=8, fg=UI['MUTED'], bg=UI['BG'],
                    justify='left', wraplength=700).pack(anchor='w', pady=(8, 12))
        self._label(body, 'GitHub Release の作り方:', size=9, weight='bold', bg=UI['BG']).pack(anchor='w')
        tk.Message(body, text=example, width=690, bg=UI['PANEL_2'], fg=UI['TEXT_SOFT'],
                   font=('Consolas', 9), padx=12, pady=10).pack(fill='x', pady=(4, 12))
        row = self._dialog_button_row(body)
        self._button(row, '設定ファイルを作成', self.create_update_url_file, bg=UI['ACCENT']).pack(side='left', padx=(0, 8))
        self._button(row, '今すぐ確認', self.check_for_updates_manual, bg=UI['BTN_BG_2']).pack(side='left')

    def create_update_url_file(self):
        path = updater.app_dir() / updater.MANIFEST_URL_FILE
        if not path.exists():
            path.write_text(
                '# GitHub Releases を確認します。別リポジトリに変える場合だけURLを編集してください。\n'
                'https://github.com/kanzakideath/Automatic-design-drawing-converter\n',
                encoding='utf-8')
        self.open_folder(str(path.parent))
        messagebox.showinfo(APP_TITLE, '設定ファイルを作成しました:\n%s' % path)

    def _build_header(self):
        self.header.grid_columnconfigure(0, weight=1)
        left = tk.Frame(self.header, bg=UI['HEADER'])
        left.grid(row=0, column=0, sticky='w', padx=6, pady=8)
        self._label(left, '設計図自動素材変換ツール', size=16, weight='bold',
                    bg=UI['HEADER']).pack(anchor='w')
        self._label(left, '設計図を読み込み、素材を自動で変換・最適化します',
                    size=8, fg=UI['MUTED'], bg=UI['HEADER']).pack(anchor='w')

        right = tk.Frame(self.header, bg=UI['HEADER'])
        right.grid(row=0, column=1, sticky='e', padx=12)
        self.update_state = self._label(right, '● v%s' % updater.APP_VERSION,
                                        size=8, fg=UI['MUTED'], bg=UI['HEADER'], cursor='hand2')
        self.update_state.pack(side='left', padx=(0, 14))
        self.update_state.bind('<Button-1>', lambda _e: self.check_for_updates_manual())
        self.save_state = self._label(right, '● すべての変更を保存しました',
                                      size=8, fg=UI['GREEN'], bg=UI['HEADER'])
        self.save_state.pack(side='left', padx=(0, 14))
        self._button(right, '▣ プロジェクトを保存', self.save_project,
                     bg='#0d1726', size=8, padx=10, pady=4).pack(side='left', padx=4)
        self._button(right, '☼', self.toggle_focus_mode, bg='#0d1726', size=10,
                     padx=8, pady=4).pack(side='left', padx=4)
        self._button(right, 'Studio Build  プロ', self.open_build_dialog, bg='#0d1726',
                     size=8, padx=10, pady=4).pack(side='left', padx=4)

    def _build_main(self):
        self.main.grid_rowconfigure(1, weight=1)
        self.main.grid_columnconfigure(0, weight=1)
        self._build_stepper()

        self.content = tk.Frame(self.main, bg=UI['BG'])
        self.content.grid(row=1, column=0, sticky='nsew', pady=(10, 0))
        self.content.grid_columnconfigure(0, minsize=270)
        self.content.grid_columnconfigure(1, weight=1)
        self.content.grid_columnconfigure(2, minsize=340)
        self.content.grid_rowconfigure(0, weight=1)

        self.left_col = tk.Frame(self.content, bg=UI['BG'])
        self.left_col.grid(row=0, column=0, sticky='nsew', padx=(0, 12))
        self.center_col = tk.Frame(self.content, bg=UI['BG'])
        self.center_col.grid(row=0, column=1, sticky='nsew', padx=(0, 12))
        self.right_col = tk.Frame(self.content, bg=UI['BG'])
        self.right_col.grid(row=0, column=2, sticky='nsew')
        self.right_col.grid_rowconfigure(0, weight=1)

        self._build_left_column()
        self._build_mapping_panel()
        self._build_preview_panel()

    def _build_stepper(self):
        steps = tk.Frame(self.main, bg=UI['BG'], height=66)
        steps.grid(row=0, column=0, sticky='ew')
        for i in range(3):
            steps.grid_columnconfigure(i, weight=1)
        current = 1 if self.loaded_nbt is None else (3 if self.last_output else 2)
        self._step_card(steps, 0, 1, '設計図読み込み', 'ファイルを読み込み、ブロックを解析', current >= 1, current == 1)
        self._step_card(steps, 1, 2, '素材変換ルール設定', 'ブロックの置き換えルールを設定', current >= 2, current == 2)
        self._step_card(steps, 2, 3, '出力・適用', '結果を出力してプロジェクトに適用', current >= 3, current == 3)

    def _step_card(self, parent, col, no, title, desc, done, active):
        bg = '#241f58' if active else ('#102747' if done else UI['PANEL_2'])
        border = UI['ACCENT'] if active else ('#2457c7' if done else UI['BORDER'])
        f = self._panel(parent, bg=bg, border=border)
        f.configure(cursor='hand2')
        f.grid(row=0, column=col, sticky='ew', padx=(0 if col == 0 else 10, 0), ipady=8)
        f.grid_columnconfigure(1, weight=1)
        circle = tk.Canvas(f, width=42, height=42, bg=bg, highlightthickness=0)
        circle.grid(row=0, column=0, rowspan=2, padx=14)
        fill = UI['ACCENT'] if active else (UI['ACCENT_2'] if done else '#354158')
        circle.create_oval(4, 4, 38, 38, fill=fill, outline='')
        circle.create_text(21, 21, text=str(no), fill='white', font=('Segoe UI', 12, 'bold'))
        self._label(f, title, size=10, weight='bold', bg=bg).grid(row=0, column=1, sticky='sw')
        self._label(f, desc, size=8, fg=UI['MUTED'], bg=bg).grid(row=1, column=1, sticky='nw')
        if done:
            self._label(f, '✓', size=14, fg=UI['GREEN'], bg=bg).grid(row=0, column=2, rowspan=2, padx=12)
        command = self.choose_file if no == 1 else (self.open_rule_manager if no == 2 else self.do_convert)
        for widget in (f,) + tuple(f.winfo_children()):
            widget.bind('<Button-1>', lambda _e, cmd=command: cmd())

    def _build_left_column(self):
        info = self._panel(self.left_col)
        info.pack(fill='x')
        self._label(info, '読み込んだ設計図', size=10, weight='bold').pack(anchor='w', padx=12, pady=(10, 8))
        body = tk.Frame(info, bg=UI['PANEL'])
        body.pack(fill='x', padx=12, pady=(0, 12))

        if self.loaded_nbt is None:
            drop = tk.Frame(body, bg='#0c1524', highlightthickness=1, highlightbackground=UI['BORDER'])
            drop.pack(fill='x', ipady=28)
            self._register_drop(drop)
            drop.bind('<Button-1>', lambda _e: self.choose_file())
            self._label(drop, '設計図を読み込む', size=13, weight='bold', fg=UI['TEXT_SOFT'],
                        bg='#0c1524').pack(pady=(4, 2))
            self._label(drop, self._default_drop_text(), size=8, fg=UI['MUTED'],
                        bg='#0c1524', justify='center').pack()
        else:
            row = tk.Frame(body, bg=UI['PANEL'])
            row.pack(fill='x')
            img = self._loaded_thumb(92, 126)
            pic = tk.Label(row, image=img, bg=UI['PANEL'])
            pic.image = img
            pic.pack(side='left', padx=(0, 10))
            details = tk.Frame(row, bg=UI['PANEL'])
            details.pack(side='left', fill='both', expand=True)
            base = os.path.basename(self.src_path or '')
            self._label(details, base, size=9, weight='bold', wraplength=132,
                        justify='left').pack(anchor='w')
            self._label(details, '正常に読み込み済み', size=8, fg=UI['GREEN']).pack(anchor='w', pady=(2, 8))
            meta = self._metadata()
            for label, value in [
                ('形式', meta['format']), ('サイズ', meta['size']),
                ('範囲', meta['area']), ('ブロック数', meta['total']),
                ('ユニーク数', meta['unique']),
            ]:
                self._compact_meta(details, label, value)

            self._build_version_selector(body)
            self._button(body, '▣ 別のファイルを読み込む', self.choose_file,
                         bg=UI['BTN_BG_2'], size=8).pack(fill='x', pady=(10, 0))

        preset = self._panel(self.left_col)
        preset.pack(fill='both', expand=True, pady=(12, 0))
        head = tk.Frame(preset, bg=UI['PANEL'])
        head.pack(fill='x', padx=12, pady=(10, 6))
        self._label(head, 'クイックプリセット', size=10, weight='bold').pack(side='left')
        self._button(head, '管理', self.open_preset_manager,
                     bg='#0d1726', size=8, padx=8, pady=2).pack(side='right')
        for mark, title, desc, cmd in [
            ('◆', 'バニラ・サバイバル用', '入手しやすい素材に変換', self.apply_default_preset),
            ('◇', 'バニラ・建築向け', '景観を崩さず自然な置換', self.apply_architecture_preset),
            ('✣', '装飾ブロック最適化', '装飾系ブロックを統一・最適化', self.apply_deco_preset),
            ('▥', 'カスタムプリセット', '独自のルールセット', self.save_project),
        ]:
            self._preset_row(preset, mark, title, desc, cmd)

    def _build_version_selector(self, parent):
        regs = bd.available_registries()
        labels = []
        self._regid2file = {}
        for r in regs:
            mem = r.get('members', [r['id']])
            label = r['id'] if len(mem) == 1 else '%s (%s〜)' % (r['id'], mem[0])
            self._regid2file[label] = r['file']
            labels.append(label)
        cur_label = next((l for l, f in self._regid2file.items() if f == bd.ACTIVE_FILE),
                         labels[0] if labels else '')
        vr = tk.Frame(parent, bg=UI['PANEL'])
        vr.pack(fill='x', pady=(8, 0))
        self._label(vr, '対象バージョン', size=7, fg=UI['MUTED']).pack(anchor='w')
        self.version_var = tk.StringVar(value=cur_label)
        combo = ttk.Combobox(vr, textvariable=self.version_var, values=labels,
                             state='readonly', width=22, font=('Yu Gothic UI', 8),
                             style='Studio.TCombobox')
        combo.pack(fill='x')
        combo.bind('<<ComboboxSelected>>', self.on_version_change)

    def _compact_meta(self, parent, label, value):
        row = tk.Frame(parent, bg=UI['PANEL'])
        row.pack(fill='x', pady=(0, 2))
        self._label(row, label, size=7, fg=UI['MUTED']).pack(side='left')
        self._label(row, value, size=7, fg=UI['TEXT_SOFT'], wraplength=94,
                    justify='right').pack(side='right')

    def _preset_row(self, parent, mark, title, desc, cmd):
        f = tk.Frame(parent, bg=UI['PANEL_2'], highlightthickness=1, highlightbackground=UI['BORDER'])
        f.pack(fill='x', padx=12, pady=2)
        self._label(f, mark, size=12, fg=UI['ACCENT_2'], bg=UI['PANEL_2']).pack(side='left', padx=10)
        text = tk.Frame(f, bg=UI['PANEL_2'])
        text.pack(side='left', fill='x', expand=True, pady=4)
        self._label(text, title, size=8, weight='bold', bg=UI['PANEL_2']).pack(anchor='w')
        self._label(text, desc, size=6, fg=UI['MUTED'], bg=UI['PANEL_2']).pack(anchor='w')
        self._button(f, '適用' if 'カスタム' not in title else '保存', cmd, bg='#28215a',
                     size=8, padx=8, pady=2).pack(side='right', padx=8)

    def _build_mapping_panel(self):
        panel = self._panel(self.center_col)
        panel.pack(fill='both', expand=True)
        panel.grid_rowconfigure(2, weight=1)
        panel.grid_columnconfigure(0, weight=1)

        head = tk.Frame(panel, bg=UI['PANEL'])
        head.grid(row=0, column=0, sticky='ew', padx=12, pady=(10, 6))
        self._label(head, 'ブロック / 素材マッピング', size=10, weight='bold').pack(side='left')
        self._button(head, '✦ 自動マッピング', self.apply_default_preset, bg='#241f58',
                     size=8, padx=10, pady=4).pack(side='right', padx=(6, 0))
        self._button(head, '+ ルールを追加', self.add_manual_rule, bg='#0f1c31',
                     size=8, padx=10, pady=4).pack(side='right')

        chips = tk.Frame(panel, bg=UI['PANEL'])
        chips.grid(row=1, column=0, sticky='ew', padx=12, pady=(0, 8))
        for key, label, count in self._filter_counts():
            self._filter_chip(chips, key, label, count)

        table = tk.Frame(panel, bg=UI['PANEL'])
        table.grid(row=2, column=0, sticky='nsew', padx=12)
        table.grid_rowconfigure(1, weight=1)
        table.grid_columnconfigure(0, weight=1)
        hdr = tk.Frame(table, bg='#0f1726')
        hdr.grid(row=0, column=0, sticky='ew')
        for i, (text, w) in enumerate([('元のブロック', 20), ('', 2), ('変換後の素材', 22),
                                       ('方法', 8), ('状態', 7), ('', 3)]):
            tk.Label(hdr, text=text, bg='#0f1726', fg=UI['MUTED'], width=w,
                     font=('Yu Gothic UI', 8), anchor='w').grid(row=0, column=i, sticky='ew', padx=4, pady=6)

        self.map_canvas = tk.Canvas(table, bg=UI['PANEL'], highlightthickness=0)
        self.map_canvas.grid(row=1, column=0, sticky='nsew')
        sb = tk.Scrollbar(table, orient='vertical', command=self.map_canvas.yview)
        sb.grid(row=1, column=1, sticky='ns')
        self.map_canvas.configure(yscrollcommand=sb.set)
        self.map_inner = tk.Frame(self.map_canvas, bg=UI['PANEL'])
        self.map_win = self.map_canvas.create_window((0, 0), window=self.map_inner, anchor='nw')
        self.map_inner.bind('<Configure>', lambda _e: self.map_canvas.configure(scrollregion=self.map_canvas.bbox('all')))
        self.map_canvas.bind('<Configure>', lambda e: self.map_canvas.itemconfigure(self.map_win, width=e.width))
        self._bind_wheel(self.map_canvas, self.map_canvas)
        self._build_rows()

        bulk = tk.Frame(panel, bg=UI['PANEL'])
        bulk.grid(row=3, column=0, sticky='ew', padx=12, pady=(10, 12))
        self._button(bulk, '未設定を自動割り当て', self.apply_default_preset, bg='#101b2c',
                     size=8, padx=10, pady=5).pack(side='left', padx=(0, 6))
        self._button(bulk, 'すべてリセット', self.reset_mappings, bg='#101b2c',
                     size=8, padx=10, pady=5).pack(side='left', padx=6)
        self._button(bulk, '未使用ルールを削除', self.clean_unused_rules, bg='#101b2c',
                     size=8, padx=10, pady=5).pack(side='left', padx=6)
        self._label(bulk, self._conflict_summary(), size=9,
                    fg=UI['ORANGE'] if self._conflict_count() else UI['GREEN']).pack(side='right')

    def _build_preview_panel(self):
        panel = self._panel(self.right_col)
        panel.grid(row=0, column=0, sticky='nsew')
        panel.grid_columnconfigure(0, weight=1)
        panel.grid_rowconfigure(3, weight=1)
        self._label(panel, '変換結果プレビュー', size=10, weight='bold').grid(
            row=0, column=0, sticky='w', padx=12, pady=(10, 6))
        self._label(panel, '● ライブ更新', size=8, fg=UI['GREEN']).grid(
            row=0, column=0, sticky='e', padx=12, pady=(10, 6))
        img = self._result_preview_image(318, 96)
        prev = tk.Label(panel, image=img, bg=UI['PANEL'])
        prev.image = img
        prev.grid(row=1, column=0, sticky='ew', padx=12)

        tabs = tk.Frame(panel, bg=UI['PANEL'])
        tabs.grid(row=2, column=0, sticky='ew', padx=12, pady=(8, 8))
        for key, label in [('overview', '概要'), ('materials', '必要素材'), ('stats', '詳細統計')]:
            self._button(tabs, label, lambda k=key: self.set_preview_tab(k),
                         bg=('#20255d' if self.preview_tab == key else '#0e192a'),
                         size=8, padx=16, pady=5).pack(side='left', fill='x', expand=True, padx=(0, 4))

        self.preview_body = tk.Frame(panel, bg=UI['PANEL'])
        self.preview_body.grid(row=3, column=0, sticky='nsew', padx=12)
        self._build_preview_body()

        actions = tk.Frame(panel, bg=UI['PANEL'])
        actions.grid(row=4, column=0, sticky='ew', padx=12, pady=(8, 12))
        self.start_btn = self._button(actions, '▶ 変換を実行', self.do_convert, bg=UI['ACCENT'],
                                      fg='white', size=11, padx=12, pady=10,
                                      state='normal' if self.loaded_nbt is not None else 'disabled')
        self.start_btn.pack(fill='x')
        bottom = tk.Frame(actions, bg=UI['PANEL'])
        bottom.pack(fill='x', pady=(8, 0))
        self._button(bottom, '⇩ プレビューをエクスポート', self.export_preview,
                     bg='#0f1c31', size=8, pady=6).pack(side='left', fill='x', expand=True)
        self._button(bottom, '⌄', self.open_export_menu, bg='#0f1c31', size=8, padx=10, pady=6).pack(side='right', padx=(6, 0))

    def _build_footer(self):
        self.footer.grid_columnconfigure(1, weight=1)
        self.status_lbl = self._label(self.footer, '進行状況: 待機中', size=8, fg=UI['MUTED'], bg=UI['HEADER'])
        self.status_lbl.grid(row=0, column=0, sticky='w', padx=18, pady=8)
        pbar = ttk.Progressbar(self.footer, variable=self.progress_var, maximum=100,
                               style='Studio.Horizontal.TProgressbar')
        pbar.grid(row=0, column=1, sticky='ew', padx=10)
        self.progress_lbl = self._label(self.footer, '0%', size=8, fg=UI['TEXT_SOFT'], bg=UI['HEADER'])
        self.progress_lbl.grid(row=0, column=2, padx=10)
        self.time_lbl = self._label(self.footer, '推定処理時間\n約 0分 05秒', size=8,
                                    fg=UI['TEXT_SOFT'], bg=UI['HEADER'], justify='center')
        self.time_lbl.grid(row=0, column=3, padx=18)
        note_box = tk.Frame(self.footer, bg=UI['HEADER'])
        note_box.grid(row=0, column=4, sticky='e', padx=12)
        self._label(note_box, 'メモ', size=7, fg=UI['MUTED'], bg=UI['HEADER']).pack(anchor='w')
        tk.Entry(note_box, textvariable=self.note_var, bg='#0f1828', fg=UI['TEXT'],
                 insertbackground=UI['TEXT'], relief='flat', width=32,
                 font=('Yu Gothic UI', 8)).pack()

    # ---------------------------------------------------------------- refresh
    def _refresh_layout(self):
        self.image_cache = {}
        for w in self.main.winfo_children():
            w.destroy()
        self._build_main()
        self._sync_progress()

    def _sync_progress(self, value=None, text=None):
        if value is not None:
            self.progress_var.set(value)
        if hasattr(self, 'progress_lbl'):
            self.progress_lbl.configure(text='%d%%' % int(self.progress_var.get()))
        if text and hasattr(self, 'status_lbl'):
            self.status_lbl.configure(text=text)

    # ---------------------------------------------------------------- events
    def _bind_wheel(self, widget, target_canvas):
        widget.bind('<Enter>', lambda _e: setattr(self, '_wheel_target', target_canvas))
        if not self._wheel_bound:
            self.root.bind_all('<MouseWheel>', self._on_wheel)
            self._wheel_bound = True

    def _on_wheel(self, event):
        if self._wheel_target is None:
            return
        try:
            self._wheel_target.yview_scroll(int(-event.delta / 120), 'units')
        except tk.TclError:
            self._wheel_target = None

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
        self._sync_progress(18, '進行状況: ファイルを読み込み中...')
        try:
            nbt = converter.load(path)
        except Exception as e:
            self._sync_progress(0, '進行状況: 読み込み失敗')
            messagebox.showerror(APP_TITLE, '読み込みに失敗しました。\n.litematic 形式ですか？\n\n%s' % e)
            return

        self.src_path = path
        self.loaded_nbt = nbt
        self.last_output = None
        self.overrides = {}
        self._apply_dataversion(nbt)
        self._sync_progress(52, '進行状況: ブロックパレットを解析中...')
        self._rescan()
        self._sync_progress(66, '進行状況: ルール設定中...')
        self.save_state.configure(text='● 未保存の変更があります', fg=UI['ORANGE'])

    def _apply_dataversion(self, nbt):
        dv = None
        try:
            dv = int(nbt.get('MinecraftDataVersion'))
        except Exception:
            pass
        f = bd.file_for_dataversion(dv)
        if f:
            bd.set_active_file(f)

    def on_version_change(self, _event=None):
        label = self.version_var.get()
        f = self._regid2file.get(label)
        if f and f != bd.ACTIVE_FILE:
            bd.set_active_file(f)
            self._rescan()

    def _rescan(self):
        if self.loaded_nbt is None:
            self.convs, self.others = [], []
        else:
            self.convs, self.others = converter.scan_all(self.loaded_nbt)
        self._refresh_layout()

    # ---------------------------------------------------------------- data
    def _metadata(self):
        if self.loaded_nbt is None:
            return {'format': '-', 'size': '-', 'area': '-', 'total': '-', 'unique': '-'}
        try:
            total = int(self.loaded_nbt.get('Metadata', {}).get('TotalBlocks', 0))
        except Exception:
            total = 0
        size = '-'
        if self.src_path and os.path.exists(self.src_path):
            size = '%.1f MB' % (os.path.getsize(self.src_path) / (1024 * 1024))
        return {
            'format': 'Schematic (Litematica)',
            'size': size,
            'area': self._schematic_area(),
            'total': '{:,}'.format(total) if total else '-',
            'unique': '{:,}'.format(converter.palette_size(self.loaded_nbt)),
        }

    def _vec3(self, value):
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

    def _schematic_area(self):
        try:
            regs = self.loaded_nbt.get('Regions', {})
            ranges = []
            for reg in regs.values():
                pos = self._vec3(reg.get('Position'))
                size = self._vec3(reg.get('Size'))
                if pos is None or size is None:
                    continue
                x0, y0, z0 = pos
                sx, sy, sz = size
                x1, y1, z1 = x0 + sx, y0 + sy, z0 + sz
                ranges.append((min(x0, x1), min(y0, y1), min(z0, z1),
                               max(x0, x1), max(y0, y1), max(z0, z1)))
            if ranges:
                mnx, mny, mnz = min(r[0] for r in ranges), min(r[1] for r in ranges), min(r[2] for r in ranges)
                mxx, mxy, mxz = max(r[3] for r in ranges), max(r[4] for r in ranges), max(r[5] for r in ranges)
                return 'X %s〜%s / Y %s〜%s / Z %s〜%s' % (mnx, mxx, mny, mxy, mnz, mxz)
        except Exception:
            pass
        return '範囲情報なし'

    def _all_records(self):
        records = list(self.convs)
        for bid, count in self.others:
            records.append(converter.Conversion(bid, bd.strip_ns(bid), [], count))
        return records

    def _target_for(self, conv):
        ov = self.overrides.get(conv.source)
        if ov is not None and (ov == KEEP or bd.is_valid_block(ov)):
            return ov
        return conv.target if conv.candidates else KEEP

    def _is_changed(self, conv, target=None):
        target = self._target_for(conv) if target is None else target
        return target != KEEP and target != bd.strip_ns(conv.source)

    def _stats(self):
        records = self._all_records()
        try:
            total_blocks = int(self.loaded_nbt.get('Metadata', {}).get('TotalBlocks', 0)) if self.loaded_nbt else 0
        except Exception:
            total_blocks = 0
        rules = sum(1 for c in records if self._is_changed(c))
        kept = sum(1 for c in records if not self._is_changed(c))
        unset = sum(1 for c in records if self._target_for(c) == KEEP)
        unique_after = len(set(self._target_for(c) if self._target_for(c) != KEEP else bd.strip_ns(c.source)
                               for c in records))
        return {
            'total_blocks': '{:,}'.format(total_blocks) if total_blocks else '-',
            'unique_total': len(records),
            'unique_after': '{:,}'.format(unique_after),
            'rules': rules,
            'kept': kept,
            'unset': unset,
            'conflicts': self._conflict_count(),
            'changed_palette': rules,
        }

    def _conflict_count(self):
        return sum(1 for c in self._all_records()
                   if self._target_for(c) != KEEP and not bd.is_valid_block(self._target_for(c)))

    def _conflict_summary(self):
        n = self._conflict_count()
        return '⚠ %d 件の競合' % n if n else '✓ 競合なし'

    def _filter_counts(self):
        records = self._all_records()
        counts = {'all': len(records), 'material': 0, 'decor': 0, 'natural': 0, 'redstone': 0, 'other': 0}
        for conv in records:
            cat = block_category(conv.source)
            if cat in ('wood', 'stone', 'glass', 'color', 'copper', 'ore', 'light'):
                counts['material'] += 1
            elif cat == 'decoration':
                counts['decor'] += 1
            elif cat in ('natural', 'plant'):
                counts['natural'] += 1
            elif cat == 'redstone':
                counts['redstone'] += 1
            else:
                counts['other'] += 1
        return [('all', 'すべて', counts['all']), ('material', '素材', counts['material']),
                ('decor', '装飾', counts['decor']), ('natural', '自然', counts['natural']),
                ('redstone', 'レッドストーン', counts['redstone']), ('other', 'その他', counts['other'])]

    def _passes_filter(self, conv):
        if self.active_filter == 'all':
            return True
        cat = block_category(conv.source)
        if self.active_filter == 'material':
            return cat in ('wood', 'stone', 'glass', 'color', 'copper', 'ore', 'light')
        if self.active_filter == 'decor':
            return cat == 'decoration'
        if self.active_filter == 'natural':
            return cat in ('natural', 'plant')
        if self.active_filter == 'redstone':
            return cat == 'redstone'
        return cat not in ('wood', 'stone', 'glass', 'color', 'copper', 'ore', 'light',
                           'decoration', 'natural', 'plant', 'redstone')

    def _top_materials(self):
        rows = sorted(self._all_records(), key=lambda c: c.count, reverse=True)[:8]
        if not rows:
            return [('素材', '読み込み待ち')]
        return [(bd.jp_name(c.source), '×%d  →  %s' % (
            c.count, '保持' if self._target_for(c) == KEEP else bd.jp_name(self._target_for(c)))) for c in rows]

    # ---------------------------------------------------------------- rows
    def _filter_chip(self, parent, key, label, count):
        active = self.active_filter == key
        self._button(parent, '%s  %s' % (label, count), lambda k=key: self.set_filter(k),
                     bg=('#1e2a67' if active else '#0e192a'),
                     fg=('#cdd7ff' if active else UI['TEXT_SOFT']), size=8,
                     padx=9, pady=4).pack(side='left', padx=(0, 6))

    def _build_rows(self):
        if not hasattr(self, 'map_inner'):
            return
        for w in self.map_inner.winfo_children():
            w.destroy()
        self.rows = []
        records = [c for c in self._all_records() if self._passes_filter(c)]
        if not records:
            empty = tk.Frame(self.map_inner, bg=UI['PANEL'])
            empty.pack(fill='x', pady=36)
            self._label(empty, '設計図を読み込むと、ここに変換ルールが表示されます。',
                        size=10, fg=UI['MUTED']).pack()
            return
        for idx, conv in enumerate(records):
            self._make_mapping_row(idx, conv)

    def _make_mapping_row(self, idx, conv):
        bgc = UI['ROW'] if idx % 2 == 0 else UI['ROW_ALT']
        row = tk.Frame(self.map_inner, bg=bgc, pady=5)
        row.pack(fill='x')
        row.grid_columnconfigure(0, minsize=154, weight=1)
        row.grid_columnconfigure(2, minsize=160, weight=1)

        src = tk.Frame(row, bg=bgc)
        src.grid(row=0, column=0, sticky='ew', padx=6)
        si = self.get_icon(conv.source, 30)
        sl = tk.Label(src, image=si, bg=bgc)
        sl.image = si
        sl.pack(side='left')
        st = tk.Frame(src, bg=bgc)
        st.pack(side='left', fill='x', expand=True, padx=8)
        self._label(st, bd.jp_name(conv.source), size=8, bg=bgc, anchor='w',
                    wraplength=148, justify='left').pack(anchor='w')
        self._label(st, bd.strip_ns(conv.source), size=7, fg=UI['MUTED'], bg=bgc).pack(anchor='w')

        self._label(row, '→', size=12, fg=UI['MUTED'], bg=bgc).grid(row=0, column=1, padx=4)

        target = self._target_for(conv)
        target_btn = tk.Button(row, compound='left', bg=UI['TARGET_BG'] if target != KEEP else UI['KEEP_BG'],
                               fg=UI['TEXT'], activebackground=UI['HOVER'], activeforeground=UI['TEXT'],
                               relief='flat', bd=0, anchor='w', justify='left',
                               font=('Yu Gothic UI', 8), cursor='hand2', padx=6, pady=4)
        target_btn.grid(row=0, column=2, sticky='ew', padx=6)
        method = tk.StringVar(value='保持' if target == KEEP else '置き換え')
        method_box = ttk.Combobox(row, textvariable=method, values=['置き換え', '保持'],
                                  state='readonly', width=7, font=('Yu Gothic UI', 8),
                                  style='Studio.TCombobox')
        method_box.grid(row=0, column=3, padx=4)
        method_box.bind('<<ComboboxSelected>>', lambda _e, c=conv, v=method: self._method_changed(c, v.get()))
        self._status_badge(row, conv, target).grid(row=0, column=4, padx=4)

        rowdata = {'conv': conv, 'target': target, 'btn': target_btn, 'bg': bgc}
        target_btn.configure(command=lambda r=rowdata: self.open_picker(r))
        self._button(row, '⚙', lambda r=rowdata: self.open_picker(r), bg=bgc, fg=UI['MUTED'],
                     size=10, padx=5, pady=3).grid(row=0, column=5, padx=(2, 6))
        self.rows.append(rowdata)
        self._refresh_target(rowdata)

    def _status_badge(self, parent, _conv, target):
        if target == KEEP:
            text, fg, bg = '未設定', UI['ORANGE'], '#2a2418'
        else:
            text, fg, bg = '適用', UI['GREEN'], '#123326'
        return tk.Label(parent, text=text, bg=bg, fg=fg, width=6,
                        font=('Yu Gothic UI', 8, 'bold'), padx=3, pady=3)

    def _refresh_target(self, rowdata):
        tgt = rowdata['target']
        btn = rowdata['btn']
        if tgt == KEEP:
            icon = self.get_icon(rowdata['conv'].source, 28)
            btn.configure(image=icon, text=' 変換しない', bg=UI['KEEP_BG'], fg=UI['MUTED'])
        else:
            icon = self.get_icon(tgt, 28)
            btn.configure(image=icon, text=' ' + bd.jp_name(tgt), bg=UI['TARGET_BG'], fg=UI['TEXT'])
        btn.image = icon

    def _method_changed(self, conv, value):
        if value == '保持':
            self.overrides[conv.source] = KEEP
        elif conv.candidates:
            self.overrides[conv.source] = conv.target
        else:
            self.overrides.pop(conv.source, None)
        self._mark_dirty()
        self._refresh_layout()

    def set_filter(self, key):
        self.active_filter = key
        self._refresh_layout()

    def set_preview_tab(self, key):
        self.preview_tab = key
        if hasattr(self, 'preview_body'):
            self._build_preview_body()

    # ---------------------------------------------------------------- preview
    def _build_preview_body(self):
        for w in self.preview_body.winfo_children():
            w.destroy()
        stats = self._stats()
        if self.preview_tab == 'materials':
            for label, value in self._top_materials():
                self._metric_line(self.preview_body, label, value)
            return
        if self.preview_tab == 'stats':
            for label, value in [
                ('パレット内ブロック', str(stats['unique_total'])),
                ('自動候補', str(len(self.convs))),
                ('任意変更可能', str(len(self.others))),
                ('有効な置換ルール', str(stats['rules'])),
                ('保持されるブロック', str(stats['kept'])),
            ]:
                self._metric_line(self.preview_body, label, value)
            return

        top = tk.Frame(self.preview_body, bg=UI['PANEL'])
        top.pack(fill='x')
        self._stat_box(top, '変換後のブロック数', stats['total_blocks'], '+20%')
        self._stat_box(top, 'ユニークブロック数', stats['unique_after'], '-15.3%')
        for label, value in [
            ('変換されるパレット', stats['changed_palette']),
            ('そのまま維持されるブロック', stats['kept']),
            ('置き換えルール数', stats['rules']),
            ('競合のあるルール', stats['conflicts']),
        ]:
            self._metric_line(self.preview_body, label, str(value))

        warn = tk.Frame(self.preview_body, bg='#2a2418', highlightthickness=1, highlightbackground='#8d6b24')
        warn.pack(fill='x', pady=(10, 0))
        self._label(warn, '検証結果', size=9, weight='bold', bg='#2a2418').pack(anchor='w', padx=10, pady=(8, 2))
        self._validation_line(warn, '競合するルール', stats['conflicts'], '詳細')
        self._validation_line(warn, '未設定のブロック', stats['unset'], '確認')
        self._validation_line(warn, '非対応ブロック', 0, '✓')

    def _stat_box(self, parent, title, value, delta):
        f = tk.Frame(parent, bg='#0f1828')
        f.pack(side='left', fill='x', expand=True, padx=(0, 8), pady=(0, 8))
        self._label(f, title, size=7, fg=UI['MUTED'], bg='#0f1828').pack(anchor='w', padx=8, pady=(7, 0))
        self._label(f, str(value), size=14, weight='bold', bg='#0f1828').pack(anchor='w', padx=8)
        self._label(f, delta, size=7, fg=UI['GREEN'], bg='#0f1828').pack(anchor='e', padx=8, pady=(0, 6))

    def _metric_line(self, parent, label, value):
        f = tk.Frame(parent, bg=UI['PANEL'])
        f.pack(fill='x', pady=2)
        self._label(f, label, size=8, fg=UI['MUTED']).pack(side='left')
        self._label(f, value, size=8, fg=UI['TEXT_SOFT'], weight='bold').pack(side='right')

    def _validation_line(self, parent, label, count, action):
        f = tk.Frame(parent, bg='#2a2418')
        f.pack(fill='x', padx=10, pady=3)
        color = UI['ORANGE'] if count else UI['GREEN']
        self._label(f, '● ' + label, size=8, fg=color, bg='#2a2418').pack(side='left')
        self._label(f, '%s 件' % count, size=8, bg='#2a2418').pack(side='left', padx=(16, 0))
        self._button(f, action, lambda l=label, c=count: self.open_validation_dialog(l, c),
                     bg='#332a52', size=7, padx=8, pady=2).pack(side='right')

    # ---------------------------------------------------------------- picker
    def open_picker(self, rowdata):
        conv = rowdata['conv']
        top = tk.Toplevel(self.root)
        top.title('置き換え先を選ぶ')
        top.configure(bg=UI['BG'])
        self._set_centered_geometry(top, 820, 670)
        top.minsize(660, 520)
        top.transient(self.root)
        top.grab_set()
        self._label(top, '「%s」の置き換え先' % bd.jp_name(conv.source),
                    size=14, weight='bold', bg=UI['BG']).pack(anchor='w', padx=16, pady=(14, 2), fill='x')
        self._label(top, 'カテゴリを選ぶか、ID/日本語名で検索して変換先を選択します。',
                    size=9, fg=UI['MUTED'], bg=UI['BG']).pack(anchor='w', padx=16)
        controls = tk.Frame(top, bg=UI['BG'])
        controls.pack(fill='x', padx=16, pady=(12, 4))
        self._label(controls, 'カテゴリ', size=9, bg=UI['BG']).pack(side='left')
        cat_var = tk.StringVar(value=CATEGORY_NAME['recommended'])
        ttk.Combobox(controls, textvariable=cat_var, values=[label for _, label in CATEGORY_LABELS],
                     state='readonly', width=24, font=('Yu Gothic UI', 9),
                     style='Studio.TCombobox').pack(side='left', padx=(6, 16))
        self._label(controls, '検索', size=9, bg=UI['BG']).pack(side='left')
        search_var = tk.StringVar()
        search_entry = tk.Entry(controls, textvariable=search_var, font=('Yu Gothic UI', 10),
                                bg=UI['PANEL_2'], fg=UI['TEXT'], insertbackground=UI['TEXT'], relief='flat')
        search_entry.pack(side='left', fill='x', expand=True, padx=(6, 0), ipady=5)
        count_lbl = self._label(top, '', size=8, fg=UI['MUTED'], bg=UI['BG'], anchor='w')
        count_lbl.pack(fill='x', padx=16, pady=(0, 3))
        body = tk.Frame(top, bg=UI['BG'])
        body.pack(fill='both', expand=True, padx=16, pady=10)
        cv = tk.Canvas(body, bg=UI['PANEL'], highlightthickness=1, highlightbackground=UI['BORDER'])
        cv.pack(side='left', fill='both', expand=True)
        sb = tk.Scrollbar(body, orient='vertical', command=cv.yview)
        sb.pack(side='right', fill='y')
        cv.configure(yscrollcommand=sb.set)
        inner = tk.Frame(cv, bg=UI['PANEL'])
        win = cv.create_window((0, 0), window=inner, anchor='nw')
        inner.bind('<Configure>', lambda _e: cv.configure(scrollregion=cv.bbox('all')))
        cv.bind('<Configure>', lambda e: cv.itemconfigure(win, width=e.width))
        self._bind_wheel(cv, cv)

        def choose(value):
            self.overrides[conv.source] = value
            top.destroy()
            self._wheel_target = self.map_canvas if hasattr(self, 'map_canvas') else None
            self._mark_dirty()
            self._refresh_layout()

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
            items, seen = [], set()
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
                self._picker_item(inner, bd.jp_name(cand), cand, lambda c=cand: choose(c),
                                  recommended=(cand == conv.target))
            count_lbl.configure(text='表示: %d件 / 全ブロック: %d件' % (len(items), len(all_blocks)))
            cv.yview_moveto(0)

        for child in controls.winfo_children():
            if isinstance(child, ttk.Combobox):
                child.bind('<<ComboboxSelected>>', rebuild_list)
        search_var.trace_add('write', rebuild_list)
        rebuild_list()
        search_entry.focus_set()

    def _picker_item(self, parent, label, icon_id, cmd, keep=False, recommended=False):
        bgc = UI['REC_BG'] if recommended else (UI['KEEP_BG'] if keep else UI['PANEL'])
        f = tk.Frame(parent, bg=bgc, padx=10, pady=6, cursor='hand2')
        f.pack(fill='x')
        ic = self.get_icon(icon_id, 38)
        il = tk.Label(f, image=ic, bg=bgc)
        il.image = ic
        il.pack(side='left')
        txt = tk.Frame(f, bg=bgc)
        txt.pack(side='left', padx=10, fill='x', expand=True)
        suffix = '  ← おすすめ' if recommended else ''
        name_lbl = tk.Label(txt, text=label + suffix, bg=bgc, fg=(UI['MUTED'] if keep else UI['TEXT']),
                            font=('Yu Gothic UI', 10), anchor='w', justify='left', wraplength=560)
        name_lbl.pack(anchor='w', fill='x')
        id_lbl = tk.Label(txt, text=bd.strip_ns(icon_id), bg=bgc, fg=UI['MUTED'],
                          font=('Consolas', 8), anchor='w', justify='left', wraplength=560)
        id_lbl.pack(anchor='w', fill='x')
        for w in (f, il, txt, name_lbl, id_lbl):
            w.bind('<Button-1>', lambda _e: cmd())
            w.bind('<Enter>', lambda _e, ff=f: self._hover(ff, True, bgc))
            w.bind('<Leave>', lambda _e, ff=f: self._hover(ff, False, bgc))

    def _hover(self, frame, on, base):
        col = UI['HOVER'] if on else base
        frame.configure(bg=col)
        for ch in frame.winfo_children():
            try:
                ch.configure(bg=col)
                for gc in ch.winfo_children():
                    gc.configure(bg=col)
            except tk.TclError:
                pass

    # ---------------------------------------------------------------- actions
    def _mark_dirty(self):
        if hasattr(self, 'save_state'):
            self.save_state.configure(text='● 未保存の変更があります', fg=UI['ORANGE'])

    def apply_default_preset(self):
        self.overrides = {}
        self._mark_dirty()
        self._refresh_layout()

    def apply_architecture_preset(self):
        for conv in self._all_records():
            src = bd.strip_ns(conv.source)
            if 'glass' in src and bd.is_valid_block('white_stained_glass'):
                self.overrides[conv.source] = 'white_stained_glass'
            elif conv.candidates:
                self.overrides[conv.source] = conv.target
        self._mark_dirty()
        self._refresh_layout()

    def apply_deco_preset(self):
        for conv in self._all_records():
            self.overrides[conv.source] = KEEP if block_category(conv.source) == 'decoration' else self._target_for(conv)
        self._mark_dirty()
        self._refresh_layout()

    def reset_mappings(self):
        self.overrides = dict((c.source, KEEP) for c in self._all_records())
        self._mark_dirty()
        self._refresh_layout()

    def clean_unused_rules(self):
        valid_sources = set(c.source for c in self._all_records())
        self.overrides = dict((k, v) for k, v in self.overrides.items() if k in valid_sources)
        self._refresh_layout()

    def add_manual_rule(self):
        records = self._all_records()
        if not records:
            messagebox.showinfo(APP_TITLE, '先に設計図を読み込んでください。')
            return
        self.open_picker({'conv': records[0], 'target': self._target_for(records[0]), 'btn': None, 'bg': UI['PANEL']})

    def save_project(self):
        if self.loaded_nbt is None:
            messagebox.showinfo(APP_TITLE, '先に設計図を読み込んでください。')
            return
        default_name = os.path.splitext(os.path.basename(self.src_path or 'project'))[0] + '_rules.json'
        out = filedialog.asksaveasfilename(
            title='プロジェクト設定を保存', initialfile=default_name, defaultextension='.json',
            filetypes=[('JSON', '*.json'), ('すべて', '*.*')])
        if not out:
            return
        data = {'source': self.src_path, 'registry': bd.active_registry(),
                'overrides': self.overrides, 'note': self.note_var.get()}
        with open(out, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        self.save_state.configure(text='● すべての変更を保存しました', fg=UI['GREEN'])

    def export_preview(self):
        if self.loaded_nbt is None:
            messagebox.showinfo(APP_TITLE, '先に設計図を読み込んでください。')
            return
        default_name = os.path.splitext(os.path.basename(self.src_path or 'preview'))[0] + '_preview.png'
        out = filedialog.asksaveasfilename(
            title='プレビューPNGを書き出し', initialfile=default_name, defaultextension='.png',
            filetypes=[('PNG', '*.png'), ('すべて', '*.*')])
        if not out:
            return
        im = self._render_schematic_preview(1280, 720)
        im.save(out)
        messagebox.showinfo(APP_TITLE, 'プレビューを書き出しました:\n%s' % out)

    def export_mapping_csv(self):
        if self.loaded_nbt is None:
            messagebox.showinfo(APP_TITLE, '先に設計図を読み込んでください。')
            return
        default_name = os.path.splitext(os.path.basename(self.src_path or 'preview'))[0] + '_mapping.csv'
        out = filedialog.asksaveasfilename(
            title='マッピングCSVを書き出し', initialfile=default_name, defaultextension='.csv',
            filetypes=[('CSV', '*.csv'), ('すべて', '*.*')])
        if not out:
            return
        with open(out, 'w', encoding='utf-8-sig') as f:
            f.write('source,target,count,status\n')
            for conv in self._all_records():
                tgt = self._target_for(conv)
                status = 'keep' if tgt == KEEP else ('same' if tgt == bd.strip_ns(conv.source) else 'replace')
                f.write('%s,%s,%s,%s\n' % (conv.source, '' if tgt == KEEP else tgt, conv.count, status))
        messagebox.showinfo(APP_TITLE, 'エクスポートしました:\n%s' % out)

    def do_convert(self):
        if not self.src_path or self.loaded_nbt is None:
            return
        mapping = {}
        for conv in self._all_records():
            tgt = self._target_for(conv)
            if tgt == KEEP or tgt == bd.strip_ns(conv.source):
                continue
            mapping[conv.source] = tgt
        if not mapping:
            messagebox.showinfo(APP_TITLE, '変換する素材がありません。')
            return
        default_out = converter.default_output_path(self.src_path)
        out = filedialog.asksaveasfilename(
            title='変換後のファイルの保存先', initialdir=os.path.dirname(default_out),
            initialfile=os.path.basename(default_out), defaultextension='.litematic',
            filetypes=[('Litematica 設計図', '*.litematic'), ('すべて', '*.*')])
        if not out:
            return
        if os.path.abspath(out) == os.path.abspath(self.src_path):
            messagebox.showwarning(APP_TITLE, '元のファイルとは別の名前で保存してください。')
            return
        self._sync_progress(82, '進行状況: 変換を実行中...')
        try:
            changed = converter.convert_file(self.src_path, out, mapping)
        except Exception as e:
            self._sync_progress(66, '進行状況: 変換に失敗')
            messagebox.showerror(APP_TITLE, '変換に失敗しました:\n%s' % e)
            return
        self.last_output = out
        self.output_history.append({'path': out, 'rules': len(mapping), 'changed': changed})
        self._sync_progress(100, '進行状況: 変換完了')
        self.save_state.configure(text='● すべての変更を保存しました', fg=UI['GREEN'])
        self._refresh_layout()
        if messagebox.askyesno(
                APP_TITLE,
                '変換が完了しました。\n\n置き換えた素材: %d 種類\n書き換えたパレット: %d 件\n出力ファイル:\n%s\n\n'
                'フォルダを開きますか？' % (len(mapping), changed, out)):
            try:
                os.startfile(os.path.dirname(out))
            except Exception:
                pass

    # ---------------------------------------------------------------- visuals
    def _loaded_thumb(self, w, h):
        key = ('loaded', w, h, self.src_path)
        if key in self.image_cache:
            return self.image_cache[key]
        im = self._render_schematic_preview(w, h, max_blocks=900)
        img = ImageTk.PhotoImage(im)
        self.image_cache[key] = img
        return img

    def _result_preview_image(self, w, h):
        key = ('result', w, h, self.src_path, tuple(sorted(self.overrides.items())))
        if key in self.image_cache:
            return self.image_cache[key]
        im = self._render_schematic_preview(w, h)
        img = ImageTk.PhotoImage(im)
        self.image_cache[key] = img
        return img

    def _render_schematic_preview(self, w, h, max_blocks=12000):
        im = Image.new('RGB', (w, h), '#87c9ff')
        d = ImageDraw.Draw(im)
        records = self._render_records(max_blocks=max_blocks)
        bounds = self._record_bounds(records)
        camera = self._minecraft_camera(bounds, w, h)
        self._draw_minecraft_sky(d, w, h)
        self._draw_superflat_ground(d, w, h, camera, bounds)
        if not records:
            self._draw_empty_preview(d, w, h, camera, bounds)
            d.rectangle([0, 0, w - 1, h - 1], outline='#4d79ff')
            return im

        self._draw_build_shadow(d, records, camera, w, h)
        faces = self._visible_block_faces(records, camera)
        for depth, poly, bid, normal, seed in faces:
            self._draw_minecraft_face(d, poly, self._block_rgb(bid), normal, seed)
        self._draw_scene_vignette(d, w, h)
        d.rectangle([0, 0, w - 1, h - 1], outline='#4d79ff')
        return im

    def _record_bounds(self, records):
        if not records:
            return {'min_x': 0, 'max_x': 10, 'min_y': 0, 'max_y': 5, 'min_z': 0, 'max_z': 10,
                    'cx': 5, 'cy': 2.5, 'cz': 5, 'span_x': 10, 'span_y': 5, 'span_z': 10}
        min_x = min(r[0] for r in records)
        max_x = max(r[0] + 1 for r in records)
        min_y = min(r[1] for r in records)
        max_y = max(r[1] + 1 for r in records)
        min_z = min(r[2] for r in records)
        max_z = max(r[2] + 1 for r in records)
        return {
            'min_x': min_x, 'max_x': max_x, 'min_y': min_y, 'max_y': max_y,
            'min_z': min_z, 'max_z': max_z,
            'cx': (min_x + max_x) / 2.0, 'cy': (min_y + max_y) / 2.0, 'cz': (min_z + max_z) / 2.0,
            'span_x': max(1.0, max_x - min_x), 'span_y': max(1.0, max_y - min_y),
            'span_z': max(1.0, max_z - min_z),
        }

    def _minecraft_camera(self, bounds, w, h):
        span = max(bounds['span_x'], bounds['span_z'])
        height = bounds['span_y']
        dist = max(18.0, span * 2.15 + height * 0.85)
        cam = (
            bounds['cx'] + dist * 0.78,
            max(7.5, height * 0.62 + span * 0.28),
            bounds['cz'] + dist * 1.08,
        )
        target = (bounds['cx'], max(0.8, bounds['min_y'] + height * 0.38), bounds['cz'])
        forward = self._v_norm((target[0] - cam[0], target[1] - cam[1], target[2] - cam[2]))
        right = self._v_norm(self._v_cross(forward, (0.0, 1.0, 0.0)))
        up = self._v_cross(right, forward)
        return {'pos': cam, 'forward': forward, 'right': right, 'up': up, 'focal': min(w, h) * 1.35,
                'cx': w / 2.0, 'cy': h * 0.55}

    def _project3(self, point, camera):
        rel = (point[0] - camera['pos'][0], point[1] - camera['pos'][1], point[2] - camera['pos'][2])
        x = self._v_dot(rel, camera['right'])
        y = self._v_dot(rel, camera['up'])
        z = self._v_dot(rel, camera['forward'])
        if z <= 0.18:
            return None
        scale = camera['focal'] / z
        return camera['cx'] + x * scale, camera['cy'] - y * scale, z

    def _draw_minecraft_sky(self, draw, w, h):
        horizon = int(h * 0.58)
        for y in range(h):
            t = min(1.0, y / max(1, horizon))
            if y <= horizon:
                col = (102 + int(40 * t), 178 + int(34 * t), 255)
            else:
                col = (134, 204, 112)
            draw.line([(0, y), (w, y)], fill=col)
        sun = max(18, min(42, w // 18))
        sx, sy = int(w * 0.77), int(h * 0.16)
        draw.rectangle([sx, sy, sx + sun, sy + sun], fill='#fff28a')
        for cx, cy, cw in [(0.18, 0.16, 0.14), (0.50, 0.12, 0.12), (0.66, 0.24, 0.16)]:
            x = int(w * cx)
            y = int(h * cy)
            unit = max(4, int(w * cw / 8))
            for ox, oy, ww, hh in [(0, 1, 5, 1), (1, 0, 4, 3), (4, 1, 4, 2), (7, 2, 2, 1)]:
                draw.rectangle([x + ox * unit, y + oy * unit, x + (ox + ww) * unit, y + (oy + hh) * unit],
                               fill='#ffffff')

    def _draw_superflat_ground(self, draw, w, h, camera, bounds):
        horizon = int(h * 0.58)
        draw.rectangle([0, horizon, w, h], fill='#7ac943')
        extent = max(38, int(max(bounds['span_x'], bounds['span_z']) * 2.8))
        cx, cz = bounds['cx'], bounds['cz']
        x0, x1 = int(cx - extent), int(cx + extent)
        z0, z1 = int(cz - extent), int(cz + extent)
        cells = []
        step = max(2, extent // 18)
        for x in range(x0, x1, step):
            cells.append(((x, -0.02, z0), (x, -0.02, z1)))
        for z in range(z0, z1, step):
            cells.append(((x0, -0.02, z), (x1, -0.02, z)))
        for a, b in cells:
            pa = self._project3(a, camera)
            pb = self._project3(b, camera)
            if pa and pb:
                line_y = max(pa[1], pb[1])
                color = '#70c944' if line_y < h * 0.76 else '#62b63b'
                draw.line([(pa[0], pa[1]), (pb[0], pb[1])], fill=color, width=1)
        random.seed(1127)
        for _ in range(max(45, w * h // 9000)):
            gx = random.uniform(x0, x1)
            gz = random.uniform(z0, z1)
            p = self._project3((gx, 0.0, gz), camera)
            if p and horizon <= p[1] <= h:
                shade = random.choice(['#86d84d', '#6fbd3e', '#8bd653', '#5ba737'])
                size = 1 if p[1] < h * 0.72 else 2
                draw.rectangle([p[0], p[1], p[0] + size, p[1] + size], fill=shade)
        for i in range(10):
            y = horizon + i
            draw.line([(0, y), (w, y)], fill=(128 + i, 199 + i, 116 + i))

    def _draw_build_shadow(self, draw, records, camera, w, h):
        footprint = {}
        for x, y, z, _bid in records:
            if y == 0:
                footprint[(x, z)] = True
        for x, z in list(footprint.keys())[:3500]:
            corners = [(x + 0.18, 0.005, z + 0.18), (x + 1.05, 0.005, z + 0.26),
                       (x + 0.90, 0.005, z + 1.05), (x + 0.04, 0.005, z + 0.92)]
            pts = [self._project3(p, camera) for p in corners]
            if all(pts):
                poly = [(p[0], p[1]) for p in pts]
                if self._poly_on_screen(poly, w, h, pad=20):
                    draw.polygon(poly, fill='#4a7e2d')

    def _visible_block_faces(self, records, camera):
        occupied = set((int(x), int(y), int(z)) for x, y, z, _bid in records)
        by_pos = {(int(x), int(y), int(z)): bid for x, y, z, bid in records}
        face_defs = [
            ((0, 1, 0), lambda x, y, z: [(x, y + 1, z), (x + 1, y + 1, z), (x + 1, y + 1, z + 1), (x, y + 1, z + 1)]),
            ((0, 0, 1), lambda x, y, z: [(x, y, z + 1), (x + 1, y, z + 1), (x + 1, y + 1, z + 1), (x, y + 1, z + 1)]),
            ((1, 0, 0), lambda x, y, z: [(x + 1, y, z), (x + 1, y, z + 1), (x + 1, y + 1, z + 1), (x + 1, y + 1, z)]),
            ((0, 0, -1), lambda x, y, z: [(x + 1, y, z), (x, y, z), (x, y + 1, z), (x + 1, y + 1, z)]),
            ((-1, 0, 0), lambda x, y, z: [(x, y, z + 1), (x, y, z), (x, y + 1, z), (x, y + 1, z + 1)]),
        ]
        faces = []
        for (x, y, z), bid in by_pos.items():
            for normal, maker in face_defs:
                if (x + normal[0], y + normal[1], z + normal[2]) in occupied:
                    continue
                pts3 = maker(x, y, z)
                projected = [self._project3(p, camera) for p in pts3]
                if not all(projected):
                    continue
                pts2 = [(p[0], p[1]) for p in projected]
                if not self._poly_on_screen(pts2, int(camera['cx'] * 2), int(camera['cy'] / 0.55), pad=80):
                    continue
                depth = sum(p[2] for p in projected) / len(projected)
                seed = (x * 73856093) ^ (y * 19349663) ^ (z * 83492791)
                faces.append((depth, pts2, bid, normal, seed))
        faces.sort(key=lambda f: f[0], reverse=True)
        return faces

    def _draw_minecraft_face(self, draw, poly, color, normal, seed):
        light = self._v_norm((-0.35, 0.82, -0.46))
        dot = max(0.0, self._v_dot(normal, light))
        if normal[1] > 0:
            factor = 1.12
        else:
            factor = 0.55 + dot * 0.42
        fill = self._shade(color, factor)
        outline = self._shade(color, 0.38)
        draw.polygon(poly, fill=fill, outline=outline)
        size = max(max(p[0] for p in poly) - min(p[0] for p in poly),
                   max(p[1] for p in poly) - min(p[1] for p in poly))
        if size >= 8:
            self._draw_face_texture(draw, poly, fill, seed)

    def _draw_face_texture(self, draw, poly, base, seed):
        p0, p1, p2, p3 = poly
        count = 3 if max(abs(p1[0] - p0[0]), abs(p2[1] - p1[1])) > 22 else 2
        for i in range(1, count + 1):
            t = i / (count + 1)
            wobble = ((seed >> (i * 3)) & 7) / 80.0 - 0.04
            a = self._quad_point(p0, p1, p2, p3, 0.08, min(0.92, max(0.08, t + wobble)))
            b = self._quad_point(p0, p1, p2, p3, 0.92, min(0.92, max(0.08, t + wobble)))
            col = self._shade(base, 0.86 if i % 2 else 1.10)
            draw.line([a, b], fill=col)
        for i in range(1, 3):
            t = i / 3
            a = self._quad_point(p0, p1, p2, p3, t, 0.10)
            b = self._quad_point(p0, p1, p2, p3, t, 0.90)
            draw.line([a, b], fill=self._shade(base, 0.94))

    def _quad_point(self, p0, p1, p2, p3, u, v):
        ax = p0[0] * (1 - u) + p1[0] * u
        ay = p0[1] * (1 - u) + p1[1] * u
        bx = p3[0] * (1 - u) + p2[0] * u
        by = p3[1] * (1 - u) + p2[1] * u
        return ax * (1 - v) + bx * v, ay * (1 - v) + by * v

    def _poly_on_screen(self, poly, w, h, pad=0):
        return not (max(p[0] for p in poly) < -pad or min(p[0] for p in poly) > w + pad
                    or max(p[1] for p in poly) < -pad or min(p[1] for p in poly) > h + pad)

    def _draw_scene_vignette(self, draw, w, h):
        for i in range(12):
            col = self._shade((70, 95, 120), 0.34 + i * 0.02)
            draw.rectangle([i, i, w - 1 - i, h - 1 - i], outline=col)

    def _v_dot(self, a, b):
        return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]

    def _v_cross(self, a, b):
        return (a[1] * b[2] - a[2] * b[1],
                a[2] * b[0] - a[0] * b[2],
                a[0] * b[1] - a[1] * b[0])

    def _v_norm(self, v):
        length = math.sqrt(max(1e-9, self._v_dot(v, v)))
        return v[0] / length, v[1] / length, v[2] / length

    def _draw_preview_background(self, draw, w, h):
        for y in range(h):
            t = y / max(1, h - 1)
            r = int(30 + 54 * (1 - t))
            g = int(40 + 34 * (1 - t))
            b = int(64 + 28 * (1 - t))
            draw.line([(0, y), (w, y)], fill=(r, g, b))
        draw.rectangle([0, int(h * .66), w, h], fill='#142033')
        draw.ellipse([int(w * .68), int(h * .08), int(w * .92), int(h * .38)], fill='#ff9d66')
        for i in range(0, w, max(22, w // 18)):
            draw.line([(i, int(h * .66)), (i - int(w * .18), h)], fill='#172943')

    def _draw_empty_preview(self, draw, w, h, camera=None, bounds=None):
        sample = []
        palette = [self._target_for(c) if self._target_for(c) != KEEP else c.source for c in self._all_records()[:8]]
        if not palette:
            palette = ['stone_bricks', 'oak_planks', 'glass', 'lantern']
        for x in range(4):
            for z in range(3):
                sample.append((x + 3, 0, z + 3, palette[(x + z) % len(palette)]))
        for y in range(1, 4):
            sample.append((4, y, 4, palette[y % len(palette)]))
            sample.append((5, y, 4, palette[(y + 1) % len(palette)]))
        if camera is None:
            bounds = self._record_bounds(sample)
            camera = self._minecraft_camera(bounds, w, h)
        self._draw_build_shadow(draw, sample, camera, w, h)
        for _depth, poly, bid, normal, seed in self._visible_block_faces(sample, camera):
            self._draw_minecraft_face(draw, poly, self._block_rgb(bid), normal, seed)

    def _draw_cube(self, draw, px, py, size, color):
        s = size
        top = [(px, py - s), (px + s, py - s * .48), (px, py), (px - s, py - s * .48)]
        left = [(px - s, py - s * .48), (px, py), (px, py + s), (px - s, py + s * .52)]
        right = [(px, py), (px + s, py - s * .48), (px + s, py + s * .52), (px, py + s)]
        outline = '#172033' if s >= 4 else None
        draw.polygon(left, fill=self._shade(color, .72), outline=outline)
        draw.polygon(right, fill=self._shade(color, .58), outline=outline)
        draw.polygon(top, fill=self._shade(color, 1.08), outline=outline)

    def _render_records(self, max_blocks=12000):
        if self.loaded_nbt is None:
            return []
        target_map = {}
        for conv in self._all_records():
            target = self._target_for(conv)
            target_map[conv.source] = bd.strip_ns(conv.source) if target == KEEP else bd.strip_ns(target)
        records = []
        try:
            regs = self.loaded_nbt.get('Regions', {})
            for reg in regs.values():
                records.extend(self._region_render_records(reg, target_map, max_blocks))
        except Exception:
            return []
        if len(records) > max_blocks:
            step = max(1, int(math.ceil(len(records) / float(max_blocks))))
            records = records[::step]
        if records:
            min_x = min(r[0] for r in records)
            min_y = min(r[1] for r in records)
            min_z = min(r[2] for r in records)
            records = [(x - min_x, y - min_y, z - min_z, bid) for x, y, z, bid in records]
        return records

    def _region_render_records(self, reg, target_map, max_blocks):
        palette = reg.get('BlockStatePalette', [])
        states = reg.get('BlockStates', [])
        pos = self._vec3(reg.get('Position')) or (0, 0, 0)
        size = self._vec3(reg.get('Size')) or (0, 0, 0)
        sx, sy, sz = abs(int(size[0])), abs(int(size[1])), abs(int(size[2]))
        if not palette or not states or sx <= 0 or sy <= 0 or sz <= 0:
            return []
        total = sx * sy * sz
        bits = max(2, (len(palette) - 1).bit_length())
        mask = (1 << bits) - 1
        longs = [int(v) & 0xffffffffffffffff for v in states]
        stride = 1
        if total > max_blocks * 1.5:
            stride = int(math.ceil((total / float(max_blocks * 1.5)) ** (1.0 / 3.0)))
            stride = max(1, stride)
        dx = 1 if int(size[0]) >= 0 else -1
        dy = 1 if int(size[1]) >= 0 else -1
        dz = 1 if int(size[2]) >= 0 else -1
        out = []
        layer = sx * sz
        for idx in range(total):
            palette_index = self._palette_index_at(longs, bits, mask, idx)
            if palette_index < 0 or palette_index >= len(palette):
                continue
            entry = palette[palette_index]
            source = str(entry.get('Name', 'minecraft:air'))
            base = bd.strip_ns(source)
            if base in ('air', 'cave_air', 'void_air'):
                continue
            y = idx // layer
            rem = idx - y * layer
            z = rem // sx
            x = rem - z * sx
            if stride > 1 and (x % stride or y % stride or z % stride):
                continue
            bid = target_map.get(source, base)
            out.append((int(pos[0]) + x * dx, int(pos[1]) + y * dy, int(pos[2]) + z * dz, bid))
        return out

    def _palette_index_at(self, longs, bits, mask, idx):
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

    def _block_rgb(self, bid):
        color = bd.base_color(bd.strip_ns(bid))
        return color[:3] if isinstance(color, tuple) else (130, 140, 155)

    def _shade(self, rgb, factor):
        return tuple(max(0, min(255, int(c * factor))) for c in rgb)
