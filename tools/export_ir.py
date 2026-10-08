"""Export the IR of funground sketches (and the Cairo reference they were drawn to) for the web spike S-135.

Run with the playground venv (never plain python):

    C:\\Projects\\playground\\.venv\\Scripts\\python.exe tools/export_ir.py --all
    C:\\Projects\\playground\\.venv\\Scripts\\python.exe tools/export_ir.py session1-05_text

Each case is run in its own subprocess (one at a time: the machine is small). A case is
written to cases/<id>/:

    ir.json      {"width","height","scale","steps":[...],"overlay":[...]|null,"cairo_ms":..}
    ref.png      the golden (the Cairo reference), copied from tests/golden
    *.bin        raw premultiplied BGRA pixels of pictures (Image snapshots) and Pixels blocks

How the replay is recorded: CairoRenderer.draw / begin_frame / draw_batch / end_frame are wrapped,
so what JS replays is exactly what Cairo was asked to draw, in order, including mid-frame batches
(f.get()), script canvases and picture snapshots.  Text ops get an "outlines" field (the FillPath
ops the Python typography produced); Rect ops with corner radii get a "path" field.  Everything
before the last Clear is dropped (a Clear replaces every pixel).
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

CORE = Path(os.environ.get("FUNGROUND_CORE", r"C:\Projects\playground-0.2"))
WEB = Path(__file__).resolve().parent.parent
CASES = WEB / "cases"

SESSION1 = [f"session1-{p.stem}" for p in sorted((CORE / "examples" / "session1").glob("*.py"))
            if p.stem != "11_delta_time" and (CORE / "tests" / "golden" / f"{p.stem}.png").exists()]

GALLERY = [
    "colour-03_gradients", "compositing-01_blend_opacity_shadow", "compositing-02_graphics",
    "compositing-03_scratch_card", "compositing-04_layers", "images-01_load_image",
    "images-02_tint_and_parts", "images-03_pixels", "lines-02_caps_joins_dashes",
    "lines-03_pixel_art", "paths-01_star", "paths-02_path_and_clip", "paths-04_holes",
    "shapes-04_rounded", "studios-01_placement", "studios-03_rhythm", "studios-06_poster_series",
    "text-01_text", "text-05_text_path", "transforms-03_shear_and_matrices", "interaction-02_paint",
    "saving-02_transparent_png", "colour-01_colour_forms", "shapes-03_modes",
]


HIDPI = ["studios-03_rhythm", "studios-06_poster_series", "text-05_text_path", "compositing-01_blend_opacity_shadow",
         "shapes-04_rounded", "colour-03_gradients", "paths-02_path_and_clip", "images-01_load_image"]


def all_cases() -> list[str]:
    return SESSION1 + [f"gallery-{g}" for g in GALLERY]


# --------------------------------------------------------------------------------------------- one case
def export_case(case: str) -> dict:
    os.environ["SDL_VIDEODRIVER"] = "dummy"
    os.environ["SDL_AUDIODRIVER"] = "dummy"
    os.environ["FUNGROUND_HEADLESS"] = "1"
    sys.path.insert(0, str(CORE))
    import cairo  # noqa: F401
    import funground
    from funground import api, ir
    from funground.sketch import Sketch
    from funground.renderers.cairo2d import CairoRenderer

    case_base, _, sfx = case.partition("@")
    if sfx == "2x":
        os.environ["FUNGROUND_BACKING_SCALE"] = "2"      # the headless platform then draws at 2 physical pixels per logical one
    kind, _, name = case_base.partition("-")
    if kind == "session1":
        path = CORE / "examples" / "session1" / f"{name}.py"
        golden = CORE / "tests" / "golden" / f"{name}.png"
    else:
        area = name.split("-")[0]
        path = CORE / "examples" / "gallery" / area / f"{name.split('-', 1)[1]}.py"
        golden = CORE / "tests" / "golden" / "gallery" / f"{name}.png"
    out = CASES / case
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)

    # ---- recording wrappers
    events: list[tuple] = []           # (renderer, kind, ops-or-None, ms)
    cap = {"in_view": None, "last_view": None, "main_ref": None}
    orig = {n: getattr(CairoRenderer, n) for n in ("draw", "begin_frame", "draw_batch", "end_frame")}

    def is_canvas(ctx):
        return isinstance(ctx.get_target(), cairo.ImageSurface)

    def w_draw(self, ctx, frame):
        ops = tuple(frame)
        t = time.perf_counter()
        r = orig["draw"](self, ctx, frame)
        if is_canvas(ctx):
            events.append((self, "frame", ops, (time.perf_counter() - t) * 1000))
        return r

    def w_begin(self, ctx):
        r = orig["begin_frame"](self, ctx)
        if is_canvas(ctx):
            events.append((self, "begin", None, 0.0))
        return r

    def w_batch(self, ctx, frame, depth=0):
        ops = tuple(frame)
        t = time.perf_counter()
        r = orig["draw_batch"](self, ctx, ir.Frame(list(ops)), depth)
        ms = (time.perf_counter() - t) * 1000
        if is_canvas(ctx):
            if cap["in_view"] is not None and self is not cap["main_ref"]():
                if self is cap.get("view_ren"):          # the layers drawn over the canvas copy (not a picture's own flush)
                    cap["in_view"].extend(ops)
            else:
                events.append((self, "batch", ops, ms))
        return r

    def w_end(self, ctx, depth):
        r = orig["end_frame"](self, ctx, depth)
        if is_canvas(ctx):
            events.append((self, "end", None, 0.0))
        return r

    CairoRenderer.draw, CairoRenderer.begin_frame = w_draw, w_begin
    CairoRenderer.draw_batch, CairoRenderer.end_frame = w_batch, w_end

    orig_view = Sketch._view
    import funground.sketch as sketch_mod
    orig_default = sketch_mod.default_renderer

    def w_default():
        r = orig_default()
        if cap["in_view"] is not None:
            cap["view_ren"] = r
        return r

    sketch_mod.default_renderer = w_default

    def w_view(self, guides=False):
        cap["main_ref"] = lambda s=self: s._renderer
        cap["in_view"] = []
        try:
            view = orig_view(self, guides)
        finally:
            ops, cap["in_view"] = cap["in_view"], None
        cap["last_view"] = None if view is self._renderer else ops
        return view

    Sketch._view = w_view

    # ---- run the sketch as the tests do (conftest.run_sketch)
    api.use_sketch(Sketch()).random_seed(0)
    scratch = tempfile.mkdtemp(prefix="fgexport_")
    os.chdir(scratch)
    namespace = {"__name__": "__sketch__", "__file__": str(path)}
    import inspect

    def harness_run(*, fps=1000, max_frames=30):
        caller = inspect.currentframe().f_back
        api.active_sketch().run_namespace(caller.f_globals, fps=fps, max_frames=max_frames)

    orig_run, orig_show = funground.run, funground.show
    funground.run, funground.show = harness_run, (lambda: None)
    try:
        exec(compile(path.read_text(encoding="utf-8"), str(path), "exec"), namespace)
    finally:
        funground.run, funground.show = orig_run, orig_show
    sk = api.active_sketch()
    if sk.last_frame is None and sk._script:
        from funground.platform.headless import HeadlessPlatform
        sk._script_flush()
        platform = HeadlessPlatform()
        platform.present(sk._view_pixels())
        frame = platform.capture()
        script = True
    else:
        frame = sk.last_frame
        script = False
    (w, h), rgb = frame
    main = sk._renderer
    scale = main._scale

    # ---- reference: the golden; check the re-run equals it
    import pygame
    if sfx:                                      # no golden at this density: the reference is Cairo's own re-run
        pygame.image.save(pygame.image.frombuffer(rgb, (w, h), "RGB"), str(out / "ref.png"))
        rerun_equals_golden = None
    else:
        shutil.copyfile(golden, out / "ref.png")
        exp = pygame.image.tobytes(pygame.image.load(str(golden)), "RGB")
        rerun_equals_golden = exp == rgb
        if not rerun_equals_golden:
            pygame.image.save(pygame.image.frombuffer(rgb, (w, h), "RGB"), str(out / "ref_rerun.png"))

    # ---- keep only this renderer's events, trimmed from the last Clear
    mine = [e for e in events if e[0] is main]
    start = 0
    if not script:
        for i, (_, k, ops, _) in enumerate(mine):
            if ops and any(type(o) is ir.Clear for o in ops):
                j = i
                while j > 0 and mine[j][1] not in ("frame", "begin"):
                    j -= 1
                start = j
    mine = mine[start:]

    # ---- serialise
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from irenc import Encoder
    E = Encoder(out, main)
    enc = E.op
    files = E.files

    steps = []
    for _, k, ops, ms in mine:
        steps.append({"k": k, **({"ops": [enc(o) for o in ops]} if ops is not None else {})})
    overlay = None
    if cap["last_view"]:
        overlay = [enc(o) for o in cap["last_view"]]
    # Cairo time of the final frame (the events from the last frame/begin)
    last = 0
    for i, (_, k, _, _) in enumerate(mine):
        if k in ("frame", "begin"):
            last = i
    cairo_ms = sum(e[3] for e in mine[last:])
    nops = sum(len(s.get("ops", ())) for s in steps[last:])

    if sfx:
        w, h = round(w / scale), round(h / scale)       # the frame is physical pixels; the IR's size is logical
    doc = {"case": case, "width": w, "height": h, "scale": scale, "script": script,
           "steps": steps, "overlay": overlay, "cairo_ms": cairo_ms, "final_frame_ops": nops,
           "rerun_equals_golden": rerun_equals_golden, "files": sorted(files)}
    (out / "ir.json").write_text(json.dumps(doc, separators=(",", ":")), encoding="utf-8")
    op_types = sorted({o["op"] for s in steps for o in s.get("ops", ())} | {o["op"] for o in (overlay or ())})
    return {"case": case, "width": w, "height": h, "scale": scale, "ops": op_types, "frame_ops": nops,
            "cairo_ms": round(cairo_ms, 2), "rerun_equals_golden": rerun_equals_golden,
            "size_kb": round(sum(f.stat().st_size for f in out.iterdir()) / 1024)}


def main() -> None:
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        return
    if args[0] == "--one":
        print("RESULT " + json.dumps(export_case(args[1])))
        return
    cases = all_cases() if args[0] == "--all" else ([f"gallery-{g}@2x" for g in HIDPI] if args[0] == "--hidpi" else args)
    CASES.mkdir(exist_ok=True)
    manifest = []
    for c in cases:
        r = subprocess.run([sys.executable, __file__, "--one", c], capture_output=True, text=True)
        line = next((l for l in r.stdout.splitlines() if l.startswith("RESULT ")), None)
        if line is None:
            print(f"FAIL {c}\n{r.stderr[-1500:]}")
            manifest.append({"case": c, "error": r.stderr[-400:]})
        else:
            info = json.loads(line[7:])
            manifest.append(info)
            print(f"ok   {c}  {info['width']}x{info['height']} ops={info['frame_ops']} "
                  f"cairo={info['cairo_ms']}ms same_as_golden={info['rerun_equals_golden']} {info['ops']}")
    mf = CASES / "manifest.json"
    old = {m["case"]: m for m in (json.loads(mf.read_text(encoding="utf-8")) if mf.exists() else []) if "case" in m}
    old.update({m["case"]: m for m in manifest if "case" in m})
    mf.write_text(json.dumps(list(old.values()), indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
