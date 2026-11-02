# Used by tools/test_models.py (story S-232): how many answers a second the models give in a browser.
# A new picture every frame (the photograph with a dot drawn on it), so every frame is sent. TASK and PHOTO are put in
# front by the test, as in models_sketch.py.
import time

import funground as f
from funground import host_services, ml

photo = f.load_image(PHOTO)
find = ml.pose if TASK == "pose" else ml.hand
SECONDS = 8
started = None
g = None


def setup():
    global g
    f.size(photo.width, photo.height)
    g = f.create_graphics(photo.width, photo.height)


def draw():
    global started
    g.image(photo, 0, 0)
    g.circle(f.frame_count % photo.width, 5, 3)
    found = find(g)
    f.image(g, 0, 0)
    models = host_services.models
    if found is not None and started is None:
        started = (time.perf_counter(), models.generation, f.frame_count)
    if started is not None and time.perf_counter() - started[0] >= SECONDS:
        seconds = time.perf_counter() - started[0]
        print(f"speed {(models.generation - started[1]) / seconds:.2f} answers a second, "
              f"{(f.frame_count - started[2]) / seconds:.1f} frames a second")
        f.stop()
    elif f.frame_count >= 3000 and started is None:
        print("speed none")
        f.stop()
