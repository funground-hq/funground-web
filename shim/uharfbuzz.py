"""uharfbuzz's subset that funground uses, over harfbuzzjs (HarfBuzz compiled to wasm). S-133.

For Pyodide only. harfbuzzjs must already be loaded by the page or worker and published as the
global `hb` (`self.hb = await import(".../harfbuzzjs/index.mjs")`); this module reaches it through
the `js` module. Names and behaviour follow uharfbuzz 0.56 where funground and its tests use them:

    Face(data: bytes, index: int = 0)            .upem
    Font(face)                                   .scale (get/set a pair), .set_variations({tag: value})
    Buffer()                                     .add_str(text), .add_codepoints(cps), .guess_segment_properties(),
                                                 .glyph_infos, .glyph_positions, .clear_contents()
    shape(font, buffer, features=None)           features: {tag: bool | int | [(start, end, value), ...]}
    GlyphInfo (.codepoint .cluster .mask .flags), GlyphPosition (.x_advance .y_advance .x_offset .y_offset)

Everything else in uharfbuzz (drawing, metrics, names, math, colour, shapers, serialising) is not here;
use of it raises AttributeError. Clusters are indices into the code points of the text, as in
uharfbuzz (`add_str`), not UTF-16 units: the text goes in with `addCodePoints`, never `addText`.
"""
from __future__ import annotations

import js
from pyodide.ffi import to_js

_hb = js.hb
_GLOBAL_END = 0xFFFFFFFF            # hb's "to the end of the buffer" (uharfbuzz: end -1)


class GlyphInfo:
    __slots__ = ("codepoint", "cluster", "mask", "flags")

    def __init__(self, codepoint: int, cluster: int, mask: int = 0, flags: int = 0) -> None:
        self.codepoint, self.cluster, self.mask, self.flags = codepoint, cluster, mask, flags

    def __repr__(self) -> str:
        return f"GlyphInfo(codepoint={self.codepoint}, cluster={self.cluster})"


class GlyphPosition:
    __slots__ = ("x_advance", "y_advance", "x_offset", "y_offset")

    def __init__(self, x_advance: int, y_advance: int, x_offset: int, y_offset: int) -> None:
        self.x_advance, self.y_advance, self.x_offset, self.y_offset = x_advance, y_advance, x_offset, y_offset

    def __repr__(self) -> str:
        return f"GlyphPosition(x_advance={self.x_advance}, y_advance={self.y_advance}, x_offset={self.x_offset}, y_offset={self.y_offset})"


class Face:
    def __init__(self, data: bytes, index: int = 0) -> None:
        self._blob = _hb.Blob.new(to_js(bytes(data)))        # Uint8Array copy; harfbuzzjs copies it again into wasm memory
        self._face = _hb.Face.new(self._blob, index)
        self.upem: int = self._face.upem


class Font:
    def __init__(self, face: Face) -> None:
        self._face = face
        self._font = _hb.Font.new(face._face)                # scale starts at the face's upem, as in hb_font_create

    @property
    def scale(self) -> tuple[int, int]:
        return self._scale if hasattr(self, "_scale") else (self._face.upem, self._face.upem)

    @scale.setter
    def scale(self, value: tuple[int, int]) -> None:
        self._scale = (int(value[0]), int(value[1]))
        self._font.setScale(*self._scale)

    def set_variations(self, variations: dict) -> None:
        """Replaces every variation on the font; axes not named go back to their defaults."""
        self._font.setVariations(to_js([_hb.Variation.new(tag, float(v)) for tag, v in variations.items()]))


class Buffer:
    def __init__(self) -> None:
        self._buf = _hb.Buffer.new()
        self._glyphs = None                                  # (infos, positions), read once after each shape

    def add_str(self, text: str, item_offset: int = 0, item_length: int = -1) -> None:
        self.add_codepoints([ord(c) for c in text], item_offset, item_length)

    def add_codepoints(self, codepoints, item_offset: int = 0, item_length: int = -1) -> None:
        cps = list(codepoints)
        self._buf.addCodePoints(to_js(cps), item_offset, len(cps) - item_offset if item_length < 0 else item_length)
        self._glyphs = None

    def guess_segment_properties(self) -> None:
        self._buf.guessSegmentProperties()

    def clear_contents(self) -> None:
        self._buf.clearContents()
        self._glyphs = None

    def _read(self):
        if self._glyphs is None:
            rows = self._buf.getGlyphInfosAndPositions().to_py()
            self._glyphs = (None, None) if not rows else (    # uharfbuzz 0.56 answers None, not [], for an empty buffer
                [GlyphInfo(r["codepoint"], r["cluster"], 0, r["flags"]) for r in rows],
                [GlyphPosition(r["xAdvance"], r["yAdvance"], r["xOffset"], r["yOffset"]) for r in rows],
            )
        return self._glyphs

    @property
    def glyph_infos(self) -> list[GlyphInfo]:
        return self._read()[0]

    @property
    def glyph_positions(self) -> list[GlyphPosition]:
        return self._read()[1]


def shape(font: Font, buffer: Buffer, features: dict | None = None) -> None:
    feats = []
    for tag, value in (features or {}).items():
        if len(tag) != 4:
            raise NotImplementedError(f"uharfbuzz shim: feature strings are not supported ({tag!r})")
        if isinstance(value, (bool, int)):
            feats.append(_hb.Feature.new(tag, int(value)))
        else:                                                # a sequence of (start, end, value) triples
            for start, end, v in value:
                feats.append(_hb.Feature.new(tag, int(v), start, _GLOBAL_END if end < 0 else end))
    _hb.shape(font._font, buffer._buf, to_js(feats) if feats else None)
    buffer._glyphs = None


def version_string() -> str:
    return str(_hb.versionString())
