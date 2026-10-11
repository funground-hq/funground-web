# funground

Write a [funground](https://funground-hq.github.io) sketch in Python and watch it run beside your code, in
your browser: in **github.dev** (press `.` on any GitHub repository), on **vscode.dev**, or in VS Code.
Nothing to install on your computer.

## How to use it

1. Open a Python file that uses funground, for example:

   ```python
   import funground as f

   def setup():
       f.size(640, 400)

   def draw():
       f.background("white")
       f.fill("tomato")
       f.circle(320, 200, 80)

   f.run()
   ```

2. Press **Ctrl+Enter** (**Cmd+Enter** on a Mac), or the ▷ button at the top right of the editor.
   A panel opens beside your code and the sketch runs in it. The first time takes a few seconds while
   Python loads into the page.
3. Change the code. The sketch runs again a moment after you stop typing, and at once when you save.
   If something is wrong, the panel shows the error and the line is underlined in red.

Pictures and sounds in a `data` folder next to your sketch load as they would on your computer
(`f.load_image("data/photo.png")`), and other `.py` files in the same folder can be imported.

To keep your sketches, make your own copy of the
[funground sketchbook](https://github.com/funground-hq/sketchbook) on GitHub and open it with `.`.
Saving is GitHub's own: **Source Control**, then **Commit & Push**.

## Safe by design

Your sketch runs in a part of the page of its own, never with the editor's rights or your GitHub
account. Python and funground load from the funground website, nothing else.

## What does not work here yet

- The microphone: VS Code does not let an extension's panel use it. Sketches that listen run on your
  computer or on the funground website's [Play](https://funground-hq.github.io/play/) page.
- A few things only a computer has, such as your own installed fonts and saving videos (`.mp4`).

This is a preview, made for Chrome first.

## More

- funground: [funground-hq.github.io](https://funground-hq.github.io), with a guide and a gallery of
  examples.
- Source code and issues: [funground-hq/funground-web](https://github.com/funground-hq/funground-web).
- Licence: LGPL 2.1 only.
