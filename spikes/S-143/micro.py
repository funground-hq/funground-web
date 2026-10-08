"""S-143 micro-benchmarks of the prototype patches: interleaved baseline/patched rounds, min over 25 rounds."""
import sys, timeit, json
import profile_native as pn
pn.setup_env(1)
import prototypes as pr
from funground import api
sk = pn.fresh_sketch()
sk.size(640, 400)
P = {p.name.split()[0]: p for p in pr.make_patches()}
V = api.Vector
def circ():
    sk.circle(10, 10, 5); sk.frame.clear()
tests = {
 "fill('tomato')": (lambda: sk.fill("tomato"), ["P1"]),
 "fill('#336699')": (lambda: sk.fill("#336699"), ["P1"]),
 "fill(200,100,50)  [tuple, no cache]": (lambda: sk.fill(200, 100, 50), ["P2"]),
 "stroke_width(2)  [state update only]": (lambda: sk.stroke_width(2), ["P2"]),
 "fill('tomato') with P1+P2": (lambda: sk.fill("tomato"), ["P1", "P2"]),
 "Vector(1.5, 2.5)": (lambda: V(1.5, 2.5), ["P3"]),
 "circle()  [control: no patch applies]": (circ, []),
}
res = {}
N = 4000
for label, (fn, plist) in tests.items():
    b, a = [], []
    for _ in range(25):
        b.append(timeit.timeit(fn, number=N) / N * 1e6)
        for k in plist: P[k].apply()
        a.append(timeit.timeit(fn, number=N) / N * 1e6)
        for k in reversed(plist): P[k].revert()
        sk.frame.clear()
    res[label] = {"before_us": round(min(b), 2), "after_us": round(min(a), 2)}
    print(label, res[label], flush=True)
open("out/micro.json", "w").write(json.dumps(res, indent=1))
