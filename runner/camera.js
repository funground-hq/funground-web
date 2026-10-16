// The camera, page side (story S-172; docs/design/Camera_Note.md and Web_Runner_Note.md in funground).
//
// A worker cannot open the camera, so the page does. When the sketch calls cam.start(), the worker posts
// `camera {command: "start", fields: {width, height}}`; the page asks the browser for the camera (the browser asks the
// visitor), plays it in a hidden <video>, and before each step draws the newest video frame, scaled to the asked size,
// into an OffscreenCanvas and posts its RGBA pixels to the worker (the buffer is transferred). A frame is sent only when
// the camera has a new one, and at most one per step, so frames are dropped rather than queued. funground mirrors the
// picture when the sketch asks for that; the page never does.
//
// If the camera cannot be opened (refused, none, busy, or a host that does not allow it), the worker is told the
// reason once per start, and funground prints one line; the sketch's camera stays not ready.

/**
 * @param {object} options
 * @param {(pixels: Uint8ClampedArray, width: number, height: number) => void} options.onFrame  a frame for the worker (transfer its buffer)
 * @param {(reason: string) => void} options.onUnavailable  the camera could not be opened, and why, in a few plain words
 * @param {string | null} [options.cameraRefusal]  when set, the camera is never asked for: a sketch that starts it is told this
 *   reason instead (for a host that does not allow the camera, such as VS Code's panel)
 */
export function createCamera({ onFrame, onUnavailable, cameraRefusal = null }) {
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
        watchFrames(video);
      } catch (error) {
        opening = null;
        onUnavailable(reason(error));
      }
    })();
    return opening;
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
    context.drawImage(video, 0, 0, width, height);
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
  }

  // For tests and tools: whether the camera is open and the sketch wants its frames.
  function state() {
    return camera ? { open: true, wanted: wanted !== null } : null;
  }

  return { command, sendFrame, reset: close, state };
}
