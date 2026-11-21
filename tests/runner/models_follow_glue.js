// Used by tests/runner/models_follow.js (story S-328): runner/models-glue.js with two changes for a test. Each finder counts how many
// times its detector ran (and tells the page), and its filters see a clock of 1/24 s a picture, not the real one, so that the
// numbers are the same on every run and can be set beside the desktop's (tests/runner/models_follow_desktop.py uses the same clock).
// The models worker loads this as its glue, in place of models-glue.js: everything else is the same file.
import { createFinder as realFinder } from "/runner/models-glue.js";
export * from "/runner/models-glue.js";

export function createFinder(task, ort, sessions) {
  let pictures = 0, looks = 0;
  const detector = new Proxy(sessions[0], {
    get(session, name) {
      if (name !== "run") return Reflect.get(session, name, session);
      return (...args) => {
        looks++;
        self.postMessage({ type: "looks", looks });
        return session.run(...args);
      };
    },
  });
  const finder = realFinder(task, ort, [detector, ...sessions.slice(1)], () => pictures / 24);
  return { find: (picture, moving) => { pictures++; return finder.find(picture, moving); } };
}
