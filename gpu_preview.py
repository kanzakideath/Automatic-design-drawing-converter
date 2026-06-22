# -*- coding: utf-8 -*-
"""OpenGL preview window for large Minecraft schematic previews.

The Tk/Pillow preview is intentionally kept lightweight.  This module builds a
static exposed-face mesh once, uploads it to the GPU, and then only updates the
camera while the user rotates or moves around the model.
"""

from __future__ import annotations

from array import array
import math
import threading
import traceback


_active_thread = None
_active_lock = threading.Lock()


FACE_DEFS = (
    ((0, 1, 0), ((0, 1, 0), (1, 1, 0), (1, 1, 1), (0, 1, 1)), 1.18),
    ((0, -1, 0), ((0, 0, 1), (1, 0, 1), (1, 0, 0), (0, 0, 0)), 0.48),
    ((0, 0, 1), ((0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1)), 0.86),
    ((1, 0, 0), ((1, 0, 1), (1, 0, 0), (1, 1, 0), (1, 1, 1)), 0.76),
    ((0, 0, -1), ((1, 0, 0), (0, 0, 0), (0, 1, 0), (1, 1, 0)), 0.68),
    ((-1, 0, 0), ((0, 0, 0), (0, 0, 1), (0, 1, 1), (0, 1, 0)), 0.60),
)

TRI_ORDER = (0, 1, 2, 0, 2, 3)


def open_preview_async(payload):
    """Open a GPU preview window on its own pyglet event-loop thread."""
    global _active_thread
    with _active_lock:
        if _active_thread is not None and _active_thread.is_alive():
            raise RuntimeError('GPUプレビューはすでに開いています。先に閉じてください。')
        _active_thread = threading.Thread(target=_run_preview_safe, args=(payload,), daemon=True)
        _active_thread.start()


def _run_preview_safe(payload):
    try:
        _run_preview(payload)
    except Exception:
        traceback.print_exc()


def _run_preview(payload):
    import pyglet
    from pyglet import gl

    try:
        config = gl.Config(double_buffer=True, depth_size=24, major_version=3, minor_version=3)
        window = GpuPreviewWindow(payload, config=config)
    except Exception:
        window = GpuPreviewWindow(payload)
    pyglet.clock.schedule_interval(window.update, 1.0 / 240.0)
    pyglet.app.run(interval=0)


def _shade(color, factor):
    return (
        max(0, min(255, int(color[0] * factor))),
        max(0, min(255, int(color[1] * factor))),
        max(0, min(255, int(color[2] * factor))),
    )


def _count_exposed_faces(blocks, occupied):
    total = 0
    for x, y, z, _r, _g, _b in blocks:
        ix, iy, iz = int(x), int(y), int(z)
        for normal, _corners, _light in FACE_DEFS:
            if (ix + normal[0], iy + normal[1], iz + normal[2]) not in occupied:
                total += 1
    return total


def build_mesh(payload):
    blocks = payload.get('blocks') or []
    occupied = payload.get('occupied') or set()
    max_faces = int(payload.get('max_faces') or 260000)
    face_total = _count_exposed_faces(blocks, occupied)
    stride = max(1, int(math.ceil(face_total / float(max_faces)))) if max_faces > 0 else 1

    positions = array('f')
    colors = array('B')
    face_index = 0
    emitted_faces = 0

    for x, y, z, r, g, b in blocks:
        ix, iy, iz = int(x), int(y), int(z)
        base = (int(r), int(g), int(b))
        for normal, corners, light in FACE_DEFS:
            if (ix + normal[0], iy + normal[1], iz + normal[2]) in occupied:
                continue
            if face_index % stride:
                face_index += 1
                continue
            shaded = _shade(base, light)
            pts = [(ix + cx, iy + cy, iz + cz) for cx, cy, cz in corners]
            for corner_index in TRI_ORDER:
                px, py, pz = pts[corner_index]
                positions.extend((float(px), float(py), float(pz)))
                colors.extend((shaded[0], shaded[1], shaded[2], 255))
            emitted_faces += 1
            face_index += 1

    return positions, colors, face_total, emitted_faces, stride


def build_ground(bounds):
    cx = float(bounds.get('cx', 0.0))
    cz = float(bounds.get('cz', 0.0))
    y = float(bounds.get('min_y', 0.0)) - 0.04
    span = max(float(bounds.get('span_x', 32.0)), float(bounds.get('span_z', 32.0)), 32.0)
    extent = max(96.0, span * 2.2)
    x0, x1 = cx - extent, cx + extent
    z0, z1 = cz - extent, cz + extent

    ground_positions = array('f', (
        x0, y, z0, x1, y, z0, x1, y, z1,
        x0, y, z0, x1, y, z1, x0, y, z1,
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
    return ground_positions, ground_colors, grid_positions, grid_colors


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
        self._build_vertex_lists()
        self._reset_camera()
        self.label = pyglet.text.Label('', font_name='Yu Gothic UI', font_size=11,
                                       x=12, y=self.window.height - 12, anchor_x='left',
                                       anchor_y='top', color=(255, 255, 255, 255))
        gl.glEnable(gl.GL_DEPTH_TEST)
        gl.glDisable(gl.GL_CULL_FACE)

    def _build_vertex_lists(self):
        from pyglet import gl

        positions, colors, face_total, emitted_faces, stride = build_mesh(self.payload)
        self.face_total = face_total
        self.face_emitted = emitted_faces
        self.stride = stride
        self.vertex_count = len(positions) // 3
        self.mesh_list = self.program.vertex_list(
            self.vertex_count, gl.GL_TRIANGLES,
            position=('f', positions),
            colors=('Bn', colors),
        ) if self.vertex_count else None

        gp, gc, gridp, gridc = build_ground(self.bounds)
        self.ground_list = self.program.vertex_list(
            len(gp) // 3, gl.GL_TRIANGLES,
            position=('f', gp),
            colors=('Bn', gc),
        )
        self.grid_list = self.program.vertex_list(
            len(gridp) // 3, gl.GL_LINES,
            position=('f', gridp),
            colors=('Bn', gridc),
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
        self.program.use()
        self.program['mvp'] = self._mvp_matrix()
        self.ground_list.draw(gl.GL_TRIANGLES)
        self.grid_list.draw(gl.GL_LINES)
        if self.mesh_list is not None:
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

    def update(self, dt):
        self._fps_frames += 1
        self._fps_time += dt
        if self._fps_time >= 0.35:
            self.fps = self._fps_frames / self._fps_time
            self._fps_frames = 0
            self._fps_time = 0.0
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
        title = self.payload.get('title') or 'GPU Preview'
        mode = '内部視点' if self.mode == 'walk' else '外観'
        downsample = ' / 間引き %d' % self.stride if self.stride > 1 else ''
        self.label.x = 12
        self.label.y = self.window.height - 12
        self.label.text = (
            '%s  |  %s  |  %.0f fps  |  %s faces%s\n'
            'ドラッグ: 回転  ホイール: 拡大縮小  F: 内部視点  WASD/Space/Ctrl: 移動  R: リセット  Esc: 閉じる'
            % (title, mode, self.fps, f'{self.face_emitted:,}/{self.face_total:,}', downsample)
        )
        self.label.draw()

    def on_mouse_press(self, _x, _y, button, _mods):
        if button == self.pyglet.window.mouse.LEFT:
            self.mouse_down = True

    def on_mouse_release(self, _x, _y, button, _mods):
        if button == self.pyglet.window.mouse.LEFT:
            self.mouse_down = False

    def on_mouse_drag(self, _x, _y, dx, dy, buttons, _mods):
        if buttons & self.pyglet.window.mouse.LEFT:
            self.yaw += dx * 0.22
            self.pitch = max(-82.0, min(82.0, self.pitch + dy * 0.18))

    def on_mouse_scroll(self, _x, _y, _sx, sy):
        self.zoom = max(0.18, min(8.0, self.zoom * (1.12 ** sy)))

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
        elif symbol == key.F:
            self.mode = 'walk' if self.mode == 'orbit' else 'orbit'
            if self.mode == 'walk':
                self.pitch = 8.0

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
uniform mat4 mvp;
out vec4 v_color;
void main()
{
    gl_Position = mvp * vec4(position, 1.0);
    v_color = colors;
}
"""


FRAGMENT_SHADER = """#version 330 core
in vec4 v_color;
out vec4 final_color;
void main()
{
    final_color = v_color;
}
"""
