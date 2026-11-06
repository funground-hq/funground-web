// The pictures-in, points-out part of the pose and hand models, and the person's mask, for the page (stories S-232, S-233).
//
// This is the JavaScript twin of funground-ml's `_glue.py` (in the funground repository, ml/funground_ml). It runs the same five
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
// swaps left and right for a mirrored camera). The person's mask comes out as bytes, in the mask's own size (256 x 256): the
// Python side stretches it over the picture.

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

// ---- the person's mask: one model, no boxes

export const MASK_SIZE = 256;              // the selfie model reads a 256 x 256 picture and gives a 256 x 256 mask (_glue.py has the same)

/**
 * The weights for resizing one line of `inSize` pixels to `outSize`, as Pillow's `Image.resize(..., BILINEAR)` makes them: a
 * triangle as wide as one output pixel is when enlarging, and as wide as the input pixels one output pixel covers when
 * shrinking (so a big picture is averaged, not skipped). Returns, for each output pixel, where its input pixels start and
 * their weights, which add up to 1.
 */
function lineWeights(inSize, outSize) {
  const scale = inSize / outSize, filterScale = Math.max(scale, 1);
  return Array.from({ length: outSize }, (_, i) => {
    const centre = (i + 0.5) * scale;
    const start = Math.max(Math.floor(centre - filterScale + 0.5), 0), end = Math.min(Math.floor(centre + filterScale + 0.5), inSize);
    const weights = [];
    let total = 0;
    for (let x = start; x < end; x++) {
      const distance = Math.abs((x - centre + 0.5) / filterScale);
      const weight = distance < 1 ? 1 - distance : 0;
      weights.push(weight);
      total += weight;
    }
    return { start, weights: weights.map((weight) => weight / total) };
  });
}

/**
 * The whole picture stretched to size x size (not letterboxed: the mask must cover the whole picture) with the same resampling
 * as Pillow's `resize`, as the model's input: 0 to 1, no mean, channels first, a Float32Array. The line is resized across, then
 * down, and rounded to a whole number between the two, as Pillow does for 8-bit pictures.
 */
export function stretchToTensor(picture, size) {
  const { rgba, width, height } = picture;
  const across = lineWeights(width, size), down = lineWeights(height, size);
  const wide = new Uint8Array(size * height * 3);                  // the rows resized across: size wide, height tall
  for (let y = 0; y < height; y++) {
    for (let x = 0; x < size; x++) {
      const { start, weights } = across[x];
      for (let channel = 0; channel < 3; channel++) {
        let sum = 0;
        for (let k = 0; k < weights.length; k++) sum += rgba[((y * width) + start + k) * 4 + channel] * weights[k];
        wide[(y * size + x) * 3 + channel] = Math.min(Math.max(Math.round(sum), 0), 255);
      }
    }
  }
  const out = new Float32Array(size * size * 3), plane = size * size;
  for (let y = 0; y < size; y++) {
    const { start, weights } = down[y];
    for (let x = 0; x < size; x++) {
      for (let channel = 0; channel < 3; channel++) {
        let sum = 0;
        for (let k = 0; k < weights.length; k++) sum += wide[((start + k) * size + x) * 3 + channel] * weights[k];
        out[channel * plane + y * size + x] = Math.min(Math.max(Math.round(sum), 0), 255) / 255;
      }
    }
  }
  return out;
}

/**
 * The model's mask for the whole picture: MASK_SIZE x MASK_SIZE bytes, 0 (not the person) to 255 (the person). The model gives a
 * 0 to 1 value for each pixel; it stays soft, nothing is cut at a threshold. Returns {mask, maskWidth, maskHeight}. (The twin of
 * `person_mask` in _glue.py.)
 */
export async function personMask(ort, session, picture) {
  const outputs = await run(ort, session, stretchToTensor(picture, MASK_SIZE), [1, 3, MASK_SIZE, MASK_SIZE]);
  const alphas = outputs[session.outputNames[0]].data;
  const mask = new Uint8Array(MASK_SIZE * MASK_SIZE);
  for (let i = 0; i < mask.length; i++) mask[i] = Math.min(Math.max(Math.floor(alphas[i] * 255 + 0.5), 0), 255);
  return { mask, maskWidth: MASK_SIZE, maskHeight: MASK_SIZE };
}

// ---- the tasks

const TASKS = {
  pose: { detector: POSE_DETECTOR, region: bodyRegion, landmarks: bodyLandmarks },
  hand: { detector: PALM_DETECTOR, region: handRegion, landmarks: handLandmarks },
};

/**
 * One source's finder for a task, made from the task's sessions (the order of `tasks` in models.json): it keeps that
 * source's state and shares the sessions. `find(picture)` gives
 *   "pose" and "hand": {points, score} (points flat, in the picture's pixels) or null when nobody is there;
 *   "person": {mask, maskWidth, maskHeight}, never null (the model always gives a mask).
 */
export function createFinder(task, ort, sessions) {
  if (task === "person") return { find: (picture) => personMask(ort, sessions[0], picture) };
  const [detectorSession, landmarkSession] = sessions;
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

// ---- the words: Whisper tiny.en (story S-234)
//
// The JavaScript twin of funground-ml's `_whisper.py` and the sums in `_speech.py`, for the "words" task. The same steps, the
// same numbers: resample the sound to 16 kHz, make the log-mel picture of 30 s padded with silence, run the encoder, then the
// decoder one piece at a time (the likeliest each time, until `tokenLimit` or a loop, `loopTail`), and turn the pieces into text. If the one changes,
// the other changes with it. The Python side drops an answer with a low score or no text, so nothing is filtered here.

const WORDS_RATE = 16000;                  // the model hears 16 kHz ...
const WINDOW_SAMPLES = 30 * WORDS_RATE;    // ... and 30 s at a time
const FFT_SIZE = 400, HOP = 160, MEL_BANDS = 80, FREQUENCIES = FFT_SIZE / 2 + 1;
const FRAMES = WINDOW_SAMPLES / HOP;       // 3000 columns of the picture
const LOG_RANGE = 8, LOG_SHIFT = 4, LOG_SCALE = 4, FLOOR = 1e-10;
const HEADS = 6, HEAD_SIZE = 64;           // the decoder's past keys and values are (1, 6, length, 64)
export const END_OF_TEXT = 50256;
const START_OF_TEXT = 50257, NO_TIMESTAMPS = 50362;
export const MAX_TOKENS = 224;
const TOKENS_PER_SECOND = 10, MIN_TOKENS = 16, LOOP_REPEATS = 4;   // the numbers of `_speech.py` (S-257, D-131)
const FIRST_WORD_BANNED = [220, 50256];
const SUPPRESSED = [
  1, 2, 7, 8, 9, 10, 14, 25, 26, 27, 28, 29, 31, 58, 59, 60, 61, 62, 63, 90, 91, 92, 93, 357, 366, 438, 532,
  685, 705, 796, 930, 1058, 1220, 1267, 1279, 1303, 1343, 1377, 1391, 1635, 1782, 1875, 2162, 2361, 2488,
  3467, 4008, 4211, 4600, 4808, 5299, 5855, 6329, 7203, 9609, 9959, 10563, 10786, 11420, 11709, 11907, 13163,
  13697, 13700, 14808, 15306, 16410, 16791, 17992, 19203, 19510, 20724, 22305, 22935, 27007, 30109, 30420,
  33409, 34949, 40283, 40493, 40549, 47282, 49146, 50257, 50357, 50358, 50359, 50360, 50361];

/**
 * The samples as float32 at 16 kHz, by linear interpolation, with the exact formula of `to_model_rate` in _whisper.py:
 * count = floor(n * 16000 / rate); output j is at p = j * rate / 16000, i = floor(p), t = p - i, and
 * y[j] = x[i] * (1 - t) + x[min(i + 1, n - 1)] * t. (Math.fround is used where Python's float32 rounds.)
 */
export function toModelRate(samples, rate) {
  if (rate === WORDS_RATE || samples.length === 0) return samples;
  const count = Math.floor(samples.length * WORDS_RATE / rate), last = samples.length - 1;
  const out = new Float32Array(count);
  for (let j = 0; j < count; j++) {
    const p = j * rate / WORDS_RATE, i = Math.floor(p), t = Math.fround(p - i);
    out[j] = Math.fround(Math.fround(samples[i] * Math.fround(1 - t)) + Math.fround(samples[Math.min(i + 1, last)] * t));
  }
  return out;
}

// The Slaney mel filter bank (80 x 201), the Hann window and the Fourier tables, made once.
let tables = null;
function melTables() {
  if (tables) return tables;
  const hertzToMel = (hz) => (hz < 1000 ? hz / (200 / 3) : 15 + Math.log(Math.max(hz, 1e-9) / 1000) / (Math.log(6.4) / 27));
  const melToHertz = (mel) => (mel < 15 ? mel * (200 / 3) : 1000 * Math.exp((Math.log(6.4) / 27) * (mel - 15)));
  const top = hertzToMel(WORDS_RATE / 2), edges = [];
  for (let i = 0; i < MEL_BANDS + 2; i++) edges.push(melToHertz(top * i / (MEL_BANDS + 1)));
  const filters = new Float64Array(MEL_BANDS * FREQUENCIES);
  for (let m = 0; m < MEL_BANDS; m++) {
    for (let k = 0; k < FREQUENCIES; k++) {
      const hz = k * WORDS_RATE / FFT_SIZE;
      const rising = (hz - edges[m]) / (edges[m + 1] - edges[m]), falling = (edges[m + 2] - hz) / (edges[m + 2] - edges[m + 1]);
      filters[m * FREQUENCIES + k] = Math.max(0, Math.min(rising, falling)) * (2 / (edges[m + 2] - edges[m]));
    }
  }
  const window = new Float64Array(FFT_SIZE), cos = new Float64Array(FREQUENCIES * FFT_SIZE), sin = new Float64Array(FREQUENCIES * FFT_SIZE);
  for (let n = 0; n < FFT_SIZE; n++) window[n] = 0.5 - 0.5 * Math.cos(2 * Math.PI * n / FFT_SIZE);
  for (let k = 0; k < FREQUENCIES; k++) {
    for (let n = 0; n < FFT_SIZE; n++) {
      const angle = 2 * Math.PI * ((k * n) % FFT_SIZE) / FFT_SIZE;
      cos[k * FFT_SIZE + n] = Math.cos(angle);
      sin[k * FFT_SIZE + n] = Math.sin(angle);
    }
  }
  tables = { filters, window, cos, sin };
  return tables;
}

/**
 * The encoder's input for 16 kHz `audio`: a Float32Array of 80 x 3000 (row = mel band), as `log_mel` in _whisper.py. Sound past
 * 30 s is cut; less is padded with silence. The Fourier sums are done directly (400 x 201 products for a column): the columns
 * that see only the silence after the sound all have the same value, so they are worked out once.
 */
export function logMel(audio) {
  const { filters, window, cos, sin } = melTables();
  const half = FFT_SIZE / 2;
  const body = new Float32Array(WINDOW_SAMPLES);
  body.set(audio.subarray(0, Math.min(audio.length, WINDOW_SAMPLES)));
  const padded = new Float32Array(WINDOW_SAMPLES + FFT_SIZE);        // reflected at both ends, as numpy's pad(mode="reflect")
  padded.set(body, half);
  for (let i = 1; i <= half; i++) {
    padded[half - i] = body[i];
    padded[half + WINDOW_SAMPLES - 1 + i] = body[WINDOW_SAMPLES - 1 - i];
  }
  // Column t reads padded[t * HOP, t * HOP + 400). From this column on, that is all zeros (the sound ends before it).
  const firstSilent = Math.ceil((Math.min(audio.length, WINDOW_SAMPLES) + half) / HOP) + 1;
  const mel = new Float32Array(MEL_BANDS * FRAMES), power = new Float64Array(FREQUENCIES), segment = new Float64Array(FFT_SIZE);
  let silent = null;
  for (let t = 0; t < FRAMES; t++) {
    let column;
    if (t > firstSilent && silent) {
      column = silent;
    } else {
      for (let n = 0; n < FFT_SIZE; n++) segment[n] = padded[t * HOP + n] * window[n];
      for (let k = 0; k < FREQUENCIES; k++) {
        let re = 0, im = 0;
        const at = k * FFT_SIZE;
        for (let n = 0; n < FFT_SIZE; n++) { re += segment[n] * cos[at + n]; im -= segment[n] * sin[at + n]; }
        power[k] = re * re + im * im;
      }
      column = new Float64Array(MEL_BANDS);
      for (let m = 0; m < MEL_BANDS; m++) {
        let sum = 0;
        for (let k = 0; k < FREQUENCIES; k++) sum += filters[m * FREQUENCIES + k] * power[k];
        column[m] = sum;
      }
      if (t === firstSilent) silent = column;
    }
    for (let m = 0; m < MEL_BANDS; m++) mel[m * FRAMES + t] = column[m];
  }
  let loudest = -Infinity;
  for (let i = 0; i < mel.length; i++) {
    mel[i] = Math.log10(Math.max(mel[i], FLOOR));
    if (mel[i] > loudest) loudest = mel[i];
  }
  for (let i = 0; i < mel.length; i++) mel[i] = (Math.max(mel[i], loudest - LOG_RANGE) + LOG_SHIFT) / LOG_SCALE;
  return mel;
}

/** GPT-2's table: the character that stands for each byte value, turned round (character -> byte). Same as `_speech.py`. */
function byteOfCharacter() {
  const printable = new Set();
  for (let b = 33; b <= 126; b++) printable.add(b);
  for (let b = 161; b <= 172; b++) printable.add(b);
  for (let b = 174; b <= 255; b++) printable.add(b);
  const table = new Map();
  let spare = 0;
  for (let b = 0; b < 256; b++) table.set(String.fromCharCode(printable.has(b) ? b : 256 + spare++), b);
  return table;
}

/** The text for the numbers the model chose: control numbers skipped, pieces joined, characters turned to bytes, read as UTF-8. */
export function decodeWords(numbers, vocabulary) {
  const bytes = byteOfCharacter();
  const joined = numbers.filter((n) => n < END_OF_TEXT).map((n) => vocabulary[n]).join("");
  return new TextDecoder().decode(Uint8Array.from(joined, (character) => bytes.get(character) ?? 0x3F)).trim();
}

/** The most pieces of words that `seconds` of sound can give. The twin of `token_limit` in _speech.py. */
export function tokenLimit(seconds) {
  return Math.max(MIN_TOKENS, Math.min(MAX_TOKENS, Math.trunc(seconds * TOKENS_PER_SECOND)));
}

/** How many pieces at the end of `chosen` are a loop to drop, or 0. The twin of `loop_tail` in _speech.py. */
export function loopTail(chosen) {
  for (const size of [1, 2]) {
    const length = size * LOOP_REPEATS;
    if (chosen.length < length) continue;
    const tail = chosen.slice(-length);
    if (tail.every((piece, i) => piece === tail[i % size])) return size * (LOOP_REPEATS - 1);
  }
  return 0;
}

/**
 * Whisper from its sessions (the order of "words" in models.json: encoder, decoder) and `vocab.json` (a parsed object, piece ->
 * number). `transcribe(samples, rate)` gives {text, score}: the words heard ("" for none) and the mean probability of the
 * pieces the model chose (0 for none). The twin of `Whisper.transcribe` in _whisper.py.
 */
export function createWords(ort, [encoder, decoder], vocabularyFile) {
  const vocabulary = [];
  for (const [piece, number] of Object.entries(vocabularyFile)) vocabulary[number] = piece;
  const suppressed = new Set(SUPPRESSED);
  const pastNames = decoder.inputNames.filter((name) => name.startsWith("past_key_values"));
  const presentNames = decoder.outputNames.slice(1);
  return {
    async transcribe(samples, rate) {
      const features = new ort.Tensor("float32", logMel(toModelRate(samples, rate)), [1, MEL_BANDS, FRAMES]);
      const hidden = (await encoder.run({ [encoder.inputNames[0]]: features }))[encoder.outputNames[0]];
      const past = Object.fromEntries(pastNames.map((name) => [name, new ort.Tensor("float32", new Float32Array(0), [1, HEADS, 0, HEAD_SIZE])]));
      const chosen = [], probabilities = [];
      let feed = [START_OF_TEXT, NO_TIMESTAMPS], first = true;
      const limit = tokenLimit(samples.length / rate);
      while (chosen.length < limit) {
        const outputs = await decoder.run({
          input_ids: new ort.Tensor("int64", BigInt64Array.from(feed, BigInt), [1, feed.length]),
          encoder_hidden_states: hidden,
          use_cache_branch: new ort.Tensor("bool", [!first], [1]),
          ...past,
        });
        const logits = outputs.logits, size = logits.dims[2], offset = (logits.dims[1] - 1) * size;
        const allowed = (v) => !suppressed.has(v) && !(chosen.length === 0 && FIRST_WORD_BANNED.includes(v));
        let best = -1;
        for (let v = 0; v < size; v++) if (allowed(v) && (best < 0 || logits.data[offset + v] > logits.data[offset + best])) best = v;
        if (best === END_OF_TEXT) break;
        chosen.push(best);
        let total = 0;
        for (let v = 0; v < size; v++) if (allowed(v)) total += Math.exp(logits.data[offset + v] - logits.data[offset + best]);
        probabilities.push(1 / total);
        const extra = loopTail(chosen);
        if (extra) {
          chosen.length -= extra;
          probabilities.length -= extra;
          break;
        }
        for (const name of presentNames) {
          const key = name.replace("present", "past_key_values");
          if (first || key.includes(".decoder.")) past[key] = outputs[name];       // the encoder's keys and values are worked out once
        }
        feed = [best];
        first = false;
      }
      if (chosen.length === 0) return { text: "", score: 0 };
      return { text: decodeWords(chosen, vocabulary), score: probabilities.reduce((a, b) => a + b, 0) / probabilities.length };
    },
  };
}

// ---- the sound: YAMNet (story S-250)
//
// The JavaScript twin of funground-ml's `_yamnet.py`, for the "sound" task. YAMNet takes the raw waveform (float32, 16 kHz, nothing
// else done to it) and gives a table of one row of 521 scores for every 0.96 s of sound. The answer is the mean of the rows, column
// by column (a microphone's 0.96 s is one row). The names are not here: funground-ml chooses them from the 521 scores, the same
// code on the desktop and in a page. The quiet-window rule is applied in Python before a window is sent.

/**
 * YAMNet from its session (the one file of "sound" in models.json). `classify(samples, rate)` gives a Float32Array of 521 scores:
 * the samples are resampled with `toModelRate` (the same formula as the desktop's), run, and the rows averaged (in double
 * precision, as the desktop does, then rounded to float32 to travel).
 */
export function createSound(ort, [session]) {
  return {
    async classify(samples, rate) {
      const waveform = toModelRate(samples, rate);
      const outputs = await session.run({ [session.inputNames[0]]: new ort.Tensor("float32", waveform, [waveform.length]) });
      const table = outputs[session.outputNames[0]], rows = table.dims[0], size = table.dims[1];
      const mean = new Float64Array(size);
      for (let r = 0; r < rows; r++) for (let c = 0; c < size; c++) mean[c] += table.data[r * size + c];
      return Float32Array.from(mean, (total) => total / rows);
    },
  };
}
