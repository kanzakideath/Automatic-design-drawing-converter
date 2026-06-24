# -*- coding: utf-8 -*-
"""OpenGL preview window for large Minecraft schematic previews.

The Tk/Pillow preview is intentionally kept lightweight.  This module builds a
static exposed-face mesh once, uploads it to the GPU, and then only updates the
camera while the user rotates or moves around the model.
"""

from __future__ import annotations

from array import array
import ctypes
import math
import queue
import sys
import threading
import traceback


_active_thread = None
_active_lock = threading.Lock()
_embedded_handle = None
_embedded_lock = threading.Lock()


FACE_DEFS = (
    ((0, 1, 0), ((0, 1, 1), (1, 1, 1), (1, 1, 0), (0, 1, 0)), 1.18),
    ((0, -1, 0), ((0, 0, 0), (1, 0, 0), (1, 0, 1), (0, 0, 1)), 0.48),
    ((0, 0, 1), ((0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1)), 0.86),
    ((1, 0, 0), ((1, 0, 1), (1, 0, 0), (1, 1, 0), (1, 1, 1)), 0.76),
    ((0, 0, -1), ((1, 0, 0), (0, 0, 0), (0, 1, 0), (1, 1, 0)), 0.68),
    ((-1, 0, 0), ((0, 0, 0), (0, 0, 1), (0, 1, 1), (0, 1, 0)), 0.60),
)

TRI_ORDER = (0, 1, 2, 0, 2, 3)
FACE_TILE_INDEX = {
    (0, 1, 0): 0,
    (0, -1, 0): 1,
    (0, 0, -1): 2,
    (0, 0, 1): 3,
    (1, 0, 0): 4,
    (-1, 0, 0): 5,
}

SHAPE_BOUNDS = {
    0: (0.0, 0.0, 0.0, 1.0, 1.0, 1.0),       # full cube
    1: (0.0, 0.0, 0.0, 1.0, 0.5, 1.0),       # slab-like
    2: (0.0, 0.02, 0.0, 1.0, 0.08, 1.0),    # rail/carpet/plate-like
    3: (0.32, 0.0, 0.32, 0.36, 1.0, 0.36),  # fence/wall post approximation
    4: (0.45, 0.0, 0.0, 0.10, 1.0, 1.0),    # pane/bars approximation
}

DIR_BITS = {'north': 1, 'east': 2, 'south': 4, 'west': 8}


def open_preview_async(payload):
    """Open a GPU preview window on its own pyglet event-loop thread."""
    global _active_thread
    close_embedded_preview(wait=True)
    status_q = queue.Queue(maxsize=1)
    with _active_lock:
        if _active_thread is not None and _active_thread.is_alive():
            raise RuntimeError('全画面プレビューはすでに開いています。先に閉じてください。')
        _active_thread = threading.Thread(target=_run_preview_safe, args=(payload, status_q), daemon=True)
        _active_thread.start()
    try:
        status, detail = status_q.get(timeout=float(payload.get('startup_timeout', 3.0)))
    except queue.Empty:
        return
    if status == 'error':
        raise RuntimeError(detail)


class EmbeddedPreviewHandle:
    """Thread-safe command handle for the Tk-embedded OpenGL preview."""

    def __init__(self, command_q, thread):
        self._command_q = command_q
        self._thread = thread
        self._closed = False

    def _put(self, *cmd):
        if self._closed:
            return
        try:
            self._command_q.put_nowait(cmd)
        except Exception:
            pass

    def resize(self, width, height):
        self._put('resize', int(width), int(height))

    def set_view(self, yaw, pitch, zoom, mode='orbit'):
        self._put('set_view', float(yaw), float(pitch), float(zoom), str(mode or 'orbit'))

    def raise_window(self):
        self._put('raise')

    def close(self, wait=False):
        if self._closed:
            if wait and self._thread is not threading.current_thread():
                try:
                    self._thread.join(timeout=1.2)
                except Exception:
                    pass
            return
        self._closed = True
        try:
            self._command_q.put_nowait(('close',))
        except Exception:
            pass
        if wait and self._thread is not threading.current_thread():
            try:
                self._thread.join(timeout=1.2)
            except Exception:
                pass

    @property
    def alive(self):
        try:
            return self._thread.is_alive()
        except Exception:
            return False


def close_embedded_preview(wait=False):
    global _embedded_handle
    with _embedded_lock:
        handle = _embedded_handle
        _embedded_handle = None
    if handle is not None:
        handle.close(wait=wait)


def open_embedded_preview_async(payload, parent_hwnd, width, height):
    """Open a borderless OpenGL preview as a child of a Tk widget HWND."""
    global _embedded_handle
    parent_hwnd = int(parent_hwnd or 0)
    if not parent_hwnd:
        raise RuntimeError('embedded preview parent window is not ready')
    if _active_thread is not None and _active_thread.is_alive():
        raise RuntimeError('fullscreen GPU preview is already open')

    command_q = queue.Queue()
    status_q = queue.Queue(maxsize=1)
    embedded_payload = dict(payload)
    embedded_payload.update({
        'embedded': True,
        'parent_hwnd': parent_hwnd,
        'width': max(240, int(width)),
        'height': max(160, int(height)),
        'startup_timeout': 3.0,
        'command_queue': command_q,
        'show_overlay': False,
        'force_continuous_redraw': False,
        'target_fps': 90,
        'uncapped_fps': False,
        'async_mesh': True,
    })
    thread = threading.Thread(target=_run_embedded_preview_safe,
                              args=(embedded_payload, status_q),
                              daemon=True)
    handle = EmbeddedPreviewHandle(command_q, thread)
    with _embedded_lock:
        old = _embedded_handle
        _embedded_handle = handle
    if old is not None:
        old.close(wait=True)
    thread.start()
    try:
        status, detail = status_q.get(timeout=embedded_payload['startup_timeout'])
    except queue.Empty:
        return handle
    if status == 'error':
        with _embedded_lock:
            if _embedded_handle is handle:
                _embedded_handle = None
        raise RuntimeError(detail)
    return handle


def _run_preview_safe(payload, status_q=None):
    try:
        _run_preview(payload, status_q)
    except Exception:
        if status_q is not None:
            try:
                status_q.put_nowait(('error', traceback.format_exc()))
            except queue.Full:
                pass
        traceback.print_exc()
    finally:
        global _active_thread
        with _active_lock:
            if _active_thread is threading.current_thread():
                _active_thread = None


def _run_embedded_preview_safe(payload, status_q=None):
    try:
        _run_preview(payload, status_q)
    except Exception:
        if status_q is not None:
            try:
                status_q.put_nowait(('error', traceback.format_exc()))
            except queue.Full:
                pass
        traceback.print_exc()
    finally:
        global _embedded_handle
        with _embedded_lock:
            handle = _embedded_handle
            if handle is not None and handle._thread is threading.current_thread():
                _embedded_handle = None


def _run_preview(payload, status_q=None):
    import pyglet

    pyglet.options['debug_gl'] = False
    pyglet.options['vsync'] = False
    from pyglet import gl
    if sys.platform.startswith('win'):
        try:
            pyglet.app.platform_event_loop._event_thread = ctypes.windll.kernel32.GetCurrentThreadId()
        except Exception:
            pass

    try:
        config = gl.Config(double_buffer=True, depth_size=24, major_version=3, minor_version=3)
        window = GpuPreviewWindow(payload, config=config)
    except Exception:
        window = GpuPreviewWindow(payload)
    if status_q is not None:
        try:
            status_q.put_nowait(('ok', ''))
        except queue.Full:
            pass
    if payload.get('uncapped_fps') or not payload.get('target_fps'):
        pyglet.clock.schedule(window.update)
    else:
        target_fps = max(60.0, min(360.0, float(payload.get('target_fps', 240.0) or 240.0)))
        pyglet.clock.schedule_interval(window.update, 1.0 / target_fps)
    pyglet.app.run(interval=0)


def _shade(color, factor):
    return (
        max(0, min(255, int(color[0] * factor))),
        max(0, min(255, int(color[1] * factor))),
        max(0, min(255, int(color[2] * factor))),
    )


def _half_depth_box(facing, y0, y1):
    if facing == 0:      # north
        return (0.0, y0, 0.0, 1.0, y1, 0.5)
    if facing == 2:      # south
        return (0.0, y0, 0.5, 1.0, y1, 1.0)
    if facing == 1:      # east
        return (0.5, y0, 0.0, 1.0, y1, 1.0)
    return (0.0, y0, 0.0, 0.5, y1, 1.0)


def _wall_button_box(facing):
    if facing == 0:
        return (0.35, 0.35, 0.00, 0.65, 0.65, 0.12)
    if facing == 2:
        return (0.35, 0.35, 0.88, 0.65, 0.65, 1.00)
    if facing == 1:
        return (0.88, 0.35, 0.35, 1.00, 0.65, 0.65)
    return (0.00, 0.35, 0.35, 0.12, 0.65, 0.65)


def _connected_boxes(mask, pane=False):
    if pane:
        thickness = 0.10
        lo, hi = 0.5 - thickness / 2.0, 0.5 + thickness / 2.0
        if not mask:
            return [(lo, 0.0, 0.0, hi, 1.0, 1.0), (0.0, 0.0, lo, 1.0, 1.0, hi)]
        boxes = [(lo, 0.0, lo, hi, 1.0, hi)]
        if mask & DIR_BITS['north']:
            boxes.append((lo, 0.0, 0.0, hi, 1.0, 0.5))
        if mask & DIR_BITS['south']:
            boxes.append((lo, 0.0, 0.5, hi, 1.0, 1.0))
        if mask & DIR_BITS['east']:
            boxes.append((0.5, 0.0, lo, 1.0, 1.0, hi))
        if mask & DIR_BITS['west']:
            boxes.append((0.0, 0.0, lo, 0.5, 1.0, hi))
        return boxes

    boxes = [(0.34, 0.0, 0.34, 0.66, 1.0, 0.66)]
    if mask & DIR_BITS['north']:
        boxes.append((0.42, 0.30, 0.0, 0.58, 0.82, 0.5))
    if mask & DIR_BITS['south']:
        boxes.append((0.42, 0.30, 0.5, 0.58, 0.82, 1.0))
    if mask & DIR_BITS['east']:
        boxes.append((0.5, 0.30, 0.42, 1.0, 0.82, 0.58))
    if mask & DIR_BITS['west']:
        boxes.append((0.0, 0.30, 0.42, 0.5, 0.82, 0.58))
    return boxes


def _trapdoor_boxes(variant):
    facing = variant & 3
    top = bool(variant & 4)
    opened = bool(variant & 8)
    t = 0.1875
    if not opened:
        return [(0.0, 1.0 - t, 0.0, 1.0, 1.0, 1.0)] if top else [(0.0, 0.0, 0.0, 1.0, t, 1.0)]
    if facing == 0:
        return [(0.0, 0.0, 0.0, 1.0, 1.0, t)]
    if facing == 2:
        return [(0.0, 0.0, 1.0 - t, 1.0, 1.0, 1.0)]
    if facing == 1:
        return [(1.0 - t, 0.0, 0.0, 1.0, 1.0, 1.0)]
    return [(0.0, 0.0, 0.0, t, 1.0, 1.0)]


def _fence_gate_boxes(variant):
    facing = variant & 3
    opened = bool(variant & 4)
    in_wall = bool(variant & 8)
    y_shift = -0.125 if in_wall else 0.0
    y0 = max(0.0, 0.0 + y_shift)
    y1 = max(0.72, 1.0 + y_shift)
    post = 0.1875
    rail_lo = max(0.18, 0.3125 + y_shift)
    rail_hi = max(0.38, 0.8125 + y_shift)
    thick0, thick1 = 0.375, 0.625
    rail0, rail1 = 0.4375, 0.5625

    if facing in (0, 2):  # north/south: closed gate spans west-east.
        boxes = [
            (0.0, y0, thick0, post, y1, thick1),
            (1.0 - post, y0, thick0, 1.0, y1, thick1),
        ]
        if opened:
            boxes.extend([
                (post, rail_lo, 0.0, post + 0.125, rail_hi, 0.50),
                (1.0 - post - 0.125, rail_lo, 0.50, 1.0 - post, rail_hi, 1.0),
            ])
        else:
            boxes.extend([
                (post, rail_lo, rail0, 1.0 - post, rail_lo + 0.1875, rail1),
                (post, rail_hi - 0.1875, rail0, 1.0 - post, rail_hi, rail1),
            ])
        return boxes

    boxes = [
        (thick0, y0, 0.0, thick1, y1, post),
        (thick0, y0, 1.0 - post, thick1, y1, 1.0),
    ]
    if opened:
        boxes.extend([
            (0.0, rail_lo, post, 0.50, rail_hi, post + 0.125),
            (0.50, rail_lo, 1.0 - post - 0.125, 1.0, rail_hi, 1.0 - post),
        ])
    else:
        boxes.extend([
            (rail0, rail_lo, post, rail1, rail_lo + 0.1875, 1.0 - post),
            (rail0, rail_hi - 0.1875, post, rail1, rail_hi, 1.0 - post),
        ])
    return boxes


def _door_boxes(variant):
    facing = variant & 3
    opened = bool(variant & 4)
    hinge_right = bool(variant & 8)
    t = 0.1875
    if not opened:
        if facing == 0:
            return [(0.0, 0.0, 0.0, 1.0, 1.0, t)]
        if facing == 2:
            return [(0.0, 0.0, 1.0 - t, 1.0, 1.0, 1.0)]
        if facing == 1:
            return [(1.0 - t, 0.0, 0.0, 1.0, 1.0, 1.0)]
        return [(0.0, 0.0, 0.0, t, 1.0, 1.0)]
    if facing in (0, 2):
        if hinge_right:
            return [(1.0 - t, 0.0, 0.0, 1.0, 1.0, 1.0)]
        return [(0.0, 0.0, 0.0, t, 1.0, 1.0)]
    if hinge_right:
        return [(0.0, 0.0, 1.0 - t, 1.0, 1.0, 1.0)]
    return [(0.0, 0.0, 0.0, 1.0, 1.0, t)]


def _sign_boxes(variant):
    facing = variant & 3
    wall = bool(variant & 4)
    if wall:
        if facing == 0:
            return [(0.125, 0.25, 0.00, 0.875, 0.78, 0.08)]
        if facing == 2:
            return [(0.125, 0.25, 0.92, 0.875, 0.78, 1.00)]
        if facing == 1:
            return [(0.92, 0.25, 0.125, 1.00, 0.78, 0.875)]
        return [(0.00, 0.25, 0.125, 0.08, 0.78, 0.875)]
    return [
        (0.125, 0.42, 0.44, 0.875, 0.86, 0.56),
        (0.45, 0.00, 0.47, 0.55, 0.42, 0.53),
    ]


def _shape_boxes(shape_id, variant):
    if shape_id == 0:
        return [(0.0, 0.0, 0.0, 1.0, 1.0, 1.0, True)]
    if shape_id == 1:
        return [(0.0, 0.0, 0.0, 1.0, 0.5, 1.0, False)]
    if shape_id == 5:
        return [(0.0, 0.5, 0.0, 1.0, 1.0, 1.0, False)]
    if shape_id == 6:
        facing = variant & 3
        if variant & 4:
            boxes = [(0.0, 0.5, 0.0, 1.0, 1.0, 1.0), _half_depth_box(facing, 0.0, 0.5)]
        else:
            boxes = [(0.0, 0.0, 0.0, 1.0, 0.5, 1.0), _half_depth_box(facing, 0.5, 1.0)]
        return [box + (False,) for box in boxes]
    if shape_id == 7:
        return [box + (False,) for box in _trapdoor_boxes(variant)]
    if shape_id == 8:
        facing = variant & 3
        face = (variant >> 2) & 3
        if face == 0:
            return [(0.32, 0.0, 0.32, 0.68, 0.12, 0.68, False)]
        if face == 2:
            return [(0.32, 0.88, 0.32, 0.68, 1.0, 0.68, False)]
        return [_wall_button_box(facing) + (False,)]
    if shape_id == 9:
        return [box + (False,) for box in _connected_boxes(variant, pane=False)]
    if shape_id == 10:
        return [box + (False,) for box in _connected_boxes(variant, pane=True)]
    if shape_id == 11:
        return [box + (False,) for box in _fence_gate_boxes(variant)]
    if shape_id == 12:
        return [box + (False,) for box in _door_boxes(variant)]
    if shape_id == 13:
        return [box + (False,) for box in _sign_boxes(variant)]
    if shape_id == 14:
        return [(0.0, 0.0, 0.0, 1.0, 0.36, 1.0, False)]
    bounds = SHAPE_BOUNDS.get(shape_id, SHAPE_BOUNDS[0])
    ox, oy, oz, sx, sy, sz = bounds
    return [(ox, oy, oz, ox + sx, oy + sy, oz + sz, False)]


def _count_exposed_faces(blocks, occupied):
    total = 0
    for block in blocks:
        x, y, z = block[:3]
        if len(block) >= 14:
            shape_id = int(block[12])
            variant = int(block[13])
        else:
            shape_id = int(block[8]) if len(block) > 8 else 0
            variant = int(block[9]) if len(block) > 9 else 0
        ix, iy, iz = int(x), int(y), int(z)
        for _x0, _y0, _z0, _x1, _y1, _z1, occluding in _shape_boxes(shape_id, variant):
            for normal, _corners, _light in FACE_DEFS:
                if not occluding or (ix + normal[0], iy + normal[1], iz + normal[2]) not in occupied:
                    total += 1
    return total


def build_mesh(payload):
    blocks = payload.get('blocks') or []
    occupied = payload.get('occupied') or set()
    atlas_uvs = payload.get('atlas_uvs') or [(0.0, 0.0, 1.0, 1.0)]
    max_faces = int(payload.get('max_faces') or 260000)
    estimated_faces = max(1, len(blocks) * 3)
    stride = max(1, int(math.ceil(estimated_faces / float(max_faces)))) if max_faces > 0 else 1

    positions = array('f')
    colors = array('B')
    tex_coords = array('f')
    indices = array('I')
    face_index = 0
    face_total = 0
    emitted_faces = 0
    shape_boxes = _shape_boxes
    face_defs = FACE_DEFS
    face_tile_index = FACE_TILE_INDEX
    atlas_len = len(atlas_uvs)
    occupied_has = occupied.__contains__
    positions_extend = positions.extend
    colors_extend = colors.extend
    tex_extend = tex_coords.extend
    indices_extend = indices.extend

    for block in blocks:
        x, y, z, _r, _g, _b = block[:6]
        if len(block) >= 14:
            face_tiles = tuple(int(v) for v in block[6:12])
            shape_id = int(block[12])
            variant = int(block[13])
        else:
            top_tile = int(block[6]) if len(block) > 6 else 0
            side_tile = int(block[7]) if len(block) > 7 else top_tile
            face_tiles = (top_tile, side_tile, side_tile, side_tile, side_tile, side_tile)
            shape_id = int(block[8]) if len(block) > 8 else 0
            variant = int(block[9]) if len(block) > 9 else 0
        ix, iy, iz = int(x), int(y), int(z)
        for x0, y0, z0, x1, y1, z1, occluding in shape_boxes(shape_id, variant):
            sx, sy, sz = x1 - x0, y1 - y0, z1 - z0
            for normal, corners, light in face_defs:
                if occluding and occupied_has((ix + normal[0], iy + normal[1], iz + normal[2])):
                    continue
                face_total += 1
                if face_index % stride:
                    face_index += 1
                    continue
                if max_faces > 0 and emitted_faces >= max_faces:
                    face_index += 1
                    continue
                light_value = max(0, min(255, int(255 * light)))
                pts = [(ix + x0 + cx * sx, iy + y0 + cy * sy, iz + z0 + cz * sz) for cx, cy, cz in corners]
                tile_index = face_tiles[face_tile_index.get(normal, 3)]
                if tile_index < 0 or tile_index >= atlas_len:
                    tile_index = 0
                u0, v0, u1, v1 = atlas_uvs[tile_index]
                quad_uvs = ((u0, v0), (u1, v0), (u1, v1), (u0, v1))
                base_vertex = len(positions) // 3
                for corner_index, (px, py, pz) in enumerate(pts):
                    positions_extend((float(px), float(py), float(pz)))
                    colors_extend((light_value, light_value, light_value, 255))
                    tex_extend(quad_uvs[corner_index])
                indices_extend((base_vertex, base_vertex + 1, base_vertex + 2,
                                base_vertex, base_vertex + 2, base_vertex + 3))
                emitted_faces += 1
                face_index += 1

    return positions, colors, tex_coords, indices, face_total, emitted_faces, stride


def build_ground(bounds):
    cx = float(bounds.get('cx', 0.0))
    cz = float(bounds.get('cz', 0.0))
    y = float(bounds.get('min_y', 0.0)) - 0.04
    span = max(float(bounds.get('span_x', 32.0)), float(bounds.get('span_z', 32.0)), 32.0)
    extent = max(96.0, span * 2.2)
    x0, x1 = cx - extent, cx + extent
    z0, z1 = cz - extent, cz + extent

    ground_positions = array('f', (
        x0, y, z0, x0, y, z1, x1, y, z1,
        x0, y, z0, x1, y, z1, x1, y, z0,
    ))
    ground_colors = array('B')
    for _ in range(6):
        ground_colors.extend((92, 188, 64, 255))

    grid_positions = array('f')
    grid_colors = array('B')
    step = max(4, int(extent / 48.0))
    x = math.floor(x0 / step) * step
    while x <= x1:
        grid_positions.extend((float(x), y + 0.01, z0, float(x), y + 0.01, z1))
        grid_colors.extend((82, 216, 92, 255, 82, 216, 92, 255))
        x += step
    z = math.floor(z0 / step) * step
    while z <= z1:
        grid_positions.extend((x0, y + 0.01, float(z), x1, y + 0.01, float(z)))
        grid_colors.extend((82, 216, 92, 255, 82, 216, 92, 255))
        z += step
    ground_tex = array('f', (0.0, 0.0, 1.0, 0.0, 1.0, 1.0, 0.0, 0.0, 1.0, 1.0, 0.0, 1.0))
    grid_tex = array('f', (0.0, 0.0) * (len(grid_positions) // 3))
    return ground_positions, ground_colors, ground_tex, grid_positions, grid_colors, grid_tex


class GpuPreviewWindow:
    def __init__(self, payload, config=None):
        import pyglet
        from pyglet import gl
        from pyglet.graphics.shader import Shader, ShaderProgram

        self.pyglet = pyglet
        self.gl = gl
        self.payload = payload
        self.bounds = payload.get('bounds') or {}
        self.blocks = payload.get('blocks') or []
        self.vertex_count = 0
        self.index_count = 0
        self.face_total = 0
        self.face_emitted = 0
        self.stride = 1
        self.keys = set()
        self.mouse_down = False
        self.default_mode = str(payload.get('initial_mode') or 'orbit')
        self.default_yaw = float(payload.get('initial_yaw', -42.0))
        self.default_pitch = float(payload.get('initial_pitch', 26.0))
        self.default_zoom = float(payload.get('initial_zoom', 1.0))
        self.mode = self.default_mode
        self.yaw = self.default_yaw
        self.pitch = self.default_pitch
        self.zoom = self.default_zoom
        self.fps = 0.0
        self._fps_accum = 0.0
        self._fps_frames = 0
        self._fps_time = 0.0
        self._closed = False
        self._overlay_size = (0, 0)
        self._overlay_dirty = True
        self.show_overlay = bool(payload.get('show_overlay', False))
        self.force_continuous_redraw = bool(payload.get('force_continuous_redraw', True))
        self._caption_title = str(payload.get('title') or '全画面プレビュー')

        self.embedded = bool(payload.get('embedded', False))
        self.command_queue = payload.get('command_queue')
        self._parent_hwnd = int(payload.get('parent_hwnd') or 0)
        self._embedded_hwnd = 0
        self._mesh_result_q = queue.Queue(maxsize=1)
        self._mesh_building = False
        self._mesh_error = None
        self._redraw_frames = 4

        width = int(payload.get('width') or 1280)
        height = int(payload.get('height') or 760)
        kwargs = {'width': width, 'height': height, 'caption': 'Minecraft 全画面プレビュー', 'resizable': True,
                  'vsync': False}
        if self.embedded:
            kwargs['resizable'] = False
            kwargs['style'] = 'borderless'
        if config is not None:
            kwargs['config'] = config
        self.window = pyglet.window.Window(**kwargs)
        if self.embedded:
            self._embed_into_parent(width, height)
        else:
            try:
                screen = self.window.display.get_default_screen()
                self.window.set_location(
                    int(screen.x + (screen.width - width) / 2),
                    int(screen.y + (screen.height - height) / 2),
                )
            except Exception:
                pass
        try:
            self.window.set_vsync(False)
        except Exception:
            pass
        self.window.push_handlers(self)
        if not self.embedded:
            self.window.set_minimum_size(860, 520)

        self.program = ShaderProgram(Shader(VERTEX_SHADER, 'vertex'), Shader(FRAGMENT_SHADER, 'fragment'))
        self.texture = self._create_atlas_texture()
        self._build_vertex_lists()
        self._reset_camera()
        self.label = pyglet.text.Label('', font_name='Yu Gothic UI', font_size=11,
                                       x=12, y=self.window.height - 12, anchor_x='left',
                                       anchor_y='top', color=(255, 255, 255, 255),
                                       multiline=True, width=max(240, self.window.width - 24))
        gl.glEnable(gl.GL_DEPTH_TEST)
        gl.glEnable(gl.GL_BLEND)
        gl.glBlendFunc(gl.GL_SRC_ALPHA, gl.GL_ONE_MINUS_SRC_ALPHA)
        gl.glEnable(gl.GL_CULL_FACE)
        gl.glCullFace(gl.GL_BACK)
        gl.glFrontFace(gl.GL_CCW)
        try:
            gl.glDisable(gl.GL_MULTISAMPLE)
        except Exception:
            pass
        try:
            gl.glDisable(gl.GL_DITHER)
        except Exception:
            pass
        self._update_overlay_text()
        self._request_redraw(4)

    def _native_hwnd(self):
        hwnd = getattr(self.window, '_hwnd', 0) or getattr(self.window, '_view_hwnd', 0)
        return int(getattr(hwnd, 'value', hwnd) or 0)

    def _embed_into_parent(self, width, height):
        if not sys.platform.startswith('win') or not self._parent_hwnd:
            return
        hwnd = self._native_hwnd()
        if not hwnd:
            return
        self._embedded_hwnd = hwnd
        user32 = ctypes.windll.user32
        GWL_STYLE = -16
        GWL_EXSTYLE = -20
        WS_CHILD = 0x40000000
        WS_VISIBLE = 0x10000000
        WS_CLIPSIBLINGS = 0x04000000
        WS_CLIPCHILDREN = 0x02000000
        WS_POPUP = 0x80000000
        WS_CAPTION = 0x00C00000
        WS_THICKFRAME = 0x00040000
        WS_MINIMIZEBOX = 0x00020000
        WS_MAXIMIZEBOX = 0x00010000
        WS_SYSMENU = 0x00080000
        WS_EX_APPWINDOW = 0x00040000
        WS_EX_TOOLWINDOW = 0x00000080

        user32.GetWindowLongW.restype = ctypes.c_long
        user32.SetWindowLongW.restype = ctypes.c_long
        style = int(user32.GetWindowLongW(hwnd, GWL_STYLE)) & 0xffffffff
        style &= ~(WS_POPUP | WS_CAPTION | WS_THICKFRAME | WS_MINIMIZEBOX | WS_MAXIMIZEBOX | WS_SYSMENU)
        style |= WS_CHILD | WS_VISIBLE | WS_CLIPSIBLINGS | WS_CLIPCHILDREN
        user32.SetWindowLongW(hwnd, GWL_STYLE, ctypes.c_long(style).value)

        ex_style = int(user32.GetWindowLongW(hwnd, GWL_EXSTYLE)) & 0xffffffff
        ex_style &= ~WS_EX_APPWINDOW
        ex_style |= WS_EX_TOOLWINDOW
        user32.SetWindowLongW(hwnd, GWL_EXSTYLE, ctypes.c_long(ex_style).value)

        user32.SetParent(hwnd, self._parent_hwnd)
        self._set_child_window_bounds(width, height, frame_changed=True)

    def _set_child_window_bounds(self, width, height, frame_changed=False, to_front=True):
        if not self.embedded or not self._embedded_hwnd or not sys.platform.startswith('win'):
            return
        user32 = ctypes.windll.user32
        SWP_NOZORDER = 0x0004
        SWP_SHOWWINDOW = 0x0040
        SWP_FRAMECHANGED = 0x0020
        SW_SHOW = 5
        flags = SWP_SHOWWINDOW
        if not to_front:
            flags |= SWP_NOZORDER
        if frame_changed:
            flags |= SWP_FRAMECHANGED
        try:
            user32.ShowWindow(self._embedded_hwnd, SW_SHOW)
        except Exception:
            pass
        user32.SetWindowPos(self._embedded_hwnd, 0, 0, 0, max(1, int(width)), max(1, int(height)), flags)
        try:
            user32.UpdateWindow(self._embedded_hwnd)
        except Exception:
            pass

    def _drain_commands(self):
        if self.command_queue is None:
            return
        changed = False
        while True:
            try:
                cmd = self.command_queue.get_nowait()
            except queue.Empty:
                break
            if not cmd:
                continue
            name = cmd[0]
            if name == 'close':
                self.close()
                return
            if name == 'raise':
                self._set_child_window_bounds(self.window.width, self.window.height, to_front=True)
                changed = True
                continue
            if name == 'resize' and len(cmd) >= 3:
                width = max(240, int(cmd[1]))
                height = max(160, int(cmd[2]))
                try:
                    self.window.set_size(width, height)
                except Exception:
                    pass
                self._set_child_window_bounds(width, height, to_front=True)
                self._overlay_dirty = True
                changed = True
            elif name == 'set_view' and len(cmd) >= 5:
                self.yaw = float(cmd[1])
                self.pitch = max(-12.0, min(78.0, float(cmd[2])))
                self.zoom = max(0.18, min(8.0, float(cmd[3])))
                self.mode = str(cmd[4] or 'orbit')
                if self.mode == 'orbit':
                    self._reset_camera()
                self._overlay_dirty = True
                changed = True
        if changed:
            self._request_redraw(4)

    def _create_atlas_texture(self):
        atlas = self.payload.get('atlas') or {}
        width = int(atlas.get('width') or 1)
        height = int(atlas.get('height') or 1)
        data = atlas.get('rgba') or b'\xff\xff\xff\xff'
        image = self.pyglet.image.ImageData(width, height, 'RGBA', data, pitch=-width * 4)
        texture = image.get_texture()
        gl = self.gl
        gl.glBindTexture(texture.target, texture.id)
        gl.glTexParameteri(texture.target, gl.GL_TEXTURE_MIN_FILTER, gl.GL_NEAREST)
        gl.glTexParameteri(texture.target, gl.GL_TEXTURE_MAG_FILTER, gl.GL_NEAREST)
        gl.glTexParameteri(texture.target, gl.GL_TEXTURE_WRAP_S, gl.GL_CLAMP_TO_EDGE)
        gl.glTexParameteri(texture.target, gl.GL_TEXTURE_WRAP_T, gl.GL_CLAMP_TO_EDGE)
        return texture

    def _build_vertex_lists(self):
        from pyglet import gl

        self.mesh_list = None
        prebuilt = self.payload.get('prebuilt_mesh')
        if prebuilt and len(prebuilt) == 7:
            self._upload_mesh(prebuilt)
        elif self.payload.get('async_mesh'):
            self._start_mesh_worker()
        else:
            self._upload_mesh(build_mesh(self.payload))
        self._build_ground_lists()

    def _upload_mesh(self, mesh):
        from pyglet import gl

        positions, colors, tex_coords, indices, face_total, emitted_faces, stride = mesh
        self.face_total = face_total
        self.face_emitted = emitted_faces
        self.stride = stride
        self.vertex_count = len(positions) // 3
        self.index_count = len(indices)
        if self.mesh_list is not None:
            try:
                self.mesh_list.delete()
            except Exception:
                pass
        self.mesh_list = self.program.vertex_list_indexed(
            self.vertex_count, gl.GL_TRIANGLES,
            indices,
            position=('f', positions),
            colors=('Bn', colors),
            tex_coords=('f', tex_coords),
        ) if self.vertex_count and self.index_count else None
        self._mesh_building = False
        self._mesh_error = None
        self._overlay_dirty = True
        self._request_redraw(8)

    def _start_mesh_worker(self):
        if self._mesh_building:
            return
        self._mesh_building = True

        def worker():
            try:
                mesh = build_mesh(self.payload)
                self._mesh_result_q.put_nowait(('ok', mesh))
            except Exception:
                try:
                    self._mesh_result_q.put_nowait(('error', traceback.format_exc()))
                except Exception:
                    pass

        threading.Thread(target=worker, daemon=True).start()

    def _consume_mesh_result(self):
        try:
            status, detail = self._mesh_result_q.get_nowait()
        except queue.Empty:
            return False
        if status == 'ok':
            self._upload_mesh(detail)
            return True
        self._mesh_building = False
        self._mesh_error = detail
        self._overlay_dirty = True
        self._request_redraw(4)
        return True

    def _build_ground_lists(self):
        gl = self.gl
        gp, gc, gt, gridp, gridc, gridt = build_ground(self.bounds)
        self.ground_list = self.program.vertex_list(
            len(gp) // 3, gl.GL_TRIANGLES,
            position=('f', gp),
            colors=('Bn', gc),
            tex_coords=('f', gt),
        )
        self.grid_list = self.program.vertex_list(
            len(gridp) // 3, gl.GL_LINES,
            position=('f', gridp),
            colors=('Bn', gridc),
            tex_coords=('f', gridt),
        )

    def _reset_camera(self):
        bounds = self.bounds
        cx = float(bounds.get('cx', 0.0))
        cy = float(bounds.get('cy', 0.0))
        cz = float(bounds.get('cz', 0.0))
        sx = float(bounds.get('span_x', 32.0))
        sy = float(bounds.get('span_y', 16.0))
        sz = float(bounds.get('span_z', 32.0))
        span = max(sx, sy, sz, 8.0)
        self.target = (cx, cy, cz)
        self.distance = max(18.0, span * 2.05)
        self.walk_pos = [cx, float(bounds.get('min_y', 0.0)) + max(2.0, min(14.0, sy * 0.24)),
                         cz - max(8.0, span * 0.70)]

    def on_draw(self):
        from pyglet.math import Mat4

        gl = self.gl
        self.window.switch_to()
        gl.glViewport(0, 0, self.window.width, self.window.height)
        gl.glClearColor(0.46, 0.73, 1.0, 1.0)
        gl.glClear(gl.GL_COLOR_BUFFER_BIT | gl.GL_DEPTH_BUFFER_BIT)
        gl.glEnable(gl.GL_DEPTH_TEST)
        gl.glEnable(gl.GL_BLEND)
        self.program.use()
        self.program['mvp'] = self._mvp_matrix()
        gl.glActiveTexture(gl.GL_TEXTURE0)
        gl.glBindTexture(self.texture.target, self.texture.id)
        self.program['atlas_texture'] = 0
        self.program['use_texture'] = 0
        self.ground_list.draw(gl.GL_TRIANGLES)
        self.grid_list.draw(gl.GL_LINES)
        if self.mesh_list is not None:
            self.program['use_texture'] = 1
            self.mesh_list.draw(gl.GL_TRIANGLES)
        gl.glDisable(gl.GL_DEPTH_TEST)
        if self.show_overlay:
            self._draw_overlay()

    def _mvp_matrix(self):
        from pyglet.math import Mat4, Vec3

        aspect = max(0.1, self.window.width / float(max(1, self.window.height)))
        projection = Mat4.perspective_projection(aspect, 0.08, 10000.0, 62.0)
        eye, target = self._camera_points()
        view = Mat4.look_at(Vec3(*eye), Vec3(*target), Vec3(0.0, 1.0, 0.0))
        return projection @ view

    def _camera_points(self):
        yaw = math.radians(self.yaw)
        pitch = math.radians(max(-82.0, min(82.0, self.pitch)))
        if self.mode == 'walk':
            forward = (math.sin(yaw) * math.cos(pitch), math.sin(pitch), math.cos(yaw) * math.cos(pitch))
            eye = tuple(self.walk_pos)
            target = (eye[0] + forward[0], eye[1] + forward[1], eye[2] + forward[2])
            return eye, target
        dist = self.distance / max(0.20, self.zoom)
        tx, ty, tz = self.target
        eye = (
            tx + math.sin(yaw) * math.cos(pitch) * dist,
            ty + math.sin(pitch) * dist + max(2.0, float(self.bounds.get('span_y', 8.0)) * 0.16),
            tz + math.cos(yaw) * math.cos(pitch) * dist,
        )
        return eye, self.target

    def _camera_basis(self):
        eye, target = self._camera_points()
        forward = self._norm((target[0] - eye[0], target[1] - eye[1], target[2] - eye[2]))
        right = self._norm(self._cross(forward, (0.0, 1.0, 0.0)))
        up = self._cross(right, forward)
        return right, up

    def _pan_orbit(self, dx, dy):
        right, up = self._camera_basis()
        scale = (self.distance / max(0.2, self.zoom)) / float(max(320, self.window.width)) * 0.95
        self.target = (
            self.target[0] - right[0] * dx * scale + up[0] * dy * scale,
            self.target[1] - right[1] * dx * scale + up[1] * dy * scale,
            self.target[2] - right[2] * dx * scale + up[2] * dy * scale,
        )

    def _norm(self, vec):
        length = math.sqrt(max(1e-9, vec[0] * vec[0] + vec[1] * vec[1] + vec[2] * vec[2]))
        return vec[0] / length, vec[1] / length, vec[2] / length

    def _cross(self, a, b):
        return (
            a[1] * b[2] - a[2] * b[1],
            a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0],
        )

    def _request_redraw(self, frames=2):
        self._redraw_frames = max(self._redraw_frames, int(frames or 1))
        try:
            self.window.invalid = True
        except Exception:
            pass

    def update(self, dt):
        self._drain_commands()
        if self._closed:
            return
        self._consume_mesh_result()
        self._fps_frames += 1
        self._fps_time += dt
        if self._fps_time >= 0.35:
            self.fps = self._fps_frames / self._fps_time
            self._fps_frames = 0
            self._fps_time = 0.0
            self._overlay_dirty = True
            self._update_overlay_text()
        is_moving = self.mode == 'walk' and bool(self.keys)
        if self.force_continuous_redraw or self.mouse_down or is_moving:
            try:
                self.window.invalid = True
            except Exception:
                pass
        elif self._redraw_frames > 0:
            try:
                self.window.invalid = True
            except Exception:
                pass
            self._redraw_frames -= 1
        if self.mode != 'walk':
            return
        span = max(float(self.bounds.get('span_x', 32.0)), float(self.bounds.get('span_z', 32.0)))
        speed = max(3.5, min(24.0, span * 0.12))
        move = speed * dt * (2.0 if self._key('LSHIFT') or self._key('RSHIFT') else 1.0)
        yaw = math.radians(self.yaw)
        forward = (math.sin(yaw), 0.0, math.cos(yaw))
        right = (math.cos(yaw), 0.0, -math.sin(yaw))
        if self._key('W'):
            self._move(forward, move)
        if self._key('S'):
            self._move(forward, -move)
        if self._key('D'):
            self._move(right, move)
        if self._key('A'):
            self._move(right, -move)
        if self._key('SPACE'):
            self.walk_pos[1] += move
        if self._key('LCTRL') or self._key('RCTRL'):
            self.walk_pos[1] -= move
        if is_moving:
            self._request_redraw(2)

    def _key(self, name):
        return name in self.keys

    def _move(self, vec, amount):
        self.walk_pos[0] += vec[0] * amount
        self.walk_pos[1] += vec[1] * amount
        self.walk_pos[2] += vec[2] * amount

    def _draw_overlay(self):
        size = (self.window.width, self.window.height)
        if self._overlay_dirty or self._overlay_size != size:
            self._update_overlay_text()
            self._overlay_dirty = False
            self._overlay_size = size
        self.label.x = 12
        self.label.y = self.window.height - 12
        self.label.width = max(240, self.window.width - 24)
        self.label.draw()

    def _update_overlay_text(self):
        title = self._caption_title
        if len(title) > 54:
            title = title[:51] + '...'
        mode = '内部視点' if self.mode == 'walk' else '外観'
        downsample = ' / 高速LOD %d' % self.stride if self.stride > 1 else ''
        caption = '%s | %s | %.0f fps | faces %s%s' % (
            title, mode, self.fps, f'{self.face_emitted:,}/{self.face_total:,}', downsample)
        try:
            self.window.set_caption(caption)
        except Exception:
            pass
        self.label.text = (
            '%s\n左ドラッグ: 回転 / 右ドラッグ: 移動 / ホイール: 拡大縮小 / R: リセット / F: 内部視点 / H: 表示切替'
            % caption
        )

    def on_mouse_press(self, _x, _y, button, _mods):
        if button == self.pyglet.window.mouse.LEFT:
            self.mouse_down = True
            self._request_redraw(8)

    def on_mouse_release(self, _x, _y, button, _mods):
        if button == self.pyglet.window.mouse.LEFT:
            self.mouse_down = False
            self._request_redraw(4)

    def on_mouse_drag(self, _x, _y, dx, dy, buttons, mods):
        mouse = self.pyglet.window.mouse
        key = self.pyglet.window.key
        if self.mode == 'orbit' and (buttons & mouse.RIGHT or buttons & mouse.MIDDLE
                                     or (buttons & mouse.LEFT and mods & key.MOD_SHIFT)):
            self._pan_orbit(dx, dy)
        elif buttons & mouse.LEFT:
            self.yaw += dx * 0.10
            self.pitch = max(-12.0, min(78.0, self.pitch - dy * 0.07))
        self._request_redraw(4)

    def on_mouse_scroll(self, _x, _y, _sx, sy):
        self.zoom = max(0.18, min(8.0, self.zoom * (1.04 ** sy)))
        self._request_redraw(4)

    def on_key_press(self, symbol, _mods):
        key = self.pyglet.window.key
        name = key.symbol_string(symbol)
        self.keys.add(name)
        if symbol == key.ESCAPE:
            self.close()
        elif symbol == key.R:
            self.yaw = self.default_yaw
            self.pitch = self.default_pitch
            self.zoom = self.default_zoom
            self.mode = self.default_mode
            self._reset_camera()
            self._overlay_dirty = True
        elif symbol == key.F:
            self.mode = 'walk' if self.mode == 'orbit' else 'orbit'
            if self.mode == 'walk':
                self.pitch = 8.0
            self._overlay_dirty = True
        elif symbol == key.H:
            self.show_overlay = not self.show_overlay
            self._overlay_dirty = True
        elif self.mode == 'orbit' and symbol == key.LEFT:
            self.yaw -= 8.0
            self._overlay_dirty = True
        elif self.mode == 'orbit' and symbol == key.RIGHT:
            self.yaw += 8.0
            self._overlay_dirty = True
        elif self.mode == 'orbit' and symbol == key.UP:
            self.pitch = min(78.0, self.pitch + 5.0)
            self._overlay_dirty = True
        elif self.mode == 'orbit' and symbol == key.DOWN:
            self.pitch = max(-12.0, self.pitch - 5.0)
            self._overlay_dirty = True
        elif name in ('PLUS', 'EQUAL', 'NUM_ADD', 'NUM_PLUS'):
            self.zoom = max(0.18, min(8.0, self.zoom * 1.12))
            self._overlay_dirty = True
        elif name in ('MINUS', 'NUM_SUBTRACT', 'NUM_MINUS'):
            self.zoom = max(0.18, min(8.0, self.zoom / 1.12))
            self._overlay_dirty = True
        elif symbol in (key._1, key.NUM_1):
            self.mode = 'orbit'
            self.yaw = -42.0
            self.pitch = 26.0
            self.zoom = 1.0
            self._overlay_dirty = True
        elif symbol in (key._2, key.NUM_2):
            self.mode = 'orbit'
            self.yaw = 0.0
            self.pitch = 70.0
            self.zoom = 1.15
            self._overlay_dirty = True
        elif symbol in (key._3, key.NUM_3):
            self.mode = 'orbit'
            self.yaw = -90.0
            self.pitch = 12.0
            self.zoom = 1.05
            self._overlay_dirty = True
        self._request_redraw(6)

    def on_key_release(self, symbol, _mods):
        name = self.pyglet.window.key.symbol_string(symbol)
        self.keys.discard(name)
        self._request_redraw(4)

    def on_close(self):
        self.close()

    def close(self):
        if self._closed:
            return
        self._closed = True
        try:
            self.window.close()
        finally:
            self.pyglet.app.exit()


VERTEX_SHADER = """#version 330 core
in vec3 position;
in vec4 colors;
in vec2 tex_coords;
uniform mat4 mvp;
out vec4 v_color;
out vec2 v_tex_coords;
void main()
{
    gl_Position = mvp * vec4(position, 1.0);
    v_color = colors;
    v_tex_coords = tex_coords;
}
"""


FRAGMENT_SHADER = """#version 330 core
in vec4 v_color;
in vec2 v_tex_coords;
uniform sampler2D atlas_texture;
uniform int use_texture;
out vec4 final_color;
void main()
{
    vec4 color = v_color;
    if (use_texture == 1) {
        vec4 tex = texture(atlas_texture, v_tex_coords);
        if (tex.a < 0.08) {
            discard;
        }
        color = tex * v_color;
        color.a = max(tex.a, 0.72);
    }
    final_color = color;
}
"""
