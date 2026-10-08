r"""Build the S-133 text corpus and its native reference (desktop, uharfbuzz).

    C:\Projects\playground\.venv\Scripts\python.exe tools/s133_corpus.py [--skip-record]

1. Records every shaping call of the Session-1 sketches and of the gallery examples that have a golden
   (tools/s133_record.py, one process each, 30 frames, 120 s limit).
2. Collects the string constants of the text tests in playground-0.2/tests (T-rows) and shapes them
   in the built-in fonts.
3. Adds Devanagari, emoji, symbol, Latin (kerning, ligatures, features, tracking), Arabic, Hebrew,
   Cyrillic and Greek samples, and a variable test font (tests/fontmaker.py) with variations.
4. Writes spikes/S-133/corpus.json and runs harness/s133/corpus_run.py natively to write
   spikes/S-133/reference.json. The extra fonts it needs are copied to harness/s133/dist/extra/.
"""
from __future__ import annotations

import argparse
import ast
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

WEB = Path(__file__).resolve().parent.parent
CORE = Path(os.environ.get("FUNGROUND_CORE", r"C:\Projects\playground-0.2"))
PY = sys.executable
OUT = WEB / "spikes" / "S-133"
EXTRA = WEB / "harness" / "s133" / "dist" / "extra"
TEST_FILES = ["test_text.py", "test_text_settings.py", "test_text_layout.py", "test_text_path.py", "test_fonts.py",
              "test_fallback.py", "test_formatted.py", "test_font_info.py", "test_pdf_text.py", "test_svg_text.py"]
NORMAL, BOLD, ITALIC, BOLDITALIC = ("fonts/DejaVuSans.ttf", "fonts/DejaVuSans-Bold.ttf",
                                    "fonts/DejaVuSans-Oblique.ttf", "fonts/DejaVuSans-BoldOblique.ttf")
EMOJI, SYMBOLS, DEVA = "fonts/NotoEmoji-Regular.ttf", "fonts/NotoSansSymbols2-Regular.ttf", "fonts/NotoSansDevanagari-Regular.ttf"


def case(font, text, src, features=(), variations=(), tracking=0.0, fallback=None, face=0):
    return {"src": src, "font": font, "face": face, "text": text, "tracking": tracking,
            "features": [list(x) for x in features], "variations": [list(x) for x in variations], "fallback": fallback}


def record(skip: bool) -> list[dict]:
    raw = OUT / "recorded.jsonl"
    if not skip:
        raw.unlink(missing_ok=True)
        sketches = [p for p in sorted((CORE / "examples" / "session1").glob("*.py")) if p.stem != "11_delta_time"]
        for g in sorted((CORE / "tests" / "golden" / "gallery").glob("*.png")):
            area, _, stem = g.stem.partition("-")
            p = CORE / "examples" / "gallery" / area / f"{stem}.py"
            if p.exists():
                sketches.append(p)
        for p in sketches:
            try:
                r = subprocess.run([PY, str(WEB / "tools" / "s133_record.py"), str(p), str(raw)], capture_output=True,
                                   text=True, timeout=120)
                print(r.stdout.strip().splitlines()[-1] if r.stdout.strip() else "(no output)", r.stderr.strip()[-200:])
            except subprocess.TimeoutExpired:
                print(f"{p.name}: timeout")
    cases = []
    for line in raw.read_text(encoding="utf-8").splitlines():
        cases.append(json.loads(line))
    return cases


def test_strings() -> list[str]:
    seen: dict[str, None] = {}
    for name in TEST_FILES:
        tree = ast.parse((CORE / "tests" / name).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                s = node.value
                if 1 <= len(s) <= 100 and "\n" not in s and "\r" not in s and "\0" not in s:
                    seen.setdefault(s, None)
    return list(seen)


EXTRAS = [
    # Devanagari: conjuncts, pre-base vowel, marks, reph, nukta
    *[(DEVA, t, ()) for t in ["क्षत्रिय नमस्ते", "हिन्दी", "संस्कृत भाषा", "कि", "र्क", "दुनिया", "श्रृंगार", "ज्ञान", "द्वारा",
                              "अनुस्वार ं ँ ः", "निर्माण", "विद्यार्थी", "पुस्तकालय में", "क़ ख़ ग़ ज़ ड़ ढ़ फ़ य़", "द्ध ट्ट ह्म श्र त्र क्ष"]],
    *[(NORMAL, t, []) for t in ["क्षत्रिय नमस्ते", "Hello नमस्ते world", "रागा: भैरवी", "नमस्ते 😀 दुनिया"]],
    # emoji: single, modifier, ZWJ, flags, keycap, VS16, tags
    *[(EMOJI, t, ()) for t in ["😀", "👍🏽", "👨‍👩‍👧‍👦", "🇮🇳🇯🇵", "❤️", "☺️", "⌚", "1️⃣", "🏳️‍🌈", "🏴󠁧󠁢󠁥󠁮󠁧󠁿", "😀😃😄😁"]],
    *[(NORMAL, t, []) for t in ["Hello 😀 world", "I ❤️ funground", "Flags 🇮🇳🇯🇵 here", "👍🏽 ok", "a😀b😃c", "👨‍👩‍👧‍👦 family"]],
    *[(BOLD, t, []) for t in ["Bold 😀", "☺️ text"]],
    # symbols
    *[(SYMBOLS, t, ()) for t in ["→←↑↓", "∑∏∫", "♠♥♦♣", "✓✗", "𝔸𝔹ℂ", "⚀⚁⚂⚃⚄⚅", "𓀀𓀁"]],
    *[(NORMAL, t, []) for t in ["Dice ⚀⚁⚂ and ♠♥♦♣", "Maths ∑∏∫ → ∞", "𝔸𝔹ℂ fraktur"]],
    # Latin, kerning, ligatures, spacing
    *[(NORMAL, t, ()) for t in ["", " ", "  ", "AVATAR To Wa Te Ty", "ffi fl ffl fi ff", "Hello, funground!", "The quick brown fox jumps over the lazy dog",
                                "Ä Ö Ü ä ö ü ß é è ê ñ ç ø å æ œ", "1234567890 +-*/=", "fi\u200cfl \u00adsoft\u00adhyphen", "A\u0301 e\u0308 o\u0302 combining marks",
                                "Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed do eiusmod tempor incididunt ut labore et dolore magna aliqua. "
                                "Ut enim ad minim veniam, quis nostrud exercitation ullamco laboris nisi ut aliquip ex ea commodo consequat."]],
    # other scripts DejaVu has: Arabic (joining, RTL), Hebrew, Greek, Cyrillic
    *[(NORMAL, t, ()) for t in ["مرحبا بالعالم", "السلام عليكم", "שלום עולם", "Привет мир ΑΒΓ αβγ", "Ελληνικά Кириллица"]],
]
FEATURE_SETS = [[("liga", False)], [("kern", False)], [("smcp", True)], [("frac", True)], [("liga", False), ("kern", False)], [("onum", True)],
                [("c2sc", True), ("smcp", True)]]
FEATURE_TEXTS = ["ffi fl AVATAR 1/2 3/4", "Hello World 0123456789", "Small Caps Test"]


def extra_cases(extra_font_names: dict[str, str]) -> list[dict]:
    out = [case(f, t, "extra", fallback=fb) for f, t, fb in ((f, t, (None if fb == () else fb)) for f, t, fb in EXTRAS)]
    for fs in FEATURE_SETS:
        for t in FEATURE_TEXTS:
            out.append(case(NORMAL, t, "extra-features", features=fs))
    out.append(case(NORMAL, "Tracked text", "extra-tracking", tracking=2.5))
    out.append(case(BOLD, "Tracked bold", "extra-tracking", tracking=-1.0))
    for font in (BOLD, ITALIC, BOLDITALIC):
        out.append(case(font, "AVATAR To Wa ffi — Hello", "extra-styles"))
    # variations: the variable test font from tests/fontmaker.py (one axis, wght 100..900), and a static font that ignores them
    tv = extra_font_names["TestVar"]
    for w in (100, 200, 300.5, 450, 500, 700, 899, 900, 2000, 0):
        out.append(case(tv, "AAA A", "extra-variations", variations=[("wght", w)]))
    out.append(case(tv, "AAA A", "extra-variations"))
    out.append(case(tv, "A A", "extra-variations", variations=[("wght", 650), ("wdth", 80)]))
    out.append(case(NORMAL, "Static font ignores wght", "extra-variations", variations=[("wght", 700)]))
    return out


def make_extra_fonts() -> dict[str, str]:
    EXTRA.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(CORE / "tests"))
    import fontmaker

    with tempfile.TemporaryDirectory() as tmp:
        shutil.copyfile(fontmaker.make_variable_font(Path(tmp)), EXTRA / "TestVar.ttf")
    mono = CORE / "examples" / "gallery" / "text" / "fonts" / "DejaVuSansMono.ttf"
    shutil.copyfile(mono, EXTRA / "DejaVuSansMono.ttf")
    return {"TestVar": "extra/TestVar.ttf", "Mono": "extra/DejaVuSansMono.ttf"}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-record", action="store_true")
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    extras = make_extra_fonts()
    cases: list[dict] = []
    for c in record(a.skip_record):
        if c["font"].endswith("DejaVuSansMono.ttf") and not c["font"].startswith("fonts/"):
            c["font"] = extras["Mono"]
        if not c["font"].startswith(("fonts/", "extra/")):
            print("skipped font outside the bundle:", c["font"])
            continue
        # a fallback chain naming a loaded font cannot be rebuilt here; keep only chains of built-in keys
        if c["fallback"] and any(not k.startswith(("DejaVu", "Noto")) for k in c["fallback"]):
            c["fallback"] = []
        cases.append(c)
    recorded = len(cases)
    for s in test_strings():
        cases.append(case(NORMAL, s, "tests", fallback=[]))
        if sum(map(ord, s)) % 5 == 0:
            cases.append(case(BOLD, s, "tests-bold"))
            cases.append(case(ITALIC, s, "tests-italic", tracking=1.0))
    tests = len(cases) - recorded
    cases += extra_cases(extras)
    seen, unique = set(), []
    for c in cases:                                           # one case per distinct call
        k = json.dumps([c["font"], c["face"], c["text"], c["tracking"], c["features"], c["variations"], c["fallback"]])
        if k not in seen:
            seen.add(k)
            unique.append(c)
    for i, c in enumerate(unique):
        c["id"] = i
    (OUT / "corpus.json").write_text(json.dumps(unique, ensure_ascii=False), encoding="utf-8")
    print(f"corpus: {len(unique)} cases ({recorded} recorded from sketches, {tests} from tests, rest extra)")

    sys.path.insert(0, str(CORE))
    sys.path.insert(0, str(WEB / "harness" / "s133"))
    os.environ["FUNGROUND_HEADLESS"] = "1"
    import corpus_run
    import uharfbuzz as hb

    roots = {"fonts": str(CORE / "funground" / "fonts"), "extra": str(EXTRA)}
    res = corpus_run.run_all(unique, roots)
    res["hb"] = {"uharfbuzz": hb.__version__, "harfbuzz": hb.version_string()}
    errors = [(i, r["error"]) for i, r in enumerate(res["results"]) if "error" in r]
    (OUT / "reference.json").write_text(json.dumps(res), encoding="utf-8")
    print(f"reference: {len(res['results'])} cases in {res['seconds']:.1f} s, {len(errors)} errors", errors[:5])


if __name__ == "__main__":
    main()
