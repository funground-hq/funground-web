// Test the pure parts of a body that is followed and steadied in a camera's pictures (story S-328), with Node and nothing else:
//
//   C:\sw\nodejs\node.exe tools/test_follow.mjs
//
// runner/models-glue.js is the JavaScript twin of funground-ml's _glue.py (Tracker with follow=, Smoother, Steadier, body_landmarks).
// These checks are the twins of ml/tests/test_unit.py's, and follow_reference.json holds the numbers _glue.py's own Steadier gave for
// one sequence (made with a clock that ticks 1/24 s a picture; see the notes at the bottom), which the JavaScript must give too.
// The models themselves (onnxruntime) are not run here: tools/test_models.py does that, in Chrome.
import { readFileSync } from "node:fs";
import assert from "node:assert/strict";

import {
  REUSE_LIMIT, POINTS_SMOOTHING, Smoother, Steadier, Tracker, bodyLandmarks,
} from "../runner/models-glue.js";

const reference = JSON.parse(readFileSync(new URL("./follow_reference.json", import.meta.url)));
const tests = [];
const test = (name, body) => tests.push([name, body]);

const clockAt = () => { const clock = () => clock.now; clock.now = 0; return clock; };
const body = (x = 0) => Float64Array.of(100 + x, 100, 300 + x, 500);        // a body 200 by 400: its size is 300

// ---- the tracker

test("with follow the region from the landmarks is kept and never goes stale", async () => {
  const tracker = new Tracker(), looked = [];
  let detects = 0;
  const landmarks = async (region) => { looked.push(region); return { score: 0.99, region: `next after ${looked.length}` }; };
  for (let i = 0; i < REUSE_LIMIT + 5; i++) {
    await tracker.find(64, 48, async () => { detects++; return "detected"; }, landmarks, (region) => "steady " + region);
  }
  assert.equal(detects, 1);                                                  // no look again at REUSE_LIMIT: the region follows
  assert.deepEqual(looked.slice(0, 3), ["detected", "steady next after 1", "steady next after 2"]);
});

test("without follow a photo keeps the detector's box, and looks again after REUSE_LIMIT pictures", async () => {
  const tracker = new Tracker(), looked = [];
  let detects = 0;
  const landmarks = async (region) => { looked.push(region); return { score: 0.99, region: "next" }; };
  for (let i = 0; i < REUSE_LIMIT + 2; i++) await tracker.find(64, 48, async () => { detects++; return "detected"; }, landmarks);
  assert.ok(looked.every((region) => region === "detected"));
  assert.equal(detects, 2);                                                  // the first look, and one more after REUSE_LIMIT reuses
});

test("a landmark answer without a region cannot be followed, so the detector's box is kept", async () => {
  const tracker = new Tracker(), looked = [];
  const landmarks = async (region) => { looked.push(region); return { score: 0.99 }; };
  for (let i = 0; i < 3; i++) await tracker.find(64, 48, async () => "detected", landmarks, () => "steady");
  assert.deepEqual(looked, ["detected", "detected", "detected"]);
});

test("a new picture size starts again", async () => {
  const tracker = new Tracker();
  let detects = 0;
  const landmarks = async () => ({ score: 0.99, region: "next" });
  const detect = async () => { detects++; return "detected"; };
  await tracker.find(64, 48, detect, landmarks, (r) => r);
  await tracker.find(64, 48, detect, landmarks, (r) => r);
  await tracker.find(32, 24, detect, landmarks, (r) => r);
  assert.equal(detects, 2);
});

// ---- the smoother

test("the first points are given as they are", () => {
  const smoother = new Smoother(...POINTS_SMOOTHING, clockAt());
  assert.deepEqual(smoother.smooth(body()), body());
});

test("a still body that shakes is held steady", () => {
  const clock = clockAt(), smoother = new Smoother(...POINTS_SMOOTHING, clock);
  smoother.smooth(body());
  const shakes = [];
  for (let i = 1; i < 49; i++) {                                              // two seconds at 24 a second, shaking by 3 pixels
    clock.now = i / 24;
    shakes.push(smoother.smooth(body(i % 2 ? 3 : -3))[0] - 100);
  }
  assert.ok(Math.max(...shakes.slice(-24).map(Math.abs)) < 1.0);
});

test("a body that moves fast is not left behind", () => {
  const clock = clockAt(), smoother = new Smoother(...POINTS_SMOOTHING, clock);
  smoother.smooth(body());
  let x = 0;
  for (let i = 1; i < 13; i++) {                                              // half a second, moving 600 pixels a second
    clock.now = i / 24;
    x = smoother.smooth(body(25 * i))[0];
  }
  assert.ok(Math.abs(x - (100 + 25 * 12)) < 25);                              // less than one picture's move behind
});

test("after a gap the smoothing starts afresh", () => {
  const clock = clockAt(), smoother = new Smoother(...POINTS_SMOOTHING, clock);
  smoother.smooth(body());
  clock.now = smoother.gap + 0.1;
  assert.deepEqual(smoother.smooth(body(50)), body(50));
});

test("points of another shape start afresh", () => {
  const clock = clockAt(), smoother = new Smoother(...POINTS_SMOOTHING, clock);
  smoother.smooth(body());
  clock.now = 1 / 24;
  assert.deepEqual(smoother.smooth(Float64Array.of(1, 2, 3, 4, 5, 6)), Float64Array.of(1, 2, 3, 4, 5, 6));
});

test("the steadier gives a region in the tracker's shape", () => {
  assert.deepEqual(new Steadier(clockAt()).region([[1, 2], [3, 4]]), [[1, 2], [3, 4]]);
});

test("the steadier gives the numbers funground-ml's gave for a shaking, then moving, body", () => {
  const clock = clockAt(), steadier = new Steadier(clock);
  let worst = 0;
  reference.forEach((row, index) => {
    clock.now = (index + 1) / 24;
    const out = steadier.points(Float64Array.from(row.in));
    const region = steadier.region([[row.in[0], row.in[1]], [row.in[2], row.in[3]]]);
    worst = Math.max(worst, ...out.map((v, i) => Math.abs(v - row.out[i])),
      ...region.flat().map((v, i) => Math.abs(v - row.region.flat()[i])));
  });
  assert.ok(worst < 1e-9, `the largest difference from _glue.py is ${worst}`);
  console.log(`  (largest difference from _glue.py over ${reference.length} pictures: ${worst})`);
});

// ---- the pose landmark model's rows, with a model that is not one (the rows say where the points go)

/** A session that answers like the pose landmark model: 39 rows of (x, y, depth, visible, present) in the 256 x 256 crop, and a score. */
function fakePose(visible) {
  const rows = new Float32Array(39 * 5);
  for (let i = 0; i < 39; i++) rows.set([10 + i, 20 + 2 * i, 0, visible(i), 0], i * 5);
  return {
    inputNames: ["input"], outputNames: ["landmarks", "score"],
    run: async () => ({ landmarks: { data: rows }, score: { data: Float32Array.of(0.97) } }),
  };
}
const fakeOrt = { Tensor: class { constructor(type, data, dims) { Object.assign(this, { type, data, dims }); } } };
const photo = { rgba: new Uint8Array(200 * 100 * 4).fill(128), width: 200, height: 100 };

test("body_landmarks gives 33 points, the two helper rows as the next region, and the sigmoid of the visible column", async () => {
  const found = await bodyLandmarks(fakeOrt, fakePose((i) => (i % 2 ? 4 : -4)), photo, [[100, 50], [100, 20]]);
  assert.equal(found.points.length, 66);
  assert.equal(found.scores.length, 33);
  assert.ok(Math.abs(found.scores[0] - 1 / (1 + Math.exp(4))) < 1e-6 && Math.abs(found.scores[1] - 1 / (1 + Math.exp(-4))) < 1e-6);
  assert.ok(found.scores.every((v) => v >= 0 && v <= 1));
  // the helper rows come from the same map as the points: row 33 follows row 32 by one crop pixel across and two down, turned alike
  const step = (a, b) => [b[0] - a[0], b[1] - a[1]];
  const rowStep = step([found.points[64], found.points[65]], found.region[0]);
  const nextStep = step(found.region[0], found.region[1]);
  assert.ok(Math.abs(rowStep[0] - nextStep[0]) < 1e-9 && Math.abs(rowStep[1] - nextStep[1]) < 1e-9);
});

// ---- run

let failed = 0;
for (const [name, body] of tests) {
  try {
    await body();
    console.log(`ok   ${name}`);
  } catch (error) {
    failed++;
    console.log(`FAIL ${name}\n${error.stack ?? error}`);
  }
}
console.log(failed ? `${failed} of ${tests.length} failed` : `all ${tests.length} passed`);
process.exit(failed ? 1 : 0);

// The reference was made with: Steadier(clock) from funground_ml._glue, a clock set to i / 24 before picture i (1 to 29), the
// four-point body of the tests above (100,100  300,500  200,300  150,450) shaken by plus or minus 3 pixels with noise (numpy
// default_rng(1), sigma 1) and, from picture 13, moving 20 pixels a picture; "out" is steadier.points(in), "region" is
// steadier.region(first two points of in).
