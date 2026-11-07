# Used by tools/test_models.py (story S-250): names the sounds in some recordings and prints the names.
# The same file runs on the desktop and in the browser. The test puts one line in front of it: SOUNDS (the .wav files beside the sketch).
#
# Each recording is one window of sound, sent whole: ml.sound(clip) gives None until the answer is in (a few seconds in a browser, the
# first time), and on a computer it waits for it. After the last one, the first recording is heard again as a new Sound, so that the
# time of one answer (with the model already loaded) can be printed.
import json
import time

import funground as f
from funground import ml, sound

LIMIT = 6000                       # frames to wait for an answer: in a browser the first one takes a few seconds


started = time.time()
clips = [(name, sound.load(name)) for name in SOUNDS]
print("loaded " + json.dumps({"seconds": round(time.time() - started, 3), "recording": round(sum(c.duration() for _, c in clips), 3)}))
index = 0
asked = None
second = None
again = None
started = None
frame_asked = 0


def setup():
    f.size(200, 100)


def show(heard):
    return {"name": heard.name, "score": round(heard.score, 4), "next": [{"name": g.name, "score": round(g.score, 4)} for g in heard.next]}


def draw():
    global index, asked, second, again, started, frame_asked
    if index < len(clips):
        name, clip = clips[index]
        if asked is None:
            asked, frame_asked = time.time(), f.frame_count
        heard = ml.sound(clip)
        if heard:
            print("sound " + json.dumps({"clip": name, **show(heard), "rate": clip._sample_rate(), "seconds": round(clip.duration(), 3),
                                          "wait": round(time.time() - asked, 3)}))
            index, asked = index + 1, None
        elif f.frame_count - frame_asked >= LIMIT:
            print("sound none " + name)
            index, asked = index + 1, None
        if index == len(clips):
            again = sound.load(SOUNDS[0])
            started = time.time()
    elif second is None:
        second = ml.sound(again)
        if second:
            print("speed " + json.dumps({"seconds": round(time.time() - started, 3), "recording": round(again.duration(), 3)}))
            f.stop()
        elif f.frame_count >= 2 * LIMIT:
            print("speed none")
            f.stop()
