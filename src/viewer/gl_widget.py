"""
viewer/gl_widget.py — Roblox R6 avatar 3D preview (PyQt6 + OpenGL).

Clean rewrite. Key design decisions:
  - draw_part() draws ALL 6 faces unconditionally — textured if a tex region exists,
    solid skin colour if not. Never leaves a face invisible.
  - UV coords use a simple, consistent winding: every face maps its pixel rect with
    bottom-left origin in GL UV space.
  - Texture upload flips top-bottom once (PIL top-left → GL bottom-left).
  - SHIRT_FACES / PANTS_FACES contain only the faces that actually have texture
    content; unlisted faces fall back to skin colour automatically.
"""
from __future__ import annotations
import math
from typing import Optional
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
        GL_AMBIENT, GL_DIFFUSE, GL_QUADS, GL_LINES,
        GL_TRIANGLES, GL_TEXTURE_2D,
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

# ── Template dimensions ───────────────────────────────────────────────────────
TW, TH = 585.0, 559.0

# ── Skin / dark colours ───────────────────────────────────────────────────────
SKIN = (0.91, 0.73, 0.60)
DARK = (0.20, 0.14, 0.10)

# ── Official Roblox 585×559 shirt template UV regions ────────────────────────
#
# Torso cross-layout (verified from roblox_shirt_template.png):
#   UP    (231,  8)–(359, 72)   128×64
#   FRONT (231, 74)–(359,202)   128×128
#   R     (165, 74)–(229,202)    64×128  ← character's RIGHT
#   L     (361, 74)–(425,202)    64×128  ← character's LEFT
#   BACK  (427, 74)–(555,202)   128×128
#   DOWN  (231,204)–(359,268)   128×64
#
# Arm block (right arm shown; left arm mirrors starting at x=308):
#   L col (gold,  outer)   x= 19– 82  ← face normal (-1,0,0) = "right" in box
#   B col (dkblue,back)    x= 85–148  ← face normal ( 0,0,-1) = "back"
#   R col (green, inner)   x=151–214  ← face normal (+1,0,0) = "left" in box
#   F col (red,   front)   x=217–280  ← face normal ( 0,0,+1) = "front"
#   U     above F col      y=289–352
#   D     below F col      y=485–549
#
SHIRT_FACES = {
    "torso": {
        "top":    (231,   8, 359,  72),
        "front":  (231,  74, 359, 202),
        "right":  (165,  74, 229, 202),   # character RIGHT
        "left":   (361,  74, 425, 202),   # character LEFT
        "back":   (427,  74, 555, 202),
        "bottom": (231, 204, 359, 268),
    },
    "right_arm": {
        "top":    (217, 289, 280, 352),
        "front":  (217, 355, 280, 483),   # F — faces viewer
        "back":   ( 85, 355, 148, 483),   # B — faces away
        "right":  ( 19, 355,  82, 483),   # outer side
        "left":   (151, 355, 214, 483),   # inner side (toward torso)
        "bottom": (217, 485, 280, 549),
    },
    "left_arm": {
        "top":    (308, 289, 371, 352),
        "front":  (308, 355, 371, 483),   # F — faces viewer
        "back":   (440, 355, 503, 483),   # B — faces away
        "right":  (374, 355, 437, 483),   # inner side (toward torso)
        "left":   (506, 355, 569, 483),   # outer side
        "bottom": (308, 485, 371, 549),
    },
}

PANTS_FACES = {
    "torso": {
        "top":    (231,   8, 359,  72),
        "front":  (231,  74, 359, 202),
        "right":  (165,  74, 229, 202),
        "left":   (361,  74, 425, 202),
        "back":   (427,  74, 555, 202),
        "bottom": (231, 204, 359, 268),
    },
    "right_leg": {
        "top":    (217, 289, 280, 352),
        "front":  (217, 355, 280, 483),
        "back":   ( 85, 355, 148, 483),
        "right":  ( 19, 355,  82, 483),
        "left":   (151, 355, 214, 483),
        "bottom": (217, 485, 280, 549),
    },
    "left_leg": {
        "top":    (308, 289, 371, 352),
        "front":  (308, 355, 371, 483),
        "back":   (440, 355, 503, 483),
        "right":  (374, 355, 437, 483),
        "left":   (506, 355, 569, 483),
        "bottom": (308, 485, 371, 549),
    },
}

# ── R6 part geometry (studs) ─────────────────────────────────────────────────
#   Legs:  y = 0–2   Arms/Torso: y = 2–4   Head: y = 4–5
R6_PARTS = {
    "head":      (( 0.0, 4.5, 0.0), (0.5, 0.5, 0.5)),
    "torso":     (( 0.0, 3.0, 0.0), (1.0, 1.0, 0.5)),
    "right_arm": ((-1.5, 3.0, 0.0), (0.5, 1.0, 0.5)),
    "left_arm":  (( 1.5, 3.0, 0.0), (0.5, 1.0, 0.5)),
    "right_leg": ((-0.5, 1.0, 0.0), (0.5, 1.0, 0.5)),
    "left_leg":  (( 0.5, 1.0, 0.0), (0.5, 1.0, 0.5)),
}

# ── UV helpers ────────────────────────────────────────────────────────────────

def _uv(px0, py0, px1, py1, face_name: str):
    """
    Convert a pixel rect (top-left origin) to 4 UV pairs for a quad.

    GL textures are stored bottom-row-first (after our FLIP_TOP_BOTTOM upload),
    so v=0 is the BOTTOM of the image and v=1 is the TOP.
    We therefore flip: v = 1 - py/TH.

    Vertex winding from _box_verts:
      side faces:   BL, BR, TR, TL  (CCW from outside)
      top face:     back-L, front-L, front-R, back-R
      bottom face:  front-L, back-L, back-R, front-R
    """
    u0 = px0 / TW;  u1 = px1 / TW
    v0 = 1.0 - py1 / TH   # py1 is bottom of pixel rect → v0 (GL bottom)
    v1 = 1.0 - py0 / TH   # py0 is top of pixel rect    → v1 (GL top)

    if face_name == "top":
        # back-L → front-L → front-R → back-R
        # map: left→u0, right→u1, back→v1(top), front→v0(bot)
        return [(u0, v1), (u0, v0), (u1, v0), (u1, v1)]
    elif face_name == "bottom":
        # front-L → back-L → back-R → front-R
        # map: left→u0, right→u1, front→v0(bot), back→v1(top)
        return [(u0, v0), (u0, v1), (u1, v1), (u1, v0)]
    else:
        # BL, BR, TR, TL
        return [(u0, v0), (u1, v0), (u1, v1), (u0, v1)]


def _box_verts(x0, y0, z0, x1, y1, z1):
    """
    Return list of (face_name, normal_xyz, [4 verts]) for a box.
    All faces wound CCW when viewed from outside (correct for back-face culling).
    """
    return [
        # name      normal         verts (CCW from outside)
        ("front",  (0, 0, 1),  [(x0,y0,z1),(x1,y0,z1),(x1,y1,z1),(x0,y1,z1)]),  # BL BR TR TL
        ("back",   (0, 0,-1),  [(x1,y0,z0),(x0,y0,z0),(x0,y1,z0),(x1,y1,z0)]),  # BL BR TR TL
        ("right",  (-1,0, 0),  [(x0,y0,z0),(x0,y0,z1),(x0,y1,z1),(x0,y1,z0)]),  # BL BR TR TL
        ("left",   ( 1,0, 0),  [(x1,y0,z1),(x1,y0,z0),(x1,y1,z0),(x1,y1,z1)]),  # BL BR TR TL
        ("top",    (0, 1, 0),  [(x0,y1,z0),(x0,y1,z1),(x1,y1,z1),(x1,y1,z0)]),  # bL fL fR bR
        ("bottom", (0,-1, 0),  [(x0,y0,z1),(x0,y0,z0),(x1,y0,z0),(x1,y0,z1)]),  # fL bL bR fR
    ]


def draw_part(cx, cy, cz, hw, hh, hd,
              shirt_faces, pants_faces,
              shirt_tex, pants_tex,
              skin_color=SKIN):
    """
    Draw one box body part with per-face texture mapping.
    Every face is drawn. Textured faces use the shirt or pants texture.
    Faces with no texture entry draw as solid skin_color.
    """
    if not OPENGL_AVAILABLE:
        return

    x0, x1 = cx - hw, cx + hw
    y0, y1 = cy - hh, cy + hh
    z0, z1 = cz - hd, cz + hd

    for fname, normal, verts in _box_verts(x0, y0, z0, x1, y1, z1):
        # Find texture for this face
        px_rect = None
        tex_id  = 0

        if shirt_faces and shirt_tex:
            rect = shirt_faces.get(fname)
            if rect:
                px_rect = rect
                tex_id  = shirt_tex

        if (not px_rect) and pants_faces and pants_tex:
            rect = pants_faces.get(fname)
            if rect:
                px_rect = rect
                tex_id  = pants_tex

        # Draw face — textured if we have a valid rect+tex, skin fallback otherwise
        if px_rect and tex_id:
            glEnable(GL_TEXTURE_2D)
            glBindTexture(GL_TEXTURE_2D, tex_id)
            glColor4f(1.0, 1.0, 1.0, 1.0)
            uvs = _uv(*px_rect, fname)
            glBegin(GL_QUADS)
            glNormal3f(*normal)
            for (u, v), vert in zip(uvs, verts):
                glTexCoord2f(u, v)
                glVertex3f(*vert)
            glEnd()
        else:
            glDisable(GL_TEXTURE_2D)
            glColor3f(*skin_color)
            glBegin(GL_QUADS)
            glNormal3f(*normal)
            for vert in verts:
                glVertex3f(*vert)
            glEnd()

    glDisable(GL_TEXTURE_2D)


# ── Camera ────────────────────────────────────────────────────────────────────

class Camera:
    def __init__(self):
        self.reset()

    def reset(self):
        self.azimuth   = 0.0
        self.elevation = 12.0
        self.distance  = 9.0
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


# ── Main widget ───────────────────────────────────────────────────────────────

class AvatarViewerWidget(QOpenGLWidget):
    """
    3D Roblox R6 avatar viewer.
    Left-drag = orbit · Right/Middle-drag = pan · Scroll = zoom · Dbl-click = reset
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
        self._skin_color   = SKIN

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
        self.makeCurrent()
        for tid in (self._shirt_tex_id, self._pants_tex_id):
            if tid:
                try: glDeleteTextures([tid])
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

    def set_ambient(self, v: float):   self._ambient = v;      self.update()
    def set_diffuse(self, v: float):   self._diffuse = v;      self.update()
    def set_show_grid(self, s: bool):  self._show_grid = s;    self.update()

    def set_skin_color(self, r: float, g: float, b: float):
        self._skin_color = (r, g, b)
        self.update()

    def set_auto_rotate(self, enabled: bool):
        self._auto_rotate = enabled
        if enabled: self._rot_timer.start(16)
        else:       self._rot_timer.stop()

    # ── Mouse ─────────────────────────────────────────────────────────────────

    def mousePressEvent(self, event: QMouseEvent):
        self._last_mouse   = event.pos()
        self._mouse_button = event.button()
        self.setCursor(Qt.CursorShape.ClosedHandCursor
                       if event.button() == Qt.MouseButton.LeftButton
                       else Qt.CursorShape.SizeAllCursor)

    def mouseMoveEvent(self, event: QMouseEvent):
        if self._last_mouse is None:
            return
        dx = event.pos().x() - self._last_mouse.x()
        dy = event.pos().y() - self._last_mouse.y()
        self._last_mouse = event.pos()
        if self._mouse_button == Qt.MouseButton.LeftButton:
            self._camera.orbit(dx * 0.4, -dy * 0.4)
        elif self._mouse_button in (Qt.MouseButton.RightButton,
                                    Qt.MouseButton.MiddleButton):
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
        delta = event.angleDelta().y() / 120.0
        self._camera.zoom(-delta * self._camera.distance * 0.08)
        self.update()

    # ── Private helpers ───────────────────────────────────────────────────────

    def _on_auto_rotate(self):
        self._camera.orbit(0.4, 0)
        self.update()

    def _upload_texture(self, img: Image.Image, old_id: int) -> int:
        if not OPENGL_AVAILABLE:
            return 0
        if old_id:
            try: glDeleteTextures([old_id])
            except: pass
        # Convert to RGBA, flip vertically (PIL top-left → GL bottom-left)
        img  = img.convert("RGBA").transpose(Image.FLIP_TOP_BOTTOM)
        data = np.ascontiguousarray(np.array(img, dtype=np.uint8))
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
        glColor4f(0.22, 0.22, 0.32, 0.5)
        glBegin(GL_LINES)
        for i in range(-8, 9):
            glVertex3f(float(i), 0.0, -8.0); glVertex3f(float(i), 0.0,  8.0)
            glVertex3f(-8.0, 0.0, float(i)); glVertex3f( 8.0, 0.0, float(i))
        glEnd()
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
        sk = self._skin_color

        for part, (center, half) in R6_PARTS.items():
            cx, cy, cz = center
            hw, hh, hd = half

            if part == "head":
                self._draw_head(cx, cy, cz, hw, hh, hd)
            elif part == "torso":
                draw_part(cx, cy, cz, hw, hh, hd,
                          SHIRT_FACES.get("torso"),
                          PANTS_FACES.get("torso"), s, p, sk)
            else:
                draw_part(cx, cy, cz, hw, hh, hd,
                          SHIRT_FACES.get(part),
                          PANTS_FACES.get(part), s, p, sk)

    def _draw_head(self, cx, cy, cz, hw, hh, hd):
        """Superellipsoid head (n=4 gives the classic rounded-box Roblox shape)."""
        if not OPENGL_AVAILABLE:
            return
        skin = self._skin_color
        SEGS_U, SEGS_V, N = 20, 16, 4.0

        def _sgn(v): return 1.0 if v >= 0 else -1.0

        def _se(u, v):
            cu, su = math.cos(u), math.sin(u)
            cv, sv = math.cos(v), math.sin(v)
            e = 2.0 / N
            def sp(val):
                a = abs(val)
                return _sgn(val) * (a ** e if a > 1e-9 else 0.0)
            px = hw * sp(cu) * sp(cv)
            py = hh * sp(sv)
            pz = hd * sp(su) * sp(cv)
            ne = N - 1.0
            nx = (abs(cu*cv)**ne * _sgn(cu*cv)) / (hw + 1e-9)
            ny = (abs(sv)    **ne * _sgn(sv))    / (hh + 1e-9)
            nz = (abs(su*cv)**ne * _sgn(su*cv)) / (hd + 1e-9)
            mag = math.sqrt(nx*nx + ny*ny + nz*nz) + 1e-9
            return (cx+px, cy+py, cz+pz), (nx/mag, ny/mag, nz/mag)

        glDisable(GL_TEXTURE_2D)
        glEnable(GL_LIGHTING)
        glColor3f(*skin)

        for j in range(SEGS_V):
            v0 = -math.pi/2 + math.pi *  j      / SEGS_V
            v1 = -math.pi/2 + math.pi * (j+1)   / SEGS_V
            for i in range(SEGS_U):
                u0 = 2*math.pi *  i      / SEGS_U
                u1 = 2*math.pi * (i+1)   / SEGS_U
                p00, n00 = _se(u0, v0)
                p01, n01 = _se(u1, v0)
                p10, n10 = _se(u0, v1)
                p11, n11 = _se(u1, v1)
                glBegin(GL_QUADS)
                glNormal3f(*n00); glVertex3f(*p00)
                glNormal3f(*n01); glVertex3f(*p01)
                glNormal3f(*n11); glVertex3f(*p11)
                glNormal3f(*n10); glVertex3f(*p10)
                glEnd()

        # Face features
        glDisable(GL_LIGHTING)
        ez = cz + hd + 0.006

        # Eyes
        glColor3f(0.08, 0.06, 0.05)
        for ecx in (cx - hw*0.27, cx + hw*0.27):
            ery, erx = hh*0.10, hw*0.09
            ey = cy + hh*0.08
            for i in range(14):
                a0 = 2*math.pi *  i      / 14
                a1 = 2*math.pi * (i+1)   / 14
                glBegin(GL_QUADS)
                glVertex3f(ecx, ey, ez)
                glVertex3f(ecx + erx*math.cos(a0), ey + ery*math.sin(a0), ez)
                glVertex3f(ecx + erx*math.cos(a1), ey + ery*math.sin(a1), ez)
                glVertex3f(ecx, ey, ez)
                glEnd()

        # Smile
        glColor3f(0.15, 0.08, 0.06)
        scx, scy = cx, cy - hh*0.22
        srx, sry, sth = hw*0.28, hh*0.13, hh*0.038
        a0, a1 = math.radians(210), math.radians(330)
        for i in range(14):
            t0 = a0 + (a1-a0)*i/14
            t1 = a0 + (a1-a0)*(i+1)/14
            glBegin(GL_QUADS)
            glVertex3f(scx+(srx+sth)*math.cos(t0), scy+(sry+sth)*math.sin(t0), ez)
            glVertex3f(scx+(srx+sth)*math.cos(t1), scy+(sry+sth)*math.sin(t1), ez)
            glVertex3f(scx+(srx-sth)*math.cos(t1), scy+(sry-sth)*math.sin(t1), ez)
            glVertex3f(scx+(srx-sth)*math.cos(t0), scy+(sry-sth)*math.sin(t0), ez)
            glEnd()

        glEnable(GL_LIGHTING)

    def _paint_fallback(self):
        from PyQt6.QtGui import QPainter, QColor, QFont
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(28, 28, 40))
        p.setPen(QColor(137, 180, 250))
        p.setFont(QFont("Arial", 13))
        p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter,
                   "3D Preview requires PyOpenGL\n\n"
                   "pip install PyOpenGL PyOpenGL_accelerate")
        p.end()
