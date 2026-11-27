// The camera, page side (story S-172; docs/design/Camera_Note.md and Web_Runner_Note.md in funground).
//
// A worker cannot open the camera, so the page does. When the sketch calls cam.start(), the worker posts
// `camera {command: "start", fields: {width, height}}`; the page asks the browser for the camera (the browser asks the
// visitor), plays it in a hidden <video>, and before each step draws the newest video frame, scaled to the asked size,
// into an OffscreenCanvas and posts its RGBA pixels to the worker (the buffer is transferred). A frame is sent only when
// the camera has a new one, and at most one per step, so frames are dropped rather than queued. funground mirrors the
// picture when the sketch asks for that; the page never does.
//
// The camera may give a different shape from the one asked for (a phone held upright gives a tall picture). The `fit`
// option says what to do then: "cover" (the default, D-154 and contract row I4: cut evenly from the long sides, then scale,
// so the picture keeps its shape) or "stretch" (scale each side to the asked size, so the picture may be squashed; the old
// way, kept for the camera check page to compare). Only a host sets it; no sketch can.
//
// Focus (D-155): where the browser offers it (mostly Chrome on Android, and some webcams) a host can show a focus control.
// `onCamera` says when the camera opens or closes and what focus it offers; `focus(setting)` applies one. The sketch never
// sees any of this; only a host sets it.
//
// If the camera cannot be opened (refused, none, busy, or a host that does not allow it), the worker is told the
// reason once per start, and funground prints one line; the sketch's camera stays not ready.

/**
 * @param {object} options
 * @param {(pixels: Uint8ClampedArray, width: number, height: number) => void} options.onFrame  a frame for the worker (transfer its buffer)
 * @param {(reason: string) => void} options.onUnavailable  the camera could not be opened, and why, in a few plain words
 * @param {string | null} [options.cameraRefusal]  when set, the camera is never asked for: a sketch that starts it is told this
 *   reason instead (for a host that does not allow the camera, such as VS Code's panel)
 * @param {"stretch" | "cover"} [options.fit]  what to do when the camera's picture has another shape than the asked size:
 *   "cover" (default, D-154) cuts evenly from the long sides, then scales; "stretch" scales it to the size, so it may be squashed
 * @param {(info: {open: boolean, focus?: object | null}) => void} [options.onCamera]  the camera opened ({open: true, focus}) or
 *   closed ({open: false}). `focus` is null when the camera offers no focus; else {modes, distance: {min, max, step} | null,
 *   mode, value}: the focus modes it lists, the range of its focus distance, and what it is set to now (null where unknown)
 */
export function createCamera({ onFrame, onUnavailable, cameraRefusal = null, fit = "cover", onCamera = () => {} }) {
  if (fit !== "stretch" && fit !== "cover") throw new Error('createCamera(): fit must be "stretch" or "cover".');
  let wanted = null;                          // {width, height} while the sketch wants frames, else null
  let camera = null;                          // {stream, video} once opened
  let opening = null;                         // the promise of the camera being opened
  let fresh = false;                          // the video has a frame that has not been sent
  let canvas = null;                          // where frames are scaled, made again when the size changes
  let context = null;

  function command({ command: name, fields }) {
    if (name === "start") {
      wanted = { width: fields.width, height: fields.height };
      if (cameraRefusal !== null) return onUnavailable(cameraRefusal);
      open();
    } else if (name === "stop" || name === "close") {
      close();                                // cam.stop() lets the camera go, as on a computer: its light goes off
    }
  }

  function open() {
    opening ??= (async () => {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({ video: { width: wanted?.width, height: wanted?.height }, audio: false });
        const video = document.createElement("video");
        video.muted = true;
        video.playsInline = true;
        video.srcObject = stream;
        await video.play();
        camera = { stream, video };
        await keepFocus(stream);                // so that the focus told to the host is the one in use
        watchFrames(video);
        if (camera?.stream === stream) onCamera({ open: true, focus: focusInfo(stream.getVideoTracks()[0]) });
      } catch (error) {
        opening = null;
        onUnavailable(reason(error));
      }
    })();
    return opening;
  }

  // A phone's camera may focus once and stay: ask for continuous focus where the camera offers it, and go on if it refuses.
  async function keepFocus(stream) {
    const track = stream.getVideoTracks()[0];
    if (!track?.getCapabilities?.().focusMode?.includes("continuous")) return;
    await track.applyConstraints({ advanced: [{ focusMode: "continuous" }] }).catch(() => {});
  }

  // What the track offers for focus, and its setting now, or null when it offers none a person can use.
  function focusInfo(track) {
    if (track?.getSettings?.().facingMode === "user") return null;   // D-156: a front camera lists focus but does not use it
    const capabilities = track?.getCapabilities?.() ?? {};
    const modes = capabilities.focusMode ?? [];
    const range = capabilities.focusDistance;
    const distance = range && Number.isFinite(range.min) && Number.isFinite(range.max)
      ? { min: range.min, max: range.max, step: range.step ?? 0 } : null;
    if (!modes.includes("manual") && !modes.includes("continuous") && !distance) return null;
    const settings = track.getSettings?.() ?? {};
    return { modes: [...modes], distance, mode: settings.focusMode ?? null, value: settings.focusDistance ?? null };
  }

  // Set the focus: {mode: "auto"} (continuous) or {mode: "manual", distance}. Resolves to the focus now in use (as focusInfo),
  // or null when the camera is closed or offers no focus. A browser that refuses is not an error: the answer shows what it kept.
  function focus(setting) {
    const mode = setting?.mode;
    if (mode !== "auto" && mode !== "manual") throw new Error('camera focus: mode must be "auto" or "manual".');
    if (mode === "manual" && !Number.isFinite(setting.distance)) throw new Error("camera focus: a manual focus needs a distance (a number).");
    return applyFocus(setting);
  }

  async function applyFocus({ mode, distance }) {
    const track = camera?.stream.getVideoTracks()[0];
    const info = focusInfo(track);
    if (!info) return null;
    const wanted = mode === "auto" ? { focusMode: "continuous" } : { focusMode: "manual" };
    if (mode === "manual" && info.distance) wanted.focusDistance = Math.min(Math.max(distance, info.distance.min), info.distance.max);
    await track.applyConstraints({ advanced: [wanted] }).catch(() => {});
    return focusInfo(track);
  }

  // A browser that can say when the video has a new frame says so; any other is asked each step.
  function watchFrames(video) {
    if (!("requestVideoFrameCallback" in video)) return;
    const next = () => {
      if (camera?.video !== video) return;
      fresh = true;
      video.requestVideoFrameCallback(next);
    };
    video.requestVideoFrameCallback(next);
  }

  // Called before each step: send the newest frame if there is one the sketch has not had.
  function sendFrame() {
    const video = camera?.video;
    if (!wanted || !video || video.readyState < HTMLMediaElement.HAVE_CURRENT_DATA) return;
    if ("requestVideoFrameCallback" in video ? !fresh : video.paused) return;
    fresh = false;
    const { width, height } = wanted;
    if (!canvas || canvas.width !== width || canvas.height !== height) {
      canvas = new OffscreenCanvas(width, height);
      context = canvas.getContext("2d", { willReadFrequently: true });
    }
    if (fit === "cover" && video.videoWidth > 0 && video.videoHeight > 0) {
      const { videoWidth: vw, videoHeight: vh } = video;
      const cutWidth = Math.min(vw, vh * width / height);          // the part of the picture with the asked shape, in the middle
      const cutHeight = Math.min(vh, vw * height / width);
      context.drawImage(video, (vw - cutWidth) / 2, (vh - cutHeight) / 2, cutWidth, cutHeight, 0, 0, width, height);
    } else {
      context.drawImage(video, 0, 0, width, height);
    }
    onFrame(context.getImageData(0, 0, width, height).data, width, height);
  }

  function reason(error) {
    if (error?.name === "NotAllowedError" || error?.name === "SecurityError") {
      return "it was not allowed. Allow it with the icon in the address bar, then run the sketch again";
    }
    if (error?.name === "NotFoundError" || error?.name === "OverconstrainedError") {
      return "this computer has no camera the browser can use";
    }
    if (error?.name === "NotReadableError") return "another program is using it. Close that program, then run again";
    return `the browser could not open it (${error?.message ?? error})`;
  }

  function close() {
    wanted = null;
    const closing = camera;
    camera = null;
    opening = null;
    fresh = false;
    if (!closing) return;
    for (const track of closing.stream.getTracks()) track.stop();       // the camera's light goes off
    closing.video.srcObject = null;
    onCamera({ open: false });
  }

  // For tests and tools: whether the camera is open and the sketch wants its frames, the camera's name, what the browser
  // says it gives now (settings) and what it could give (capabilities), and the fit. null when the camera is not open.
  function state() {
    if (!camera) return null;
    const track = camera.stream.getVideoTracks()[0];
    return {
      open: true, wanted: wanted !== null, fit, label: track?.label ?? "",
      videoSize: [camera.video.videoWidth, camera.video.videoHeight],
      settings: track?.getSettings?.() ?? {}, capabilities: track?.getCapabilities?.() ?? {},
    };
  }

  return { command, sendFrame, reset: close, state, focus };
}
