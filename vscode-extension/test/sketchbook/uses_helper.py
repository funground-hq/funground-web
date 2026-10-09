import funground as f
import helpers                                # helpers.py, beside this file

print("helper value", helpers.VALUE)


def setup():
    f.size(320, 200)


def draw():
    f.background("white")
    f.fill("tomato")
    f.circle(160, 100, 20 * helpers.VALUE)


f.run()
