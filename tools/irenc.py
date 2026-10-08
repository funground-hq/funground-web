"""Shared IR -> JSON encoding for the S-135 exporters (funground must already be importable)."""
from __future__ import annotations

import hashlib
import zlib
from pathlib import Path


class Encoder:
    """Turns live IR ops into the JSON the browser replays.

    Beyond Frame.to_jsonable(): Text ops carry "outlines" (the FillPath ops the Python typography made),
    rounded Rect ops carry "path", Image ops carry their picture's pixels as a .bin file, and Pixels ops
    carry their PixelBlock as a .bin file. All of that is data the real IR holds in memory but never
    serialises (NEVER_SERIALISE) or derives from Python helpers."""

    def __init__(self, out: Path, renderer) -> None:
        self.out, self.renderer, self.files = out, renderer, set()

    def blob(self, data: bytes) -> str:
        name = "b" + hashlib.sha1(bytes(data)).hexdigest()[:16] + ".bin"
        if name not in self.files:
            (self.out / name).write_bytes(zlib.compress(bytes(data), 6))   # zlib; the harness inflates with DecompressionStream
            self.files.add(name)
        return name

    def op(self, op) -> dict:
        from funground import ir
        d = ir.op_to_jsonable(op)
        t = type(op)
        if t is ir.Text:
            d["outlines"] = [ir.op_to_jsonable(o) for o in self.renderer._text_ops(op)]
        elif t is ir.Rect and op.radii:
            from funground.geometry import Path as GPath
            d["path"] = ir._value_to_jsonable(GPath.rounded_rect(op.x, op.y, op.width, op.height, op.radii))
        elif t is ir.Image:
            s = op.snapshot
            d["file"] = self.blob(s.pixels)
            d["pw"], d["ph"], d["lw"], d["lh"] = s.phys_width, s.phys_height, s.logical_width, s.logical_height
        elif t is ir.Pixels:
            b = op.data
            d["file"] = self.blob(b.bgra)
            d["block"] = {"scale": b.scale, "x": b.x, "y": b.y, "w": b.width, "h": b.height}
        return d
