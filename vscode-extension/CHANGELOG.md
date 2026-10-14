# Changelog

## 0.2.0

Suggestions. While you type, the editor now knows funground, also in github.dev and vscode.dev where Python has no
funground installed: the names after `f.` (and bare, after `from funground import *`) with their signatures and a
link to the reference; the colours after `f.COLORS.` (with a swatch) and the words after `f.CONSTANTS.` and
`f.CONSTANTS.ALIGN.`; colour names inside the quotes of `f.fill("`, and option words inside the quotes of
`f.blend_mode("`; a hint on hover; the parameters while you type a call. They come from funground's own list
(`completions.json`), which belongs to the funground the runtime runs. The new setting `funground.suggestions` turns
them off.

## 0.1.0

First preview. Runs a funground sketch in a panel beside the editor, in github.dev, vscode.dev and VS Code:
re-runs a moment after typing stops and at once on save, shows output and errors (the line underlined in
the editor), plays sound, loads pictures and sounds from `data/` and imports `.py` files beside the
sketch. Python and funground load from the funground website. No microphone in the panel.
