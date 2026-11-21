# Used by tools/test_models.py (story S-328): the desktop's numbers for tests/runner/models_follow.js. Run with a Python that has
# funground-ml (onnxruntime, numpy, Pillow): python models_follow_desktop.py PHOTO FRAMES SHIFT LEFT WIDTH HEIGHT.
#
# One photograph, moved to the right by SHIFT pixels a picture on a black canvas, goes through _glue.py's own Tracker and Steadier as
# a camera's pictures do ("moving") and as still pictures do, with a clock of 1/24 s a picture. Prints one line, "follow {...}", with
# for each of "still" and "moving": the mean and the largest distance of a point's move from the true move (SHIFT, 0), in pixels, how
# many times the detector ran, and the 33 scores of the first picture.
import json
import sys

import numpy as np
from PIL import Image

from funground_ml import _fetch, _glue, _runtime

photo_file, frames, shift, left, width, height = sys.argv[1], *map(int, sys.argv[2:7])
photo = Image.open(photo_file).convert("RGB")
paths = _fetch.ensure("pose", None, "the test")
detector = _runtime.session(paths["detector"], "pose")
landmark_model = _runtime.session(paths["landmarks"], "pose")


class Clock:
    now = 0.0

    def __call__(self):
        return self.now


def sequence(moving: bool) -> dict:
    clock, tracker = Clock(), _glue.Tracker()
    steadier = _glue.Steadier(clock)
    looks, points, first_scores = 0, [], None
    for k in range(frames):
        clock.now = (k + 1) / 24
        image = Image.new("RGB", (width, height))
        image.paste(photo, (left + shift * k, 0))

        def detect_region():
            nonlocal looks
            looks += 1
            detection = _glue.detect(detector, image, _glue.POSE_DETECTOR)
            return None if detection is None else _glue.body_region(detection)

        steady = steadier if moving else None
        found = tracker.find(image, detect_region, lambda region: _glue.body_landmarks(landmark_model, image, region),
                             follow=steady.region if steady else None)
        if found is None:
            if steady:
                steady.reset()
            points.append(None)
            continue
        points.append(steady.points(found.points) if steady else found.points)
        if first_scores is None:
            first_scores = [round(float(v), 6) for v in found.scores]
    jumps = [np.hypot(*(now - before - np.array([shift, 0.0])).T) for before, now in zip(points, points[1:])
             if before is not None and now is not None]
    jumps = np.concatenate(jumps)
    return {"jump_mean": round(float(jumps.mean()), 3), "jump_max": round(float(jumps.max()), 3), "detector_runs": looks,
            "found": sum(p is not None for p in points), "pictures": frames, "scores": first_scores}


print("follow " + json.dumps({"still": sequence(False), "moving": sequence(True)}))
