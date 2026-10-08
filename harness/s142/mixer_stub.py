"""Opt-in stand-in for pygame.mixer under Pyodide (MIXER_STUB=1 in run.mjs).

pygame-ce's mixer cannot start in Pyodide 314.0.7 under Node: SDL's audio subsystem (even the "dummy"
driver) needs a thread, and ``mixer.init`` fails with "Couldn't create audio thread startup semaphore".
funground then raises "sound support is not available on this computer" for every f.melody()/f.pluck()/...
This stub lets headless runs (FUNGROUND_HEADLESS=1: nothing is ever played) build sounds from samples, so the
sketches' drawing can be rendered and timed. It plays nothing. Sounds loaded from files are not supported.
"""
import pygame
import pygame.mixer as _mixer

_state = {"init": None}


def init(frequency=44100, size=-16, channels=2, buffer=512, **kw):
    _state["init"] = (frequency, size, channels)


def get_init():
    return _state["init"]


def quit():
    _state["init"] = None


class Sound:
    def __init__(self, file=None, buffer=None, **kw):
        if buffer is None:
            raise pygame.error("mixer stub: sounds from files are not supported")
        rate, _, ch = _state["init"]
        self._len = len(buffer) / (2.0 * ch * rate)

    def get_length(self):
        return self._len

    def play(self, loops=0, **kw):
        return None


def install():
    _mixer.init, _mixer.get_init, _mixer.quit, _mixer.Sound = init, get_init, quit, Sound
