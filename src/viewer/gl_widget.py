"""
viewer/gl_widget.py - Roblox R6 avatar viewer (PyQt6 + OpenGL).

Correct per-face UV mapping from the official 585x559 shirt template.
Solid opaque fallback when no texture loaded (never transparent).
Exact R6 stud dimensions matching StudioR6.rbxm.
"""
from __future__ import annotations
import math
from typing import Optional, Tuple
import numpy as np
from PIL import Image
from PyQt6.QtWidgets import QSizePolicy
from PyQt6.QtCore import Qt, QPoint, QTimer
from PyQt6.QtGui import QMouseEvent, QWheelEvent

try:
    from PyQt6.QtOpenGLWidgets import QOpenGLWidget
except ImportError:
    from PyQt6.QtWidgets import QOpenGLWidget  # type: ignore

try:
    from OpenGL.GL import (
        glClearColor, glEnable, glDisable, glClear, glLoadIdentity,
        glBegin, glEnd, glVertex3f, glNormal3f, glTexCoord2f,
        glColor3f, glColor4f, glLineWidth, glViewport,
        glMatrixMode, glLightfv, glColorMaterial, glShadeModel,
        glBlendFunc, glBindTexture, glGenTextures, glDeleteTextures,
        glTexParameteri, glTexImage2D,
        GL_COLOR_BUFFER_BIT, GL_DEPTH_BUFFER_BIT, GL_DEPTH_TEST,
        GL_LIGHTING, GL_LIGHT0, GL_COLOR_MATERIAL, GL_SMOOTH,
        GL_FRONT_AND_BACK, GL_AMBIENT_AND_DIFFUSE,
        GL_AMBIENT, GL_DIFFUSE, GL_QUADS, GL_LINES, GL_TRIANGLES, GL_TRIANGLE_FAN, GL_TEXTURE_2D,
        GL_LINEAR, GL_CLAMP_TO_EDGE, GL_RGBA, GL_UNSIGNED_BYTE,
        GL_TEXTURE_MIN_FILTER, GL_TEXTURE_MAG_FILTER,
        GL_TEXTURE_WRAP_S, GL_TEXTURE_WRAP_T,
        GL_PROJECTION, GL_MODELVIEW, GL_BLEND,
        GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA,
    )
    from OpenGL.GLU import gluPerspective, gluLookAt
    OPENGL_AVAILABLE = True
except ImportError:
    OPENGL_AVAILABLE = False

# Template dimensions
TW, TH = 585.0, 559.0

# ---------------------------------------------------------------------------
# Shirt template face pixel regions (verified pixel-by-pixel from template PNG)
# ---------------------------------------------------------------------------
SHIRT_FACES = {
    "torso": {
        "top":    (231,   8, 359,  72),   # UP
        "front":  (231,  74, 359, 202),   # FRONT
        "right":  (165,  74, 229, 202),   # R (character right)
        "left":   (361,  74, 425, 202),   # L (character left)
        "back":   (427,  74, 555, 202),   # BACK
        "bottom": (231, 204, 359, 268),   # DOWN
    },
    "right_arm": {
        "top":    ( 19, 355,  83, 407),
        "left":   ( 19, 408,  83, 483),
        "back":   ( 85, 408, 149, 483),
        "right":  (151, 408, 215, 483),
        "front":  (217, 408, 281, 483),
        "bottom": (217, 485, 281, 549),
    },
    "left_arm": {
        "top":    (374, 355, 438, 407),
        "front":  (308, 408, 372, 483),
        "left":   (374, 408, 438, 483),
        "back":   (440, 408, 504, 483),
        "right":  (506, 408, 570, 483),
        "bottom": (308, 485, 372, 549),
    },
}

PANTS_FACES = {
    "right_leg": {
        "top":    ( 19, 355,  83, 407),
        "left":   ( 19, 408,  83, 483),
        "back":   ( 85, 408, 149, 483),
        "right":  (151, 408, 215, 483),
        "front":  (217, 408, 281, 483),
        "bottom": (217, 485, 281, 549),
    },
    "left_leg": {
        "top":    (374, 355, 438, 407),
        "front":  (308, 408, 372, 483),
        "left":   (374, 408, 438, 483),
        "back":   (440, 408, 504, 483),
        "right":  (506, 408, 570, 483),
        "bottom": (308, 485, 372, 549),
    },
    "torso": {
        "top":    (231,   8, 359,  72),
        "front":  (231,  74, 359, 202),
        "right":  (165,  74, 229, 202),
        "left":   (361,  74, 425, 202),
        "back":   (427,  74, 555, 202),
        "bottom": (231, 204, 359, 268),
    },
}

# ---------------------------------------------------------------------------
# Exact Roblox R6 part geometry in studs
#
# All parts touch seamlessly:
#   Legs:  center=(±0.5, 1.0, 0)  half=(0.5, 1.0, 0.5) → Y: 0.0 to 2.0
#   Torso: center=(0.0,  3.0, 0)  half=(1.0, 1.0, 0.5) → Y: 2.0 to 4.0
#   Arms:  center=(±1.5, 3.0, 0)  half=(0.5, 1.0, 0.5) → Y: 2.0 to 4.0 (same as torso)
#   Head:  center=(0.0,  4.5, 0)  half=(0.5, 0.5, 0.5) → Y: 4.0 to 5.0
#
# Total character height = 5 studs (ground to top of head)
# ---------------------------------------------------------------------------
SKIN  = (0.91, 0.73, 0.60)   # Roblox classic yellow skin
DARK  = (0.30, 0.22, 0.16)   # eye / hair dark

R6_PARTS = {
    #             center (x,   y,    z)   half-extents (w,   h,   d)
    "head":      (( 0.0,  4.5,  0.0),    (0.5,  0.5,  0.5)),
    "torso":     (( 0.0,  3.0,  0.0),    (1.0,  1.0,  0.5)),
    "right_arm": ((-1.5,  3.0,  0.0),    (0.5,  1.0,  0.5)),
    "left_arm":  (( 1.5,  3.0,  0.0),    (0.5,  1.0,  0.5)),
    "right_leg": ((-0.5,  1.0,  0.0),    (0.5,  1.0,  0.5)),
    "left_leg":  (( 0.5,  1.0,  0.0),    (0.5,  1.0,  0.5)),
}

def _box_faces(x0, y0, z0, x1, y1, z1):
    """Return 6 faces as (name, normal, [4 verts CCW from outside])."""
    return [
        ("front",  ( 0,  0,  1), [(x0,y0,z1),(x1,y0,z1),(x1,y1,z1),(x0,y1,z1)]),
        ("back",   ( 0,  0, -1), [(x1,y0,z0),(x0,y0,z0),(x0,y1,z0),(x1,y1,z0)]),
        ("right",  (-1,  0,  0), [(x0,y0,z0),(x0,y0,z1),(x0,y1,z1),(x0,y1,z0)]),
        ("left",   ( 1,  0,  0), [(x1,y0,z1),(x1,y0,z0),(x1,y1,z0),(x1,y1,z1)]),
        ("top",    ( 0,  1,  0), [(x0,y1,z0),(x0,y1,z1),(x1,y1,z1),(x1,y1,z0)]),
        ("bottom", ( 0, -1,  0), [(x0,y0,z1),(x0,y0,z0),(x1,y0,z0),(x1,y0,z1)]),
    ]

def _px_to_uv(x0, y0, x1, y1, face="side"):
    """
    Pixel rect (top-left origin) -> 4 UV corners matched to each face vertex winding.
    Side faces wind BL,BR,TR,TL. Top winds TL,BL,BR,TR. Bottom winds BL,TL,TR,BR.
    """
    u0, u1 = x0 / TW, x1 / TW
    v_bot  = 1.0 - y1 / TH
    v_top  = 1.0 - y0 / TH
    if face == "top":
        return [(u0,v_top), (u0,v_bot), (u1,v_bot), (u1,v_top)]
    elif face == "bottom":
        return [(u0,v_bot), (u0,v_top), (u1,v_top), (u1,v_bot)]
    else:
        return [(u0,v_bot), (u1,v_bot), (u1,v_top), (u0,v_top)]

def draw_part(cx, cy, cz, hw, hh, hd,
              shirt_faces, pants_faces,
              shirt_tex, pants_tex,
              default_color=SKIN):
    """
    Draw a box body part.
    - If a texture is loaded, UV-maps the correct region of it onto each face.
    - If NO texture is loaded, draws each face as a solid opaque colour.
    - All GL state set BEFORE glBegin (avoids GLError 1282).
    """
    if not OPENGL_AVAILABLE:
        return
    x0, x1 = cx - hw, cx + hw
    y0, y1 = cy - hh, cy + hh
    z0, z1 = cz - hd, cz + hd

    for face_name, normal, verts in _box_faces(x0, y0, z0, x1, y1, z1):
        # Decide texture for this face
        px_rect = None
        tex_id  = 0
        if shirt_faces and shirt_tex and face_name in shirt_faces:
            px_rect = shirt_faces[face_name]
            tex_id  = shirt_tex
        elif pants_faces and pants_tex and face_name in pants_faces:
            px_rect = pants_faces[face_name]
            tex_id  = pants_tex

        # ── Set state BEFORE glBegin ──────────────────────────────────────
        if px_rect and tex_id:
            glEnable(GL_TEXTURE_2D)
            glBindTexture(GL_TEXTURE_2D, tex_id)
            glColor3f(1.0, 1.0, 1.0)   # white = show texture as-is
            uvs = _px_to_uv(*px_rect, face=face_name)
        else:
            # No texture → solid opaque fallback colour, never transparent
            glDisable(GL_TEXTURE_2D)
            glColor3f(*default_color)
            uvs = None

        glBegin(GL_QUADS)
        glNormal3f(*normal)
        if uvs:
            for (u, v), vert in zip(uvs, verts):
                glTexCoord2f(u, v)
                glVertex3f(*vert)
        else:
            for vert in verts:
                glVertex3f(*vert)
        glEnd()

    glDisable(GL_TEXTURE_2D)


# ---------------------------------------------------------------------------
# Camera
# ---------------------------------------------------------------------------
class Camera:
    def __init__(self):
        self.reset()

    def reset(self):
        self.azimuth   = 25.0
        self.elevation = 18.0
        self.distance  = 9.0
        # Target = centre of avatar (height 0..5, midpoint 2.5)
        self.target    = [0.0, 2.5, 0.0]
        self.fov       = 38.0

    def orbit(self, da, de):
        self.azimuth   = (self.azimuth + da) % 360.0
        self.elevation = max(-89.0, min(89.0, self.elevation + de))

    def zoom(self, delta):
        self.distance = max(3.0, min(25.0, self.distance + delta))

    def pan(self, dx, dy):
        s  = self.distance * 0.003
        az = math.radians(self.azimuth)
        self.target[0] -= math.cos(az) * dx * s
        self.target[2] += math.sin(az) * dx * s
        self.target[1] += math.cos(math.radians(self.elevation)) * dy * s

    def get_eye(self):
        az = math.radians(self.azimuth)
        el = math.radians(self.elevation)
        x  = self.target[0] + self.distance * math.cos(el) * math.sin(az)
        y  = self.target[1] + self.distance * math.sin(el)
        z  = self.target[2] + self.distance * math.cos(el) * math.cos(az)
        return x, y, z

    def apply(self):
        if not OPENGL_AVAILABLE:
            return
        eye = self.get_eye()
        gluLookAt(eye[0], eye[1], eye[2],
                  self.target[0], self.target[1], self.target[2],
                  0.0, 1.0, 0.0)


# ---------------------------------------------------------------------------
# Main widget
# ---------------------------------------------------------------------------
class AvatarViewerWidget(QOpenGLWidget):
    """
    3D Roblox R6 avatar viewer.
      Left-drag        = orbit
      Right/Middle-drag = pan
      Scroll wheel     = zoom
      Double-click     = reset camera
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumSize(300, 380)

        self._camera       = Camera()
        self._last_mouse:  Optional[QPoint] = None
        self._mouse_button = None
        self._shirt_tex_id = 0
        self._pants_tex_id = 0
        self._ambient      = 0.35
        self._diffuse      = 1.0
        self._show_grid    = True
        self._auto_rotate  = False
        self._bg_color     = (0.11, 0.11, 0.16)

        self._rot_timer = QTimer(self)
        self._rot_timer.timeout.connect(self._on_auto_rotate)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)

    # ── GL lifecycle ──────────────────────────────────────────────────────────

    def initializeGL(self):
        if not OPENGL_AVAILABLE:
            return
        r, g, b = self._bg_color
        glClearColor(r, g, b, 1.0)
        glEnable(GL_DEPTH_TEST)
        glEnable(GL_LIGHTING)
        glEnable(GL_LIGHT0)
        glEnable(GL_COLOR_MATERIAL)
        glColorMaterial(GL_FRONT_AND_BACK, GL_AMBIENT_AND_DIFFUSE)
        glShadeModel(GL_SMOOTH)
        # Blend enabled but avatar parts are fully opaque
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        self._apply_lighting()

    def resizeGL(self, w, h):
        if not OPENGL_AVAILABLE:
            return
        h = max(h, 1)
        glViewport(0, 0, w, h)
        glMatrixMode(GL_PROJECTION)
        glLoadIdentity()
        gluPerspective(self._camera.fov, w / h, 0.1, 200.0)
        glMatrixMode(GL_MODELVIEW)

    def paintGL(self):
        if not OPENGL_AVAILABLE:
            self._paint_fallback()
            return
        r, g, b = self._bg_color
        glClearColor(r, g, b, 1.0)
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        glLoadIdentity()
        self._camera.apply()
        self._apply_lighting()
        if self._show_grid:
            self._draw_grid()
        self._draw_avatar()

    # ── Public API ────────────────────────────────────────────────────────────

    def update_shirt_texture(self, image: Image.Image):
        self.makeCurrent()
        self._shirt_tex_id = self._upload_texture(image, self._shirt_tex_id)
        self.update()

    def update_pants_texture(self, image: Image.Image):
        self.makeCurrent()
        self._pants_tex_id = self._upload_texture(image, self._pants_tex_id)
        self.update()

    def clear_textures(self):
        """Remove all textures – avatar shows solid skin colour."""
        self.makeCurrent()
        if self._shirt_tex_id:
            try: glDeleteTextures([self._shirt_tex_id])
            except: pass
        if self._pants_tex_id:
            try: glDeleteTextures([self._pants_tex_id])
            except: pass
        self._shirt_tex_id = 0
        self._pants_tex_id = 0
        self.update()

    def set_bg_color(self, r: float, g: float, b: float):
        self._bg_color = (r, g, b)
        self.update()

    def set_camera_preset(self, preset: str):
        presets = {
            "front":        (  0, 15),
            "back":         (180, 15),
            "left":         ( 90, 15),
            "right":        (270, 15),
            "top":          ( 30, 80),
            "threequarter": ( 35, 22),
        }
        if preset in presets:
            self._camera.azimuth, self._camera.elevation = presets[preset]
            self.update()

    def set_ambient(self, v: float):  self._ambient = v; self.update()
    def set_diffuse(self, v: float):  self._diffuse = v; self.update()
    def set_show_grid(self, s: bool): self._show_grid = s; self.update()

    def set_auto_rotate(self, enabled: bool):
        self._auto_rotate = enabled
        if enabled: self._rot_timer.start(16)
        else:       self._rot_timer.stop()

    # ── Mouse ─────────────────────────────────────────────────────────────────

    def mousePressEvent(self, event: QMouseEvent):
        self._last_mouse   = event.pos()
        self._mouse_button = event.button()
        if event.button() == Qt.MouseButton.LeftButton:
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
        else:
            self.setCursor(Qt.CursorShape.SizeAllCursor)

    def mouseMoveEvent(self, event: QMouseEvent):
        if self._last_mouse is None:
            return
        dx = event.pos().x() - self._last_mouse.x()
        dy = event.pos().y() - self._last_mouse.y()
        self._last_mouse = event.pos()
        if self._mouse_button == Qt.MouseButton.LeftButton:
            self._camera.orbit(dx * 0.4, -dy * 0.4)
        elif self._mouse_button in (Qt.MouseButton.RightButton, Qt.MouseButton.MiddleButton):
            self._camera.pan(dx, -dy)
        self.update()

    def mouseReleaseEvent(self, event: QMouseEvent):
        self._mouse_button = None
        self._last_mouse   = None
        self.setCursor(Qt.CursorShape.ArrowCursor)

    def mouseDoubleClickEvent(self, event: QMouseEvent):
        self._camera.reset()
        self.update()

    def wheelEvent(self, event: QWheelEvent):
        # Zoom: negative delta = zoom in (reduce distance)
        delta = event.angleDelta().y() / 120.0
        self._camera.zoom(-delta * self._camera.distance * 0.08)
        self.update()

    # ── Private ───────────────────────────────────────────────────────────────

    def _on_auto_rotate(self):
        self._camera.orbit(0.4, 0)
        self.update()

    def _upload_texture(self, img: Image.Image, old_id: int) -> int:
        if not OPENGL_AVAILABLE:
            return 0
        if old_id:
            try: glDeleteTextures([old_id])
            except: pass
        img  = img.convert("RGBA").transpose(Image.FLIP_TOP_BOTTOM)
        data = np.array(img, dtype=np.uint8)
        h, w = data.shape[:2]
        tid  = int(glGenTextures(1))
        glBindTexture(GL_TEXTURE_2D, tid)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE)
        glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, w, h, 0,
                     GL_RGBA, GL_UNSIGNED_BYTE, data.tobytes())
        return tid

    def _apply_lighting(self):
        if not OPENGL_AVAILABLE:
            return
        glLightfv(GL_LIGHT0, GL_AMBIENT, [self._ambient] * 3 + [1.0])
        glLightfv(GL_LIGHT0, GL_DIFFUSE, [self._diffuse] * 3 + [1.0])
        glLightfv(GL_LIGHT0, 0x1203,     [4.0, 8.0, 6.0, 1.0])  # GL_POSITION

    def _draw_grid(self):
        if not OPENGL_AVAILABLE:
            return
        glDisable(GL_LIGHTING)
        glDisable(GL_TEXTURE_2D)
        glLineWidth(1.0)
        # Minor grid
        glColor4f(0.22, 0.22, 0.32, 0.5)
        glBegin(GL_LINES)
        for i in range(-8, 9):
            glVertex3f(float(i), 0.0, -8.0); glVertex3f(float(i), 0.0,  8.0)
            glVertex3f(-8.0, 0.0, float(i)); glVertex3f( 8.0, 0.0, float(i))
        glEnd()
        # Bold centre lines
        glLineWidth(1.5)
        glColor4f(0.35, 0.35, 0.50, 0.8)
        glBegin(GL_LINES)
        glVertex3f(0, 0, -8); glVertex3f(0, 0, 8)
        glVertex3f(-8, 0, 0); glVertex3f(8, 0, 0)
        glEnd()
        glLineWidth(1.0)
        glEnable(GL_LIGHTING)

    def _draw_avatar(self):
        s = self._shirt_tex_id
        p = self._pants_tex_id
        for part, (center, half) in R6_PARTS.items():
            cx, cy, cz = center
            hw, hh, hd = half
            if part == "head":
                self._draw_roblox_head(cx, cy, cz, hw, hh, hd)
            elif part == "torso":
                draw_part(cx, cy, cz, hw, hh, hd,
                          SHIRT_FACES.get("torso"),
                          PANTS_FACES.get("torso"), s, p, SKIN)
            else:
                draw_part(cx, cy, cz, hw, hh, hd,
                          SHIRT_FACES.get(part),
                          PANTS_FACES.get(part), s, p, SKIN)

    def _draw_roblox_head(self, cx, cy, cz, hw, hh, hd):
        """
        Roblox R6 head rendered as a superellipsoid (smooth rounded box).
        Uses parametric superellipse: |x/a|^n + |y/b|^n + |z/c|^n = 1, n=4.
        This gives a box-like shape with fully rounded edges and corners on
        ALL sides, matching the classic Roblox head appearance.
        """
        if not OPENGL_AVAILABLE:
            return
        import math as _m

        skin = SKIN
        SEGS_U = 20   # longitude subdivisions (around)
        SEGS_V = 16   # latitude subdivisions (pole to pole)
        N = 4.0       # superellipsoid exponent (higher = more box-like)

        def _sgn(v):
            return 1.0 if v >= 0 else -1.0

        def _se_pt(u, v):
            """
            Superellipsoid parametric surface.
            u in [0, 2pi], v in [-pi/2, pi/2]
            Returns (point, normal) scaled to head half-extents.
            """
            cu = _m.cos(u); su = _m.sin(u)
            cv = _m.cos(v); sv = _m.sin(v)
            # Superellipse terms with sign preservation
            def _sp(val, exp):
                a = abs(val)
                return _sgn(val) * (a ** exp if a > 1e-9 else 0.0)
            e = 2.0 / N   # exponent for surface
            px = hw * _sp(cu, e) * _sp(cv, e)
            py = hh * _sp(sv, e)
            pz = hd * _sp(su, e) * _sp(cv, e)
            # Normal from gradient of implicit function
            ne = N - 1.0
            nx = (abs(cu*cv)**ne * _sgn(cu*cv)) / (hw + 1e-9)
            ny = (abs(sv)    **ne * _sgn(sv))    / (hh + 1e-9)
            nz = (abs(su*cv)**ne * _sgn(su*cv)) / (hd + 1e-9)
            mag = _m.sqrt(nx*nx + ny*ny + nz*nz) + 1e-9
            return (cx+px, cy+py, cz+pz), (nx/mag, ny/mag, nz/mag)

        glDisable(GL_TEXTURE_2D)
        glEnable(GL_LIGHTING)
        glColor3f(*skin)

        # Draw as quad grid
        for j in range(SEGS_V):
            v0 = -_m.pi/2 + _m.pi * j       / SEGS_V
            v1 = -_m.pi/2 + _m.pi * (j+1)   / SEGS_V
            for i in range(SEGS_U):
                u0 = 2*_m.pi * i       / SEGS_U
                u1 = 2*_m.pi * (i+1)   / SEGS_U
                p00, n00 = _se_pt(u0, v0)
                p01, n01 = _se_pt(u1, v0)
                p10, n10 = _se_pt(u0, v1)
                p11, n11 = _se_pt(u1, v1)
                # Shade front face (z+) slightly warmer
                if p00[2] > cz+hd*0.6 or p01[2] > cz+hd*0.6:
                    glColor3f(skin[0]*1.02, skin[1]*0.99, skin[2]*0.94)
                else:
                    glColor3f(*skin)
                glBegin(GL_QUADS)
                glNormal3f(*n00); glVertex3f(*p00)
                glNormal3f(*n01); glVertex3f(*p01)
                glNormal3f(*n11); glVertex3f(*p11)
                glNormal3f(*n10); glVertex3f(*p10)
                glEnd()

        # ── Face features on front of head ────────────────────────────────────
        glDisable(GL_LIGHTING)
        ez = cz + hd + 0.006

        # Eyes — filled ovals
        eye_rx = hw * 0.09; eye_ry = hh * 0.10
        eye_y  = cy + hh * 0.08
        glColor3f(0.08, 0.06, 0.05)
        for eye_cx in (cx - hw*0.27, cx + hw*0.27):
            segs = 14
            for i in range(segs):
                a0 = 2*_m.pi * i       / segs
                a1 = 2*_m.pi * (i+1)   / segs
                glBegin(GL_TRIANGLES)
                glVertex3f(eye_cx, eye_y, ez)
                glVertex3f(eye_cx + eye_rx*_m.cos(a0), eye_y + eye_ry*_m.sin(a0), ez)
                glVertex3f(eye_cx + eye_rx*_m.cos(a1), eye_y + eye_ry*_m.sin(a1), ez)
                glEnd()

        # Smile — thick arc
        sm_cx = cx; sm_cy = cy - hh*0.22
        sm_rx = hw*0.28; sm_ry = hh*0.13; sm_th = hh*0.038
        a_start = _m.radians(210); a_end = _m.radians(330)
        sm_segs = 14
        glColor3f(0.15, 0.08, 0.06)
        for i in range(sm_segs):
            a0 = a_start + (a_end - a_start) * i       / sm_segs
            a1 = a_start + (a_end - a_start) * (i+1)   / sm_segs
            ox0 = sm_cx+(sm_rx+sm_th)*_m.cos(a0); oy0 = sm_cy+(sm_ry+sm_th)*_m.sin(a0)
            ox1 = sm_cx+(sm_rx+sm_th)*_m.cos(a1); oy1 = sm_cy+(sm_ry+sm_th)*_m.sin(a1)
            ix0 = sm_cx+(sm_rx-sm_th)*_m.cos(a0); iy0 = sm_cy+(sm_ry-sm_th)*_m.sin(a0)
            ix1 = sm_cx+(sm_rx-sm_th)*_m.cos(a1); iy1 = sm_cy+(sm_ry-sm_th)*_m.sin(a1)
            glBegin(GL_QUADS)
            glVertex3f(ox0,oy0,ez); glVertex3f(ox1,oy1,ez)
            glVertex3f(ix1,iy1,ez); glVertex3f(ix0,iy0,ez)
            glEnd()

        glEnable(GL_LIGHTING)


    def _draw_eyes(self, cx, cy, cz, hw, hh, hd):
        """Legacy — now handled by _draw_roblox_head."""
        pass

    def _paint_fallback(self):
        from PyQt6.QtGui import QPainter, QColor, QFont
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(28, 28, 40))
        p.setPen(QColor(137, 180, 250))
        p.setFont(QFont("Arial", 13))
        p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter,
                   "3D Preview requires PyOpenGL\n\npip install PyOpenGL PyOpenGL_accelerate")
        p.end()
