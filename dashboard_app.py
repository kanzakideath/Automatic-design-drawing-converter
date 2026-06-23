# -*- coding: utf-8 -*-
"""Dark dashboard UI for the schematic material converter."""

import json
import math
import os
import random
import csv
import ctypes
import threading
import time
import tkinter as tk
from tkinter import font as tkfont
from tkinter import filedialog, messagebox, ttk

try:
    from tkinterdnd2 import DND_FILES
    _HAS_DND = True
except Exception:
    DND_FILES = None
    _HAS_DND = False

from PIL import Image, ImageChops, ImageDraw, ImageFont, ImageTk

import blockdata as bd
import converter
import icons
import updater

try:
    import gpu_preview as preview_geom
except Exception:
    preview_geom = None


APP_TITLE = '設計図自動素材変換ツール'
KEEP = '__keep__'
GPU_PREVIEW_BLOCK_LIMIT = 220000
GPU_PREVIEW_FACE_LIMIT = 120000
CPU_PREVIEW_IDLE_BLOCK_LIMIT = 1050
CPU_PREVIEW_IDLE_FACE_LIMIT = 1350
CPU_PREVIEW_TEXTURE_FACE_LIMIT = 360
CPU_PREVIEW_DRAG_BLOCK_LIMIT = 42
CPU_PREVIEW_DRAG_FACE_LIMIT = 60

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
    'BG': '#070b12', 'SIDEBAR': '#0b111b', 'HEADER': '#0b111b',
    'PANEL': '#101823', 'PANEL_2': '#151f2c', 'PANEL_3': '#1d2a3a',
    'ROW': '#101823', 'ROW_ALT': '#131d29', 'BORDER': '#263447',
    'BORDER_HI': '#3da2ff', 'TEXT': '#ecf3fb', 'TEXT_SOFT': '#c8d3df',
    'MUTED': '#8696a8', 'MUTED_2': '#617083', 'ACCENT': '#2f8cff',
    'ACCENT_2': '#44d7ff', 'ACCENT_3': '#7c5cff', 'ACCENT_DK': '#1467d8',
    'CYAN': '#44d7ff', 'GREEN': '#36d182', 'ORANGE': '#ffb34d',
    'RED': '#ff5c6c', 'BTN_BG': '#1a2635', 'BTN_BG_2': '#202d3d',
    'KEEP_BG': '#16202c', 'TARGET_BG': '#123021', 'REC_BG': '#172542',
    'HOVER': '#24364a', 'CARD': '#121b27', 'BADGE_BG': '#172b48',
    'BADGE_FG': '#8bc6ff', 'NBADGE_BG': '#17202d', 'NBADGE_FG': '#b9c7d6',
    'WARNING_BG': '#2f2512', 'SUCCESS_BG': '#10291d', 'DROP_BG': '#0d1724',
}
UI_FONT_BOOST = 2


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
        self.font = ('Yu Gothic UI', size + UI_FONT_BOOST, weight)
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
        radius = self.radius or max(14, min(24, height // 2))
        img = Image.new('RGBA', (width * scale, height * scale), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        shadow = (0, 0, 0, 28)
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


class InteractivePreview(tk.Canvas):
    def __init__(self, parent, app, width=318, height=190):
        super().__init__(parent, width=width, height=height, bg=UI['PANEL_2'],
                         highlightthickness=0, bd=0, relief='flat', cursor='fleur',
                         takefocus=1)
        self.app = app
        self.yaw = -28.0
        self.pitch = 0.24
        self.zoom = 3.2
        self.pan_x = 0.0
        self.pan_y = 0.0
        self.mode = 'orbit'
        self.focus_view = True
        self._photo = None
        self._drag = None
        self._after_id = None
        self._last_render_ms = 0
        self._last_render_key = None
        self._last_render_image = None
        self._gpu_handle = None
        self._gpu_token = None
        self._gpu_starting = False
        self._gpu_start_time = 0.0
        self._gpu_error = None
        self._gpu_recover_after_id = None
        self.bind('<Configure>', lambda _e: self.refresh())
        self.bind('<Enter>', self._on_enter)
        self.bind('<ButtonPress-1>', lambda e: self._on_press(e, 'rotate'))
        self.bind('<ButtonPress-2>', lambda e: self._on_press(e, 'pan'))
        self.bind('<ButtonPress-3>', lambda e: self._on_press(e, 'pan'))
        self.bind('<B1-Motion>', self._on_drag)
        self.bind('<B2-Motion>', self._on_drag)
        self.bind('<B3-Motion>', self._on_drag)
        self.bind('<ButtonRelease-1>', self._on_release)
        self.bind('<ButtonRelease-2>', self._on_release)
        self.bind('<ButtonRelease-3>', self._on_release)
        self.bind('<MouseWheel>', self._on_wheel)
        self.bind('<Double-Button-1>', self._toggle_detail_view)
        self.bind('<KeyPress>', self._on_key)
        self._draw_loading(width, height)
        self.refresh()

    def destroy(self):
        self.close_gpu(wait=False)
        try:
            super().destroy()
        except tk.TclError:
            pass

    def close_gpu(self, wait=False):
        if self._gpu_recover_after_id:
            try:
                self.after_cancel(self._gpu_recover_after_id)
            except tk.TclError:
                pass
            self._gpu_recover_after_id = None
        handle = self._gpu_handle
        self._gpu_handle = None
        self._gpu_starting = False
        self._gpu_start_time = 0.0
        if handle is not None:
            try:
                handle.close(wait=wait)
            except Exception:
                pass

    def _on_enter(self, _event):
        self.app._wheel_target = None
        self.focus_set()

    def _on_press(self, event, mode='rotate'):
        if mode == 'rotate' and (event.state & 0x0001):
            mode = 'pan'
        self._drag = (mode, event.x, event.y, self.yaw, self.pitch, self.pan_x, self.pan_y)
        self.focus_set()

    def _on_drag(self, event):
        if not self._drag:
            return
        mode, x0, y0, yaw0, pitch0, panx0, pany0 = self._drag
        if mode == 'pan':
            scale_x = 1.65 / max(0.45, self.zoom)
            scale_y = 1.15 / max(0.45, self.zoom)
            self.pan_x = panx0 - ((event.x - x0) / float(max(180, self.winfo_width()))) * scale_x
            self.pan_y = pany0 + ((event.y - y0) / float(max(140, self.winfo_height()))) * scale_y
        else:
            self.yaw = yaw0 + (event.x - x0) * 0.18
            self.pitch = max(-0.12, min(0.88, pitch0 + (y0 - event.y) * 0.0024))
        self.refresh()

    def _on_release(self, _event):
        self._drag = None
        self.refresh(immediate=True)

    def _on_wheel(self, event):
        factor = 1.08 if event.delta > 0 else 0.925
        self.set_zoom(self.zoom * factor)
        self.refresh(immediate=True)
        return 'break'

    def _on_key(self, event):
        key = (event.keysym or '').lower()
        if key in ('r', 'home'):
            self.reset_view()
        elif key == 'f':
            self.toggle_mode()
        elif key in ('plus', 'equal', 'add'):
            self.set_zoom(self.zoom * 1.16)
            self.refresh(immediate=True)
        elif key in ('minus', 'subtract'):
            self.set_zoom(self.zoom / 1.16)
            self.refresh(immediate=True)
        elif key in ('left', 'a'):
            self.yaw -= 8.0
            self.refresh(immediate=True)
        elif key in ('right', 'd'):
            self.yaw += 8.0
            self.refresh(immediate=True)
        elif key in ('up', 'w'):
            self.pitch = min(0.88, self.pitch + 0.06)
            self.refresh(immediate=True)
        elif key in ('down', 's'):
            self.pitch = max(-0.12, self.pitch - 0.06)
            self.refresh(immediate=True)
        elif key in ('1', 'num_1'):
            self.set_view(-28.0, 0.24, 3.2, focus=True)
        elif key in ('2', 'num_2'):
            self.set_view(-38.0, 0.34, 2.2, focus=True)
        elif key in ('3', 'num_3'):
            self.set_view(0.0, 0.72, 2.0, focus=True)
        return 'break'

    def set_zoom(self, value):
        self.zoom = max(0.45, min(7.2, float(value)))

    def set_view(self, yaw, pitch, zoom=None, focus=None):
        self.yaw = float(yaw)
        self.pitch = max(-0.12, min(0.88, float(pitch)))
        if zoom is not None:
            self.set_zoom(zoom)
        if focus is not None:
            self.focus_view = bool(focus)
        self.pan_x = 0.0
        self.pan_y = 0.0
        self.mode = 'orbit'
        self.refresh(immediate=True)

    def toggle_mode(self, _event=None):
        self.mode = 'walk' if self.mode == 'orbit' else 'orbit'
        self.zoom = max(0.85, min(1.7, self.zoom))
        if self.mode == 'walk':
            self.pan_x = 0.0
            self.pan_y = 0.0
        self.refresh(immediate=True)

    def _toggle_detail_view(self, _event=None):
        if self.zoom < 3.0 or not self.focus_view:
            self.set_view(-28.0, 0.24, 3.2, focus=True)
        else:
            self.set_view(-38.0, 0.34, 2.2, focus=True)
        return 'break'

    def reset_view(self):
        self.yaw = -28.0
        self.pitch = 0.24
        self.zoom = 3.2
        self.pan_x = 0.0
        self.pan_y = 0.0
        self.mode = 'orbit'
        self.focus_view = True
        self.refresh(immediate=True)

    def refresh(self, immediate=False):
        if self._after_id:
            try:
                self.after_cancel(self._after_id)
            except tk.TclError:
                pass
            self._after_id = None
        if immediate:
            self._render()
        else:
            self._after_id = self.after(12 if self._drag else 36, self._render)

    def view_state(self):
        return {
            'yaw': self.yaw,
            'pitch': self.pitch,
            'zoom': self.zoom,
            'pan_x': self.pan_x,
            'pan_y': self.pan_y,
            'mode': self.mode,
            'focus_view': self.focus_view,
        }

    def _render_gpu(self, w, h):
        if self.app.loaded_nbt is None:
            self.close_gpu(wait=False)
            self._draw_waiting(w, h)
            return True
        if preview_geom is None:
            self.close_gpu(wait=False)
            self._draw_error(w, h, 'gpu_preview module is not available')
            return True
        try:
            if not self.winfo_ismapped() or w < 320 or h < 220:
                self._draw_loading(w, h)
                self.after(160, lambda: self.refresh(immediate=True))
                return True
            token = self.app._preview_cache_token()
            if self._gpu_handle is not None and self._gpu_token == token and self._gpu_handle.alive:
                self._gpu_handle.resize(w, h)
                self._send_gpu_view()
                self._raise_gpu_view()
                return True
            if self._gpu_starting and self._gpu_token == token:
                if time.monotonic() - self._gpu_start_time > 12.0:
                    self.close_gpu(wait=False)
                    self._gpu_token = None
                else:
                    self._draw_loading(w, h)
                    self.after(220, lambda: self.refresh(immediate=True))
                    return True

            self.close_gpu(wait=False)
            self._gpu_token = token
            self._gpu_starting = True
            self._gpu_start_time = time.monotonic()
            self._gpu_error = None
            self._draw_loading(w, h)
            try:
                self.update_idletasks()
                parent_hwnd = int(self.winfo_id())
            except Exception:
                parent_hwnd = 0
            view = self._gpu_view_values()

            def worker(expected_token, parent, width, height, view_values):
                payload = None
                error = None
                try:
                    payload = self.app._gpu_preview_payload()
                    if payload.get('blocks') and 'prebuilt_mesh' not in payload:
                        import gpu_preview
                        payload['prebuilt_mesh'] = gpu_preview.build_mesh(payload)
                    payload = dict(payload)
                    payload.update({
                        'width': width,
                        'height': height,
                        'startup_timeout': 3.0,
                        'target_fps': 240,
                        'uncapped_fps': False,
                        'show_overlay': False,
                        'force_continuous_redraw': True,
                        'initial_yaw': view_values[0],
                        'initial_pitch': view_values[1],
                        'initial_zoom': view_values[2],
                        'initial_mode': view_values[3],
                    })
                except Exception as exc:
                    error = exc
                self.app._safe_after(lambda: self._finish_gpu_embed(expected_token, parent, width, height, payload, error))

            threading.Thread(target=worker, args=(token, parent_hwnd, w, h, view), daemon=True).start()
            return True
        except Exception as exc:
            self.close_gpu(wait=False)
            self._draw_error(w, h, exc)
            return True

    def _finish_gpu_embed(self, expected_token, parent_hwnd, width, height, payload, error):
        self._gpu_starting = False
        self._gpu_start_time = 0.0
        try:
            if not self.winfo_exists() or self.app.loaded_nbt is None:
                return
        except tk.TclError:
            return
        if expected_token != self.app._preview_cache_token():
            self.refresh()
            return
        if error is not None:
            self._gpu_error = error
            self._draw_error(width, height, error)
            return
        if not payload or not payload.get('blocks'):
            self._draw_error(width, height, 'preview mesh is empty')
            return
        try:
            import gpu_preview
            self._gpu_handle = gpu_preview.open_embedded_preview_async(payload, parent_hwnd, width, height)
            self._gpu_token = expected_token
            self._send_gpu_view()
            self._sync_gpu_size()
            self._raise_gpu_view()
            self._schedule_gpu_recover()
        except Exception as exc:
            self._gpu_error = exc
            self._draw_error(width, height, exc)

    def _gpu_view_values(self):
        yaw = self.yaw - 10.0
        pitch = max(-12.0, min(78.0, self.pitch * 108.0))
        zoom = max(0.18, min(8.0, self.zoom / 1.94))
        return yaw, pitch, zoom, self.mode

    def _send_gpu_view(self):
        if self._gpu_handle is None:
            return
        try:
            self._gpu_handle.set_view(*self._gpu_view_values())
        except Exception:
            pass

    def _raise_gpu_view(self):
        if self._gpu_handle is None:
            return
        try:
            self._gpu_handle.raise_window()
        except Exception:
            pass

    def _sync_gpu_size(self):
        if self._gpu_handle is None:
            return
        try:
            self._gpu_handle.resize(max(260, self.winfo_width()), max(150, self.winfo_height()))
        except Exception:
            pass

    def _schedule_gpu_recover(self, delay=120, attempts=6):
        if self._gpu_recover_after_id:
            try:
                self.after_cancel(self._gpu_recover_after_id)
            except tk.TclError:
                pass
        def recover():
            self._gpu_recover_after_id = None
            self._sync_gpu_size()
            self._send_gpu_view()
            self._raise_gpu_view()
            if self._gpu_handle is not None and attempts > 1:
                self._gpu_recover_after_id = self.after(450, lambda: self._schedule_gpu_recover(0, attempts - 1))
        self._gpu_recover_after_id = self.after(delay, recover)

    def _draw_error(self, w, h, exc):
        self.delete('all')
        self.create_rectangle(0, 0, w, h, fill='#101820', outline='#4d79ff')
        self.create_text(w / 2, h / 2, text='GPU preview failed\n%s' % exc,
                         fill='#ffffff', font=('Yu Gothic UI', 10, 'bold'), justify='center')

    def _render(self):
        self._after_id = None
        w = max(260, self.winfo_width())
        h = max(150, self.winfo_height())
        if self._render_gpu(w, h):
            return
        try:
            large = w * h >= 260000
            render_scale = 0.24 if self._drag else (0.72 if large else 0.82)
            rw = max(220, int(w * render_scale))
            rh = max(135, int(h * render_scale))
            if self._drag:
                max_blocks = CPU_PREVIEW_DRAG_BLOCK_LIMIT if large else max(32, int(CPU_PREVIEW_DRAG_BLOCK_LIMIT * 0.85))
                face_limit = CPU_PREVIEW_DRAG_FACE_LIMIT if large else max(48, int(CPU_PREVIEW_DRAG_FACE_LIMIT * 0.85))
                texture_limit = 0
            else:
                max_blocks = int(CPU_PREVIEW_IDLE_BLOCK_LIMIT * (1.35 if large else 1.0))
                face_limit = int(CPU_PREVIEW_IDLE_FACE_LIMIT * (1.65 if large else 1.15))
                texture_limit = face_limit
            state = self.view_state()
            cache_key = None if self._drag else (
                w, h, rw, rh,
                round(self.yaw, 2), round(self.pitch, 3), round(self.zoom, 3),
                round(self.pan_x, 3), round(self.pan_y, 3),
                self.mode, self.focus_view, self.app._preview_cache_token(),
            )
            if cache_key is not None and cache_key == self._last_render_key and self._last_render_image is not None:
                im = self._last_render_image.copy()
            else:
                im = self.app._render_schematic_preview(rw, rh, max_blocks=max_blocks,
                                                        view=state, fast=True,
                                                        face_limit_override=face_limit,
                                                        texture_limit=texture_limit,
                                                        min_face_px=1.35 if not self._drag else 3.2,
                                                        focus_view=self.focus_view and not self._drag)
                if (rw, rh) != (w, h):
                    im = im.resize((w, h), Image.Resampling.NEAREST)
                if cache_key is not None:
                    self._last_render_key = cache_key
                    self._last_render_image = im.copy()
            self._photo = ImageTk.PhotoImage(im)
            self.delete('all')
            self.create_image(0, 0, image=self._photo, anchor='nw')
            self._draw_overlay(w, h)
        except Exception as exc:
            self.delete('all')
            self.create_rectangle(0, 0, w, h, fill='#101820', outline='#4d79ff')
            self.create_text(w / 2, h / 2, text='プレビュー生成中に失敗しました\n%s' % exc,
                             fill='#ffffff', font=('Yu Gothic UI', 9), justify='center')

    def _draw_waiting(self, w, h):
        self.delete('all')
        self.create_rectangle(0, 0, w, h, fill='#101820', outline='#4d79ff')
        self.create_text(w / 2, h / 2 - 14, text='設計図待機中', fill='#ffffff',
                         font=('Yu Gothic UI', 16, 'bold'))
        self.create_text(w / 2, h / 2 + 18, text='.litematic を読み込むとここにプレビューを表示します',
                         fill='#b8c7d8', font=('Yu Gothic UI', 10))

    def _draw_loading(self, w, h):
        self.delete('all')
        self.create_rectangle(0, 0, w, h, fill='#101820', outline='#4d79ff')
        self.create_text(w / 2, h / 2, text='プレビュー準備中...', fill='#ffffff',
                         font=('Yu Gothic UI', 10, 'bold'))

    def _draw_overlay(self, w, h):
        mode_text = '近景' if self.mode == 'orbit' and self.zoom >= 3.0 else ('内部視点' if self.mode == 'walk' else '全体')
        zoom_text = '%d%%' % int(self.zoom * 100)
        quality = '軽量' if self._drag else '高品質'
        self.create_rectangle(10, 10, 206, 36, fill='#000000', outline='', stipple='gray50')
        self.create_text(20, 23, text='%s  %s  %s' % (mode_text, zoom_text, quality), anchor='w',
                         fill='#ffffff', font=('Yu Gothic UI', 9, 'bold'))


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
        self._preview_source_cache = {}
        self._target_map_cache_token = None
        self._target_map_cache = {}
        self._gpu_payload_cache_token = None
        self._gpu_payload_cache = None
        self._gpu_payload_building = False
        self._gpu_warmup_after_id = None
        self._gpu_open_when_ready = False
        self._focus_surface_building = False
        self._regid2file = {}
        self.active_filter = 'all'
        self.preview_tab = 'overview'
        self.last_output = None
        self.output_history = []
        self.focus_mode = False
        self.sidebar_collapsed = False
        self.sidebar_items = {}
        self.preview_tab_buttons = {}
        self.pending_update = None
        self.update_checking = False
        self.update_notified = False
        self.note_var = tk.StringVar(value='')
        self.progress_var = tk.DoubleVar(value=0)
        self._build_ui()
        self.root.after(1800, self.check_for_updates_silent)

    # ------------------------------------------------------------------ basics
    def _preview_cache_token(self):
        return (
            id(self.loaded_nbt),
            self.src_path,
            icons.minecraft_assets_label(),
            tuple(sorted((str(k), str(v)) for k, v in self.overrides.items())),
        )

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
                        troughcolor=UI['PANEL_3'], background=UI['ACCENT'],
                        bordercolor=UI['BORDER'], lightcolor=UI['ACCENT'],
                        darkcolor=UI['ACCENT_DK'])

    def _label(self, parent, text, size=10, weight='normal', fg=None, bg=None, **kw):
        return tk.Label(parent, text=text, bg=bg or parent.cget('bg'), fg=fg or UI['TEXT'],
                        font=('Yu Gothic UI', size + UI_FONT_BOOST, weight), **kw)

    def _button(self, parent, text, command=None, bg=None, fg=None, size=9, weight='bold',
                padx=10, pady=5, state='normal', **kw):
        return RoundedButton(parent, text=text, command=command, bg=bg or UI['BTN_BG'],
                             fg=fg or UI['TEXT'], active_bg=UI['HOVER'],
                             size=size, weight=weight, padx=padx, pady=pady,
                             state=state, **kw)

    def _panel(self, parent, bg=None, border=None):
        return tk.Frame(parent, bg=bg or UI['PANEL'], highlightthickness=1,
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
        mx, my, mw, mh = self._current_monitor_work_area(window)
        width = min(int(width), max(1024, mw - 80))
        height = min(int(height), max(720, mh - 90))
        x = mx + max(0, int((mw - width) / 2))
        y = my + max(0, int((mh - height) / 2))
        window.geometry('%dx%d+%d+%d' % (width, height, x, y))
        return width, height

    def _current_monitor_work_area(self, window):
        if os.name == 'nt':
            try:
                class POINT(ctypes.Structure):
                    _fields_ = [('x', ctypes.c_long), ('y', ctypes.c_long)]

                class RECT(ctypes.Structure):
                    _fields_ = [('left', ctypes.c_long), ('top', ctypes.c_long),
                                ('right', ctypes.c_long), ('bottom', ctypes.c_long)]

                class MONITORINFO(ctypes.Structure):
                    _fields_ = [('cbSize', ctypes.c_ulong), ('rcMonitor', RECT),
                                ('rcWork', RECT), ('dwFlags', ctypes.c_ulong)]

                user32 = ctypes.windll.user32
                pt = POINT()
                user32.GetCursorPos(ctypes.byref(pt))
                monitor = user32.MonitorFromPoint(pt, 2)
                info = MONITORINFO()
                info.cbSize = ctypes.sizeof(MONITORINFO)
                if monitor and user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
                    rect = info.rcWork
                    return rect.left, rect.top, max(1, rect.right - rect.left), max(1, rect.bottom - rect.top)
            except Exception:
                pass
        try:
            return (window.winfo_vrootx(), window.winfo_vrooty(),
                    max(1, window.winfo_vrootwidth()), max(1, window.winfo_vrootheight()))
        except Exception:
            return 0, 0, max(1, window.winfo_screenwidth()), max(1, window.winfo_screenheight())

    # --------------------------------------------------------------------- ui
    def _build_ui(self):
        self.root.title(APP_TITLE)
        self.root.configure(bg=UI['BG'])
        win_w, win_h = self._set_centered_geometry(self.root, 1760, 980)
        self.root.minsize(min(1180, win_w), min(760, win_h))
        self.root.grid_rowconfigure(1, weight=1)
        self.root.grid_columnconfigure(0, weight=1)
        self._configure_style()

        self.header = tk.Frame(self.root, bg=UI['HEADER'], height=62)
        self.header.grid(row=0, column=0, sticky='ew')
        self.header.grid_propagate(False)

        self.main = tk.Frame(self.root, bg=UI['BG'])
        self.main.grid(row=1, column=0, sticky='nsew', padx=16, pady=(12, 8))

        self.footer = tk.Frame(self.root, bg=UI['HEADER'], height=54)
        self.footer.grid(row=2, column=0, sticky='ew')
        self.footer.grid_propagate(False)

        self._register_drop(self.root)
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
        bg = UI['ACCENT'] if active else UI['BTN_BG']
        fg = '#ffffff' if active else UI['MUTED']
        f = tk.Frame(self.sidebar, bg=UI['SIDEBAR'])
        f.pack(fill='x', padx=8, pady=4)
        item = RoundedButton(f, text=symbol + '\n' + label,
                             command=lambda k=key: self.navigate(k),
                             bg=bg, fg=fg, active_bg=UI['HOVER'],
                             size=8, weight='bold' if active else 'normal',
                             padx=3, pady=5, radius=16)
        item.pack(fill='x')
        self.sidebar_items[key] = item

    def _set_sidebar_active(self, key):
        for name, widget in self.sidebar_items.items():
            active = name == key
            widget.configure(bg=UI['ACCENT'] if active else UI['BTN_BG'],
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
        self._button(head, '閉じる', top.destroy, bg=UI['BTN_BG'], size=8, padx=10, pady=4).pack(side='right', padx=12)
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
        try:
            self.root.attributes('-alpha', 1.0)
        except tk.TclError:
            pass
        for widget in self.header.winfo_children():
            widget.destroy()
        self._build_header()
        self._refresh_layout()
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
        self._button(row, '読み込みを解除', self.clear_loaded_file, bg=UI['BTN_BG']).pack(side='left')

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
            self._button(row, '実行', cmd, bg=UI['ACCENT'], fg='white', padx=12, pady=5).pack(side='right', padx=10)

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
            self._button(row, '実行', cmd, bg=UI['ACCENT'], fg='white', padx=12, pady=5).pack(side='right', padx=10)

    def open_full_preview(self):
        self._open_gpu_preview()

    def _open_gpu_preview(self):
        if hasattr(self, 'preview_view'):
            try:
                self.preview_view.close_gpu(wait=True)
            except Exception:
                pass
        if self.loaded_nbt is None:
            messagebox.showinfo(APP_TITLE, '先に設計図を読み込んでください。')
            return True
        try:
            import gpu_preview
        except Exception as exc:
            messagebox.showwarning(APP_TITLE, '全画面プレビューを起動できませんでした。\n\n%s' % exc)
            return True
        try:
            token = self._preview_cache_token()
            if not (self._gpu_payload_cache_token == token and self._gpu_payload_cache is not None):
                self._gpu_open_when_ready = True
                self._sync_progress(text='進行状況: 全画面プレビューを準備中です...')
                self._schedule_gpu_preview_warmup(open_when_ready=True)
                return True
            self._open_ready_gpu_payload(gpu_preview)
            return True
        except Exception as exc:
            messagebox.showwarning(APP_TITLE, '全画面プレビューの準備に失敗しました。\n\n%s' % exc)
            return True

    def _open_ready_gpu_payload(self, gpu_preview_module=None):
        payload = self._gpu_payload_cache
        if not payload or not payload.get('blocks'):
            messagebox.showinfo(APP_TITLE, 'プレビューできるブロックが見つかりませんでした。')
            return False
        if gpu_preview_module is None:
            import gpu_preview as gpu_preview_module
        gpu_preview_module.open_preview_async(payload)
        self._sync_progress(text='進行状況: 全画面プレビューを起動しました')
        return True

    def _open_cpu_full_preview(self):
        top, body = self._dialog('Minecraft風プレビュー', 1180, 760)
        body.grid_rowconfigure(0, weight=1)
        body.grid_columnconfigure(0, weight=1)
        prev = InteractivePreview(body, self, width=1080, height=600)
        prev.grid(row=0, column=0, sticky='nsew')
        row = tk.Frame(body, bg=UI['BG'])
        row.grid(row=1, column=0, sticky='ew', pady=(12, 0))
        self._button(row, '外観', lambda: setattr(prev, 'mode', 'orbit') or prev.refresh(immediate=True),
                     bg=UI['BTN_BG_2']).pack(side='left', padx=(0, 8))
        self._button(row, '内部視点', lambda: setattr(prev, 'mode', 'walk') or prev.refresh(immediate=True),
                     bg=UI['BTN_BG_2']).pack(side='left', padx=(0, 8))
        self._button(row, 'リセット', prev.reset_view, bg=UI['BTN_BG']).pack(side='left', padx=(0, 8))
        self._button(row, 'PNGとして保存', self.export_preview, bg=UI['ACCENT']).pack(side='left', padx=(0, 8))
        self._button(row, '建材リストPNG', self.export_materials_image, bg=UI['ACCENT']).pack(side='left', padx=(0, 8))
        self._button(row, 'CSVを書き出し', self.export_mapping_csv, bg=UI['BTN_BG_2']).pack(side='left', padx=(0, 8))
        self._button(row, '閉じる', top.destroy, bg=UI['BTN_BG']).pack(side='right')

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
                         bg=UI['ACCENT'], fg='white').pack(side='right', padx=10)

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
        self._button(body, '素材変換ルールを開く', self.open_rule_manager,
                     bg=UI['BTN_BG_2']).pack(anchor='w', pady=(8, 0))
        self._button(body, '大きいプレビューで確認', self.open_full_preview,
                     bg=UI['BTN_BG_2']).pack(anchor='w', pady=(8, 0))
        assets_label = icons.minecraft_assets_label()
        texture_status = 'Minecraftテクスチャ: ' + (assets_label if assets_label else '未検出（内蔵の軽量表示を使用）')
        self._label(body, texture_status, size=8, fg=UI['MUTED'], bg=UI['BG'],
                    wraplength=650).pack(anchor='w', pady=(8, 0))
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
            ('建材リストPNGを書き出し', '必要な建材と変換先をアイコン付きの画像で保存します。', self.export_materials_image),
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
            self._button(row, '実行', cmd, bg=UI['ACCENT'], fg='white', padx=12, pady=5).pack(side='right', padx=10)

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
            self._safe_after(lambda: self._finish_update_check(info, manual))

        def on_error(exc):
            self._safe_after(lambda: self._finish_update_error(exc, manual))

        updater.check_for_update_async(on_result, on_error)

    def _safe_after(self, callback):
        try:
            self.root.after(0, callback)
            return True
        except (RuntimeError, tk.TclError):
            return False

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
            self._safe_after(lambda p=pct: self._sync_progress(p, '進行状況: 更新ファイルをダウンロードしています...'))

        def worker():
            try:
                path = updater.download_update(info, progress)
                updater.schedule_replace_and_restart(path, info.sha256)
            except Exception as exc:
                self._safe_after(lambda e=exc: self._update_failed(e))
                return
            self._safe_after(self._close_for_update)

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
        left.grid(row=0, column=0, sticky='w', padx=18, pady=8)
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
                     bg=UI['BTN_BG'], size=8, padx=10, pady=4).pack(side='left', padx=4)
        self._button(right, '履歴', self.open_history_dialog, bg=UI['BTN_BG'],
                     size=8, padx=10, pady=4).pack(side='left', padx=4)
        self._button(right, '設定', self.open_settings_dialog, bg=UI['BTN_BG'],
                     size=8, padx=10, pady=4).pack(side='left', padx=4)
        focus_label = '素材編集' if self.focus_mode else 'プレビュー画面'
        self._button(right, focus_label, self.toggle_focus_mode, bg=UI['ACCENT'] if self.focus_mode else UI['BTN_BG'],
                     fg='white' if self.focus_mode else UI['TEXT'], size=8,
                     padx=10, pady=4).pack(side='left', padx=4)
        self._button(right, 'Studio Build', self.open_build_dialog, bg=UI['BTN_BG'],
                     size=8, padx=10, pady=4).pack(side='left', padx=4)

    def _build_main(self):
        self.main.grid_rowconfigure(1, weight=1)
        self.main.grid_columnconfigure(0, weight=1)
        self._build_stepper()

        self.content = tk.Frame(self.main, bg=UI['BG'])
        self.content.grid(row=1, column=0, sticky='nsew', pady=(10, 0))
        self.content.grid_rowconfigure(0, weight=1)

        if self.focus_mode:
            self.content.grid_columnconfigure(0, minsize=330, weight=0)
            self.content.grid_columnconfigure(1, minsize=1120, weight=1)
            self.left_col = tk.Frame(self.content, bg=UI['BG'])
            self.left_col.grid(row=0, column=0, sticky='nsew', padx=(0, 14))
            self.left_col.configure(width=330)
            self.left_col.grid_propagate(False)
            self.center_col = tk.Frame(self.content, bg=UI['BG'])
            self.right_col = tk.Frame(self.content, bg=UI['BG'])
            self.right_col.grid(row=0, column=1, sticky='nsew')
            self.right_col.grid_rowconfigure(0, weight=1)
            self.right_col.grid_columnconfigure(0, weight=1)
            self._build_preview_sidebar()
            self._build_preview_panel()
            return

        self.content.grid_columnconfigure(0, minsize=255, weight=0)
        self.content.grid_columnconfigure(1, minsize=500, weight=2)
        self.content.grid_columnconfigure(2, minsize=720, weight=3)

        self.left_col = tk.Frame(self.content, bg=UI['BG'])
        self.left_col.grid(row=0, column=0, sticky='nsew', padx=(0, 14))
        self.center_col = tk.Frame(self.content, bg=UI['BG'])
        self.center_col.grid(row=0, column=1, sticky='nsew', padx=(0, 14))
        self.right_col = tk.Frame(self.content, bg=UI['BG'])
        self.right_col.grid(row=0, column=2, sticky='nsew')
        self.right_col.grid_rowconfigure(0, weight=1)
        self.right_col.grid_columnconfigure(0, weight=1)

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
        self._step_card(steps, 1, 2, 'プレビュー確認', '変換後の見た目を全画面でも確認', current >= 2, current == 2)
        self._step_card(steps, 2, 3, '出力・適用', '結果を出力してプロジェクトに適用', current >= 3, current == 3)

    def _step_card(self, parent, col, no, title, desc, done, active):
        bg = '#162b46' if active else ('#132235' if done else UI['PANEL'])
        border = UI['ACCENT'] if active else ('#254b72' if done else UI['BORDER'])
        f = self._panel(parent, bg=bg, border=border)
        f.configure(cursor='hand2')
        f.grid(row=0, column=col, sticky='ew', padx=(0 if col == 0 else 10, 0), ipady=8)
        f.grid_columnconfigure(1, weight=1)
        circle = tk.Canvas(f, width=42, height=42, bg=bg, highlightthickness=0)
        circle.grid(row=0, column=0, rowspan=2, padx=14)
        fill = UI['ACCENT'] if active else (UI['ACCENT_2'] if done else UI['PANEL_3'])
        circle.create_oval(4, 4, 38, 38, fill=fill, outline='')
        circle.create_text(21, 21, text=str(no), fill='white', font=('Segoe UI', 12, 'bold'))
        self._label(f, title, size=10, weight='bold', bg=bg).grid(row=0, column=1, sticky='sw')
        self._label(f, desc, size=8, fg=UI['MUTED'], bg=bg).grid(row=1, column=1, sticky='nw')
        if done:
            self._label(f, '✓', size=14, fg=UI['GREEN'], bg=bg).grid(row=0, column=2, rowspan=2, padx=12)
        command = self.choose_file if no == 1 else (self.open_full_preview if no == 2 else self.do_convert)
        for widget in (f,) + tuple(f.winfo_children()):
            widget.bind('<Button-1>', lambda _e, cmd=command: cmd())

    def _build_preview_sidebar(self):
        panel = self._panel(self.left_col)
        panel.pack(fill='both', expand=True)
        panel.configure(width=330)
        panel.pack_propagate(False)
        panel.grid_columnconfigure(0, weight=1)

        head = tk.Frame(panel, bg=UI['PANEL'])
        head.pack(fill='x', padx=12, pady=(12, 8))
        self._label(head, 'プレビュースタジオ', size=12, weight='bold').pack(anchor='w')
        self._label(head, '見た目確認を先に行い、必要な時だけ素材を編集します。',
                    size=7, fg=UI['MUTED'], wraplength=238, justify='left').pack(anchor='w', pady=(2, 0))

        if self.loaded_nbt is None:
            drop = tk.Frame(panel, bg=UI['DROP_BG'], highlightthickness=1, highlightbackground=UI['BORDER_HI'])
            drop.pack(fill='x', padx=12, pady=(4, 12), ipady=34)
            self._register_drop(drop)
            drop.bind('<Button-1>', lambda _e: self.choose_file())
            self._label(drop, '設計図を読み込む', size=13, weight='bold', fg=UI['TEXT_SOFT'],
                        bg=UI['DROP_BG']).pack(pady=(4, 2))
            self._label(drop, self._default_drop_text(), size=8, fg=UI['MUTED'],
                        bg=UI['DROP_BG'], justify='center').pack()
            return

        hero = tk.Frame(panel, bg=UI['PANEL'])
        hero.pack(fill='x', padx=12, pady=(0, 10))
        img = self._loaded_thumb(82, 110)
        pic = tk.Label(hero, image=img, bg=UI['PANEL'])
        pic.image = img
        pic.pack(anchor='center', pady=(0, 8))
        name = os.path.basename(self.src_path or '')
        self._label(hero, name, size=10, weight='bold', wraplength=238,
                    justify='center').pack(anchor='center')
        self._label(hero, '実テクスチャでプレビュー中', size=8, fg=UI['GREEN']).pack(anchor='center', pady=(2, 0))

        stats = self._stats()
        grid = tk.Frame(panel, bg=UI['PANEL'])
        grid.pack(fill='x', padx=12, pady=(4, 10))
        for col in range(2):
            grid.grid_columnconfigure(col, weight=1, uniform='preview_stats')
        self._sidebar_stat(grid, 0, 0, '総ブロック', stats['total_blocks'])
        self._sidebar_stat(grid, 0, 1, 'ユニーク', str(stats['unique_total']))
        self._sidebar_stat(grid, 1, 0, '変換ルール', str(stats['changed_palette']))
        self._sidebar_stat(grid, 1, 1, '競合', str(stats['conflicts']))

        action = tk.Frame(panel, bg=UI['PANEL'])
        action.pack(fill='x', padx=12, pady=(0, 10))
        self._button(action, '全画面表示', self.open_full_preview,
                     bg=UI['ACCENT'], fg='white', size=10, pady=8).pack(fill='x', pady=(0, 6))
        self._button(action, '素材を編集', self.toggle_focus_mode,
                     bg=UI['BTN_BG_2'], size=9, pady=7).pack(fill='x', pady=(0, 6))
        row = tk.Frame(action, bg=UI['PANEL'])
        row.pack(fill='x')
        self._button(row, 'PNG保存', self.export_preview, bg=UI['BTN_BG'],
                     size=8, padx=8, pady=6).pack(side='left', fill='x', expand=True, padx=(0, 5))
        self._button(row, '建材リスト', self.export_materials_image, bg=UI['BTN_BG'],
                     size=8, padx=8, pady=6).pack(side='left', fill='x', expand=True, padx=(5, 0))
        self._button(action, '別の設計図を読み込む', self.choose_file,
                     bg=UI['BTN_BG'], size=8, pady=6).pack(fill='x', pady=(6, 0))

        ops = tk.Frame(panel, bg=UI['PANEL_2'], highlightthickness=1, highlightbackground=UI['BORDER'])
        ops.pack(fill='x', padx=12, pady=(0, 10))
        self._label(ops, '操作', size=9, weight='bold', bg=UI['PANEL_2']).pack(anchor='w', padx=10, pady=(8, 2))
        self._label(ops, '左ドラッグで回転 / 右ドラッグで移動',
                    size=8, fg=UI['TEXT_SOFT'], bg=UI['PANEL_2']).pack(anchor='w', padx=10)
        self._label(ops, 'ホイールで拡大縮小 / ダブルクリックで近景・全体切替',
                    size=8, fg=UI['TEXT_SOFT'], bg=UI['PANEL_2']).pack(anchor='w', padx=10)
        self._label(ops, '', size=1, bg=UI['PANEL_2']).pack(pady=(0, 4))

    def _sidebar_stat(self, parent, row, col, title, value):
        box = tk.Frame(parent, bg=UI['PANEL_2'], highlightthickness=1, highlightbackground=UI['BORDER'])
        box.grid(row=row, column=col, sticky='ew', padx=(0 if col == 0 else 5, 0 if col == 1 else 5), pady=3)
        self._label(box, title, size=7, fg=UI['MUTED'], bg=UI['PANEL_2']).pack(anchor='w', padx=8, pady=(6, 0))
        self._label(box, value, size=10, weight='bold', bg=UI['PANEL_2']).pack(anchor='w', padx=8, pady=(0, 6))

    def _build_left_column(self):
        info = self._panel(self.left_col)
        info.pack(fill='x')
        self._label(info, '読み込んだ設計図', size=10, weight='bold').pack(anchor='w', padx=12, pady=(10, 8))
        body = tk.Frame(info, bg=UI['PANEL'])
        body.pack(fill='x', padx=12, pady=(0, 12))

        if self.loaded_nbt is None:
            drop = tk.Frame(body, bg=UI['DROP_BG'], highlightthickness=1, highlightbackground=UI['BORDER_HI'])
            drop.pack(fill='x', ipady=28)
            self._register_drop(drop)
            drop.bind('<Button-1>', lambda _e: self.choose_file())
            self._label(drop, '設計図を読み込む', size=13, weight='bold', fg=UI['TEXT_SOFT'],
                        bg=UI['DROP_BG']).pack(pady=(4, 2))
            self._label(drop, self._default_drop_text(), size=8, fg=UI['MUTED'],
                        bg=UI['DROP_BG'], justify='center').pack()
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
                     bg=UI['BTN_BG'], size=8, padx=8, pady=2).pack(side='right')
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
        self._button(f, '適用' if 'カスタム' not in title else '保存', cmd, bg=UI['ACCENT'],
                     fg='white', size=8, padx=8, pady=2).pack(side='right', padx=8)

    def _build_mapping_panel(self):
        panel = self._panel(self.center_col)
        panel.pack(fill='both', expand=True)
        panel.grid_rowconfigure(2, weight=1)
        panel.grid_columnconfigure(0, weight=1)

        head = tk.Frame(panel, bg=UI['PANEL'])
        head.grid(row=0, column=0, sticky='ew', padx=12, pady=(10, 6))
        self._label(head, 'ブロック / 素材マッピング', size=10, weight='bold').pack(side='left')
        self._button(head, '✦ 自動マッピング', self.apply_default_preset, bg=UI['ACCENT'],
                     fg='white', size=8, padx=10, pady=4).pack(side='right', padx=(6, 0))
        self._button(head, '+ ルールを追加', self.add_manual_rule, bg=UI['BTN_BG'],
                     size=8, padx=10, pady=4).pack(side='right')

        chips = tk.Frame(panel, bg=UI['PANEL'])
        chips.grid(row=1, column=0, sticky='ew', padx=12, pady=(0, 8))
        for key, label, count in self._filter_counts():
            self._filter_chip(chips, key, label, count)

        table = tk.Frame(panel, bg=UI['PANEL'])
        table.grid(row=2, column=0, sticky='nsew', padx=12)
        table.grid_rowconfigure(1, weight=1)
        table.grid_columnconfigure(0, weight=1)
        hdr = tk.Frame(table, bg=UI['PANEL_2'])
        hdr.grid(row=0, column=0, sticky='ew')
        for i, (text, w) in enumerate([('元のブロック', 20), ('', 2), ('変換後の素材', 22),
                                       ('方法', 8), ('状態', 7), ('', 3)]):
            tk.Label(hdr, text=text, bg=UI['PANEL_2'], fg=UI['MUTED'], width=w,
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
        self._button(bulk, '未設定を自動割り当て', self.apply_default_preset, bg=UI['BTN_BG'],
                     size=8, padx=10, pady=5).pack(side='left', padx=(0, 6))
        self._button(bulk, 'すべてリセット', self.reset_mappings, bg=UI['BTN_BG'],
                     size=8, padx=10, pady=5).pack(side='left', padx=6)
        self._button(bulk, '未使用ルールを削除', self.clean_unused_rules, bg=UI['BTN_BG'],
                     size=8, padx=10, pady=5).pack(side='left', padx=6)
        self._label(bulk, self._conflict_summary(), size=9,
                    fg=UI['ORANGE'] if self._conflict_count() else UI['GREEN']).pack(side='right')

    def _build_preview_panel(self):
        return self._build_preview_panel_v2()

    def _build_preview_panel_legacy(self):
        panel = self._panel(self.right_col)
        panel.grid(row=0, column=0, sticky='nsew')
        panel.grid_columnconfigure(0, weight=1)
        preview_min_h = 460 if self.focus_mode else 285
        preview_w = 980 if self.focus_mode else 680
        preview_h = 560 if self.focus_mode else 430
        panel.grid_rowconfigure(1, minsize=preview_min_h, weight=10)
        panel.grid_rowconfigure(6, minsize=0, weight=0)
        self._label(panel, '変換結果プレビュー', size=10, weight='bold').grid(
            row=0, column=0, sticky='w', padx=12, pady=(10, 6))
        self._label(panel, '● リアルタイム更新', size=8, fg=UI['GREEN']).grid(
            row=0, column=0, sticky='e', padx=12, pady=(10, 6))
        self.preview_view = InteractivePreview(panel, self, width=preview_w, height=preview_h)
        self.preview_view.grid(row=1, column=0, sticky='nsew', padx=12, pady=(0, 10))

        controls = tk.Frame(panel, bg=UI['PANEL'])
        controls.grid(row=2, column=0, sticky='ew', padx=12, pady=(0, 8))
        self._button(controls, '近景', self._reset_preview_view,
                     bg=UI['BTN_BG_2'], size=8, padx=12, pady=5).pack(side='left', padx=(0, 6))
        self._button(controls, '全体', lambda: self._preview_set_view(-38.0, 0.34, 2.2, True),
                     bg=UI['BTN_BG_2'], size=8, padx=12, pady=5).pack(side='left', padx=(0, 6))
        self._button(controls, 'リセット', self._reset_preview_view,
                     bg=UI['BTN_BG'], size=8, padx=12, pady=5).pack(side='left')
        self._button(controls, '全画面表示', self.open_full_preview,
                     bg=UI['ACCENT'], size=8, padx=12, pady=5).pack(side='right')

        viewbar = tk.Frame(panel, bg=UI['PANEL'])
        viewbar.grid(row=3, column=0, sticky='ew', padx=12, pady=(0, 8))
        for label, args in [
            ('近景', (-28.0, 0.24, 3.2, True)),
            ('俯瞰', (-38.0, 0.34, 2.2, True)),
            ('上から', (0.0, 0.72, 2.0, True)),
            ('横', (-90.0, 0.20, 2.8, True)),
        ]:
            self._button(viewbar, label, lambda a=args: self._preview_set_view(*a),
                         bg=UI['BTN_BG'], size=8, padx=10, pady=4).pack(side='left', padx=(0, 6))
        self._button(viewbar, '＋', lambda: self._preview_zoom(1.16),
                     bg=UI['BTN_BG_2'], size=9, padx=10, pady=4).pack(side='right', padx=(6, 0))
        self._button(viewbar, '−', lambda: self._preview_zoom(1 / 1.16),
                     bg=UI['BTN_BG_2'], size=9, padx=10, pady=4).pack(side='right')

        primary = tk.Frame(panel, bg=UI['PANEL'])
        primary.grid(row=4, column=0, sticky='ew', padx=12, pady=(0, 8))
        self.start_btn = self._button(primary, '▶ 変換を実行', self.do_convert, bg=UI['ACCENT'],
                                      fg='white', size=11, padx=12, pady=9,
                                      state='normal' if self.loaded_nbt is not None else 'disabled')
        self.start_btn.pack(fill='x')

        tabs = tk.Frame(panel, bg=UI['PANEL'])
        tabs.grid(row=5, column=0, sticky='ew', padx=12, pady=(0, 8))
        self.preview_tab_buttons = {}
        for key, label in [('overview', '概要'), ('materials', '必要素材'), ('stats', '詳細統計')]:
            btn = self._button(tabs, label, lambda k=key: self.set_preview_tab(k),
                               bg=(UI['ACCENT'] if self.preview_tab == key else UI['BTN_BG']),
                               size=8, padx=16, pady=5)
            btn.pack(side='left', fill='x', expand=True, padx=(0, 4))
            self.preview_tab_buttons[key] = btn

        self.preview_body = tk.Frame(panel, bg=UI['PANEL'])
        self.preview_body.grid(row=6, column=0, sticky='nsew', padx=12)
        self._build_preview_body()

        actions = tk.Frame(panel, bg=UI['PANEL'])
        actions.grid(row=7, column=0, sticky='ew', padx=12, pady=(8, 12))
        bottom = tk.Frame(actions, bg=UI['PANEL'])
        bottom.pack(fill='x')
        self._button(bottom, '⇩ プレビューを書き出し', self.export_preview,
                     bg=UI['BTN_BG'], size=8, pady=6).pack(side='left', fill='x', expand=True)
        self._button(bottom, '建材リスト', self.export_materials_image,
                     bg=UI['BTN_BG'], size=8, padx=10, pady=6).pack(side='left', padx=(6, 0))
        self._button(bottom, '⌄', self.open_export_menu, bg=UI['BTN_BG'], size=8, padx=10, pady=6).pack(side='right', padx=(6, 0))

    def _build_preview_panel_v2(self):
        panel = self._panel(self.right_col)
        panel.grid(row=0, column=0, sticky='nsew')
        panel.grid_columnconfigure(0, weight=1)
        panel.grid_rowconfigure(1, minsize=430 if self.focus_mode else 320, weight=10)

        head = tk.Frame(panel, bg=UI['PANEL'])
        head.grid(row=0, column=0, sticky='ew', padx=16, pady=(14, 10))
        head.grid_columnconfigure(0, weight=1)

        title_box = tk.Frame(head, bg=UI['PANEL'])
        title_box.grid(row=0, column=0, sticky='w')
        self._label(title_box, '実ブロックプレビュー', size=14, weight='bold',
                    bg=UI['PANEL']).pack(anchor='w')
        self._label(title_box, 'Minecraftの実テクスチャで高速表示。全画面で詳細を確認できます。',
                    size=8, fg=UI['MUTED'], bg=UI['PANEL']).pack(anchor='w', pady=(2, 0))

        head_actions = tk.Frame(head, bg=UI['PANEL'])
        head_actions.grid(row=0, column=1, sticky='e')
        self._button(head_actions, '全画面表示', self.open_full_preview,
                     bg=UI['ACCENT'], fg='white', size=9, padx=14, pady=7).pack(side='left', padx=(0, 8))
        self._button(head_actions, '素材編集', self.toggle_focus_mode,
                     bg=UI['BTN_BG_2'], size=9, padx=12, pady=7).pack(side='left', padx=(0, 8))
        self.start_btn = self._button(head_actions, '変換実行', self.do_convert, bg=UI['GREEN'],
                                      fg='white', size=9, padx=14, pady=7,
                                      state='normal' if self.loaded_nbt is not None else 'disabled')
        self.start_btn.pack(side='left')

        preview_w = 1120 if self.focus_mode else 720
        preview_h = 520 if self.focus_mode else 410
        self.preview_view = InteractivePreview(panel, self, width=preview_w, height=preview_h)
        self.preview_view.grid(row=1, column=0, sticky='nsew', padx=16, pady=(0, 10))

        controls = tk.Frame(panel, bg=UI['PANEL'])
        controls.grid(row=2, column=0, sticky='ew', padx=16, pady=(0, 8))
        for label, args in [
            ('近景', (-28.0, 0.24, 3.2, True)),
            ('全体', (-38.0, 0.34, 2.2, True)),
            ('上から', (0.0, 0.72, 2.0, True)),
            ('横から', (-90.0, 0.20, 2.8, True)),
        ]:
            self._button(controls, label, lambda a=args: self._preview_set_view(*a),
                         bg=UI['BTN_BG_2'], size=9, padx=13, pady=6).pack(side='left', padx=(0, 7))
        self._button(controls, 'リセット', self._reset_preview_view,
                     bg=UI['BTN_BG'], size=9, padx=13, pady=6).pack(side='left', padx=(0, 7))
        self._button(controls, '拡大', lambda: self._preview_zoom(1.12),
                     bg=UI['BTN_BG_2'], size=9, padx=12, pady=6).pack(side='right', padx=(7, 0))
        self._button(controls, '縮小', lambda: self._preview_zoom(1 / 1.12),
                     bg=UI['BTN_BG_2'], size=9, padx=12, pady=6).pack(side='right')

        tabs = tk.Frame(panel, bg=UI['PANEL'])
        tabs.grid(row=3, column=0, sticky='ew', padx=16, pady=(0, 8))
        self.preview_tab_buttons = {}
        for key, label in [('overview', '概要'), ('materials', '建材'), ('stats', '統計')]:
            btn = self._button(tabs, label, lambda k=key: self.set_preview_tab(k),
                               bg=(UI['ACCENT'] if self.preview_tab == key else UI['BTN_BG']),
                               size=9, padx=16, pady=6)
            btn.pack(side='left', fill='x', expand=True, padx=(0, 4))
            self.preview_tab_buttons[key] = btn
        self._button(tabs, 'PNG保存', self.export_preview,
                     bg=UI['BTN_BG_2'], size=9, padx=12, pady=6).pack(side='left', padx=(8, 0))
        self._button(tabs, '建材リスト画像', self.export_materials_image,
                     bg=UI['BTN_BG_2'], size=9, padx=12, pady=6).pack(side='left', padx=(6, 0))

        self.preview_body = tk.Frame(panel, bg=UI['PANEL'])
        self.preview_body.grid(row=4, column=0, sticky='nsew', padx=16)
        self._compact_preview_body = True
        self._build_preview_body_compact()

    def _build_preview_body_compact(self):
        for w in self.preview_body.winfo_children():
            w.destroy()
        stats = self._stats()
        row = tk.Frame(self.preview_body, bg=UI['PANEL'])
        row.pack(fill='x', pady=(0, 10))
        if self.preview_tab == 'materials':
            top = self._top_materials()[:4]
            if not top:
                top = [('建材', '-')]
            for label, value in top:
                box = tk.Frame(row, bg=UI['PANEL_2'], highlightthickness=1, highlightbackground=UI['BORDER'])
                box.pack(side='left', fill='x', expand=True, padx=(0, 8))
                self._label(box, label, size=8, weight='bold', bg=UI['PANEL_2'],
                            wraplength=190).pack(anchor='w', padx=10, pady=(7, 0))
                self._label(box, value, size=9, fg=UI['ACCENT'], weight='bold',
                            bg=UI['PANEL_2']).pack(anchor='w', padx=10, pady=(0, 7))
            return
        if self.preview_tab == 'stats':
            items = [
                ('競合ルール', stats['conflicts']),
                ('未設定ブロック', stats['unset']),
                ('変換パレット', stats['changed_palette']),
                ('保持ブロック', stats['kept']),
            ]
        else:
            items = [
                ('総ブロック', stats['total_blocks']),
                ('ユニーク', stats['unique_total']),
                ('変換ルール', stats['changed_palette']),
                ('競合', stats['conflicts']),
            ]
        for label, value in items:
            box = tk.Frame(row, bg=UI['PANEL_2'], highlightthickness=1, highlightbackground=UI['BORDER'])
            box.pack(side='left', fill='x', expand=True, padx=(0, 8))
            self._label(box, label, size=8, fg=UI['MUTED'], bg=UI['PANEL_2']).pack(anchor='w', padx=10, pady=(7, 0))
            self._label(box, str(value), size=11, weight='bold', bg=UI['PANEL_2']).pack(anchor='w', padx=10, pady=(0, 7))

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
        tk.Entry(note_box, textvariable=self.note_var, bg=UI['PANEL_2'], fg=UI['TEXT'],
                 insertbackground=UI['TEXT'], relief='flat', width=32,
                 font=('Yu Gothic UI', 8)).pack()

    # ---------------------------------------------------------------- refresh
    def _refresh_layout(self):
        self.image_cache = {}
        for w in self.main.winfo_children():
            w.destroy()
        self._build_main()
        self._sync_progress()
        self._queue_gpu_preview_warmup()

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
        self._preview_source_cache = {}
        self._target_map_cache_token = None
        self._target_map_cache = {}
        self._gpu_payload_cache_token = None
        self._gpu_payload_cache = None
        self._gpu_open_when_ready = False
        self._focus_surface_building = False
        self.focus_mode = False
        for widget in self.header.winfo_children():
            widget.destroy()
        self._build_header()
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
        rows = self._material_list_rows()[:8]
        if not rows:
            return [('素材', '読み込み待ち')]
        return [(r['name'], 'x%s / %s / %s' % (
            '{:,}'.format(r['count']), r['stacks_text'], r['shulker_text'])) for r in rows]

    # ---------------------------------------------------------------- rows
    def _filter_chip(self, parent, key, label, count):
        active = self.active_filter == key
        self._button(parent, '%s  %s' % (label, count), lambda k=key: self.set_filter(k),
                     bg=(UI['ACCENT'] if active else UI['BTN_BG']),
                     fg=('white' if active else UI['TEXT_SOFT']), size=8,
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
            text, fg, bg = '未設定', UI['ORANGE'], UI['WARNING_BG']
        else:
            text, fg, bg = '適用', UI['GREEN'], UI['SUCCESS_BG']
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
        self._update_preview_tabs()
        if hasattr(self, 'preview_body'):
            if getattr(self, '_compact_preview_body', False):
                self._build_preview_body_compact()
            else:
                self._build_preview_body()

    def _update_preview_tabs(self):
        for key, btn in getattr(self, 'preview_tab_buttons', {}).items():
            active = self.preview_tab == key
            try:
                btn.configure(bg=UI['ACCENT'] if active else UI['BTN_BG'],
                              fg='white' if active else UI['TEXT'])
            except tk.TclError:
                pass

    def _set_preview_mode(self, mode):
        if hasattr(self, 'preview_view'):
            self.preview_view.mode = mode
            if mode == 'walk':
                self.preview_view.zoom = max(0.9, self.preview_view.zoom)
                self.preview_view.pan_x = 0.0
                self.preview_view.pan_y = 0.0
            self.preview_view.refresh(immediate=True)

    def _preview_set_view(self, yaw, pitch, zoom, focus=None):
        if hasattr(self, 'preview_view'):
            self.preview_view.set_view(yaw, pitch, zoom, focus=focus)

    def _preview_zoom(self, factor):
        if hasattr(self, 'preview_view'):
            self.preview_view.set_zoom(self.preview_view.zoom * factor)
            self.preview_view.refresh(immediate=True)

    def _reset_preview_view(self):
        if hasattr(self, 'preview_view'):
            self.preview_view.reset_view()

    def _refresh_preview_only(self):
        self.image_cache = {}
        if hasattr(self, 'preview_view'):
            self.preview_view.refresh(immediate=True)
        if hasattr(self, 'preview_body'):
            self._build_preview_body()
        self._schedule_gpu_preview_warmup()
        self._queue_gpu_preview_warmup()

    # ---------------------------------------------------------------- preview
    def _build_preview_body(self):
        for w in self.preview_body.winfo_children():
            w.destroy()
        stats = self._stats()
        if self.preview_tab == 'materials':
            self._button(self.preview_body, '建材リストPNGを書き出し', self.export_materials_image,
                         bg=UI['ACCENT'], size=8, padx=12, pady=6).pack(fill='x', pady=(0, 8))
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

        warn = tk.Frame(self.preview_body, bg=UI['WARNING_BG'], highlightthickness=1, highlightbackground=UI['ORANGE'])
        warn.pack(fill='x', pady=(10, 0))
        self._label(warn, '検証結果', size=9, weight='bold', bg=UI['WARNING_BG']).pack(anchor='w', padx=10, pady=(8, 2))
        self._validation_line(warn, '競合するルール', stats['conflicts'], '詳細')
        self._validation_line(warn, '未設定のブロック', stats['unset'], '確認')
        self._validation_line(warn, '非対応ブロック', 0, '✓')

    def _stat_box(self, parent, title, value, delta):
        f = tk.Frame(parent, bg=UI['PANEL_2'], highlightthickness=1, highlightbackground=UI['BORDER'])
        f.pack(side='left', fill='x', expand=True, padx=(0, 8), pady=(0, 8))
        self._label(f, title, size=7, fg=UI['MUTED'], bg=UI['PANEL_2']).pack(anchor='w', padx=8, pady=(7, 0))
        self._label(f, str(value), size=14, weight='bold', bg=UI['PANEL_2']).pack(anchor='w', padx=8)
        self._label(f, delta, size=7, fg=UI['GREEN'], bg=UI['PANEL_2']).pack(anchor='e', padx=8, pady=(0, 6))

    def _metric_line(self, parent, label, value):
        f = tk.Frame(parent, bg=UI['PANEL'])
        f.pack(fill='x', pady=2)
        self._label(f, label, size=8, fg=UI['MUTED']).pack(side='left')
        self._label(f, value, size=8, fg=UI['TEXT_SOFT'], weight='bold').pack(side='right')

    def _validation_line(self, parent, label, count, action):
        f = tk.Frame(parent, bg=UI['WARNING_BG'])
        f.pack(fill='x', padx=10, pady=3)
        color = UI['ORANGE'] if count else UI['GREEN']
        self._label(f, '● ' + label, size=8, fg=color, bg=UI['WARNING_BG']).pack(side='left')
        self._label(f, '%s 件' % count, size=8, bg=UI['WARNING_BG']).pack(side='left', padx=(16, 0))
        self._button(f, action, lambda l=label, c=count: self.open_validation_dialog(l, c),
                     bg=UI['BTN_BG'], size=7, padx=8, pady=2).pack(side='right')

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
            rowdata['target'] = self._target_for(conv)
            if rowdata.get('btn') is not None:
                self._refresh_target(rowdata)
            top.destroy()
            self._wheel_target = self.map_canvas if hasattr(self, 'map_canvas') else None
            self._mark_dirty()
            self._refresh_preview_only()

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
        self._target_map_cache_token = None
        self._target_map_cache = {}
        self._gpu_payload_cache_token = None
        self._gpu_payload_cache = None
        self._gpu_payload_building = False
        self._gpu_open_when_ready = False
        if hasattr(self, 'preview_view'):
            try:
                self.preview_view.close_gpu(wait=False)
                self.preview_view._gpu_token = None
                self.preview_view._last_render_key = None
                self.preview_view._last_render_image = None
            except Exception:
                pass
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
        view = self.preview_view.view_state() if hasattr(self, 'preview_view') else None
        im = self._render_schematic_preview(1280, 720, max_blocks=5200, view=view, fast=False,
                                            face_limit_override=8200, texture_limit=8200,
                                            min_face_px=1.0, focus_view=True)
        im.save(out)
        messagebox.showinfo(APP_TITLE, 'プレビューを書き出しました:\n%s' % out)

    def export_materials_image(self):
        if self.loaded_nbt is None:
            messagebox.showinfo(APP_TITLE, '先に設計図を読み込んでください。')
            return
        default_name = os.path.splitext(os.path.basename(self.src_path or 'materials'))[0] + '_materials.png'
        out = filedialog.asksaveasfilename(
            title='建材リストPNGを書き出し', initialfile=default_name, defaultextension='.png',
            filetypes=[('PNG', '*.png'), ('すべて', '*.*')])
        if not out:
            return
        im = self._render_materials_image()
        im.save(out)
        messagebox.showinfo(APP_TITLE, '建材リスト画像を書き出しました:\n%s' % out)

    def _material_list_rows(self):
        grouped = {}
        for conv in self._all_records():
            target = self._target_for(conv)
            final_id = bd.strip_ns(conv.source) if target == KEEP else bd.strip_ns(target)
            item = grouped.setdefault(final_id, {'count': 0, 'sources': set(), 'changed': 0})
            item['count'] += int(conv.count or 0)
            source_id = bd.strip_ns(conv.source)
            item['sources'].add(source_id)
            if source_id != final_id:
                item['changed'] += int(conv.count or 0)
        rows = []
        for bid, data in grouped.items():
            sources = sorted(data['sources'])
            if len(sources) == 1 and sources[0] == bid:
                detail = 'そのまま使用'
            elif len(sources) <= 2:
                detail = '元素材: ' + ' / '.join(bd.jp_name(s) for s in sources)
            else:
                detail = '元素材: %s ほか%d件' % (bd.jp_name(sources[0]), len(sources) - 1)
            rows.append({
                'id': bid,
                'name': bd.jp_name(bid),
                'count': data['count'],
                'stacks_text': self._stack_text(data['count']),
                'shulker_text': self._shulker_text(data['count']),
                'storage_text': self._storage_text(data['count']),
                'sources': detail,
                'changed': data['changed'],
            })
        rows.sort(key=lambda r: (-r['count'], r['name'], r['id']))
        return rows

    def _stack_parts(self, count):
        count = max(0, int(count or 0))
        return count // 64, count % 64

    def _shulker_parts(self, count):
        count = max(0, int(count or 0))
        return count // 1728, count % 1728

    def _stack_text(self, count):
        stacks, rest = self._stack_parts(count)
        if stacks == 0:
            return '%d個' % rest
        if rest:
            return '%dスタック + %d個' % (stacks, rest)
        return '%dスタック' % stacks

    def _shulker_text(self, count):
        count = max(0, int(count or 0))
        boxes, rest = self._shulker_parts(count)
        rest_stacks, rest_items = self._stack_parts(rest)
        if boxes == 0:
            if count and count / 1728.0 < 0.01:
                return 'シュルカー <0.01箱分'
            return 'シュルカー %.2f箱分' % (count / 1728.0)
        if rest == 0:
            return 'シュルカー %d箱' % boxes
        if rest_items:
            if rest_stacks == 0:
                return 'シュルカー %d箱 + %d個' % (boxes, rest_items)
            return 'シュルカー %d箱 + %dスタック + %d個' % (boxes, rest_stacks, rest_items)
        return 'シュルカー %d箱 + %dスタック' % (boxes, rest_stacks)

    def _storage_text(self, count):
        return '%s / %s' % (self._stack_text(count), self._shulker_text(count))

    def _ui_font(self, size, bold=False):
        candidates = [
            'C:/Windows/Fonts/YuGothM.ttc' if bold else 'C:/Windows/Fonts/YuGothR.ttc',
            'C:/Windows/Fonts/meiryob.ttc' if bold else 'C:/Windows/Fonts/meiryo.ttc',
            'C:/Windows/Fonts/msgothic.ttc',
        ]
        for path in candidates:
            try:
                if os.path.exists(path):
                    return ImageFont.truetype(path, size)
            except Exception:
                pass
        return ImageFont.load_default()

    def _draw_fit_text(self, draw, xy, text, font, fill, max_width, fallback_font=None):
        text = str(text)
        if draw.textlength(text, font=font) <= max_width:
            draw.text(xy, text, font=font, fill=fill)
            return
        ell = '...'
        out = text
        while out and draw.textlength(out + ell, font=font) > max_width:
            out = out[:-1]
        if out:
            draw.text(xy, out + ell, font=font, fill=fill)
        elif fallback_font:
            draw.text(xy, ell, font=fallback_font, fill=fill)

    def _render_materials_image_legacy(self):
        rows = self._material_list_rows()
        count = max(1, len(rows))
        cols = 1 if count <= 28 else (2 if count <= 90 else 3)
        width = 1200
        margin = 42
        gap = 24
        header_h = 150
        row_h = 92 if cols < 3 else 74
        rows_per_col = int(math.ceil(count / float(cols)))
        height = header_h + rows_per_col * row_h + 46
        im = Image.new('RGB', (width, height), '#f2f2f7')
        draw = ImageDraw.Draw(im)
        title_font = self._ui_font(34, True)
        sub_font = self._ui_font(17, False)
        head_font = self._ui_font(14, True)
        name_font = self._ui_font(18 if cols < 3 else 15, True)
        id_font = self._ui_font(12 if cols < 3 else 10, False)
        count_font = self._ui_font(20 if cols < 3 else 16, True)
        detail_font = self._ui_font(12 if cols < 3 else 10, False)

        draw.rounded_rectangle([18, 18, width - 18, height - 18], radius=34, fill='#ffffff')
        title = '建材リスト'
        subtitle = os.path.basename(self.src_path or '設計図') + ' / 変換後に必要な素材'
        draw.text((margin, 38), title, font=title_font, fill='#000000')
        draw.text((margin, 84), subtitle, font=sub_font, fill='#6e6e73')
        total_blocks = sum(r['count'] for r in rows)
        summary = '%d種類 / 合計 %s個 / %s / %s' % (
            len(rows), '{:,}'.format(total_blocks),
            self._stack_text(total_blocks), self._shulker_text(total_blocks))
        tw = draw.textlength(summary, font=head_font)
        draw.rounded_rectangle([width - margin - tw - 34, 46, width - margin, 82], radius=18, fill='#e8f2ff')
        draw.text((width - margin - tw - 17, 54), summary, font=head_font, fill='#007aff')
        draw.line([(margin, 122), (width - margin, 122)], fill='#d1d1d6', width=1)

        col_w = int((width - margin * 2 - gap * (cols - 1)) / cols)
        for idx, row in enumerate(rows):
            col = idx // rows_per_col
            r = idx % rows_per_col
            x = margin + col * (col_w + gap)
            y = header_h + r * row_h
            fill = '#ffffff' if r % 2 == 0 else '#f7f7fb'
            draw.rounded_rectangle([x, y, x + col_w, y + row_h - 8], radius=18, fill=fill, outline='#e5e5ea')

            icon_size = 46 if cols < 3 else 38
            icon = icons.render_block_image(row['id'], icon_size).convert('RGBA')
            im.paste(icon, (x + 14, y + int((row_h - icon_size - 8) / 2)), icon)
            tx = x + 14 + icon_size + 12
            right_w = 230 if cols == 1 else (170 if cols == 2 else 112)
            max_text = col_w - (tx - x) - right_w - 12
            self._draw_fit_text(draw, (tx, y + 13), row['name'], name_font, '#1c1c1e', max_text)
            self._draw_fit_text(draw, (tx, y + 39 if cols < 3 else y + 34), row['id'],
                                id_font, '#8e8e93', max_text)
            if row['changed']:
                self._draw_fit_text(draw, (tx, y + 56 if cols < 3 else y + 48), row['sources'],
                                    detail_font, '#34a853', max_text)
            else:
                self._draw_fit_text(draw, (tx, y + 56 if cols < 3 else y + 48), row['sources'],
                                    detail_font, '#8e8e93', max_text)
            count_text = 'x%s' % '{:,}'.format(row['count'])
            cw = draw.textlength(count_text, font=count_font)
            draw.text((x + col_w - cw - 16, y + 15 if cols < 3 else y + 12),
                      count_text, font=count_font, fill='#000000')
            sx = x + col_w - right_w - 16
            self._draw_fit_text(draw, (sx, y + 42 if cols < 3 else y + 36), row['stacks_text'],
                                detail_font, '#007aff', right_w)
            self._draw_fit_text(draw, (sx, y + 60 if cols < 3 else y + 52), row['shulker_text'],
                                detail_font, '#6e6e73', right_w)
        footer = 'この画像は現在の素材変換設定を反映しています。'
        fw = draw.textlength(footer, font=id_font)
        draw.text(((width - fw) / 2, height - 32), footer, font=id_font, fill='#8e8e93')
        return im

    def _render_materials_image(self):
        rows = self._material_list_rows()
        if not rows:
            rows = [{'id': 'barrier', 'name': '建材なし', 'count': 0,
                     'stacks_text': '0個', 'shulker_text': 'シュルカー 0.00箱分',
                     'storage_text': '0個 / シュルカー 0.00箱分',
                     'sources': '', 'changed': 0}]

        cols = 4 if len(rows) >= 4 else max(1, len(rows))
        width = 1536
        margin = 42
        gap = 14
        header_h = 108
        card_h = 136
        row_gap = 14
        row_count = int(math.ceil(len(rows) / float(cols)))
        height = header_h + row_count * (card_h + row_gap) + 38
        im = Image.new('RGB', (width, height), '#111d24')
        draw = ImageDraw.Draw(im)

        tile = 30
        for y in range(0, height, tile):
            for x in range(0, width, tile):
                fill = '#13242c' if ((x // tile + y // tile) % 2 == 0) else '#102028'
                draw.rectangle([x, y, x + tile - 1, y + tile - 1], fill=fill)
        for x in range(0, width, tile * 2):
            draw.line([(x, 0), (x, height)], fill='#172a33')
        for y in range(0, height, tile * 2):
            draw.line([(0, y), (width, y)], fill='#172a33')

        draw.rectangle([4, 4, width - 5, height - 5], outline='#4d6976', width=3)
        draw.rectangle([12, 12, width - 13, height - 13], outline='#2d4652', width=2)

        title_font = self._ui_font(43, True)
        name_font = self._ui_font(22, True)
        count_font = self._ui_font(30, True)
        meta_font = self._ui_font(12, True)
        small_font = self._ui_font(12, False)

        draw.text((margin, 35), '建材リスト', font=title_font, fill='#f4f7f8')
        line_y = 88
        draw.rectangle([margin, line_y, width - margin, line_y + 5], fill='#355564')
        draw.rectangle([margin, line_y, margin + 116, line_y + 5], fill='#89e07f')

        col_w = int((width - margin * 2 - gap * (cols - 1)) / cols)
        for idx, row in enumerate(rows):
            r = idx // cols
            col = idx % cols
            x = margin + col * (col_w + gap)
            y = header_h + r * (card_h + row_gap)

            draw.rounded_rectangle([x + 4, y + 6, x + col_w + 4, y + card_h + 6],
                                   radius=9, fill='#071016')
            draw.rounded_rectangle([x, y, x + col_w, y + card_h], radius=9,
                                   fill='#1b2c34', outline='#4b6674', width=2)
            draw.rounded_rectangle([x + 2, y + 2, x + col_w - 2, y + card_h - 2],
                                   radius=7, outline='#263f4b', width=1)

            icon_box = 76
            ix = x + 12
            iy = y + 12
            draw.rectangle([ix, iy, ix + icon_box, iy + icon_box], fill='#102029',
                           outline='#5a7581', width=2)
            draw.rectangle([ix + 6, iy + 6, ix + icon_box - 6, iy + icon_box - 6],
                           outline='#28414d', width=1)
            icon = icons.render_block_image(row['id'], 62).convert('RGBA')
            im.paste(icon, (ix + 7, iy + 7), icon)

            tx = ix + icon_box + 14
            max_text = col_w - (tx - x) - 16
            self._draw_fit_text(draw, (tx, y + 18), row['name'], name_font, '#eef3f5',
                                max_text, fallback_font=small_font)
            count_text = '{:,} 個'.format(int(row['count'] or 0))
            self._draw_fit_text(draw, (tx, y + 54), count_text, count_font, '#83e47e',
                                max_text, fallback_font=small_font)
            self._draw_fit_text(draw, (tx, y + 91), 'スタック: ' + row['stacks_text'],
                                meta_font, '#9ac7d8', max_text, fallback_font=small_font)
            shulker_detail = str(row['shulker_text']).replace('シュルカー ', '', 1)
            self._draw_fit_text(draw, (tx, y + 112), 'シュルカー: ' + shulker_detail,
                                meta_font, '#c2d0d6', max_text, fallback_font=small_font)
        return im

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
            writer = csv.writer(f)
            writer.writerow([
                'source', 'target', 'count', 'status',
                'stacks_64', 'stack_text',
                'shulker_boxes_27stacks', 'shulker_text',
            ])
            for conv in self._all_records():
                tgt = self._target_for(conv)
                status = 'keep' if tgt == KEEP else ('same' if tgt == bd.strip_ns(conv.source) else 'replace')
                writer.writerow([
                    conv.source,
                    '' if tgt == KEEP else tgt,
                    conv.count,
                    status,
                    '%.2f' % (int(conv.count or 0) / 64.0),
                    self._stack_text(conv.count),
                    '%.3f' % (int(conv.count or 0) / 1728.0),
                    self._shulker_text(conv.count),
                ])
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
            if not messagebox.askyesno(
                    APP_TITLE,
                    '変換する素材が未設定です。\n\n'
                    '置き換えは行わず、読み込んだ設計図を別名で保存しますか？\n'
                    '素材を変える場合は、中央の一覧で置き換え先を選ぶか「自動マッピング」を押してください。'):
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
                '出力が完了しました。\n\n置き換えた素材: %d 種類\n書き換えたパレット: %d 件\n出力ファイル:\n%s\n\n'
                'フォルダを開きますか？' % (len(mapping), changed, out)):
            try:
                os.startfile(os.path.dirname(out))
            except Exception:
                pass

    # ---------------------------------------------------------------- visuals
    def _preview_rec_parts(self, rec):
        props = rec[4] if len(rec) > 4 and isinstance(rec[4], dict) else {}
        return rec[0], rec[1], rec[2], rec[3], props

    def _queue_gpu_preview_warmup(self):
        if self.loaded_nbt is None:
            return
        try:
            if self._gpu_warmup_after_id is not None:
                self.root.after_cancel(self._gpu_warmup_after_id)
        except tk.TclError:
            pass
        try:
            self._gpu_warmup_after_id = self.root.after(6500, self._run_queued_gpu_preview_warmup)
        except tk.TclError:
            self._gpu_warmup_after_id = None

    def _run_queued_gpu_preview_warmup(self):
        self._gpu_warmup_after_id = None
        self._schedule_gpu_preview_warmup()

    def _queue_focus_surface_warmup(self):
        if self.loaded_nbt is None or self._focus_surface_building:
            return
        expected_id = id(self.loaded_nbt)
        self._focus_surface_building = True

        def worker():
            try:
                self._source_surface_records(max_blocks=10 ** 9)
            except Exception:
                pass
            finally:
                self._focus_surface_building = False
            if id(self.loaded_nbt) == expected_id:
                self._safe_after(self._finish_focus_surface_warmup)

        threading.Thread(target=worker, daemon=True).start()

    def _finish_focus_surface_warmup(self):
        if self.loaded_nbt is None:
            return
        current_id = id(self.loaded_nbt)
        for key in list(self._preview_source_cache.keys()):
            if (isinstance(key, tuple) and len(key) >= 2 and key[0] == current_id
                    and key[1] in ('focused_source_records', 'focused_ranked_records')):
                self._preview_source_cache.pop(key, None)
        if hasattr(self, 'preview_view'):
            self.preview_view.refresh()
        self._sync_progress(text='進行状況: 高密度プレビュー準備完了')

    def _schedule_gpu_preview_warmup(self, open_when_ready=False):
        if self.loaded_nbt is None or self._gpu_payload_building:
            if open_when_ready:
                self._gpu_open_when_ready = True
            return
        token = self._preview_cache_token()
        if self._gpu_payload_cache_token == token and self._gpu_payload_cache is not None:
            if open_when_ready:
                self._gpu_open_when_ready = False
                self._safe_after(self._open_ready_gpu_payload)
            return
        if open_when_ready:
            self._gpu_open_when_ready = True
        self._gpu_payload_building = True

        def worker(expected_token):
            error = None
            try:
                payload = self._gpu_preview_payload()
                if payload.get('blocks') and 'prebuilt_mesh' not in payload:
                    try:
                        import gpu_preview
                        payload['prebuilt_mesh'] = gpu_preview.build_mesh(payload)
                    except Exception:
                        pass
                ok = bool(payload.get('blocks')) and self._preview_cache_token() == expected_token
            except Exception as exc:
                error = exc
                ok = False
            finally:
                self._gpu_payload_building = False
            if self.loaded_nbt is not None:
                self._safe_after(lambda ok=ok, error=error: self._finish_gpu_preview_warmup(ok, error))

        threading.Thread(target=worker, args=(token,), daemon=True).start()

    def _finish_gpu_preview_warmup(self, ok, error=None):
        want_open = self._gpu_open_when_ready
        if ok:
            self._sync_progress(text='進行状況: 全画面プレビュー準備完了')
            if want_open:
                self._gpu_open_when_ready = False
                try:
                    self._open_ready_gpu_payload()
                except Exception as exc:
                    messagebox.showwarning(APP_TITLE, '全画面プレビューの起動に失敗しました。\n\n%s' % exc)
            return
        self._gpu_open_when_ready = False
        self._sync_progress(text='進行状況: 全画面プレビュー準備に失敗しました')
        if want_open:
            messagebox.showwarning(APP_TITLE, '全画面プレビューの準備に失敗しました。\n\n%s' % (error or 'unknown error'))

    def _gpu_preview_payload(self):
        token = self._preview_cache_token()
        if self._gpu_payload_cache_token == token and self._gpu_payload_cache is not None:
            return self._gpu_payload_cache
        records = self._focused_render_records(max_blocks=GPU_PREVIEW_BLOCK_LIMIT)
        occupied = set((int(self._preview_rec_parts(rec)[0]),
                        int(self._preview_rec_parts(rec)[1]),
                        int(self._preview_rec_parts(rec)[2])) for rec in records)
        bounds = self._record_bounds(records)
        atlas, tile_map = self._gpu_texture_atlas(records)
        blocks = []
        face_order = ('up', 'down', 'north', 'south', 'east', 'west')
        for rec in records:
            x, y, z, bid, props = self._preview_rec_parts(rec)
            base = bd.strip_ns(bid)
            r, g, b = self._block_rgb(bid)
            face_tiles = [tile_map.get((base, face), 0) for face in face_order]
            shape_id, variant = self._gpu_shape(base, props)
            blocks.append((int(x), int(y), int(z), int(r), int(g), int(b),
                           face_tiles[0], face_tiles[1], face_tiles[2], face_tiles[3],
                           face_tiles[4], face_tiles[5], shape_id, variant))
        payload = {
            'title': os.path.basename(self.src_path or 'schematic'),
            'blocks': blocks,
            'occupied': occupied,
            'bounds': bounds,
            'atlas': atlas,
            'atlas_uvs': atlas['uvs'],
            'max_faces': GPU_PREVIEW_FACE_LIMIT,
            'width': 1280,
            'height': 760,
            'startup_timeout': 0.05,
            'target_fps': 0,
            'uncapped_fps': True,
            'show_overlay': False,
            'force_continuous_redraw': True,
            'initial_mode': 'orbit',
            'initial_yaw': -38.0,
            'initial_pitch': 26.0,
            'initial_zoom': 1.65,
        }
        self._gpu_payload_cache_token = token
        self._gpu_payload_cache = payload
        return payload

    def _gpu_texture_atlas(self, records):
        bases = sorted({bd.strip_ns(self._preview_rec_parts(rec)[3]) for rec in records})
        tile_size = 32
        entries = []
        tile_map = {}
        face_order = ('up', 'down', 'north', 'south', 'east', 'west')
        for base in bases:
            for face in face_order:
                tile_map[(base, face)] = len(entries)
                try:
                    tex = icons.block_texture_image(base, top=(face == 'up'), face=face).convert('RGBA')
                except Exception:
                    tex = Image.new('RGBA', (tile_size, tile_size), self._block_rgb(base) + (255,))
                if tex.size != (tile_size, tile_size):
                    tex = tex.resize((tile_size, tile_size), Image.Resampling.NEAREST)
                entries.append(tex)
        if not entries:
            entries.append(Image.new('RGBA', (tile_size, tile_size), (255, 255, 255, 255)))
        cols = max(1, int(math.ceil(math.sqrt(len(entries)))))
        rows = int(math.ceil(len(entries) / float(cols)))
        atlas_img = Image.new('RGBA', (cols * tile_size, rows * tile_size), (255, 255, 255, 255))
        uvs = []
        inset = 0.25
        for index, tex in enumerate(entries):
            col = index % cols
            row = index // cols
            x = col * tile_size
            y = row * tile_size
            atlas_img.paste(tex, (x, y))
            u0 = (x + inset) / atlas_img.width
            u1 = (x + tile_size - inset) / atlas_img.width
            v0 = 1.0 - ((y + tile_size - inset) / atlas_img.height)
            v1 = 1.0 - ((y + inset) / atlas_img.height)
            uvs.append((u0, v0, u1, v1))
        return {
            'width': atlas_img.width,
            'height': atlas_img.height,
            'rgba': atlas_img.tobytes(),
            'uvs': uvs,
            'tile_size': tile_size,
            'count': len(entries),
            'source': icons.minecraft_assets_label(),
        }, tile_map

    def _gpu_shape(self, base, props=None):
        base = bd.strip_ns(base)
        props = props or {}
        facing = {'north': 0, 'east': 1, 'south': 2, 'west': 3}.get(str(props.get('facing', 'north')), 0)
        if base.endswith('_slab'):
            slab_type = str(props.get('type', 'bottom'))
            if slab_type == 'double':
                return 0, 0
            return (5 if slab_type == 'top' else 1), 0
        if base.endswith('_stairs'):
            top_bit = 4 if str(props.get('half', 'bottom')) == 'top' else 0
            return 6, facing | top_bit
        if base.endswith('_trapdoor'):
            top_bit = 4 if str(props.get('half', 'bottom')) == 'top' else 0
            open_bit = 8 if str(props.get('open', 'false')) == 'true' else 0
            return 7, facing | top_bit | open_bit
        if ('rail' in base or base.endswith('_carpet') or base.endswith('_pressure_plate')
                or base in ('snow', 'repeater', 'comparator', 'redstone_wire')):
            return 2, 0
        if base.endswith('_fence') or base.endswith('_wall'):
            return 9, self._connection_mask(props)
        if base.endswith('_pane') or base in ('iron_bars', 'chain'):
            return 10, self._connection_mask(props)
        if base.endswith('_button'):
            face_map = {'floor': 0, 'wall': 1, 'ceiling': 2}
            return 8, facing | (face_map.get(str(props.get('face', 'wall')), 1) << 2)
        if base.endswith('_pane'):
            return 10, self._connection_mask(props)
        return 0, 0

    def _connection_mask(self, props):
        mask = 0
        for bit, name in enumerate(('north', 'east', 'south', 'west')):
            value = str(props.get(name, 'none'))
            if value not in ('none', 'false', '0'):
                mask |= 1 << bit
        return mask

    def _loaded_thumb(self, w, h):
        key = ('loaded', w, h, self.src_path, icons.minecraft_assets_label())
        if key in self.image_cache:
            return self.image_cache[key]
        view = {'yaw': -28.0, 'pitch': 0.22, 'zoom': 3.6, 'pan_x': 0.0, 'pan_y': 0.0, 'mode': 'orbit'}
        im = self._render_schematic_preview(w, h, max_blocks=1200, view=view, fast=True,
                                            face_limit_override=1600, texture_limit=1600,
                                            min_face_px=0.6, focus_view=True)
        img = ImageTk.PhotoImage(im)
        self.image_cache[key] = img
        return img

    def _result_preview_image(self, w, h):
        key = ('result', w, h, self.src_path, tuple(sorted(self.overrides.items())),
               icons.minecraft_assets_label())
        if key in self.image_cache:
            return self.image_cache[key]
        view = {'yaw': -28.0, 'pitch': 0.22, 'zoom': 3.6, 'pan_x': 0.0, 'pan_y': 0.0, 'mode': 'orbit'}
        im = self._render_schematic_preview(w, h, max_blocks=1200, view=view, fast=True,
                                            face_limit_override=1600, texture_limit=1600,
                                            min_face_px=0.6, focus_view=True)
        img = ImageTk.PhotoImage(im)
        self.image_cache[key] = img
        return img

    def _render_schematic_preview(self, w, h, max_blocks=80000, view=None, fast=False,
                                  face_limit_override=None, texture_limit=None, min_face_px=0.0,
                                  focus_view=False):
        if fast:
            max_blocks = min(max_blocks, 7000)
        im = Image.new('RGB', (w, h), '#87c9ff')
        d = ImageDraw.Draw(im)
        if focus_view:
            records = self._focused_render_records(max_blocks=max_blocks)
            occupied = set((int(rec[0]), int(rec[1]), int(rec[2])) for rec in records)
        else:
            records = self._render_records(max_blocks=max_blocks)
            if fast or int(max_blocks or 0) <= CPU_PREVIEW_IDLE_BLOCK_LIMIT * 2:
                occupied = set((int(rec[0]), int(rec[1]), int(rec[2])) for rec in records)
            else:
                occupied = self._source_occupied_positions()
        bounds = self._record_bounds(records)
        camera = self._minecraft_camera(bounds, w, h, view=view)
        self._draw_minecraft_sky(d, w, h)
        self._draw_superflat_ground(d, w, h, camera, bounds, fast=fast)
        if not records:
            self._draw_empty_preview(im, d, w, h, camera, bounds)
            d.rectangle([0, 0, w - 1, h - 1], outline='#4d79ff')
            return im

        self._draw_build_shadow(d, records, camera, w, h, fast=fast)
        faces = self._visible_block_faces(records, camera, occupied_positions=occupied)
        if min_face_px:
            minimum = float(min_face_px)
            faces = [face for face in faces if self._face_screen_size(face[1]) >= minimum]
        face_limit = (int(face_limit_override) if face_limit_override is not None
                      else (4200 if fast else (32000 if w * h >= 260000 else 12000)))
        if len(faces) > face_limit:
            step = len(faces) / float(max(1, face_limit))
            faces = [faces[min(len(faces) - 1, int((i + 0.5) * step))]
                     for i in range(face_limit)]
        if texture_limit is None:
            texture_limit = 14000
        texture_limit = max(0, int(texture_limit))
        texture_start = max(0, len(faces) - texture_limit) if texture_limit else len(faces)
        for index, (depth, poly, bid, normal, seed) in enumerate(faces):
            self._draw_minecraft_face(im, d, poly, self._block_rgb(bid), normal, seed, bid,
                                      textured=index >= texture_start)
        if not fast:
            self._draw_scene_vignette(d, w, h)
        d.rectangle([0, 0, w - 1, h - 1], outline='#4d79ff')
        return im

    def _face_screen_size(self, poly):
        return max(max(p[0] for p in poly) - min(p[0] for p in poly),
                   max(p[1] for p in poly) - min(p[1] for p in poly))

    def _focused_render_records(self, max_blocks=5600):
        max_blocks = max(100, int(max_blocks or 5600))
        try:
            total_blocks = int(self.loaded_nbt.get('Metadata', {}).get('TotalBlocks', 0)) if self.loaded_nbt else 0
        except Exception:
            total_blocks = 0
        if max_blocks <= 6000 and 0 < total_blocks <= 220000:
            full_surface_key = (id(self.loaded_nbt), 'surface_records', 10 ** 9)
            if full_surface_key in self._preview_source_cache:
                source_limit = 10 ** 9
            else:
                self._queue_focus_surface_warmup()
                source_limit = max(4200, int(max_blocks * 5))
        elif max_blocks <= 1200:
            source_limit = max(3600, int(max_blocks * 5))
        elif max_blocks <= 6000:
            source_limit = max(8000, int(max_blocks * 6))
        else:
            source_limit = min(180000, max_blocks)
        raw_records = self._source_surface_records(max_blocks=source_limit)
        if not raw_records:
            return []
        source_key = (id(self.loaded_nbt), 'focused_source_records', max_blocks)
        if source_key in self._preview_source_cache:
            focused = self._preview_source_cache[source_key]
        else:
            focused = self._choose_contiguous_preview_records(raw_records, max_blocks)
            self._preview_source_cache[source_key] = focused
        return self._map_render_records(focused)

    def _choose_contiguous_preview_records(self, records, max_blocks):
        if len(records) <= max_blocks:
            return list(records)
        ranked = self._rank_contiguous_preview_records(records)
        focused = ranked[:max_blocks]
        focused.sort(key=lambda rec: (int(rec[1]), int(rec[2]), int(rec[0])))
        return focused

    def _rank_contiguous_preview_records(self, records):
        rank_key = (id(self.loaded_nbt), 'focused_ranked_records', id(records), len(records))
        cached = self._preview_source_cache.get(rank_key)
        if cached is not None:
            return cached
        bounds = self._record_bounds(records)
        span = max(bounds['span_x'], bounds['span_z'])
        cell = max(8, min(32, int(span / 12)))
        buckets = {}
        for rec in records:
            x, _y, z = rec[:3]
            key = (int(math.floor(float(x) / cell)), int(math.floor(float(z) / cell)))
            buckets[key] = buckets.get(key, 0) + 1
        if not buckets:
            ranked = list(records)
            self._preview_source_cache[rank_key] = ranked
            return ranked
        bx, bz = max(buckets.items(), key=lambda item: item[1])[0]
        cx = (bx + 0.5) * cell
        cz = (bz + 0.5) * cell
        ranked = sorted(
            records,
            key=lambda rec: (
                max(abs((float(rec[0]) + 0.5) - cx), abs((float(rec[2]) + 0.5) - cz)),
                ((float(rec[0]) + 0.5) - cx) ** 2 + ((float(rec[2]) + 0.5) - cz) ** 2,
                float(rec[1]),
            )
        )
        self._preview_source_cache[rank_key] = ranked
        return ranked

    def _source_surface_records(self, max_blocks=60000):
        if self.loaded_nbt is None:
            return []
        max_blocks = max(900, int(max_blocks or 60000))
        records = self._source_render_records(max_blocks=max_blocks)
        return self._preview_source_cache.get((id(self.loaded_nbt), 'surface_records', max_blocks), records)

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

    def _minecraft_camera(self, bounds, w, h, view=None):
        view = view or {}
        span = max(bounds['span_x'], bounds['span_z'])
        height = bounds['span_y']
        zoom = max(0.45, min(7.2, float(view.get('zoom', 3.2) or 3.2)))
        yaw = math.radians(float(view.get('yaw', -28.0) or -28.0))
        pitch = max(-0.12, min(0.88, float(view.get('pitch', 0.24) or 0.24)))
        mode = view.get('mode', 'orbit')
        if mode == 'walk':
            back = max(4.0, span * 0.95) / zoom
            ahead = max(4.0, span * 0.55)
            cam = (bounds['cx'] - math.sin(yaw) * back,
                   max(1.45, bounds['min_y'] + 1.62 + pitch * 1.2),
                   bounds['cz'] - math.cos(yaw) * back)
            target = (bounds['cx'] + math.sin(yaw) * ahead,
                      max(1.0, bounds['min_y'] + 1.25 + height * 0.18),
                      bounds['cz'] + math.cos(yaw) * ahead)
            focal = min(w, h) * (1.55 + zoom * 0.18)
            cy = h * (0.56 + pitch * 0.08)
        else:
            dist = max(12.0, (span * 2.15 + height * 0.85) / zoom)
            cam = (
                bounds['cx'] + math.sin(yaw) * dist,
                max(3.5, height * 0.54 + span * (0.16 + pitch * 0.42)),
                bounds['cz'] + math.cos(yaw) * dist,
            )
            target = (bounds['cx'], max(0.8, bounds['min_y'] + height * 0.38), bounds['cz'])
            focal = min(w, h) * 1.35
            cy = h * 0.55
        forward = self._v_norm((target[0] - cam[0], target[1] - cam[1], target[2] - cam[2]))
        right = self._v_norm(self._v_cross(forward, (0.0, 1.0, 0.0)))
        up = self._v_cross(right, forward)
        try:
            pan_x = float(view.get('pan_x', 0.0) or 0.0)
            pan_y = float(view.get('pan_y', 0.0) or 0.0)
        except Exception:
            pan_x = pan_y = 0.0
        if pan_x or pan_y:
            sx = max(1.0, span)
            sy = max(1.0, height, span * 0.55)
            offset = (
                right[0] * pan_x * sx + up[0] * pan_y * sy,
                right[1] * pan_x * sx + up[1] * pan_y * sy,
                right[2] * pan_x * sx + up[2] * pan_y * sy,
            )
            cam = (cam[0] + offset[0], cam[1] + offset[1], cam[2] + offset[2])
            target = (target[0] + offset[0], target[1] + offset[1], target[2] + offset[2])
        return {'pos': cam, 'forward': forward, 'right': right, 'up': up, 'focal': focal,
                'cx': w / 2.0, 'cy': cy, 'width': w, 'height': h}

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

    def _draw_superflat_ground(self, draw, w, h, camera, bounds, fast=False):
        horizon = int(h * 0.58)
        draw.rectangle([0, horizon, w, h], fill='#7ac943')
        extent = max(38, int(max(bounds['span_x'], bounds['span_z']) * (2.0 if fast else 2.8)))
        cx, cz = bounds['cx'], bounds['cz']
        x0, x1 = int(cx - extent), int(cx + extent)
        z0, z1 = int(cz - extent), int(cz + extent)
        cells = []
        step = max(4 if fast else 2, extent // (10 if fast else 18))
        for x in range(x0, x1, step):
            cells.append(((x, -0.02, z0), (x, -0.02, z1)))
        for z in range(z0, z1, step):
            cells.append(((x0, -0.02, z), (x1, -0.02, z)))
        for a, b in cells:
            pa = self._project3(a, camera)
            pb = self._project3(b, camera)
            if pa and pb:
                line_y = max(pa[1], pb[1])
                color = '#7ace45' if line_y < h * 0.76 else '#72c740'
                draw.line([(pa[0], pa[1]), (pb[0], pb[1])], fill=color, width=1)
        if not fast:
            random.seed(1127)
            for _ in range(max(45, w * h // 9000)):
                gx = random.uniform(x0, x1)
                gz = random.uniform(z0, z1)
                p = self._project3((gx, 0.0, gz), camera)
                if p and horizon <= p[1] <= h:
                    shade = random.choice(['#86d84d', '#6fbd3e', '#8bd653', '#5ba737'])
                    size = 1 if p[1] < h * 0.72 else 2
                    draw.rectangle([p[0], p[1], p[0] + size, p[1] + size], fill=shade)
        for i in range(4 if fast else 10):
            y = horizon + i
            draw.line([(0, y), (w, y)], fill=(128 + i, 199 + i, 116 + i))

    def _draw_build_shadow(self, draw, records, camera, w, h, fast=False):
        footprint = {}
        for rec in records:
            x, y, z = rec[:3]
            if y == 0:
                footprint[(x, z)] = True
        for x, z in list(footprint.keys())[:700 if fast else 3500]:
            corners = [(x + 0.18, 0.005, z + 0.18), (x + 1.05, 0.005, z + 0.26),
                       (x + 0.90, 0.005, z + 1.05), (x + 0.04, 0.005, z + 0.92)]
            pts = [self._project3(p, camera) for p in corners]
            if all(pts):
                poly = [(p[0], p[1]) for p in pts]
                if self._poly_on_screen(poly, w, h, pad=20):
                    draw.polygon(poly, fill='#4a7e2d')

    def _visible_block_faces(self, records, camera, occupied_positions=None):
        occupied = occupied_positions or set((int(rec[0]), int(rec[1]), int(rec[2])) for rec in records)
        face_defs = getattr(preview_geom, 'FACE_DEFS', None) if preview_geom else None
        shape_boxes = getattr(preview_geom, '_shape_boxes', None) if preview_geom else None
        if not face_defs or not shape_boxes:
            face_defs = (
                ((0, 1, 0), ((0, 1, 1), (1, 1, 1), (1, 1, 0), (0, 1, 0)), 1.18),
                ((0, -1, 0), ((0, 0, 0), (1, 0, 0), (1, 0, 1), (0, 0, 1)), 0.48),
                ((0, 0, 1), ((0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1)), 0.86),
                ((1, 0, 0), ((1, 0, 1), (1, 0, 0), (1, 1, 0), (1, 1, 1)), 0.76),
                ((0, 0, -1), ((1, 0, 0), (0, 0, 0), (0, 1, 0), (1, 1, 0)), 0.68),
                ((-1, 0, 0), ((0, 0, 0), (0, 0, 1), (0, 1, 1), (0, 1, 0)), 0.60),
            )
            shape_boxes = lambda _shape_id, _variant: [(0.0, 0.0, 0.0, 1.0, 1.0, 1.0, True)]
        faces = []
        screen_w = int(camera.get('width') or camera['cx'] * 2)
        screen_h = int(camera.get('height') or camera['cy'] / 0.55)
        for rec in records:
            x, y, z, bid, props = self._preview_rec_parts(rec)
            ix, iy, iz = int(x), int(y), int(z)
            shape_id, variant = self._gpu_shape(bd.strip_ns(bid), props)
            for x0, y0, z0, x1, y1, z1, occluding in shape_boxes(shape_id, variant):
                sx, sy, sz = x1 - x0, y1 - y0, z1 - z0
                for normal, corners, _light in face_defs:
                    if occluding and (ix + normal[0], iy + normal[1], iz + normal[2]) in occupied:
                        continue
                    pts3 = [(ix + x0 + cx * sx, iy + y0 + cy * sy, iz + z0 + cz * sz)
                            for cx, cy, cz in corners]
                    projected = [self._project3(p, camera) for p in pts3]
                    if not all(projected):
                        continue
                    pts2 = [(p[0], p[1]) for p in projected]
                    if not self._poly_on_screen(pts2, screen_w, screen_h, pad=80):
                        continue
                    depth = sum(p[2] for p in projected) / len(projected)
                    seed = (ix * 73856093) ^ (iy * 19349663) ^ (iz * 83492791)
                    faces.append((depth, pts2, bid, normal, seed))
        faces.sort(key=lambda f: f[0], reverse=True)
        return faces

    def _draw_minecraft_face(self, canvas, draw, poly, color, normal, seed, bid, textured=True):
        light = self._v_norm((-0.35, 0.82, -0.46))
        dot = max(0.0, self._v_dot(normal, light))
        if normal[1] > 0:
            factor = 1.12
        else:
            factor = 0.55 + dot * 0.42
        fill = self._shade(color, factor)
        outline = self._shade(color, 0.38)
        size = max(max(p[0] for p in poly) - min(p[0] for p in poly),
                   max(p[1] for p in poly) - min(p[1] for p in poly))
        if textured and size >= 6:
            try:
                tex = icons.block_texture_image(bid, top=normal[1] > 0,
                                                face=self._texture_face_name(normal))
            except Exception:
                tex = None
            if tex is not None and self._paste_preview_texture(canvas, tex, poly, factor):
                return
        draw.polygon(poly, fill=fill, outline=outline if size >= 5 else None)
        if size >= 8:
            self._draw_face_texture(draw, poly, fill, seed)

    def _texture_face_name(self, normal):
        if normal[1] > 0:
            return 'up'
        if normal[1] < 0:
            return 'down'
        if normal[2] < 0:
            return 'north'
        if normal[2] > 0:
            return 'south'
        if normal[0] > 0:
            return 'east'
        if normal[0] < 0:
            return 'west'
        return None

    def _paste_preview_texture(self, canvas, tex, poly, factor):
        if tex is None or len(poly) < 4:
            return False
        p0, p1, _p2, p3 = poly
        px = max(1, tex.width)
        ux, uy = p1[0] - p0[0], p1[1] - p0[1]
        vx, vy = p3[0] - p0[0], p3[1] - p0[1]
        det = (ux * vy - vx * uy) / (px * px)
        if abs(det) < 1e-6:
            return False
        min_x = max(0, int(math.floor(min(p[0] for p in poly))) - 1)
        min_y = max(0, int(math.floor(min(p[1] for p in poly))) - 1)
        max_x = min(canvas.size[0], int(math.ceil(max(p[0] for p in poly))) + 1)
        max_y = min(canvas.size[1], int(math.ceil(max(p[1] for p in poly))) + 1)
        bw = max_x - min_x
        bh = max_y - min_y
        if bw <= 0 or bh <= 0:
            return False
        a = (vy / px) / det
        b = (-vx / px) / det
        d = (-uy / px) / det
        e = (ux / px) / det
        c = -(a * p0[0] + b * p0[1])
        f = -(d * p0[0] + e * p0[1])
        local_affine = (a, b, a * min_x + b * min_y + c,
                        d, e, d * min_x + e * min_y + f)
        warped = tex.transform((bw, bh), Image.AFFINE, local_affine, resample=Image.NEAREST)
        mask = Image.new('L', (bw, bh), 0)
        local_poly = [(p[0] - min_x, p[1] - min_y) for p in poly]
        ImageDraw.Draw(mask).polygon(local_poly, fill=255)
        if warped.mode == 'RGBA':
            alpha = warped.getchannel('A')
            if alpha.getextrema() != (255, 255):
                mask = ImageChops.multiply(mask, alpha)
        canvas.paste(warped, (min_x, min_y), mask)
        sd = ImageDraw.Draw(canvas, 'RGBA')
        if factor < 0.98:
            sd.polygon(poly, fill=(0, 0, 0, min(150, int((1.0 - factor) * 145))))
        elif factor > 1.02:
            sd.polygon(poly, fill=(255, 255, 255, min(48, int((factor - 1.0) * 75))))
        return True

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

    def _draw_empty_preview(self, canvas, draw, w, h, camera=None, bounds=None):
        title = '設計図を読み込むと表示します'
        body = '.litematic をドロップしてください。'
        if self.loaded_nbt is not None:
            title = 'プレビューを取得できませんでした'
            body = 'BlockStates を確認してください。'
        title_font = self._ui_font(18 if w < 520 else 22, True)
        body_font = self._ui_font(11 if w < 520 else 13, False)
        tw = draw.textlength(title, font=title_font)
        bw = draw.textlength(body, font=body_font)
        panel_w = min(w - 28, max(360, int(max(tw, bw)) + 48))
        panel_h = 112
        x0 = int((w - panel_w) / 2)
        y0 = int((h - panel_h) / 2)
        draw.rounded_rectangle([x0, y0, x0 + panel_w, y0 + panel_h], radius=16,
                               fill='#101820', outline='#4d79ff', width=2)
        draw.text((x0 + (panel_w - tw) / 2, y0 + 28), title, font=title_font, fill='#ffffff')
        draw.text((x0 + (panel_w - bw) / 2, y0 + 70), body, font=body_font, fill='#d7e7ff')

    def _draw_cube(self, draw, px, py, size, color):
        s = size
        top = [(px, py - s), (px + s, py - s * .48), (px, py), (px - s, py - s * .48)]
        left = [(px - s, py - s * .48), (px, py), (px, py + s), (px - s, py + s * .52)]
        right = [(px, py), (px + s, py - s * .48), (px + s, py + s * .52), (px, py + s)]
        outline = '#172033' if s >= 4 else None
        draw.polygon(left, fill=self._shade(color, .72), outline=outline)
        draw.polygon(right, fill=self._shade(color, .58), outline=outline)
        draw.polygon(top, fill=self._shade(color, 1.08), outline=outline)

    def _target_map(self):
        token = self._preview_cache_token()
        if self._target_map_cache_token == token:
            return self._target_map_cache
        target_map = {}
        for conv in self._all_records():
            target = self._target_for(conv)
            mapped = bd.strip_ns(conv.source) if target == KEEP else bd.strip_ns(target)
            target_map[conv.source] = mapped
            target_map[bd.strip_ns(conv.source)] = mapped
        self._target_map_cache_token = token
        self._target_map_cache = target_map
        return target_map

    def _map_render_records(self, raw_records):
        target_map = self._target_map()
        records = []
        for rec in raw_records:
            x, y, z, source = rec[:4]
            props = rec[4] if len(rec) > 4 and isinstance(rec[4], dict) else {}
            base = bd.strip_ns(source)
            records.append((x, y, z, target_map.get(source, target_map.get(base, base)), props))
        return records

    def _render_records(self, max_blocks=12000):
        if self.loaded_nbt is None:
            return []
        raw_records = self._source_render_records(max_blocks=max_blocks)
        return self._map_render_records(raw_records)

    def _source_occupied_positions(self):
        if self.loaded_nbt is None:
            return set()
        key = (id(self.loaded_nbt), 'occupied_positions')
        if key not in self._preview_source_cache:
            records = self._source_render_records(max_blocks=10 ** 9)
            self._preview_source_cache[key] = set((int(rec[0]), int(rec[1]), int(rec[2])) for rec in records)
        return self._preview_source_cache[key]

    def _source_render_records(self, max_blocks=12000):
        if self.loaded_nbt is None:
            return []
        requested = max(1, int(max_blocks or 12000))
        key = (id(self.loaded_nbt), requested)
        if key in self._preview_source_cache:
            return self._preview_source_cache[key]
        full_source = requested >= 500000
        source_cap = 10 ** 9 if full_source else max(900, min(220000, requested * 2))
        source_key = (id(self.loaded_nbt), 'all_non_air') if full_source else (
            id(self.loaded_nbt), 'sample_non_air', source_cap)
        if source_key in self._preview_source_cache:
            records = self._preview_source_cache[source_key]
        else:
            records = []
            try:
                regs = self.loaded_nbt.get('Regions', {})
                for reg in regs.values():
                    if not full_source and len(records) >= source_cap:
                        break
                    cap_left = source_cap if full_source else max(1, source_cap - len(records))
                    records.extend(self._region_source_records(reg, cap_left))
            except Exception:
                return []
            if records:
                min_x = min(r[0] for r in records)
                min_y = min(r[1] for r in records)
                min_z = min(r[2] for r in records)
                records = [(r[0] - min_x, r[1] - min_y, r[2] - min_z, r[3],
                            r[4] if len(r) > 4 and isinstance(r[4], dict) else {})
                           for r in records]
            self._preview_source_cache[source_key] = records
        surface_key = (id(self.loaded_nbt), 'surface_records', requested)
        if surface_key in self._preview_source_cache:
            surface = self._preview_source_cache[surface_key]
        else:
            occupied = set((int(rec[0]), int(rec[1]), int(rec[2])) for rec in records)
            surface = []
            neighbor_dirs = ((0, 1, 0), (0, -1, 0), (1, 0, 0), (-1, 0, 0), (0, 0, 1), (0, 0, -1))
            for rec in records:
                x, y, z = rec[:3]
                ix, iy, iz = int(x), int(y), int(z)
                if any((ix + dx, iy + dy, iz + dz) not in occupied for dx, dy, dz in neighbor_dirs):
                    surface.append(rec)
            if full_source:
                self._preview_source_cache[(id(self.loaded_nbt), 'occupied_positions')] = occupied
            self._preview_source_cache[surface_key] = surface
        sampled = surface or records
        if len(sampled) > requested:
            step = len(sampled) / float(requested)
            sampled = [sampled[min(len(sampled) - 1, int((i + 0.5) * step))]
                       for i in range(requested)]
        self._preview_source_cache[key] = sampled
        return sampled

    def _region_source_records(self, reg, max_blocks):
        palette = reg.get('BlockStatePalette', [])
        states = reg.get('BlockStates', [])
        pos = self._vec3(reg.get('Position')) or (0, 0, 0)
        size = self._vec3(reg.get('Size')) or (0, 0, 0)
        sx, sy, sz = abs(int(size[0])), abs(int(size[1])), abs(int(size[2]))
        if len(palette) == 0 or len(states) == 0 or sx <= 0 or sy <= 0 or sz <= 0:
            return []
        total = sx * sy * sz
        bits = max(2, (len(palette) - 1).bit_length())
        mask = (1 << bits) - 1
        longs = [int(v) & 0xffffffffffffffff for v in states]
        dx = 1 if int(size[0]) >= 0 else -1
        dy = 1 if int(size[1]) >= 0 else -1
        dz = 1 if int(size[2]) >= 0 else -1
        out = []
        layer = sx * sz
        cap = max(int(max_blocks or 0), 900)
        if cap >= 10 ** 8:
            index_iter = range(total)
        else:
            scan_budget = min(total, max(6000, cap * 8))
            if scan_budget >= total:
                index_iter = range(total)
            else:
                step = total / float(scan_budget)
                index_iter = (min(total - 1, int((i + 0.5) * step)) for i in range(scan_budget))
        seen = 0
        for idx in index_iter:
            palette_index = self._palette_index_at(longs, bits, mask, idx)
            if palette_index < 0 or palette_index >= len(palette):
                continue
            entry = palette[palette_index]
            source = str(entry.get('Name', 'minecraft:air'))
            base = bd.strip_ns(source)
            if base in ('air', 'cave_air', 'void_air'):
                continue
            props_tag = entry.get('Properties', {})
            props = {}
            try:
                props = {str(k): str(v) for k, v in props_tag.items()}
            except Exception:
                props = {}
            seen += 1
            y = idx // layer
            rem = idx - y * layer
            z = rem // sx
            x = rem - z * sx
            rec = (int(pos[0]) + x * dx, int(pos[1]) + y * dy, int(pos[2]) + z * dz, source, props)
            if len(out) < cap:
                out.append(rec)
            else:
                slot = (((seen ^ (seen >> 16)) * 1103515245 + 12345) & 0x7fffffff) % seen
                if slot < cap:
                    out[slot] = rec
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
