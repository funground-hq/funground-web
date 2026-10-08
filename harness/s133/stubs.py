"""S-133: what `import funground` needs at load time that Pyodide lacks and the text test does not use
(the same stand-ins as harness/s136/shim.py: skia-pathops and the Cairo renderer). uharfbuzz is NOT
stubbed here: shim/uharfbuzz.py is the real thing under test."""
import sys
import types


class _Names:
    def __getattr__(self, attr):
        return attr


def _module(name, **present):
    mod = types.ModuleType(name)
    mod.__dict__.update(present)

    def __getattr__(attr):
        if attr.startswith("__"):
            raise AttributeError(attr)
        raise ImportError(f"{name}.{attr} is not available in this spike")

    mod.__getattr__ = __getattr__
    return mod


sys.modules["pathops"] = _module("pathops", PathVerb=_Names(), LineCap=_Names(), LineJoin=_Names())
sys.modules["funground.renderers.cairo2d"] = _module("funground.renderers.cairo2d", CairoRenderer=type("CairoRenderer", (), {}))
