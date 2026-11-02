# Used by tools/test_models.py (stories S-232, S-233): ml.pose, ml.hand and ml.person on a camera, and what they load.
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
    body, hand, person = ml.pose(cam), ml.hand(cam), ml.person(cam)
    assert ml.pose(cam) is body, "two calls in one frame must give one answer"
    assert ml.person(cam) is person, "two calls in one frame must give one picture"
    if person is not None:
        f.image(person, 0, 0)
    if host_services.models.generation >= 6:
        print("answers", host_services.models.generation)
        print("loaded", sorted(name for name in ("numpy", "PIL", "onnxruntime", "pygame") if name in sys.modules))
        f.stop()
