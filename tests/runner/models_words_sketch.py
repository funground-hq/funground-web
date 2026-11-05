# Used by tools/test_models.py (story S-234): hears the words in a recording and prints them.
# The same file runs on the desktop and in the browser. The test puts one line in front of it: SOUND (a .wav beside the sketch).
#
# The recording is one phrase, sent whole: ml.words(sound) gives None until the answer is in (a few seconds in a browser), and on
# a computer it waits for it. A second copy of the recording is then heard, so that the time of one answer (with the model
# already loaded) can be printed.
import json
import time

import funground as f
from funground import ml, sound

LIMIT = 6000                       # frames to wait for an answer: in a browser the first one takes a few seconds
heard = None
second = None
started = None
asked = None
recording = sound.load(SOUND)
again = None


def setup():
    f.size(200, 100)


def draw():
    global heard, second, started, again, asked
    if heard is None:
        asked = asked or time.time()
        heard = ml.words(recording)
        if heard:
            print("words " + json.dumps({"text": heard.text, "score": round(heard.score, 4), "rate": recording._rate, "seconds": round(recording.duration(), 3), "wait": round(time.time() - asked, 3)}))
            again = sound.load(SOUND)
            started = time.time()
        elif f.frame_count >= LIMIT:
            print("words none")
            f.stop()
    elif second is None:
        second = ml.words(again)
        if second:
            print("speed " + json.dumps({"seconds": round(time.time() - started, 3), "recording": round(again.duration(), 3)}))
            f.stop()
        elif f.frame_count >= 2 * LIMIT:
            print("speed none")
            f.stop()
