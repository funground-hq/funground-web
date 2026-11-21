// Used by tests/runner/models.html and tools/test_models.py (story S-328): a body in a sequence of pictures, sent to the real models
// worker (runner/models-worker.js) the way worker.js sends a camera's frames ("moving": true) and a still picture's ("moving": false),
// with no Python in between. The pictures are one photograph, moved to the right by `shift` pixels a picture on a black canvas, so the
// body's true move from one picture to the next is known: (shift, 0).
//
// What it reports for each of the two sequences: how far each point's move was from the true move, on average and at the worst
// ("jump", in pixels), how many times the detector ran (models_follow_glue.js counts them), and the 33 scores of the first picture.
// tests/runner/models_follow_desktop.py makes the same numbers on the desktop, from the same photograph, with _glue.py.

/** The photograph's pixels on a black canvas, at `left` pixels from the left edge, as RGBA bytes. */
async function pictureAt(bitmap, left, width, height) {
  const canvas = new OffscreenCanvas(width, height);
  const context = canvas.getContext("2d", { willReadFrequently: true });
  context.fillStyle = "black";
  context.fillRect(0, 0, width, height);
  context.drawImage(bitmap, left, 0);
  return new Uint8Array(context.getImageData(0, 0, width, height).data.buffer);
}

/** One sequence through a models worker of its own: every point of every picture, and the detector's runs. */
async function sequence(spec, bitmap, moving, ortUrl) {
  const worker = new Worker("/runner/models-worker.js", { type: "module" });
  const answers = [], looks = { count: 0 };
  let waiting = null;
  worker.onmessage = (e) => {
    const m = e.data;
    if (m.type === "looks") looks.count = m.looks;
    else if (m.type === "result") waiting?.resolve(m);
    else if (m.type === "unavailable") waiting?.reject(new Error(m.reason));
  };
  worker.onerror = (e) => waiting?.reject(new Error(`the worker failed: ${e.message}`));
  worker.postMessage({
    type: "init", onnxruntimeUrl: ortUrl, tableUrl: new URL("/runner/runtime/models.json", location.href).href,
    glueUrl: new URL("/tests/runner/models_follow_glue.js", location.href).href,
  });
  try {
    for (let k = 0; k < spec.frames; k++) {
      const pixels = await pictureAt(bitmap, spec.left + spec.shift * k, spec.width, spec.height);
      const answer = new Promise((resolve, reject) => { waiting = { resolve, reject }; });
      worker.postMessage({ type: "frame", task: "pose", key: 1, pixels: pixels.buffer, width: spec.width, height: spec.height, moving }, [pixels.buffer]);
      answers.push(await answer);
    }
  } finally {
    worker.terminate();
  }
  return { answers, looks: looks.count };
}

/** The mean and the largest distance of a point's move from the true move, over all points and all pictures but the first. */
function jumps(answers, shift) {
  let sum = 0, count = 0, worst = 0;
  for (let k = 1; k < answers.length; k++) {
    const now = answers[k].points, before = answers[k - 1].points;
    if (!now || !before) continue;
    for (let i = 0; i < now.length; i += 2) {
      const jump = Math.hypot(now[i] - before[i] - shift, now[i + 1] - before[i + 1]);
      sum += jump;
      count++;
      worst = Math.max(worst, jump);
    }
  }
  return { mean: sum / count, max: worst, pairs: count / 33 };
}

/** spec: {photo (a JPEG's bytes), frames, shift, left, width, height}. Returns {still, moving}, each {jump_mean, jump_max, detector_runs, found, scores}. */
export async function runFollow(spec, ortUrl) {
  const bitmap = await createImageBitmap(new Blob([spec.photo], { type: "image/jpeg" }));
  const out = {};
  for (const [name, moving] of [["still", false], ["moving", true]]) {
    const { answers, looks } = await sequence(spec, bitmap, moving, ortUrl);
    const jump = jumps(answers, spec.shift);
    out[name] = {
      jump_mean: +jump.mean.toFixed(3), jump_max: +jump.max.toFixed(3), detector_runs: looks,
      found: answers.filter((a) => a.points).length, pictures: answers.length,
      scores: answers[0].scores ? Array.from(answers[0].scores) : null,
    };
  }
  return out;
}
