# Used by tools/test_camera.py (story S-172): draws Chrome's fake camera, prints what one pixel of each frame looks
# like, then records half a second and saves it as a GIF.
import funground as f

cam = f.camera()
clip = None


def setup():
    f.size(64, 48)
    cam.start(64, 48)


def draw():
    global clip
    f.background("black")
    if not cam.is_ready():
        return
    f.image(cam, 0, 0)
    c = cam.picture().get(32, 24)
    print(f"frame {c.red} {c.green} {c.blue}")
    if clip is None:
        clip = cam.record(0.5)
    elif clip.done:
        clip.save("clip.gif")
        print(f"saved {len(clip)} frames")
        f.no_loop()
