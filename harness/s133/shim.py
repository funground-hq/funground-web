"""S-133 (from S-136): what funground needs to run in Pyodide without pycairo, uharfbuzz, skia-pathops or pygame.

Runs inside the module worker, after the funground source is unpacked at /src. Nothing here changes
funground's files; it installs stand-ins in sys.modules, then builds a Sketch with a BrowserPlatform and
an IR-capturing renderer, and drives it with start()/step()/finish() (D-074, L1).

Every stand-in is listed in S-136_RESULTS.md ("What needed a stub").
"""
from __future__ import annotations

import json
import sys
import time
import types

sys.path.insert(0, "/src")
perf = time.perf_counter


class _Names:
    """An enum stand-in: any member name answers a placeholder (pathops.py reads three enums at load time)."""

    def __getattr__(self, attr):
        return attr


# ---- 1. modules funground imports at load time that Pyodide does not have ---------------------------------
def _unavailable(name: str, why: str, **present) -> types.ModuleType:
    mod = types.ModuleType(name)
    mod.__dict__.update(present)             # names the importing module reads at load time

    def __getattr__(attr: str):
        raise ImportError(f"{name}.{attr} is not available in the browser build yet ({why})")

    mod.__getattr__ = __getattr__
    return mod


# uharfbuzz: not stubbed in S-133. /src/uharfbuzz.py is shim/uharfbuzz.py (harfbuzzjs), so text works.
sys.modules["pathops"] = _unavailable("pathops", "no Emscripten wheel: path booleans", PathVerb=_Names(), LineCap=_Names(), LineJoin=_Names())       # pathops.py: import pathops as _sk


# ---- 2. the renderer: records the frame's ops instead of drawing them -------------------------------------
class IrPixels:
    """What IrRenderer.pixels() returns: no pixels, the frame's ops. (Pixels is the Platform's currency.)"""

    format = "IR"
    data = b""

    def __init__(self, width, height, ops):
        self.width, self.height, self.ops = width, height, ops


def _make_renderer_class():
    from funground.capabilities import Capability

    class IrRenderer:
        """A Renderer (renderers/__init__.py) whose "surface" is the list of ops of the latest frame.

        Enough for sketches that draw shapes, colour, transforms and clips; not for pictures, pixels,
        text (needs uharfbuzz) or file export, which need pixels or Cairo."""

        name = "ir"
        capabilities = frozenset({
            Capability.RASTER_2D, Capability.ALPHA, Capability.ANTIALIAS, Capability.TRANSFORMS,
            Capability.VECTOR_PATHS, Capability.CLIP_PATH, Capability.TEXT_OUTLINES,
        })

        def __init__(self):
            self._scale = 1.0
            self._w = self._h = 0
            self.ops = ()

        def attach(self, width, height, scale=1.0):
            self._w, self._h, self._scale = width, height, scale
            self.ops = ()

        def render(self, frame):
            self.ops = tuple(frame)

        def pixels(self):
            return IrPixels(self._w, self._h, self.ops)

        def ink_bounds(self, ops):
            raise NotImplementedError("ink_bounds needs Cairo (marks)")

    return IrRenderer


# funground/picture.py does `from .renderers.cairo2d import CairoRenderer` at import time, and cairo2d
# imports cairo. This stand-in module answers CairoRenderer lazily with the IR renderer.
_stub = types.ModuleType("funground.renderers.cairo2d")
_stub.__getattr__ = lambda name: _make_renderer_class() if name == "CairoRenderer" else (_ for _ in ()).throw(AttributeError(name))
sys.modules["funground.renderers.cairo2d"] = _stub


# ---- 3. the platform: input from the page, time from the page, frames out to the page ---------------------
def _make_platform_class():
    from funground.platform.headless import HeadlessPlatform
    from funground.platform.base import InputEvent

    class BrowserPlatform(HeadlessPlatform):
        """The Platform protocol for a page that drives the loop.

        Inherits the headless platform's event queue and polled state (post/poll/input_state/key_down)
        because that already is "input arrives from outside". Differences:
          - tick() never waits and measures with the page's requestAnimationFrame timestamps;
          - present() keeps the frame's ops for the page;
          - a space key counts as the name "space" too (pygame reports " " and answers key_down("space"));
          - Escape does not end the sketch (the page has a Stop button).
        """

        def __init__(self):
            super().__init__()
            self.now = None            # seconds, set by the host before each step
            self._prev = None
            self.ops = ()

        def start(self):
            self._prev = None

        def poll(self):
            super().poll()
            for ev in self._events:
                if ev.key == " " and ev.kind == "key_pressed":
                    self._keys.add("space")
                elif ev.key == " " and ev.kind == "key_released":
                    self._keys.discard("space")
            return True

        def present(self, pixels):
            self.ops = pixels.ops

        def tick(self, fps):
            dt = (self.now - self._prev) if self._prev is not None else 1.0 / fps
            self._prev = self.now
            return dt

        def capture(self):
            return ((self._size[0], self._size[1]), b"")

        def close(self):
            self.ops = ()

    return BrowserPlatform, InputEvent


# ---- 4. the host the worker calls ---------------------------------------------------------------------------
class Host:
    def __init__(self, source: str, name: str):
        t0 = perf()
        import funground
        from funground import api, ir
        from funground.sketch import Sketch

        self.ir = ir
        Platform, self.InputEvent = _make_platform_class()
        self.platform = Platform()
        self.sketch = api.use_sketch(Sketch(platform=self.platform, renderer=_make_renderer_class()()))
        self.import_ms = (perf() - t0) * 1000
        self.started = False
        self._runs = {}
        ns = {"__name__": "__sketch__", "__file__": name}
        self.namespace = ns

        def web_run(*, fps=None, max_frames=None):
            # L1 on the web: f.run() registers the sketch and returns; the page calls step().
            self.sketch.start(ns, fps=fps, max_frames=max_frames)
            self.started = True

        funground.run = web_run
        api.run = web_run
        self.ns_code = compile(source, name, "exec")
        self.source_name = name

    def run_top_level(self):
        """Execute the learner's file (it ends in f.run(), which calls start() and so setup())."""
        t0 = perf()
        exec(self.ns_code, self.namespace)
        if not self.started:
            raise RuntimeError("the file did not call f.run() (scripts with f.show() are not in this spike)")
        return (perf() - t0) * 1000

    def encode(self, op):
        """ir.op_to_jsonable, plus what the IR holds but never serialises (as tools/irenc.py does for S-135):
        a Text op carries its shaped glyph outlines (FillPath ops from typography.py, so the page never uses fillText),
        a rounded Rect its path."""
        ir = self.ir
        d = ir.op_to_jsonable(op)
        if type(op) is ir.Text:
            d["outlines"] = [ir.op_to_jsonable(o) for o in self.text_run(op).outline_ops(op.x, op.y, op.color)]
        elif type(op) is ir.Rect and op.radii:
            from funground.geometry import Path
            d["path"] = ir._value_to_jsonable(Path.rounded_rect(op.x, op.y, op.width, op.height, op.radii))
        return d

    def text_run(self, op):
        """The shaped line for a Text op, cached like CairoRenderer._text_run (renderers/cairo2d.py)."""
        from funground.typography import effective_font, text_settings
        style = op.style
        key = (op.text, style.text_size, style.font, style.text_style, style.text_tracking, style.text_features,
               style.font_variations, style.text_fallback)
        run = self._runs.get(key)
        if run is None:
            run = self._runs[key] = effective_font(style).shape(op.text, style.text_size, **text_settings(style))
        return run

    def size(self):
        s = self.sketch
        return [s.width, s.height, self.platform.backing_scale]

    def step(self, now_ms: float, events_json: str):
        """One frame. Returns [running, step_ms, encode_ms, ops_json]."""
        p = self.platform
        p.now = now_ms / 1000.0
        if events_json != "[]":
            p.post(*(self.InputEvent(**e) for e in json.loads(events_json)))
        t0 = perf()
        running = self.sketch.step()
        t1 = perf()
        ops = [self.encode(o) for o in p.ops]
        body = json.dumps(ops, separators=(",", ":"))
        t2 = perf()
        return [running, (t1 - t0) * 1000, (t2 - t1) * 1000, body]

    def finish(self):
        self.sketch.finish()
