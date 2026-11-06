# Used by tools/test_models.py (story S-250): ml.sound on a microphone, in the browser, with Chrome's fake microphone (it plays a beep
# every second or so). Prints what the page answered: the sketch listens until `COUNT` answers have come, or a time limit passes.
import json
import time

import funground as f
from funground import ml, sound

COUNT = 3
mic = sound.microphone()
mic.start()
answers = []
started = time.time()
last = None


def setup():
    f.size(200, 100)


def draw():
    global last
    heard = ml.sound(mic)
    if heard and heard.is_new:
        answers.append({"name": heard.name, "score": round(heard.score, 3), "next": [g.name for g in heard.next], "at": round(time.time() - started, 2)})
    if len(answers) >= COUNT or time.time() - started > 60:
        print("microphone " + json.dumps({"rate": mic._rate, "answers": answers}))
        f.stop()
