// The microphone's AudioWorklet (story S-137). It runs on the browser's audio thread and does one thing: collect the
// input's samples (mono; two channels are averaged) in chunks of CHUNK samples and post each to the page, which sends
// it to the worker. The output is left silent. The sample rate is the AudioContext's, 44 100 Hz (audio.js).

const CHUNK = 1024;                                   // 23 ms: few enough messages, small enough to keep the sketch current

class FungroundMicrophone extends AudioWorkletProcessor {
  constructor() {
    super();
    this.chunk = new Float32Array(CHUNK);
    this.filled = 0;
  }

  process(inputs) {
    const channels = inputs[0];
    if (channels.length === 0) return true;           // nothing connected yet
    const block = channels[0].length;                 // 128 frames
    for (let i = 0; i < block; i++) {
      let sum = 0;
      for (const channel of channels) sum += channel[i];
      this.chunk[this.filled++] = sum / channels.length;
      if (this.filled === CHUNK) {
        this.port.postMessage(this.chunk, [this.chunk.buffer]);
        this.chunk = new Float32Array(CHUNK);
        this.filled = 0;
      }
    }
    return true;
  }
}

registerProcessor("funground-microphone", FungroundMicrophone);
