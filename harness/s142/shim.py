"""S-142: one Host for both renderers, run natively and in Pyodide (module worker).

    route "cairo":  the real funground.renderers.cairo2d.CairoRenderer (pycairo); the frame leaves Python as
                    the surface's BGRA bytes (a memoryview, no copy in Python).
    route "canvas": an IR-capturing renderer in place of Cairo (the S-136/S-133 route); the frame leaves
                    Python as JSON of the IR ops (Host.encode, as S-133), drawn by renderer/ir_canvas.js.

The sketch is driven by start()/step()/finish() (D-074). Per frame the Host reports the time in
draw() (the learner's function, wrapped), in the renderer (Cairo; zero for the IR renderer) and in the
encode (IR route), next to the whole step().
Nothing in funground changes. Used by harness/s142/worker.js (Pyodide) and tools/s142_native.py (CPython).
"""
from __future__ import annotations

import json
import os
import sys
import time
import types

perf = time.perf_counter
for _p in ("/src",):
    if os.path.isdir(_p) and _p not in sys.path:
        sys.path.insert(0, _p)


class _Acc:
    """Time accumulated by the wrapped renderer calls in one frame (re-entrant calls count once)."""
    render = 0.0
    depth = 0


ACC = _Acc()


def _timed(fn):
    def wrapper(*a, **k):
        if ACC.depth:
            return fn(*a, **k)
        ACC.depth = 1
        t = perf()
        try:
            return fn(*a, **k)
        finally:
            ACC.render += perf() - t
            ACC.depth = 0
    return wrapper


class IrPixels:
    format = "IR"
    data = b""

    def __init__(self, width, height, ops):
        self.width, self.height, self.ops = width, height, ops


class _Ink:
    cairo = False                 # set by the Host for cases whose marks need Cairo to measure


INK = _Ink()
_REAL = []


def _real_cairo():
    """A real CairoRenderer, loaded under another module name (funground.renderers.cairo2d is the stub)."""
    if not _REAL:
        import importlib.util
        import funground
        path = os.path.join(os.path.dirname(funground.__file__), "renderers", "cairo2d.py")
        spec = importlib.util.spec_from_file_location("funground.renderers._cairo2d_real", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _REAL.append(mod.CairoRenderer())
    return _REAL[0]


class _Ctx:
    """The little of a Cairo context the sketch touches on the IR renderer (script pages)."""
    def get_matrix(self):
        return None


def _make_ir_renderer_class():
    from funground.capabilities import Capability

    class IrRenderer:
        name = "ir"
        capabilities = frozenset({
            Capability.RASTER_2D, Capability.ALPHA, Capability.ANTIALIAS, Capability.TRANSFORMS,
            Capability.VECTOR_PATHS, Capability.CLIP_PATH, Capability.TEXT_OUTLINES,
        })

        def __init__(self):
            self._scale = 1.0
            self._w = self._h = 0
            self.ops = ()
            self._ctx = _Ctx()
            self._base_matrix = None

        def attach(self, width, height, scale=1.0):
            self._w, self._h, self._scale = width, height, scale
            self.ops = ()

        def render(self, frame):
            self.ops = tuple(frame)

        def draw_batch(self, ctx, frame, depth):       # script pages: ops stay in sketch.frame, taken at the end
            return depth

        def begin_frame(self, ctx):
            pass

        def end_frame(self, ctx, depth):
            pass

        def pixels(self):
            return IrPixels(self._w, self._h, self.ops)

        def ink_bounds(self, ops):
            # Marks (funground.marks) measure ink with the renderer. The IR renderer cannot; with ink="cairo" the
            # measuring is delegated to a real CairoRenderer (pycairo loaded; drawing still goes to the IR route).
            if not INK.cairo:
                raise NotImplementedError("ink_bounds needs Cairo (marks, controls)")
            return _real_cairo().ink_bounds(ops)

    return IrRenderer


def _make_timed_cairo_class():
    from funground.renderers.cairo2d import CairoRenderer

    class TimedCairo(CairoRenderer):
        render = _timed(CairoRenderer.render)
        draw_batch = _timed(CairoRenderer.draw_batch)
        begin_frame = _timed(CairoRenderer.begin_frame)
        end_frame = _timed(CairoRenderer.end_frame)
        pixels = _timed(CairoRenderer.pixels)          # flush

    return TimedCairo


def _make_platform_class():
    from funground.platform.headless import HeadlessPlatform
    from funground.platform.base import InputEvent

    class BrowserPlatform(HeadlessPlatform):
        def __init__(self):
            super().__init__()
            self.now = None
            self._prev = None
            self.ops = ()
            self.pixels = None

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
            self.pixels = pixels
            self.ops = getattr(pixels, "ops", ())

        def tick(self, fps):
            dt = (self.now - self._prev) if self._prev is not None else 1.0 / fps
            self._prev = self.now
            return dt

        def capture(self):
            return ((self._size[0], self._size[1]), b"")

        def close(self):
            self.ops = ()

    return BrowserPlatform, InputEvent


class Host:
    def __init__(self, route: str):
        assert route in ("cairo", "canvas")
        self.route = route
        os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
        os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
        os.environ["FUNGROUND_HEADLESS"] = "1"
        t0 = perf()
        if route == "canvas":
            sys.modules.pop("funground.renderers.cairo2d", None)
            stub = types.ModuleType("funground.renderers.cairo2d")
            stub.__getattr__ = lambda name: _make_ir_renderer_class() if name == "CairoRenderer" else (_ for _ in ()).throw(AttributeError(name))
            sys.modules["funground.renderers.cairo2d"] = stub
        import funground
        from funground import api, ir
        from funground.sketch import Sketch
        self.funground, self.api, self.ir, self.Sketch = funground, api, ir, Sketch
        self.Platform, self.InputEvent = _make_platform_class()
        self.renderer_class = _make_timed_cairo_class() if route == "cairo" else _make_ir_renderer_class()
        self.import_ms = (perf() - t0) * 1000
        self._runs = {}
        self.sketch = self.platform = None
        self.started = False
        self.shown = False
        self.draw_t = 0.0

    # ---- a case -------------------------------------------------------------------------------------------
    def _fresh(self, scale, name, source):
        if scale == 1:
            os.environ.pop("FUNGROUND_BACKING_SCALE", None)
        else:
            os.environ["FUNGROUND_BACKING_SCALE"] = str(scale)
        if self.sketch is not None:
            try:
                self.sketch.finish()
            except Exception:
                pass
        self._runs = {}
        self.platform = self.Platform()
        self.sketch = self.api.use_sketch(self.Sketch(platform=self.platform, renderer=self.renderer_class()))
        self.sketch.random_seed(0)
        self.started = self.shown = False
        ns = {"__name__": "__sketch__", "__file__": name}
        host = self

        def web_run(*, fps=None, max_frames=None):
            host.sketch.start(ns, fps=fps, max_frames=max_frames)
            fn = host.sketch._draw_fn
            if fn is not None:
                def timed_draw():
                    t = perf()
                    try:
                        fn()
                    finally:
                        host.draw_t += perf() - t
                host.sketch._draw_fn = timed_draw
            host.started = True

        def web_show():
            host.shown = True

        self.funground.run = web_run
        self.api.run = web_run
        self.funground.show = web_show
        self.api.show = web_show
        return ns, compile(source, name, "exec")

    def set_ink(self, on):
        INK.cairo = bool(on)

    def load_loop(self, source, name, scale=1.0):
        """Run the file up to f.run() (setup() has run). Returns [w, h, backing_scale, exec_ms]."""
        ns, code = self._fresh(scale, name, source)
        t = perf()
        exec(code, ns)
        if not self.started:
            raise RuntimeError("the file did not call f.run()")
        return self.size() + [(perf() - t) * 1000]

    def size(self):
        s = self.sketch
        return [s.width, s.height, self.platform.backing_scale]

    # ---- encode (IR route) -------------------------------------------------------------------------------------
    def encode(self, op):
        ir = self.ir
        d = ir.op_to_jsonable(op)
        if type(op) is ir.Text:
            d["outlines"] = [ir.op_to_jsonable(o) for o in self.text_run(op).outline_ops(op.x, op.y, op.color)]
        elif type(op) is ir.Rect and op.radii:
            from funground.geometry import Path
            d["path"] = ir._value_to_jsonable(Path.rounded_rect(op.x, op.y, op.width, op.height, op.radii))
        elif type(op) in (ir.Image, ir.Pixels):
            raise NotImplementedError(f"{type(op).__name__} op needs a binary payload (not in this spike)")
        return d

    def text_run(self, op):
        from funground.typography import effective_font, text_settings
        style = op.style
        key = (op.text, style.text_size, style.font, style.text_style, style.text_tracking, style.text_features,
               style.font_variations, style.text_fallback)
        run = self._runs.get(key)
        if run is None:
            run = self._runs[key] = effective_font(style).shape(op.text, style.text_size, **text_settings(style))
        return run

    def _result(self, running, t_step, t_draw, t_render, ops):
        """Common tail: encode (IR route) or count ops (Cairo route). Returns the list for JS."""
        if self.route == "canvas":
            t0 = perf()
            enc = [self.encode(o) for o in ops]
            body = json.dumps(enc, separators=(",", ":"))
            t_enc = (perf() - t0) * 1000
            n = len(ops)
        else:
            body, t_enc = None, 0.0
            n = len(self.sketch.last_ops) if self.sketch.last_ops is not None else 0
        return [running, t_step, t_draw, t_render, t_enc, body, n]

    def step(self, now_ms, events_json="[]"):
        """One frame: [running, step_ms, draw_ms, render_ms, encode_ms, ops_json|None, n_ops]."""
        p = self.platform
        p.now = now_ms / 1000.0
        if events_json != "[]":
            p.post(*(self.InputEvent(**e) for e in json.loads(events_json)))
        self.draw_t = 0.0
        ACC.render = 0.0
        t0 = perf()
        running = self.sketch.step()
        t1 = perf()
        return self._result(running, (t1 - t0) * 1000, self.draw_t * 1000, ACC.render * 1000, p.ops)

    def run_script(self, source, name, scale=1.0):
        """A script (ends with f.show()): the whole run is the frame. Returns the step() list followed by
        [w, h, backing_scale]; draw_ms is the run minus the renderer."""
        ns, code = self._fresh(scale, name, source)
        ACC.render = 0.0
        t0 = perf()
        exec(code, ns)
        sk = self.sketch
        if self.route == "cairo":
            sk._script_flush()
            pix = sk._view_pixels()
            self.platform.present(pix)
            ops = ()
            sk.last_ops = sk.frame.ops
        else:
            ops = list(sk.frame.ops)
        t1 = perf()
        total = (t1 - t0) * 1000
        r = self._result(False, total, total - ACC.render * 1000, ACC.render * 1000, ops)
        if self.route == "cairo":
            r[6] = len(sk.frame.ops)
        return r + self.size()

    def frame_view(self):
        """The Cairo route's latest frame: a memoryview of premultiplied BGRA, no copy."""
        return memoryview(self.platform.pixels.data)

    def frame_size(self):
        p = self.platform.pixels
        return [p.width, p.height]

    def native_copy(self):
        """Native column only: what handing the frame to a consumer costs (one copy of the bytes)."""
        mv = self.frame_view()
        t = perf()
        b = bytes(mv)
        return (perf() - t) * 1000, b

    def finish(self):
        if self.sketch is not None:
            self.sketch.finish()
