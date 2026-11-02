# Used by tools/test_models.py (story S-233): cuts the person out of a photograph with ml.person and prints the picture's alpha
# plane (one byte for each pixel, zlib-packed and base64), so that the desktop's mask and the browser's can be compared. The same
# file runs on the desktop and in the browser. The test puts one line in front of it: PHOTO (a file beside the sketch).
import base64
import json
import zlib

import funground as f
from funground import ml

picture = f.load_image(PHOTO)
LIMIT = 1200                       # frames to wait for an answer: in a browser the first one takes a few seconds


def setup():
    f.size(picture.width, picture.height)


def draw():
    f.background("#2b6cb0")
    cut = ml.person(picture)
    if cut is not None:
        f.image(cut, 0, 0)
        snap = cut._snapshot()
        plane = bytes(snap.pixels[3::4])
        print("alpha " + json.dumps({"width": snap.phys_width, "height": snap.phys_height,
                                     "plane": base64.b64encode(zlib.compress(plane, 9)).decode()}))
        f.stop()
    elif f.frame_count >= LIMIT:
        print("alpha none")
        f.stop()
