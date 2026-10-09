"""Listens to the microphone and prints each new loudest level it hears (used by tools/test_sound.py)."""
import funground as f

mic = f.microphone()
loudest = 0.0


def setup():
    f.size(200, 100)
    mic.start()


def draw():
    global loudest
    f.background("white")
    level = mic.level()
    f.rect(0, 0, 200 * min(1.0, level * 4), 100)
    if level > loudest + 0.005:
        loudest = level
        print("level", round(level, 4), "pitch", mic.pitch())


f.run()
