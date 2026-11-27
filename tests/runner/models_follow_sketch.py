# Used by tools/test_models.py (story S-328): a body that is followed and steadied in a camera's pictures, the whole road in a page
# (the sketch's ml.pose, Python in the page, worker.js, the models worker and back), against a still picture's. The test puts these
# in front of it: PHOTO (a file beside the sketch), MOVING (True: the pictures come from a camera, False: they are a picture).
#
# The photograph moves to the right by SHIFT pixels a picture on a black canvas, and a picture is changed only when the answer to
# the one before has come, so that every answer is for a known picture. It prints one line, "follow {...}", with the mean and the
# largest distance of a point's move from the true move (SHIFT, 0) over all 33 points, and how many pictures were answered. The time
# between two pictures is the real one (a page answers a few times a second), not the 1/24 s of models_follow.js.
import json
import math

import funground as f
from funground import host_services, ml

photo = f.load_image(PHOTO)
SHIFT, LEFT, PICTURES, LIMIT = 3, 20, 24, 3000
canvas = None


class Camera:
    """What a camera is to funground-ml: something with a picture to read now (the core's FrameSource)."""
    _mirror = False

    def _current_picture(self):
        return canvas


source = Camera() if MOVING else None
sent = 0                              # the picture the canvas shows now
answers = []                          # one list of 33 (x, y) for each picture, in order
models = getattr(host_services, "models", None)       # None on the desktop, where an answer comes at once
seen = None


def show():
    canvas.background("black")
    canvas.image(photo, LEFT + SHIFT * sent, 0)


def setup():
    global canvas, source
    f.size(740, 960)
    canvas = f.create_graphics(740, 960)
    source = source or canvas
    show()


def draw():
    global sent, seen
    f.image(canvas, 0, 0)
    found = ml.pose(source)
    fresh = models is None or models.generation != seen
    if models is not None and found is not None:
        seen = models.generation
    if found is not None and fresh:
        answers.append([(p.x, p.y) for p in found.points.values()])
        sent += 1
        if sent < PICTURES:
            show()
    if sent >= PICTURES:
        jumps = [math.hypot(x - x0 - SHIFT, y - y0) for before, now in zip(answers, answers[1:])
                 for (x0, y0), (x, y) in zip(before, now)]
        print("follow " + json.dumps({"jump_mean": round(sum(jumps) / len(jumps), 3), "jump_max": round(max(jumps), 3),
                                      "pictures": len(answers)}))
        f.stop()
    elif f.frame_count >= LIMIT:
        print("follow none")
        f.stop()
