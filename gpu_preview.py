# -*- coding: utf-8 -*-
"""OpenGL preview window for large Minecraft schematic previews.

The Tk/Pillow preview is intentionally kept lightweight.  This module builds a
static exposed-face mesh once, uploads it to the GPU, and then only updates the
camera while the user rotates or moves around the model.
"""

from __future__ import annotations

from array import array
import math
import queue
import threading
import traceback


_active_thread = None
_active_lock = threading.Lock()


FACE_DEFS = (
    ((0, 1, 0), ((0, 1, 1), (1, 1, 1), (1, 1, 0), (0, 1, 0)), 1.18),
    ((0, -1, 0), ((0, 0, 0), (1, 0, 0), (1, 0, 1), (0, 0, 1)), 0.48),
    ((0, 0, 1), ((0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1)), 0.86),
    ((1, 0, 0), ((1, 0, 1), (1, 0, 0), (1, 1, 0), (1, 1, 1)), 0.76),
    ((0, 0, -1), ((1, 0, 0), (0, 0, 0), (0, 1, 0), (1, 1, 0)), 0.68),
    ((-1, 0, 0), ((0, 0, 0), (0, 0, 1), (0, 1, 1), (0, 1, 0)), 0.60),
)

TRI_ORDER = (0, 1, 2, 0, 2, 3)

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
    status_q = queue.Queue(maxsize=1)
    with _active_lock:
        if _active_thread is not None and _active_thread.is_alive():
            raise RuntimeError('GPUプレビューはすでに開いています。先に閉じてください。')
        _active_thread = threading.Thread(target=_run_preview_safe, args=(payload, status_q), daemon=True)
        _active_thread.start()
    try:
        status, detail = status_q.get(timeout=float(payload.get('startup_timeout', 3.0)))
    except queue.Empty:
        return
    if status == 'error':
        raise RuntimeError(detail)


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


def _run_preview(payload, status_q=None):
    import pyglet

    pyglet.options['debug_gl'] = False
    from pyglet import gl

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
    pyglet.clock.schedule_interval(window.update, 1.0 / 240.0)
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
    bounds = SHAPE_BOUNDS.get(shape_id, SHAPE_BOUNDS[0])
    ox, oy, oz, sx, sy, sz = bounds
    return [(ox, oy, oz, ox + sx, oy + sy, oz + sz, False)]


def _count_exposed_faces(blocks, occupied):
    total = 0
    for block in blocks:
        x, y, z = block[:3]
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
    face_total = _count_exposed_faces(blocks, occupied)
    stride = max(1, int(math.ceil(face_total / float(max_faces)))) if max_faces > 0 else 1

    positions = array('f')
    colors = array('B')
    tex_coords = array('f')
    indices = array('I')
    face_index = 0
    emitted_faces = 0

    for block in blocks:
        x, y, z, _r, _g, _b = block[:6]
        top_tile = int(block[6]) if len(block) > 6 else 0
        side_tile = int(block[7]) if len(block) > 7 else top_tile
        shape_id = int(block[8]) if len(block) > 8 else 0
        variant = int(block[9]) if len(block) > 9 else 0
        ix, iy, iz = int(x), int(y), int(z)
        for x0, y0, z0, x1, y1, z1, occluding in _shape_boxes(shape_id, variant):
            sx, sy, sz = x1 - x0, y1 - y0, z1 - z0
            for normal, corners, light in FACE_DEFS:
                if occluding and (ix + normal[0], iy + normal[1], iz + normal[2]) in occupied:
                    continue
                if face_index % stride:
                    face_index += 1
                    continue
                light_value = max(0, min(255, int(255 * light)))
                pts = [(ix + x0 + cx * sx, iy + y0 + cy * sy, iz + z0 + cz * sz) for cx, cy, cz in corners]
                tile_index = top_tile if normal[1] else side_tile
                if tile_index < 0 or tile_index >= len(atlas_uvs):
                    tile_index = 0
                u0, v0, u1, v1 = atlas_uvs[tile_index]
                quad_uvs = ((u0, v0), (u1, v0), (u1, v1), (u0, v1))
                base_vertex = len(positions) // 3
                for corner_index, (px, py, pz) in enumerate(pts):
                    positions.extend((float(px), float(py), float(pz)))
                    colors.extend((light_value, light_value, light_value, 255))
                    tex_coords.extend(quad_uvs[corner_index])
                indices.extend((base_vertex, base_vertex + 1, base_vertex + 2,
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
        self.mode = 'orbit'
        self.yaw = -42.0
        self.pitch = 26.0
        self.zoom = 1.0
        self.fps = 0.0
        self._fps_accum = 0.0
        self._fps_frames = 0
        self._fps_time = 0.0
        self._closed = False
        self._overlay_size = (0, 0)
        self._overlay_dirty = True

        width = int(payload.get('width') or 1280)
        height = int(payload.get('height') or 760)
        kwargs = {'width': width, 'height': height, 'caption': 'Minecraft GPU Preview', 'resizable': True,
                  'vsync': False}
        if config is not None:
            kwargs['config'] = config
        self.window = pyglet.window.Window(**kwargs)
        self.window.push_handlers(self)
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
        self._update_overlay_text()

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

        positions, colors, tex_coords, indices, face_total, emitted_faces, stride = build_mesh(self.payload)
        self.face_total = face_total
        self.face_emitted = emitted_faces
        self.stride = stride
        self.vertex_count = len(positions) // 3
        self.index_count = len(indices)
        self.mesh_list = self.program.vertex_list_indexed(
            self.vertex_count, gl.GL_TRIANGLES,
            indices,
            position=('f', positions),
            colors=('Bn', colors),
            tex_coords=('f', tex_coords),
        ) if self.vertex_count and self.index_count else None

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
        scale = (self.distance / max(0.2, self.zoom)) / float(max(320, self.window.width)) * 1.35
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

    def update(self, dt):
        self._fps_frames += 1
        self._fps_time += dt
        if self._fps_time >= 0.35:
            self.fps = self._fps_frames / self._fps_time
            self._fps_frames = 0
            self._fps_time = 0.0
            self._overlay_dirty = True
        if self.mode != 'walk':
            return
        speed = max(3.5, max(float(self.bounds.get('span_x', 32.0)),
                             float(self.bounds.get('span_z', 32.0))) * 0.55)
        move = speed * dt * (3.0 if self._key('LSHIFT') or self._key('RSHIFT') else 1.0)
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
        title = self.payload.get('title') or 'GPU Preview'
        if len(title) > 54:
            title = title[:51] + '...'
        mode = '内部視点' if self.mode == 'walk' else '外観'
        downsample = ' / 速度優先LOD %d' % self.stride if self.stride > 1 else ''
        self.label.text = (
            '%s | %s | %.0f fps | 面 %s%s\n'
            '左ドラッグ: 回転/視点移動   右ドラッグ/Shift+左: 平行移動   ホイール: ズーム   '
            'F: 内部視点   1/2/3: 視点切替   R: リセット   Esc: 閉じる'
            % (title, mode, self.fps, f'{self.face_emitted:,}/{self.face_total:,}', downsample)
        )

    def on_mouse_press(self, _x, _y, button, _mods):
        if button == self.pyglet.window.mouse.LEFT:
            self.mouse_down = True

    def on_mouse_release(self, _x, _y, button, _mods):
        if button == self.pyglet.window.mouse.LEFT:
            self.mouse_down = False

    def on_mouse_drag(self, _x, _y, dx, dy, buttons, mods):
        mouse = self.pyglet.window.mouse
        key = self.pyglet.window.key
        if self.mode == 'orbit' and (buttons & mouse.RIGHT or buttons & mouse.MIDDLE
                                     or (buttons & mouse.LEFT and mods & key.MOD_SHIFT)):
            self._pan_orbit(dx, dy)
        elif buttons & mouse.LEFT:
            self.yaw += dx * 0.22
            self.pitch = max(-18.0, min(82.0, self.pitch + dy * 0.18))

    def on_mouse_scroll(self, _x, _y, _sx, sy):
        self.zoom = max(0.18, min(8.0, self.zoom * (1.09 ** sy)))

    def on_key_press(self, symbol, _mods):
        key = self.pyglet.window.key
        name = key.symbol_string(symbol)
        self.keys.add(name)
        if symbol == key.ESCAPE:
            self.close()
        elif symbol == key.R:
            self.yaw = -42.0
            self.pitch = 26.0
            self.zoom = 1.0
            self.mode = 'orbit'
            self._reset_camera()
            self._overlay_dirty = True
        elif symbol == key.F:
            self.mode = 'walk' if self.mode == 'orbit' else 'orbit'
            if self.mode == 'walk':
                self.pitch = 8.0
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

    def on_key_release(self, symbol, _mods):
        name = self.pyglet.window.key.symbol_string(symbol)
        self.keys.discard(name)

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
