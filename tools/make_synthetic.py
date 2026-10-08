r"""Synthetic IR cases for S-135: one case per op type or feature, so every one of the 20 op types and every
behaviour in cairo2d.py is exercised in isolation (the gallery and golden frames leave out ResetClip,
BeginGroup/EndGroup, erase, most blend modes and tint-with-erase).

    C:\Projects\playground\.venv\Scripts\python.exe tools/make_synthetic.py [case ...]

The ops are built directly from funground.ir and drawn by the real CairoRenderer (the reference, written as
ref.png: premultiplied RGB over black, as CairoRenderer.pixels() then capture() gives). The same ops go to
cases/<id>/ir.json for the browser. Pictures and pixel blocks are generated here (no files needed).
"""
from __future__ import annotations

import json
import math
import os
import shutil
import sys
import time
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
CORE = Path(os.environ.get("FUNGROUND_CORE", r"C:\Projects\playground-0.2"))
WEB = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(CORE))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from PIL import Image as PILImage  # noqa: E402

from funground import ir  # noqa: E402
from funground.color import Color  # noqa: E402
from funground.geometry import Path as GPath, Transform  # noqa: E402
from funground.paint import Gradient  # noqa: E402
from funground.picture import Snapshot  # noqa: E402
from funground.renderers.cairo2d import CairoRenderer  # noqa: E402
from funground.state import GraphicsState  # noqa: E402
from irenc import Encoder  # noqa: E402

C = Color
W, H = 400, 300
BG = C(250, 248, 240)
INK = C(30, 40, 90)
RED, GREEN, BLUE, GOLD, PINK, TEAL = C(220, 40, 40), C(40, 160, 80), C(40, 90, 220), C(240, 190, 20), C(230, 90, 160), C(20, 150, 150)


def st(fill=None, stroke=None, w=1, **kw) -> GraphicsState:
    return GraphicsState(fill=fill, stroke=stroke, stroke_width=w, **kw)


def clear(c=BG):
    return ir.Clear(c)


def lin(x1, y1, x2, y2, *stops):
    return Gradient("linear", (x1, y1, x2, y2), tuple((o, c) for o, c in stops))


def rad(x, y, r, *stops):
    return Gradient("radial", (x, y, r), tuple((o, c) for o, c in stops))


def poly(*pts, close=True):
    p = GPath().move_to(*pts[0])
    for q in pts[1:]:
        p = p.line_to(*q)
    return p.close() if close else p


def star(cx, cy, r1, r2, n=5):
    pts = []
    for i in range(2 * n):
        a = -math.pi / 2 + i * math.pi / n
        r = r1 if i % 2 == 0 else r2
        pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return poly(*pts)


def curve(x, y, w, h):
    return GPath().move_to(x, y + h).cubic_to(x + w * 0.2, y - h * 0.3, x + w * 0.6, y + h * 1.4, x + w, y)


def blob(path_ops=None):
    return None


# ---- picture helpers (premultiplied BGRA, like Cairo)
def make_pixels(w, h, fn):
    out = bytearray(w * h * 4)
    for y in range(h):
        for x in range(w):
            r, g, b, a = (int(v) for v in fn(x, y))
            i = (y * w + x) * 4
            out[i], out[i + 1], out[i + 2], out[i + 3] = (b * a + 127) // 255, (g * a + 127) // 255, (r * a + 127) // 255, a
    return bytes(out)


def pic_pattern(x, y):                     # checks, a colour ramp and a translucent disc
    d = math.hypot(x - 32, y - 32)
    if d < 14:
        return (255, 60, 40, 150)
    if (x // 8 + y // 8) % 2 == 0:
        return (int(x * 4), int(y * 4), 200, 255)
    return (30, 30, 60, 255)


def pic_photo(x, y):                       # smooth: a wavy colour field
    return (int(127 + 120 * math.sin(x / 9.0)), int(127 + 120 * math.sin(y / 7.0 + 1)), int(127 + 120 * math.cos((x + y) / 11.0)), 255)


def pic_alpha(x, y):                       # soft transparent edges
    d = math.hypot(x - 24, y - 24)
    return (255, 200, 40, max(0, min(255, int((24 - d) * 20))))


def snapshot(name, w, h, fn, scale=1.0):
    pw, ph = round(w * scale), round(h * scale)
    px = make_pixels(pw, ph, lambda x, y: fn(x / scale, y / scale))
    return Snapshot(name, 1, px, pw, ph, scale, w, h, None)


def image(snap, x, y, w, h, **kw):
    return ir.Image(snap.name, 1, x, y, w, h, snapshot=snap, **kw)


def pixels_op(x, y, w, h, fn, scale=1.0):
    pw, ph = round(w * scale), round(h * scale)
    bgra = make_pixels(pw, ph, lambda px, py: fn(px / scale, py / scale))
    return ir.Pixels(x, y, w, h, 0, ir.PixelBlock(scale, round(x * scale), round(y * scale), pw, ph, bgra))


def label(r, text, x, y, size=12, color=INK):
    return ir.Text(text, x, y, color, st(fill=color, text_size=size))


# =================================================================================== the cases
CASES = {}


def case(name, w=W, h=H, scale=1.0):
    def deco(fn):
        CASES[name] = (fn, w, h, scale)
        return fn
    return deco


@case("syn-clear")
def _(r):
    return [clear(C(255, 255, 255)),
            ir.Rect(20, 20, 150, 100, st(RED, INK, 4)),
            ir.Save(), ir.ClipPath(poly((250, 20), (380, 20), (380, 120), (250, 120))),
            ir.Clear(C(60, 120, 200, 255)),           # SOURCE over everything, ignoring the clip
            ir.Restore(),
            ir.Circle(80, 200, 60, st(GOLD, INK, 3)),
            ir.Clear(lin(0, 150, 0, 300, (0, C(255, 255, 255, 0)), (1, C(0, 0, 0, 200))))]   # gradient with alpha


@case("syn-shapes")
def _(r):
    ops = [clear()]
    ops += [ir.Circle(50.5, 50.25, 60, st(RED, INK, 3)), ir.Circle(130, 50, 40.5, st(None, INK, 1)), ir.Circle(190, 50, 30, st(GOLD, None)),
            ir.Circle(240, 50, 0, st(RED, INK, 4)),
            ir.Ellipse(300, 50, 90, 40, st(GREEN, INK, 2)), ir.Ellipse(300, 110, 0, 40, st(GREEN, INK, 2)),
            ir.Rect(20.3, 110.7, 80.4, 50.6, st(BLUE, INK, 5)), ir.Rect(120, 110, 70, 50, st(PINK, None), radii=(20, 0, 20, 0)),
            ir.Rect(210, 110, 70, 50, st(TEAL, INK, 3), radii=(12, 12, 12, 12)),
            ir.Rect(20, 180, 100, 40, st(C(200, 0, 100, 128), C(0, 0, 0, 128), 8)),
            ir.Line(140, 180, 260, 230, st(None, RED, 6)), ir.Line(140, 230, 260, 180, st(None, BLUE, 1)),
            ir.Line(280, 180, 380, 180, st(None, INK, 12, stroke_cap="butt")),
            ir.Line(280, 200, 380, 200, st(None, INK, 12, stroke_cap="square")),
            ir.Line(280, 220, 380, 220, st(None, INK, 12, stroke_cap="round")),
            ir.Point(30, 260, st(None, INK, 1)), ir.Point(50, 260, st(None, INK, 6)), ir.Point(80, 260, st(None, RED, 14)),
            ir.Point(110, 260.5, st(None, BLUE, 0)), ir.Point(150.5, 260.5, st(None, INK, 3))]
    return ops


@case("syn-strokes")
def _(r):
    ops = [clear()]
    zig = lambda x, y: GPath().move_to(x, y + 40).line_to(x + 30, y).line_to(x + 60, y + 40).line_to(x + 90, y)
    for i, cap in enumerate(("butt", "round", "square")):
        ops.append(ir.StrokePath(GPath().move_to(20, 30 + i * 25).line_to(110, 30 + i * 25), INK, 14, cap=cap))
    for i, join in enumerate(("miter", "round", "bevel")):
        ops.append(ir.StrokePath(zig(130 + i * 90, 20), RED, 12, cap="butt", join=join))
    for i, ml in enumerate((1.0, 2.0, 10.0)):
        ops.append(ir.StrokePath(poly((20 + i * 100, 140), (60 + i * 100, 110), (100 + i * 100, 140), close=False), BLUE, 8, cap="butt", join="miter", miter_limit=ml))
    ops += [ir.StrokePath(GPath().move_to(20, 170).line_to(380, 170), INK, 3, dash=(10, 6)),
            ir.StrokePath(GPath().move_to(20, 185).line_to(380, 185), INK, 3, dash=(10, 6), dash_offset=7),
            ir.StrokePath(GPath().move_to(20, 200).line_to(380, 200), INK, 6, cap="round", dash=(0.1, 12)),
            ir.StrokePath(GPath().move_to(20, 215).line_to(380, 215), INK, 4, cap="butt", dash=(20, 5, 2, 5)),
            ir.StrokePath(GPath().move_to(20, 230).line_to(380, 230), INK, 4, cap="square", dash=(8, 8, 3)),
            ir.StrokePath(curve(20, 245, 200, 30), TEAL, 5, cap="round", dash=(14, 8)),
            ir.StrokePath(star(320, 262, 32, 13), GOLD, 5, join="miter", cap="butt"),
            ir.Line(240, 250, 290, 285, st(None, RED, 7, stroke_cap="butt", dash=(9, 5), dash_offset=2)),
            ir.Rect(200, 240, 30, 40, st(None, BLUE, 5, stroke_join="miter", miter_limit=4)),
            ir.Rect(240, 288, 20, 8, st(PINK, INK, 3, stroke_join="bevel"))]
    return ops


@case("syn-fillpath")
def _(r):
    box = lambda x, y, s, rev=False: poly(*(((x, y), (x + s, y), (x + s, y + s), (x, y + s)) if not rev else ((x, y), (x, y + s), (x + s, y + s), (x + s, y))))
    outer = box(20, 20, 100)
    hole_same = outer.add_path(box(45, 45, 50)) if hasattr(outer, "add_path") else None
    ops = [clear(), ir.FillPath(star(70, 70, 60, 24), RED), ir.StrokePath(star(70, 70, 60, 24), INK, 2)]
    # a star through its points (self-intersecting): non-zero fill leaves the centre filled
    pts = [(180 + 50 * math.cos(-math.pi / 2 + i * 4 * math.pi / 5), 70 + 50 * math.sin(-math.pi / 2 + i * 4 * math.pi / 5)) for i in range(5)]
    ops.append(ir.FillPath(poly(*pts), BLUE))
    # a ring: outer clockwise, inner counter-clockwise (a hole); and the same direction (no hole)
    ring = box(260, 20, 100)
    ring = GPath(tuple(ring.segments) + tuple(box(285, 45, 50, rev=True).segments))
    ops.append(ir.FillPath(ring, GREEN))
    same = GPath(tuple(box(20, 160, 100).segments) + tuple(box(45, 185, 50).segments))
    ops.append(ir.FillPath(same, GOLD))
    ops.append(ir.FillPath(curve(150, 160, 120, 60).line_to(270, 230).line_to(150, 230).close(), PINK))
    ops.append(ir.FillPath(GPath().move_to(300, 160).cubic_to(380, 160, 380, 240, 300, 240).cubic_to(330, 200, 330, 200, 300, 160).close(), C(20, 150, 150, 200)))
    ops.append(ir.FillPath(poly((20, 260), (380, 262), (380, 262.5), (20, 261)), INK))     # a sliver
    ops.append(ir.FillPath(GPath().move_to(100, 280).line_to(120, 280).line_to(110, 290), INK))   # an unclosed fill
    return ops


@case("syn-transforms")
def _(r):
    T = lambda a, b, c, d, e, f: Transform(a, b, c, d, e, f)
    rot = lambda t: T(math.cos(t), math.sin(t), -math.sin(t), math.cos(t), 0, 0)
    ops = [clear(), ir.Save(), ir.Concat(T(1, 0, 0, 1, 70, 70))]
    for i in range(8):
        ops += [ir.Save(), ir.Concat(rot(i * math.pi / 4)), ir.Concat(T(1, 0, 0, 1, 30, 0)), ir.Rect(-10, -10, 20, 20, st(C(40 + i * 25, 90, 200 - i * 20, 220), INK, 2)), ir.Restore()]
    ops += [ir.Restore(),
            ir.Save(), ir.Concat(T(1, 0, 0, 1, 180, 20)), ir.Concat(T(2.5, 0, 0, 0.5, 0, 0)), ir.Circle(20, 20, 30, st(GOLD, INK, 6)), ir.Restore(),       # non-uniform scale: stroke is squashed
            ir.Save(), ir.Concat(T(1, 0, 0.7, 1, 260, 20)), ir.Rect(0, 0, 60, 60, st(PINK, INK, 4)), ir.Restore(),                                       # shear
            ir.Save(), ir.Concat(T(1, 0, 0, 1, 200, 160)), ir.Concat(rot(0.4)), ir.Save(), ir.ResetMatrix(), ir.Rect(10, 140, 60, 40, st(RED, INK, 2)), ir.Restore(), ir.Rect(0, 0, 50, 50, st(BLUE, None)), ir.Restore(),   # reset_matrix inside a transform
            ir.Save(), ir.Concat(T(-1, 0, 0, 1, 380, 0)), ir.Rect(20, 200, 80, 30, st(GREEN, INK, 3)), ir.Line(20, 250, 100, 280, st(None, RED, 5)), ir.Restore(),   # mirror
            ir.Save(), ir.Concat(T(0.5, 0, 0, 0.5, 20, 150)), ir.Concat(T(1, 0, 0, 1, 40, 40)), ir.Concat(rot(0.2)), ir.Ellipse(80, 40, 120, 60, st(TEAL, INK, 8)), ir.Restore(),
            ir.Rect(150, 260, 50, 30, st(None, INK, 2))]
    return ops


@case("syn-clip")
def _(r):
    T = Transform
    big = poly((0, 0), (400, 0), (400, 300), (0, 300))
    ops = [clear(),
           # a clip, drawing inside it, restore returns the clip to none
           ir.Save(), ir.ClipPath(GPath.rect(20, 20, 100, 100) if hasattr(GPath, "rect") else poly((20, 20), (120, 20), (120, 120), (20, 120))),
           ir.Circle(70, 70, 140, st(RED, INK, 4)), ir.Restore(), ir.Circle(70, 140, 20, st(GOLD, INK, 1)),
           # nested clips intersect
           ir.Save(), ir.ClipPath(star(210, 70, 60, 30)), ir.ClipPath(poly((150, 70), (270, 70), (270, 140), (150, 140))),
           ir.Rect(140, 10, 140, 140, st(BLUE, None)), ir.Restore(),
           # clip under a transform
           ir.Save(), ir.Concat(T(0.8, 0.6, -0.6, 0.8, 330, 20)), ir.ClipPath(poly((0, 0), (50, 0), (50, 50), (0, 50))), ir.Concat(T(1, 0, 0, 1, 0, 0)), ir.Rect(-20, -20, 100, 100, st(GREEN, INK, 3)), ir.Restore(),
           # reset_clip inside a saved state, then restore brings the outer clip back
           ir.Save(), ir.ClipPath(poly((20, 160), (180, 160), (180, 240), (20, 240))), ir.Rect(0, 150, 200, 20, st(PINK, None)),
           ir.Save(), ir.ResetClip(), ir.Rect(60, 200, 40, 90, st(TEAL, None)), ir.Save(), ir.Concat(T(1, 0, 0, 1, 20, 0)), ir.Rect(110, 200, 20, 90, st(GOLD, None)), ir.Restore(),
           ir.Restore(), ir.Rect(120, 210, 20, 60, st(INK, None)), ir.Restore(),
           # a clip, then Clear (ignores clips), then a Pixels-free frame check: draw after clear inside another clip
           ir.Save(), ir.ClipPath(poly((230, 170), (380, 170), (380, 290), (230, 290))), ir.ResetClip(), ir.ClipPath(poly((260, 190), (360, 190), (360, 270), (260, 270))),
           ir.Circle(310, 230, 120, st(C(255, 120, 0, 200), INK, 5)), ir.Restore()]
    return ops


@case("syn-gradients")
def _(r):
    ops = [clear(),
           ir.Rect(20, 20, 160, 100, st(lin(20, 20, 180, 20, (0, RED), (0.5, GOLD), (1, BLUE)), INK, 2)),
           ir.Circle(260, 70, 100, st(rad(260, 70, 50, (0, C(255, 255, 255)), (1, C(40, 60, 160))), None)),
           ir.Ellipse(350, 70, 50, 90, st(lin(0, 20, 0, 120, (0, GREEN), (1, C(0, 80, 40, 0))), None)),     # alpha stop
           ir.FillPath(star(80, 200, 60, 25), lin(20, 150, 140, 250, (0, PINK), (1, TEAL))),
           ir.StrokePath(curve(160, 160, 100, 60), lin(160, 0, 260, 0, (0, RED), (1, BLUE)), 12, cap="round"),
           ir.Rect(160, 230, 100, 50, st(rad(210, 255, 60, (0, C(255, 255, 0, 255)), (0.4, C(255, 0, 0, 128)), (1, C(0, 0, 255, 0))), None)),
           ir.Save(), ir.Concat(Transform(1, 0, 0, 1, 300, 170)), ir.Concat(Transform(0.7, 0.7, -0.7, 0.7, 0, 0)), ir.Rect(0, 0, 70, 70, st(lin(0, 0, 70, 0, (0, C(0, 0, 0)), (1, C(255, 255, 255))), INK, 2)), ir.Restore(),
           ir.Rect(20, 270, 120, 20, st(lin(20, 0, 140, 0, (0, C(255, 0, 0, 255)), (1, C(0, 0, 255, 0))), None)),
           ir.Rect(280, 250, 100, 40, st(lin(280, 0, 380, 0, (0, RED), (1, BLUE)), None, opacity=100))]
    return ops


@case("syn-blend")
def _(r):
    modes = ["normal", "multiply", "screen", "overlay", "darken", "lighten", "add", "difference", "exclusion", "dodge", "burn", "hard_light", "soft_light", "hue", "saturation", "color", "luminosity"]
    ops = [clear(C(200, 170, 120))]
    ops += [ir.Rect(0, 0, 400, 150, st(lin(0, 0, 400, 0, (0, C(255, 80, 40)), (0.5, C(60, 200, 90)), (1, C(40, 70, 220))), None))]
    for i, m in enumerate(modes):
        col, row = i % 6, i // 6
        x, y = 12 + col * 64, 30 + row * 95
        ops += [ir.Rect(x, y, 56, 56, st(C(180, 90, 200, 230), INK, 3, blend_mode=m)),
                ir.Circle(x + 28, y + 70, 30, st(C(255, 210, 60), None, blend_mode=m, opacity=150))]
    return ops


@case("syn-opacity")
def _(r):
    ops = [clear()]
    for i, a in enumerate((255, 200, 140, 80, 30)):
        ops += [ir.Rect(20 + i * 50, 20, 60, 60, st(RED, INK, 4, opacity=a)), ir.Circle(50 + i * 50, 120, 50, st(BLUE, GOLD, 6, opacity=a))]
    ops += [ir.FillPath(star(80, 220, 50, 20), GREEN, opacity=128), ir.StrokePath(curve(150, 190, 200, 60), INK, 10, opacity=100),
            label(r, "opacity text", 150, 250, 28), ir.Line(20, 280, 380, 280, st(None, INK, 10, opacity=60)),
            ir.Text("half", 300, 215, C(200, 0, 100), st(C(200, 0, 100), text_size=40, opacity=120))]
    return ops


@case("syn-shadow")
def _(r):
    sh = lambda dx, dy, b, c=C(0, 0, 0, 160): (dx, dy, b, c)
    ops = [clear(C(235, 240, 235))]
    ops += [ir.Circle(70, 70, 70, st(GOLD, None, shadow=sh(6, 8, 0))), ir.Circle(170, 70, 70, st(GOLD, INK, 4, shadow=sh(8, 8, 10))),
            ir.Rect(240, 30, 100, 80, st(TEAL, INK, 3, shadow=sh(0, 0, 20, C(0, 0, 0, 255)))),
            ir.Rect(20, 150, 100, 60, st(PINK, None, shadow=sh(10, 10, 6, C(40, 0, 120, 200)), opacity=180), radii=(15, 15, 15, 15)),
            ir.FillPath(star(190, 180, 45, 20), RED, shadow=sh(8, 6, 8)),
            ir.StrokePath(curve(250, 160, 120, 50), BLUE, 8, shadow=sh(5, 12, 4)),
            ir.Line(30, 250, 120, 280, st(None, INK, 6, shadow=sh(5, 5, 5))), ir.Point(150, 265, st(None, RED, 16, shadow=sh(6, 6, 6))),
            ir.Text("Shadow", 200, 235, INK, st(INK, text_size=44, shadow=sh(4, 5, 5))),
            ir.Save(), ir.Concat(Transform(1.5, 0, 0, 1.5, 300, 240)), ir.Rect(0, 0, 30, 20, st(GREEN, None, shadow=sh(4, 4, 4))), ir.Restore(),
            ir.Rect(340, 250, 40, 40, st(C(255, 120, 0), None, blend_mode="add", shadow=sh(0, 0, 8, C(255, 255, 255, 200))))]
    return ops


@case("syn-erase")
def _(r):
    ops = [clear(C(255, 255, 255)), ir.Rect(0, 0, 400, 300, st(lin(0, 0, 400, 300, (0, RED), (1, BLUE)), None))]
    snap = snapshot("graphics-1", 64, 64, pic_alpha if False else pic_pattern)
    ops += [ir.FillPath(star(70, 70, 50, 22), BLUE, erase=255), ir.FillPath(star(190, 70, 50, 22), BLUE, erase=110),
            ir.StrokePath(curve(250, 50, 130, 50), RED, 12, erase=255), ir.StrokePath(curve(250, 90, 130, 50), RED, 12, erase=90, dash=(10, 8)),
            ir.Circle(70, 190, 60, st(RED, INK, 8, erasing=(255, 120))), ir.Rect(130, 160, 70, 60, st(RED, INK, 6, erasing=(150, 255))),
            ir.Text("ERASE", 210, 170, INK, st(INK, text_size=48, erasing=(255, 0))),
            ir.Line(20, 260, 380, 290, st(None, INK, 14, erasing=(0, 200))), ir.Point(40, 240, st(None, INK, 16, erasing=(0, 255))),
            image(snap, 330, 150, 64, 64, erase=255), image(snap, 330, 225, 64, 64, erase=130)]
    return ops


@case("syn-groups")
def _(r):
    ops = [clear(C(240, 235, 225))]
    three = lambda cx, cy: [ir.Circle(cx - 18, cy, 50, st(RED, None)), ir.Circle(cx + 18, cy, 50, st(BLUE, None)), ir.Circle(cx, cy + 28, 50, st(GREEN, None))]
    ops += [ir.BeginGroup(0.5, "normal", ()), *three(70, 60), ir.EndGroup()]
    ops += [*[ir.Circle(*(c.x, c.y, c.diameter), st(c.style.fill, None, opacity=128)) for c in three(180, 60)]]              # no group: overlaps show through
    ops += [ir.BeginGroup(0.6, "multiply", (230, 10, 150, 130)), *three(290, 60), ir.EndGroup()]
    ops += [ir.Rect(20, 150, 360, 30, st(lin(20, 0, 380, 0, (0, GOLD), (1, TEAL)), None))]
    # nested groups: inner at 0.5, outer at 0.7; with a transform and a clip around
    ops += [ir.Save(), ir.Concat(Transform(1, 0, 0, 1, 30, 140)), ir.BeginGroup(0.7, "normal", (-10, -10, 200, 150)),
            ir.Rect(0, 0, 100, 80, st(RED, INK, 4)), ir.BeginGroup(0.5, "screen", (40, 20, 120, 100)), ir.Circle(90, 70, 90, st(C(30, 120, 255), INK, 6)), ir.EndGroup(), ir.EndGroup(), ir.Restore()]
    ops += [ir.Save(), ir.ClipPath(star(300, 230, 55, 28)), ir.BeginGroup(0.8, "normal", (240, 170, 120, 120)), *three(300, 215), ir.EndGroup(), ir.Restore()]
    # a group that erases inside (a mark that removes ink) and one with a ResetClip inside
    ops += [ir.BeginGroup(1.0, "normal", (150, 190, 100, 100)), ir.Rect(150, 190, 100, 90, st(PINK, None)), ir.Circle(200, 235, 60, st(None, None, erasing=(255, 0))),
            ir.Save(), ir.ClipPath(poly((150, 190), (200, 190), (200, 240))), ir.ResetClip(), ir.Line(150, 280, 250, 280, st(None, INK, 6)), ir.Restore(), ir.EndGroup()]
    return ops


@case("syn-antialias")
def _(r):
    T = Transform
    ops = [clear(), ir.SetAntialias(False)]
    ops += [ir.Rect(10.3, 10.6, 50.5, 30.2, st(RED, None)), ir.Rect(70, 10, 40.4, 40.4, st(BLUE, None)),
            ir.Circle(150, 30, 40, st(GREEN, None)), ir.Line(10, 70, 100, 100, st(None, INK, 1)), ir.Ellipse(180, 80, 60, 30, st(GOLD, INK, 1)),
            ir.FillPath(star(250, 40, 35, 15), PINK), ir.Rect(290, 10, 40, 40, st(None, INK, 1)),
            ir.Save(), ir.Concat(T(1, 0, 0, 1, 20, 120)), ir.Concat(T(4, 0, 0, 4, 0, 0)),
            *[ir.Rect(x, y, 1, 1, st(C(40 * ((x + y) % 6), 100, 200), None)) for y in range(10) for x in range(14) if (x * 7 + y * 3) % 5 < 3], ir.Restore(),
            ir.Save(), ir.SetAntialias(True), ir.Circle(300, 90, 40, st(TEAL, INK, 2)), ir.Restore(),
            ir.Circle(350, 90, 30, st(RED, None))]
    snap = snapshot("graphics-1", 16, 16, lambda x, y: ((x * 16) % 256, (y * 16) % 256, 150, 255))
    ops += [image(snap, 200, 170, 96, 96), image(snap, 310, 170, 16, 16)]
    ops += [ir.SetAntialias(True), image(snap, 200, 270, 24, 24)]
    return ops


@case("syn-images")
def _(r):
    pat = snapshot("graphics-1", 64, 64, pic_pattern)
    photo = snapshot("graphics-2", 96, 72, pic_photo)
    soft = snapshot("graphics-3", 48, 48, pic_alpha)
    ops = [clear(C(220, 225, 235)), ir.Rect(0, 150, 400, 40, st(C(255, 255, 255), None))]
    ops += [image(pat, 10, 10, 64, 64), image(pat, 90, 10, 100, 100), image(pat, 200, 12.5, 30.5, 30.5),
            image(photo, 240, 10, 144, 108), image(photo, 10, 120, 48, 36),
            image(photo, 70, 118, 20.4, 15.3), image(soft, 100, 125, 48, 48), image(soft, 160, 120, 96, 96),
            image(pat, 270, 130, 50, 50, opacity=120), image(pat, 330, 130, 50, 50, blend_mode="multiply"),
            image(pat, 10, 200, 64, 64, tint=C(255, 120, 120, 255)), image(pat, 80, 200, 64, 64, tint=C(80, 160, 255, 140)),
            image(soft, 150, 220, 48, 48, tint=C(40, 200, 90, 255)),
            image(photo, 210, 200, 60, 60, sx=20, sy=10, sw=30, sh=30), image(photo, 280, 200, 100, 40, sx=0, sy=0, sw=96, sh=72),
            image(pat, 280, 250, 40, 40, sx=8, sy=8, sw=24, sh=24, tint=C(255, 255, 0, 255), opacity=200),
            ir.Save(), ir.Concat(Transform(0.9, 0.4, -0.4, 0.9, 340, 235)), image(pat, 0, 0, 40, 40), ir.Restore(),
            ir.Save(), ir.ClipPath(star(70, 280, 28, 14)), image(photo, 30, 245, 80, 60), ir.Restore()]
    return ops


@case("syn-pixels")
def _(r):
    cell = lambda x, y: (255, 80, 40, 255) if (int(x) // 2 + int(y) // 2) % 2 else (40, 80, 255, 255)
    hole = lambda x, y: (0, 0, 0, 0) if math.hypot(x - 20, y - 20) < 12 else (30, 160, 90, 255)
    semi = lambda x, y: (255, 220, 40, 120)
    ops = [clear(C(250, 240, 230)), ir.Rect(0, 0, 400, 100, st(lin(0, 0, 400, 0, (0, PINK), (1, TEAL)), None)),
           pixels_op(20, 20, 24, 24, cell), pixels_op(60, 20, 40, 40, hole),            # replaces, so the hole is transparent
           pixels_op(120, 20, 40, 40, semi),
           ir.Save(), ir.ClipPath(poly((190, 10), (230, 10), (230, 50), (190, 50))), ir.Concat(Transform(0.5, 0, 0, 0.5, 100, 100)), ir.Concat(Transform(1, 0, 0, 1, 200, 40)),
           pixels_op(180, 20, 60, 40, cell), ir.Restore(),                                      # ignores clip and transform
           ir.Circle(300, 70, 70, st(RED, INK, 4, opacity=100)), pixels_op(280, 40, 40, 20, lambda x, y: (10, 10, 10, 255) if x % 8 < 4 else (240, 240, 240, 255)),
           pixels_op(20, 150, 100, 60, lambda x, y: (int(x * 2.5), int(y * 4), 128, 255))]
    return ops


@case("syn-pixels-2x", scale=2.0, w=200, h=150)
def _(r):
    cell = lambda x, y: (255, 80, 40, 255) if (int(x) // 2 + int(y) // 2) % 2 else (40, 80, 255, 255)
    return [clear(C(250, 240, 230)), ir.Circle(100, 40, 80, st(GREEN, INK, 3)),
            pixels_op(10, 10, 24, 24, cell, 2.0), pixels_op(40, 60, 30, 20, lambda x, y: (0, 0, 0, 0) if x < 15 else (255, 255, 0, 255), 2.0),
            ir.Save(), ir.ClipPath(poly((120, 90), (150, 90), (150, 120), (120, 120))), pixels_op(130, 100, 20, 20, cell, 2.0), ir.Restore()]


@case("syn-text")
def _(r):
    ops = [clear(C(255, 255, 255))]
    for i, (s, size) in enumerate([("Hamburgefonstiv 12", 12), ("Hamburgefonstiv 18", 18), ("Hamburg 28", 28), ("Hy 64", 64)]):
        ops.append(ir.Text(s, 14, [10, 36, 66, 110][i], INK, st(INK, text_size=size)))
    ops += [ir.Text("Gradient text", 14, 190, lin(14, 0, 300, 0, (0, RED), (1, BLUE)), st(None, text_size=40)),
            ir.Save(), ir.Concat(Transform(0.9, 0.3, -0.3, 0.9, 250, 215)), ir.Text("rotated", 0, 0, TEAL, st(TEAL, text_size=30)), ir.Restore(),
            ir.Text("नमस्ते 😀 ★", 14, 250, INK, st(INK, text_size=32)),
            ir.Save(), ir.ClipPath(ir_circle_path(260, 70, 50)), ir.Text("clipped", 200, 40, RED, st(RED, text_size=44)), ir.Restore()]
    return ops


def ir_circle_path(cx, cy, r):
    return GPath.ellipse(cx, cy, r, r)


@case("syn-hidpi", scale=2.0, w=200, h=150)
def _(r):
    pat = snapshot("graphics-1", 32, 32, pic_pattern, 2.0)
    return [clear(), ir.Circle(40, 40, 50, st(RED, INK, 3)), ir.Rect(80.5, 20.5, 50, 30, st(BLUE, INK, 1), radii=(8, 8, 8, 8)),
            ir.Line(10, 80, 110, 100, st(None, INK, 1.5, stroke_cap="butt")), ir.StrokePath(curve(120, 60, 70, 40), TEAL, 2, dash=(5, 3)),
            ir.Text("HiDPI", 10, 100, INK, st(INK, text_size=18)),
            ir.Save(), ir.ClipPath(star(160, 110, 30, 14)), ir.Rect(120, 80, 80, 60, st(lin(120, 0, 200, 0, (0, GOLD), (1, PINK)), None)), ir.Restore(),
            image(pat, 150, 10, 40, 40), ir.BeginGroup(0.5, "normal", (10, 105, 60, 40)), ir.Circle(30, 125, 30, st(GREEN, None)), ir.Circle(45, 125, 30, st(BLUE, None)), ir.EndGroup(),
            ir.Circle(95, 125, 30, st(GOLD, None, shadow=(3, 3, 4, C(0, 0, 0, 150))))]


# =================================================================================== driver
def build(name: str) -> dict:
    fn, w, h, scale = CASES[name]
    out = WEB / "cases" / name
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    ren = CairoRenderer()
    ren.attach(round(w * scale), round(h * scale), scale)
    ops = fn(ren)
    ren.render(ir.Frame(ops))
    px = ren.pixels()
    data = bytes(px.data)                      # the reference is the first render
    t0 = time.perf_counter()
    for _ in range(3):                         # timing: warm (text runs cached), best of 3
        t = time.perf_counter()
        ren.render(ir.Frame(ops))
        cairo_ms = min(locals().get("cairo_ms", 1e9), (time.perf_counter() - t) * 1000)
    rgb = bytearray(px.width * px.height * 3)
    rgb[0::3], rgb[1::3], rgb[2::3] = data[2::4], data[1::4], data[0::4]
    PILImage.frombytes("RGB", (px.width, px.height), bytes(rgb)).save(out / "ref.png")
    enc = Encoder(out, ren)
    doc = {"case": name, "width": w, "height": h, "scale": scale, "script": False,
           "steps": [{"k": "frame", "ops": [enc.op(o) for o in ops]}], "overlay": None, "cairo_ms": cairo_ms,
           "final_frame_ops": len(ops), "rerun_equals_golden": None, "files": sorted(enc.files), "synthetic": True}
    (out / "ir.json").write_text(json.dumps(doc, separators=(",", ":")), encoding="utf-8")
    kinds = sorted({type(o).__name__ for o in ops})
    return {"case": name, "ops": kinds, "cairo_ms": round(cairo_ms, 2)}


if __name__ == "__main__":
    names = sys.argv[1:] or list(CASES)
    for n in names:
        try:
            print("ok  ", build(n))
        except Exception as e:                     # keep going: report which case broke
            import traceback
            traceback.print_exc()
            print("FAIL", n, e)
