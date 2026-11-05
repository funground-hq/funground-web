// The models worker (stories S-232, S-233, S-234, docs/design/Web_Runner_Note.md in funground): finds a body, a hand or the outline of a
// person in a picture, and the words in a phrase of sound, with onnxruntime-web, so that ml.pose(cam), ml.hand(cam), ml.person(cam)
// and ml.words(mic) work in a page.
//
// worker.js (the one that runs Python) starts this worker the first time a sketch asks for a model. Inference takes tens of
// milliseconds and runs here, beside the sketch, so it never holds up the sketch's step. Messages are like worker.js's.
//
//   worker.js -> here
//     init   {onnxruntimeUrl, tableUrl, glueUrl}   where onnxruntime-web is (a folder), the table of model files (models.json) and models-glue.js
//     frame  {task, key, pixels, width, height}    find the "pose", "hand" or "person" in these RGBA bytes (an ArrayBuffer, transferred);
//                                                  `key` is the source they came from
//     phrase {task, key, rate, samples}            hear the "words" in this phrase: `samples` is an ArrayBuffer of float32 (mono, -1 to 1,
//                                                  transferred), `rate` how many a second; `key` is the source they came from
//     close  {}                                    the run ended: forget every source (the loaded models stay)
//
//   here -> worker.js
//     result      {task, key, points, score, width, height}   "pose" and "hand": `points` is a Float64Array x0, y0, x1, y1, ... in
//                                                  the picture's pixels (its buffer is transferred), or null when nobody is there
//     result      {task, key, mask, maskWidth, maskHeight, width, height}   "person": `mask` is a Uint8Array of the mask's own
//                                                  size (256 x 256, its buffer is transferred): 0 is not the person, 255 is
//     result      {task: "words", key, text, score}   the words heard ("" for none) and the mean probability of the pieces chosen
//     say         {text}                           one line for the learner's output (the first download)
//     unavailable {task, reason}                   the task cannot run (no connection for the download, a file that fails
//                                                  its check, ...): one plain sentence
//
// onnxruntime-web comes from a CDN at one exact version (worker.js has it), the .wasm build only. It sends nothing anywhere:
// the loader fetches its own .wasm file and nothing else (S-232 checked the source of the pinned version).
//
// The model files. models.json is made by tools/build_runtime.py from funground-ml's own table (ml/funground_ml/_models.py), so
// the addresses, sizes and SHA-256 values here are the desktop's. A file is downloaded once, checked with crypto.subtle, and
// kept in Cache Storage; later runs read the copy and download nothing, offline too. A kept copy is checked again when read:
// one that fails is downloaded again.

const CACHE = "funground-models-v1";
const post = (message, transfer = []) => postMessage(message, transfer);

let settings = null;                  // {onnxruntimeUrl, tableUrl, glueUrl}
let loaded = null;                    // Promise of {ort, glue, table}: the library, started on the first frame
const tasks = new Map();              // task -> Promise of the task's files (two sessions for "pose" and "hand", one for "person", two sessions and the token table for "words")
const finders = new Map();            // "task:key" -> that source's finder (it keeps the box to reuse)
let queue = Promise.resolve();        // frames are worked on one at a time

function init(message) {
  settings = message;
}

function close() {
  finders.clear();
  whisper = null;
}

// ---- loading

function library() {
  loaded ??= (async () => {
    const [ort, glue, table] = await Promise.all([
      import(settings.onnxruntimeUrl + "ort.wasm.mjs"),
      import(settings.glueUrl),
      fetch(settings.tableUrl).then((response) => response.json()),
    ]);
    ort.env.wasm.wasmPaths = settings.onnxruntimeUrl;     // the .wasm file beside the library
    ort.env.logLevel = "error";
    return { ort, glue, table };
  })();
  loaded.catch(() => { loaded = null; });                 // a failure is reported by the frame that met it; the next may try again
  return loaded;
}

// ---- the model files

const hex = (buffer) => [...new Uint8Array(buffer)].map((byte) => byte.toString(16).padStart(2, "0")).join("");

async function isGood(bytes, model) {
  return bytes.byteLength === model.size && hex(await crypto.subtle.digest("SHA-256", bytes)) === model.sha256;
}

const megabytes = (size) => Math.max(1, Math.round(size / 1e6));
const words = (name) => name.replace(/_/g, " ");

function short(reason) {
  const text = String(reason?.message ?? reason).trim();
  return (text || "unknown error").slice(0, 80);
}

/** The bytes of a model file: the checked copy in Cache Storage, or a download (checked, then kept). */
async function modelBytes(model, cache, task) {
  const kept = await cache.match(model.url);
  if (kept) {
    const bytes = await kept.arrayBuffer();
    if (await isGood(bytes, model)) return bytes;
    await cache.delete(model.url);                        // a damaged copy is not used again
  }
  let response;
  try {
    response = await fetch(model.url, { credentials: "omit" });
  } catch (error) {
    throw new Error(`ml.${task}(): could not download the ${words(model.name)} from huggingface.co (${short(error)}). Run the sketch once while online; after that the browser keeps a copy.`);
  }
  if (!response.ok) throw new Error(`ml.${task}(): could not download '${model.url}' (the site answered ${response.status}).`);
  const bytes = await response.arrayBuffer();
  if (!(await isGood(bytes, model))) {
    throw new Error(`ml.${task}(): the file downloaded for the ${words(model.name)} is not the one funground expects (its checksum is different), so it was not kept. Try again. If it keeps happening, tell the funground team.`);
  }
  await cache.put(model.url, new Response(bytes.slice(0), { headers: { "Content-Type": "application/octet-stream" } }));
  return bytes;
}

/** The files of a task, in the order of models.json: an ONNX file becomes a session (a detector and a landmark model, the one model
 *  of "person", the encoder and decoder of "words"), a JSON file (the words' token table) is parsed. The first
 *  time a file has to be downloaded, one line says so, as the desktop's does. */
function sessionsFor(task) {
  if (!tasks.has(task)) {
    const made = (async () => {
      const { ort, table } = await library();
      const models = table.tasks[task].map((name) => ({ name, ...table.models[name] }));
      const cache = await caches.open(CACHE);
      const missing = [];
      for (const model of models) if (!(await cache.match(model.url))) missing.push(model);
      if (missing.length) {
        const size = missing.reduce((sum, model) => sum + model.size, 0);
        post({ type: "say", text: `Downloading the ${task} model, ${megabytes(size)} MB, once. After that the browser keeps a copy.` });
      }
      const sessions = [];
      for (const model of models) {
        const bytes = await modelBytes(model, cache, task);
        sessions.push(model.file.endsWith(".json")
          ? JSON.parse(new TextDecoder().decode(bytes))
          : await ort.InferenceSession.create(new Uint8Array(bytes), { executionProviders: ["wasm"], graphOptimizationLevel: "all" }));
      }
      return sessions;
    })();
    made.catch(() => tasks.delete(task));                 // the next frame may try again
    tasks.set(task, made);
  }
  return tasks.get(task);
}

// ---- finding

async function find({ task, key, pixels, width, height }) {
  try {
    const { ort, glue } = await library();
    const sessions = await sessionsFor(task);
    const id = `${task}:${key}`;
    if (!finders.has(id)) finders.set(id, glue.createFinder(task, ort, sessions));
    const found = await finders.get(id).find({ rgba: new Uint8Array(pixels), width, height });
    if (task === "person") {
      const { mask, maskWidth, maskHeight } = found;
      post({ type: "result", task, key, mask, maskWidth, maskHeight, width, height }, [mask.buffer]);
      return;
    }
    const points = found === null ? null : found.points;
    post({ type: "result", task, key, points, score: found === null ? 0 : found.score, width, height }, points ? [points.buffer] : []);
  } catch (error) {
    post({ type: "unavailable", task, reason: errorSentence(task, error) });
  }
}

// ---- hearing

let whisper = null;                   // Whisper, made once; it keeps nothing between phrases

async function hear({ task, key, rate, samples }) {
  try {
    const { ort, glue } = await library();
    const files = await sessionsFor(task);
    whisper ??= glue.createWords(ort, files.slice(0, 2), files[2]);
    const { text, score } = await whisper.transcribe(new Float32Array(samples), rate);
    post({ type: "result", task, key, text, score });
  } catch (error) {
    post({ type: "unavailable", task, reason: errorSentence(task, error) });
  }
}

// Our own sentences ("ml.pose(): ...") are for the learner as they are; anything else (the library failed to load, a model
// file would not open) is made into one.
function errorSentence(task, error) {
  const text = String(error?.message ?? error);
  return text.startsWith(`ml.${task}()`) ? text : `ml.${task}(): the browser could not run the ${task} model (${short(error)}).`;
}

const handlers = {
  init,
  close,
  frame: (message) => { queue = queue.then(() => find(message)); },
  phrase: (message) => { queue = queue.then(() => hear(message)); },
};

self.onmessage = (e) => handlers[e.data.type](e.data);
