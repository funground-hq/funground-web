# Used by tools/test_models.py (story S-233): how long Python takes to turn the page's 256 x 256 mask into the person's picture
# at 640 x 480, in the browser (Pyodide, no numpy). This is the work ml.person does in Python for every new camera frame.
import time

import funground as f

WIDTH, HEIGHT, SIDE, ROUNDS = 640, 480, 256, 60


def setup():
    f.size(WIDTH, HEIGHT)


def draw():
    camera_frame = f.create_graphics(WIDTH, HEIGHT)
    camera_frame.background("#336699")
    mask = bytes((x * 3 + y) % 256 for y in range(SIDE) for x in range(SIDE))       # a soft pattern, every value used
    camera_frame._masked_copy(mask, SIDE, SIDE)                                      # once to warm up
    times = []
    for _ in range(ROUNDS):
        started = time.perf_counter()
        camera_frame._masked_copy(mask, SIDE, SIDE)
        times.append((time.perf_counter() - started) * 1000)
    times.sort()
    print(f"mask to person {times[len(times) // 2]:.2f} ms median, {times[-1]:.2f} ms slowest, {WIDTH} x {HEIGHT}")
    f.stop()
