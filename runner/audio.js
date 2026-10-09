// Sound and the microphone, page side (story S-137; docs/design/Web_Runner_Note.md in funground).
//
// funground makes every sound in Python and keeps its own clock. What reaches this file is the short list of
// commands a sound device needs (funground/platform/browser_audio.py), one message each:
//
//   load {rate, channels, frames} + samples   keep the buffer (32-bit float, interleaved) for this voice
//   play {loops, volume, left, right}         start the voice from its beginning; loops is -1 to repeat forever
//   pause, resume                             keep the place; carry on from it
//   volume {volume}, pan {left, right}        the voice's gain, and the gains of its left and right sides
//   stop, free                                stop the voice; forget it
//   stop_all                                  the run ended
//
// Each voice is: source -> splitter -> (left gain, right gain) -> merger -> volume gain -> speakers. The two side
// gains are funground's pan law exactly (a balance control, contract A3), which a StereoPannerNode is not.
//
// Browsers keep a page silent until the visitor has clicked or pressed a key on it. `unlock()` is called by the
// runner at such a moment (Run, or the first click or key). A sound asked for before that is skipped, with one
// line of output, never an error.
//
// The microphone is opened when the sketch starts listening. Its AudioWorklet (microphone-worklet.js) posts chunks
// of 1024 mono samples; each goes to `onChunk`, which sends it to the worker. It is connected to the speakers only
// through a gain of 0, because a node nothing pulls on may not run; the microphone is never played back.

const SAMPLE_RATE = 44100;                    // funground's rate for sound and for the microphone

/**
 * @param {object} options
 * @param {(text: string, stream: "stdout" | "stderr") => void} options.write  the page's output
 * @param {(samples: Float32Array) => void} options.onChunk  microphone samples, to send to the worker (the buffer is given away)
 * @param {URL} options.workletUrl  microphone-worklet.js
 */
export function createAudio({ write, onChunk, workletUrl }) {
  let context = null;                         // made at the first gesture
  const voices = new Map();                   // number -> the voice
  let skipped = false;                        // the "sound is off" line has been written this run
  let microphone = null;                      // {stream, source, node, listening} once opened
  let microphoneOpening = null;               // the promise of the microphone being opened
  let wanted = "stop";                        // what the sketch last asked of the microphone

  // ---- the audio context

  function unlock() {
    if (!context) context = new AudioContext({ sampleRate: SAMPLE_RATE, latencyHint: "interactive" });
    if (context.state === "suspended") context.resume().catch(() => {});
  }

  const running = () => context !== null && context.state === "running";

  // ---- sounds

  function command({ command: name, voice, fields, samples }) {
    switch (name) {
      case "load": voices.set(voice, { samples, rate: fields.rate, channels: fields.channels, frames: fields.frames,
        volume: 1, left: 1, right: 1, loop: false, state: "stopped", offset: 0, startedAt: 0 }); break;
      case "play": play(voices.get(voice), fields); break;
      case "pause": pause(voices.get(voice)); break;
      case "resume": resume(voices.get(voice)); break;
      case "volume": setGains(voices.get(voice), fields); break;
      case "pan": setGains(voices.get(voice), fields); break;
      case "stop": stop(voices.get(voice)); break;
      case "free": stop(voices.get(voice)); voices.delete(voice); break;
      case "stop_all": stopAll(); break;
    }
  }

  function play(voice, { loops, volume, left, right }) {
    if (!voice) return;
    stop(voice);
    voice.volume = volume; voice.left = left; voice.right = right;
    voice.loop = loops < 0;
    if (!running()) { skip(); return; }
    start(voice, 0);
  }

  function resume(voice) {
    if (!voice || voice.state !== "paused") return;
    if (!running()) { skip(); return; }
    start(voice, voice.offset);
  }

  function pause(voice) {
    if (!voice || voice.state !== "playing") return;
    voice.offset = position(voice);
    halt(voice);
    voice.state = "paused";
  }

  function stop(voice) {
    if (!voice) return;
    halt(voice);
    voice.state = "stopped";
    voice.offset = 0;
  }

  function stopAll() {
    for (const voice of voices.values()) stop(voice);
    skipped = false;
  }

  function skip() {
    if (skipped) return;
    skipped = true;
    write("Sound is off until you click or press a key on this page: the browser keeps a page silent until then. "
      + "Sounds the sketch started before that are skipped.", "stdout");
  }

  const duration = (voice) => voice.frames / voice.rate;
  const position = (voice) => {
    const elapsed = context.currentTime - voice.startedAt;
    return voice.loop ? elapsed % duration(voice) : Math.min(elapsed, duration(voice));
  };

  function start(voice, offset) {
    if (offset >= duration(voice)) { voice.state = "stopped"; voice.offset = 0; return; }
    const graph = voice.graph ??= makeGraph(voice);
    const source = context.createBufferSource();
    source.buffer = graph.buffer;
    source.loop = voice.loop;
    source.connect(graph.splitter);
    source.start(0, offset);
    voice.source = source;
    voice.startedAt = context.currentTime - offset;
    voice.state = "playing";
    setGains(voice, voice);
  }

  // Stops the sound that is playing, if any. A source that ends by itself needs no tidying: Python's clock knows.
  function halt(voice) {
    if (!voice.source) return;
    try { voice.source.stop(); } catch { /* already ended */ }
    voice.source.disconnect();
    voice.source = null;
  }

  function makeGraph(voice) {
    const buffer = context.createBuffer(voice.channels, voice.frames, voice.rate);
    for (let c = 0; c < voice.channels; c++) {                   // de-interleave: the buffer holds one array per channel
      const channel = new Float32Array(voice.frames);
      for (let i = 0, at = c; i < voice.frames; i++, at += voice.channels) channel[i] = voice.samples[at];
      buffer.copyToChannel(channel, c);
    }
    voice.samples = null;                                        // the AudioBuffer holds them now
    const splitter = context.createChannelSplitter(2);
    const merger = context.createChannelMerger(2);
    const left = context.createGain();
    const right = context.createGain();
    const volume = context.createGain();
    splitter.connect(left, 0).connect(merger, 0, 0);
    splitter.connect(right, 1).connect(merger, 0, 1);
    merger.connect(volume).connect(context.destination);
    return { buffer, splitter, left, right, volume };
  }

  // Set the gains of a voice that has a graph; a voice not yet played gets them when it starts.
  function setGains(voice, { volume, left, right }) {
    if (!voice) return;
    if (volume !== undefined) voice.volume = volume;
    if (left !== undefined) voice.left = left;
    if (right !== undefined) voice.right = right;
    if (!voice.graph) return;
    voice.graph.volume.gain.value = voice.volume;
    voice.graph.left.gain.value = voice.left;
    voice.graph.right.gain.value = voice.right;
  }

  // ---- the microphone

  function microphoneCommand({ command: name }) {
    wanted = name;
    if (name === "start") openMicrophone().then(() => { if (microphone) microphone.listening = wanted === "start"; });
    else if (name === "stop" && microphone) microphone.listening = false;
    else if (name === "close") closeMicrophone();
  }

  function openMicrophone() {
    microphoneOpening ??= (async () => {
      unlock();
      try {
        const stream = await navigator.mediaDevices.getUserMedia({
          audio: { echoCancellation: false, noiseSuppression: false, autoGainControl: false, channelCount: 1 },
        });
        await context.audioWorklet.addModule(workletUrl);
        const source = context.createMediaStreamSource(stream);
        const node = new AudioWorkletNode(context, "funground-microphone", { numberOfOutputs: 1, outputChannelCount: [1] });
        const silent = context.createGain();
        silent.gain.value = 0;
        source.connect(node).connect(silent).connect(context.destination);
        microphone = { stream, source, node, silent, listening: wanted === "start" };
        node.port.onmessage = (e) => { if (microphone?.listening) onChunk(e.data); };
      } catch (error) {
        microphoneOpening = null;
        write(refusal(error), "stderr");
      }
    })();
    return microphoneOpening;
  }

  function refusal(error) {
    if (error?.name === "NotFoundError" || error?.name === "OverconstrainedError") {
      return "The microphone could not be opened: this computer has no microphone the browser can use. Plug one in and run again.";
    }
    if (error?.name === "NotAllowedError" || error?.name === "SecurityError") {
      return "The microphone was not allowed. Allow it with the icon in the address bar, then run the sketch again.";
    }
    return `The microphone could not be opened (${error?.message ?? error}).`;
  }

  function closeMicrophone() {
    const closing = microphone;
    microphone = null;
    microphoneOpening = null;
    if (!closing) return;
    closing.node.port.onmessage = null;
    closing.source.disconnect();
    closing.node.disconnect();
    for (const track of closing.stream.getTracks()) track.stop();
  }

  // ---- a run ends

  function reset() {
    stopAll();
    voices.clear();
    closeMicrophone();
    wanted = "stop";
  }

  // For tests and tools: is sound unlocked, what each voice is doing, and whether the microphone is open and listening.
  function state() {
    return {
      unlocked: running(),
      voices: [...voices].map(([id, voice]) => ({ id, state: voice.state, loop: voice.loop })),
      microphone: microphone ? { listening: microphone.listening } : null,
    };
  }

  return { unlock, command, microphoneCommand, reset, state };
}
