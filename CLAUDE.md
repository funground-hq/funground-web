# funground-web

funground in the browser: Python (Pyodide) in a module Web Worker, the loop driven by the page
(`start/step/finish`), a renderer for funground's draw-op IR, sound and microphone through Web Audio,
and a static editor (H1) on GitHub Pages. Part of funground 0.2's web target (epic E-31, D-074:
target W2 "run without installing", Chrome first, Edge/Firefox/Brave/Safari kept in view).

**Process:** follow the `funground-sdlc` skill (`.claude/skills/funground-sdlc/SKILL.md`) in every
session: sprints, stories, design notes, ADRs, decision log, sprint reviews, model economy, git rules.

## Relation to funground

- `funground-hq/funground` (branch `release-0.2-web`) is the product and the reference: its semantic
  contract and golden images are what this repository is measured against. Read it; change it only
  from a funground session.
- Options, criteria and open questions: `docs/design/Web_Target_Options.md` there. Stories here are
  funground's: S-135 (Canvas 2D renderer), S-136 (inverted loop in a worker), S-137 (sound and
  microphone), S-139 (first load), S-140 (share links), later the editor.
- Records specific to this repository use the prefix `WEB-` (`WEB-ADR-001`, `WEB-D-001`).

## Local rules

- On the maintainer's Windows machine: Python is `C:\Projects\playground\.venv\Scripts\python.exe`
  (never plain `python`/`py`); Chrome runs headless from the command line; Node is at
  `/c/sw/nodejs/node`; no npm or pip installs, no installers.
- Pyodide and other browser runtimes are fetched as files into the repository or a CDN, never
  installed.
