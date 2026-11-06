# Used by tools/test_models.py (story S-250): names the sounds in some recordings and prints the names.
# The same file runs on the desktop and in the browser. The test puts one line in front of it: SOUNDS (the .wav files beside the sketch).
#
# Each recording is one window of sound, sent whole: ml.sound(clip) gives None until the answer is in (a few seconds in a browser, the
# first time), and on a computer it waits for it. After the last one, the first recording is heard again as a new Sound, so that the
# time of one answer (with the model already loaded) can be printed.
import json
import time
import wave
from array import array

import funground as f
from funground import ml, sound

ENGINE_RATE = 44100                # the rate every sound has here, as a microphone's has
LIMIT = 6000                       # frames to wait for an answer: in a browser the first one takes a few seconds


def read(name):
    """The recording as a Sound at 44.1 kHz, made here by linear interpolation in plain Python. sound.load() is not used: it decodes
    and resamples with another library on a computer than in a page (measured: the same file gives waveforms about 13 percent
    apart in size), and this test is about the model, which must be given the same numbers on both."""
    with wave.open(name) as wav:
        rate = wav.getframerate()
        raw = array("h")
        raw.frombytes(wav.readframes(wav.getnframes()))
    x = [v / 32768.0 for v in raw]
    out = []
    for j in range(int(len(x) * ENGINE_RATE / rate)):
        p = j * rate / ENGINE_RATE
        i = int(p)
        t = p - i
        out.append(x[i] * (1 - t) + x[min(i + 1, len(x) - 1)] * t)
    return sound.create(out, ENGINE_RATE)


clips = [(name, read(name)) for name in SOUNDS]
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
            again = read(SOUNDS[0])
            started = time.time()
    elif second is None:
        second = ml.sound(again)
        if second:
            print("speed " + json.dumps({"seconds": round(time.time() - started, 3), "recording": round(again.duration(), 3)}))
            f.stop()
        elif f.frame_count >= 2 * LIMIT:
            print("speed none")
            f.stop()
