# Used by tools/test_models.py (story S-232): finds the body or the hand in a photograph and prints its points.
# The same file runs on the desktop and in the browser. The test puts two lines in front of it: TASK ("pose" or
# "hand") and PHOTO (a file beside the sketch).
import json

import funground as f
from funground import ml

picture = f.load_image(PHOTO)
find = ml.pose if TASK == "pose" else ml.hand
LIMIT = 1200                       # frames to wait for an answer: in a browser the first one takes a few seconds


def setup():
    f.size(picture.width, picture.height)


def draw():
    f.image(picture, 0, 0)
    found = find(picture)
    if found:
        points = {name: [round(point.x, 3), round(point.y, 3)] for name, point in found.points.items()}
        print("points " + json.dumps({"score": round(found.score, 4), "points": points}))
        f.stop()
    elif f.frame_count >= LIMIT:
        print("points none")
        f.stop()
