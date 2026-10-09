# Spike S-156 check, not a sketch: which picture libraries load in the preview panel.
# The runner loads pygame-ce and Pillow when a file calls a picture function, such as filter( or get(.
import importlib

for name in ("PIL.Image", "pygame"):
    try:
        importlib.import_module(name)
        print(name, "loaded")
    except Exception as error:
        print(name, "failed:", type(error).__name__, str(error)[:200])
