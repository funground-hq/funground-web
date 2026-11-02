// The pictures-in, points-out part of the pose and hand models, for the page (story S-232).
//
// This is the JavaScript twin of funground-ml's `_glue.py` (in the funground repository, ml/funground_ml). It runs the same four
// ONNX files and must give the same points, so it follows the Python file step by step and uses the same numbers. If the one
// changes, the other changes with it. Nothing here touches the page or a worker: it takes onnxruntime-web's `ort` module and two
// sessions, so it can be read, and tested, on its own.
//
// Both tasks have two steps, as MediaPipe's own do:
//   1. A detector looks at the whole picture, squeezed into a square, and says roughly where the body (or the palm) is.
//   2. A landmark model looks at a square cut from the picture around that place, turned so that the body (or hand) stands
//      upright, and says where each point is.
// The detectors give a box and key points as offsets from a fixed grid of anchors; the landmark models give points in the
// cut square's own pixels. This file turns those back into pixels of the picture.
//
// A picture is `{rgba, width, height}`: opaque RGBA bytes (a Uint8Array or Uint8ClampedArray), row by row from the top left.
// Points come out in that picture's pixels, as a flat array x0, y0, x1, y1, ... of the model's own points (the Python side
// swaps left and right for a mirrored camera).

// ---- the numbers that decide what is "a body" or "a hand", and how long a found box is trusted (the same as _glue.py)
export const DETECTOR_MIN_SCORE = 0.5;     // the detector's best score, after the sigmoid, must reach this
export const POSE_MIN_SCORE = 0.5;         // the pose landmark model's "there is a body" score
export const HAND_MIN_SCORE = 0.8;         // the hand landmark model's "there is a hand" score
export const REUSE_MIN_SCORE = 0.9;        // a box is reused for the next picture only if the landmarks found in it scored this well
export const REUSE_LIMIT = 10;             // ... and for at most this many pictures in a row, then the detector looks again

// ---- cutting a square out of the picture

/**
 * Cut a square `side` pixels wide, centred on (cx, cy) and turned by `angle` radians, and resample it to size x size.
 *
 * One affine map does the cut, the turn, the black padding where the square leaves the picture, and the resize. Each output
 * pixel is looked up in the picture with bilinear interpolation, the way Pillow's `Image.transform` does it (so the crop is the
 * same as the desktop's, to the last grey level, and not the browser canvas's own smoothing). Returns the crop as RGB bytes,
 * the picture pixels for one crop pixel (`scale`), and `toPicture(points)`, the way back from crop pixels to picture pixels.
 */
export function cut(picture, cx, cy, side, angle, size) {
  const { rgba, width, height } = picture;
  const cos = Math.cos(angle), sin = Math.sin(angle), k = side / size;
  // output pixel (x, y) is read from the picture at (a x + b y + c, d x + e y + f)
  const a = k * cos, b = -k * sin, c = cx - 0.5 * side * (cos - sin);
  const d = k * sin, e = k * cos, f = cy - 0.5 * side * (sin + cos);
  const pixels = new Uint8Array(size * size * 3);        // black where nothing is read
  const lastX = width - 1, lastY = height - 1;
  for (let y = 0; y < size; y++) {
    for (let x = 0; x < size; x++) {
      let u = a * (x + 0.5) + b * (y + 0.5) + c;         // pixel centres, as in Pillow
      let v = d * (x + 0.5) + e * (y + 0.5) + f;
      if (u < 0 || u >= width || v < 0 || v >= height) continue;
      u -= 0.5;
      v -= 0.5;
      const u0 = Math.floor(u), v0 = Math.floor(v), du = u - u0, dv = v - v0;
      // the four neighbours, the edge pixel repeated at the picture's border
      const left = Math.min(Math.max(u0, 0), lastX) * 4, right = Math.min(Math.max(u0 + 1, 0), lastX) * 4;
      const top = Math.min(Math.max(v0, 0), lastY) * width * 4, bottom = Math.min(Math.max(v0 + 1, 0), lastY) * width * 4;
      const out = (y * size + x) * 3;
      for (let channel = 0; channel < 3; channel++) {
        const upper = rgba[top + left + channel] + (rgba[top + right + channel] - rgba[top + left + channel]) * du;
        const lower = rgba[bottom + left + channel] + (rgba[bottom + right + channel] - rgba[bottom + left + channel]) * du;
        pixels[out + channel] = upper + (lower - upper) * dv;     // stored as a whole number, as Pillow does
      }
    }
  }
  const toPicture = (points) => {
    const mapped = new Float64Array(points.length);
    for (let i = 0; i < points.length; i += 2) {
      mapped[i] = a * points[i] + b * points[i + 1] + c;
      mapped[i + 1] = d * points[i] + e * points[i + 1] + f;
    }
    return mapped;
  };
  return { pixels, scale: k, toPicture };
}

/** The whole picture inside a size x size square, not stretched, with black bars where it does not reach. */
export function letterbox(picture, size) {
  return cut(picture, picture.width / 2, picture.height / 2, Math.max(picture.width, picture.height), 0, size);
}

/**
 * MediaPipe's region of interest for a landmark model, from a detection. The square is turned so that the line from `from` to
 * `to` points up, made `scale` times the box's longer side, and moved along the box's own up direction by `shiftY` times its
 * height. `box` is [centre x, centre y, width, height] in picture pixels.
 */
export function regionOfInterest(picture, [cx, cy, width, height], [x0, y0], [x1, y1], scale, shiftY, size) {
  let angle = Math.PI / 2 - Math.atan2(-(y1 - y0), x1 - x0);
  angle -= 2 * Math.PI * Math.floor((angle + Math.PI) / (2 * Math.PI));        // into -pi .. pi
  return cut(picture, cx - shiftY * height * Math.sin(angle), cy + shiftY * height * Math.cos(angle), Math.max(width, height) * scale, angle, size);
}

// ---- the detectors

const sigmoid = (x) => 1 / (1 + Math.exp(-Math.max(-50, Math.min(50, x))));

/**
 * The detector's anchor centres as fractions of the square (0 to 1), a flat array x0, y0, x1, y1, ... as MediaPipe defines
 * them. Each stride gives a grid with a cell every `stride` pixels and two anchors in each cell; consecutive layers with the
 * same stride are merged into one grid with more anchors per cell.
 */
export function anchors(size, strides) {
  const out = [];
  for (let i = 0; i < strides.length;) {
    let j = i;
    while (j < strides.length && strides[j] === strides[i]) j++;
    const cells = Math.ceil(size / strides[i]);
    for (let row = 0; row < cells; row++) {
      for (let column = 0; column < cells; column++) {
        for (let n = 0; n < 2 * (j - i); n++) out.push((column + 0.5) / cells, (row + 0.5) / cells);
      }
    }
    i = j;
  }
  return Float64Array.from(out);
}

/** What differs between the two detectors; the rest of the work is shared. */
export const POSE_DETECTOR = { size: 224, strides: [8, 16, 32, 32, 32], keyPoints: 4, channelsFirst: true, centred: true };
export const PALM_DETECTOR = { size: 192, strides: [8, 16, 16, 16], keyPoints: 7, channelsFirst: false, centred: false };
const anchorCache = new Map();

function anchorsOf(spec) {
  const key = `${spec.size}:${spec.strides}`;
  if (!anchorCache.has(key)) anchorCache.set(key, anchors(spec.size, spec.strides));
  return anchorCache.get(key);
}

/** A crop's bytes as the model's input: 0 to 1 (or -1 to 1), channels last (or first), a Float32Array. */
function toTensor(pixels, size, { centred = false, channelsFirst = false } = {}) {
  const count = size * size, out = new Float32Array(count * 3);
  for (let i = 0; i < count; i++) {
    for (let channel = 0; channel < 3; channel++) {
      let value = pixels[i * 3 + channel] / 255;
      if (centred) value = (value - 0.5) * 2;
      out[channelsFirst ? channel * count + i : i * 3 + channel] = value;
    }
  }
  return out;
}

const run = (ort, session, data, dims) => session.run({ [session.inputNames[0]]: new ort.Tensor("float32", data, dims) });

/**
 * The detector's best detection in the picture, or null when its best score is under DETECTOR_MIN_SCORE. Only the best
 * detection is used (one body, one hand), so there is no non-maximum suppression. Returns {box, keyPoints}: the box is
 * [centre x, centre y, width, height] and each key point [x, y], in picture pixels.
 */
export async function detect(ort, session, picture, spec) {
  const crop = letterbox(picture, spec.size);
  const dims = spec.channelsFirst ? [1, 3, spec.size, spec.size] : [1, spec.size, spec.size, 3];
  const outputs = await run(ort, session, toTensor(crop.pixels, spec.size, spec), dims);
  // One output has a single number for each anchor (the score), the other has the box and key points. Their order is not the
  // same in every file, so they are told apart by their shape.
  const [scoreTensor, regressionTensor] = session.outputNames.map((name) => outputs[name])
    .sort((p, q) => p.dims[p.dims.length - 1] - q.dims[q.dims.length - 1]);
  const scores = scoreTensor.data, regressions = regressionTensor.data, anchor = anchorsOf(spec);
  let best = 0;
  for (let i = 1; i < scores.length; i++) if (scores[i] > scores[best]) best = i;
  if (sigmoid(scores[best]) < DETECTOR_MIN_SCORE) return null;
  const perAnchor = regressions.length / scores.length;       // the box centre, the box size, then the key points: x, y pairs
  const row = (n) => [regressions[best * perAnchor + 2 * n], regressions[best * perAnchor + 2 * n + 1]];
  const inPicture = (n) => {
    const [u, v] = row(n);
    return [(u / spec.size + anchor[best * 2]) * spec.size, (v / spec.size + anchor[best * 2 + 1]) * spec.size];
  };
  const asPoints = (rows) => crop.toPicture(rows.flat());
  const [centreX, centreY] = asPoints([inPicture(0)]);
  const keyPoints = [];
  const mapped = asPoints(Array.from({ length: spec.keyPoints }, (_, n) => inPicture(2 + n)));
  for (let n = 0; n < spec.keyPoints; n++) keyPoints.push([mapped[2 * n], mapped[2 * n + 1]]);
  const [width, height] = row(1);
  return { box: [centreX, centreY, Math.abs(width) * crop.scale, Math.abs(height) * crop.scale], keyPoints };
}

// ---- the landmark models

/** What the pose landmark model needs from a body detection: the middle of the hips and a point on the circle that holds the
 *  whole body (their distance is the body's size, their direction is which way up it is). */
export const bodyRegion = (detection) => [detection.keyPoints[0], detection.keyPoints[1]];

/** What the hand landmark model needs from a palm detection: the box, and the key points at the wrist and at the base of the
 *  middle finger (which way is up for the hand). */
export const handRegion = (detection) => [detection.box, detection.keyPoints[0], detection.keyPoints[2]];

/** The body's 33 points in the square around `region`, or null when the score is under POSE_MIN_SCORE.
 *  The model gives 39 rows of (x, y, depth, visible, present); the first 33 are the body, the last 6 are tracking helpers. */
export async function bodyLandmarks(ort, session, picture, [[x0, y0], [x1, y1]], count = 33) {
  const radius = Math.hypot(x1 - x0, y1 - y0);
  const crop = regionOfInterest(picture, [x0, y0, 2 * radius, 2 * radius], [x0, y0], [x1, y1], 1.25, 0, 256);
  const outputs = await run(ort, session, toTensor(crop.pixels, 256), [1, 256, 256, 3]);
  const score = outputs[session.outputNames[1]].data[0];
  if (score < POSE_MIN_SCORE) return null;
  const rows = outputs[session.outputNames[0]].data, xy = new Float64Array(count * 2);
  for (let i = 0; i < count; i++) xy.set([rows[i * 5], rows[i * 5 + 1]], i * 2);
  return { points: crop.toPicture(xy), score: Math.min(score, 1) };
}

/** The hand's 21 points in the square around `region`, or null when the score is under HAND_MIN_SCORE. */
export async function handLandmarks(ort, session, picture, [box, keyFrom, keyTo], count = 21) {
  const crop = regionOfInterest(picture, box, keyFrom, keyTo, 2.6, -0.5, 224);
  const outputs = await run(ort, session, toTensor(crop.pixels, 224), [1, 224, 224, 3]);
  const score = outputs[session.outputNames[1]].data[0];
  if (score < HAND_MIN_SCORE) return null;
  const rows = outputs[session.outputNames[0]].data, xy = new Float64Array(count * 2);
  for (let i = 0; i < count; i++) xy.set([rows[i * 3], rows[i * 3 + 1]], i * 2);
  return { points: crop.toPicture(xy), score: Math.min(score, 1) };
}

// ---- tracking: the box of the last picture, reused

/**
 * The region found for the last picture of one source, so the detector need not run for every picture.
 *
 * The region is reused for the next picture only while the landmarks found in it scored at least REUSE_MIN_SCORE, and for at
 * most REUSE_LIMIT pictures in a row; then, or when a reused region does not do, the detector looks again. A new picture size
 * starts again. (The same rule as `Tracker` in _glue.py.)
 */
export class Tracker {
  constructor() {
    this.region = null;
    this.reused = 0;
    this.size = null;
  }

  forget() {
    this.region = null;
    this.reused = 0;
  }

  canReuse() {
    return this.region !== null && this.reused < REUSE_LIMIT;
  }

  /** The landmarks in a picture of `width` x `height`. `detectRegion()` gives a new region (or null for nobody);
   *  `landmarks(region)` gives the points in a region (or null when the score is too low). Both may be async. */
  async find(width, height, detectRegion, landmarks) {
    if (this.size?.[0] !== width || this.size?.[1] !== height) {
      this.forget();
      this.size = [width, height];
    }
    if (this.canReuse()) {
      const found = await landmarks(this.region);
      if (found !== null && found.score >= REUSE_MIN_SCORE) {
        this.reused++;
        return found;
      }
    }
    const region = await detectRegion();
    if (region === null) {
      this.forget();
      return null;
    }
    const found = await landmarks(region);
    if (found !== null && found.score >= REUSE_MIN_SCORE) {
      this.region = region;
      this.reused = 0;
    } else {
      this.forget();
    }
    return found;
  }
}

// ---- the two tasks

const TASKS = {
  pose: { detector: POSE_DETECTOR, region: bodyRegion, landmarks: bodyLandmarks },
  hand: { detector: PALM_DETECTOR, region: handRegion, landmarks: handLandmarks },
};

/**
 * One source's finder for a task ("pose" or "hand"): it keeps that source's tracker, and shares the sessions.
 * `find(picture)` gives {points, score} (points flat, in the picture's pixels) or null when nobody is there.
 */
export function createFinder(task, ort, detectorSession, landmarkSession) {
  const { detector, region, landmarks } = TASKS[task];
  const tracker = new Tracker();
  return {
    find: (picture) => tracker.find(
      picture.width, picture.height,
      async () => {
        const detection = await detect(ort, detectorSession, picture, detector);
        return detection === null ? null : region(detection);
      },
      (found) => landmarks(ort, landmarkSession, picture, found)),
  };
}
