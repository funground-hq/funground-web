# Used by tools/test_models.py (story S-232): ml.pose and ml.hand on a camera, and what they load.
import sys

import funground as f
from funground import camera, host_services, ml

cam = camera.open()


def setup():
    f.size(320, 240)
    cam.start(320, 240)


def draw():
    f.background("black")
    if not cam.is_ready():
        return
    f.image(cam, 0, 0)
    body, hand = ml.pose(cam), ml.hand(cam)
    assert ml.pose(cam) is body, "two calls in one frame must give one answer"
    if host_services.models.generation >= 6:
        print("answers", host_services.models.generation)
        print("loaded", sorted(name for name in ("numpy", "PIL", "onnxruntime", "pygame") if name in sys.modules))
        f.stop()
