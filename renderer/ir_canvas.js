// funground IR -> Canvas 2D (spike S-135). An ES module with no dependencies.
//
// It replays the draw-op IR (Frame.to_jsonable() plus the binary payloads the IR keeps in memory) on a
// CanvasRenderingContext2D / OffscreenCanvas, following funground/renderers/cairo2d.py (the reference)
// op for op: transforms, clips (ResetClip included), caps/joins/dashes, 16 blend modes, groups,
// erase, layered shadows, pixel blocks, pictures with tint and source rectangles.
//
// Text is never drawn with fillText: a Text op must carry "outlines" (FillPath ops from the Python
// typography), exactly what CairoRenderer fills.
//
// Model. Canvas 2D can restore a clip but never remove one, while Cairo's reset_clip() can. So the
// renderer keeps its own stack of levels per drawing target (matrix, clips added at that level, a
// "cleared" flag) and rebuilds the canvas state from it whenever a ResetClip makes the canvas stack
// untruthful. See Target.rebuild().

const BLEND = {
  normal: "source-over", multiply: "multiply", screen: "screen", overlay: "overlay", darken: "darken",
  lighten: "lighten", add: "lighter", difference: "difference", exclusion: "exclusion",
  dodge: "color-dodge", burn: "color-burn", hard_light: "hard-light", soft_light: "soft-light",
  hue: "hue", saturation: "saturation", color: "color", luminosity: "luminosity",
};
const DRAWING = new Set(["Circle", "Ellipse", "Rect", "Line", "Point", "Text", "FillPath", "StrokePath", "Image"]);
const MAX_SHADOW_LAYERS = 12;
const TWO_PI = 2 * Math.PI;

// ---- matrices: [a, b, c, d, e, f]; mul(M, N) applies N first (Cairo's ctx.transform(N))
const IDENT = [1, 0, 0, 1, 0, 0];
const mul = (M, N) => [
  M[0] * N[0] + M[2] * N[1], M[1] * N[0] + M[3] * N[1],
  M[0] * N[2] + M[2] * N[3], M[1] * N[2] + M[3] * N[3],
  M[0] * N[4] + M[2] * N[5] + M[4], M[1] * N[4] + M[3] * N[5] + M[5],
];
const apply = (M, x, y) => [M[0] * x + M[2] * y + M[4], M[1] * x + M[3] * y + M[5]];
const applyDist = (M, x, y) => [M[0] * x + M[2] * y, M[1] * x + M[3] * y];
function invDist(M, x, y) {
  const det = M[0] * M[3] - M[1] * M[2];
  return [(M[3] * x - M[2] * y) / det, (-M[1] * x + M[0] * y) / det];
}

function makeCanvas(w, h) {
  w = Math.max(1, Math.round(w)); h = Math.max(1, Math.round(h));
  if (typeof OffscreenCanvas !== "undefined") return new OffscreenCanvas(w, h);
  const c = document.createElement("canvas"); c.width = w; c.height = h; return c;
}

function tracePath(ctx, segs) {
  ctx.beginPath();
  for (const s of segs) {
    switch (s[0]) {
      case "move": ctx.moveTo(s[1][0], s[1][1]); break;
      case "line": ctx.lineTo(s[1][0], s[1][1]); break;
      case "cubic": ctx.bezierCurveTo(s[1][0], s[1][1], s[2][0], s[2][1], s[3][0], s[3][1]); break;
      case "close": ctx.closePath(); break;
      default: throw new Error(`unknown path segment ${s[0]}`);
    }
  }
}
const rectSegs = (x, y, w, h) => [["move", [x, y]], ["line", [x + w, y]], ["line", [x + w, y + h]],
                                   ["line", [x, y + h]], ["close"]];

// One drawing surface with the level stack described above.
class Target {
  constructor(canvas, ox = 0, oy = 0) {
    this.canvas = canvas; this.ctx = canvas.getContext("2d"); this.ox = ox; this.oy = oy;
    this.levels = []; this.depth = 0; this.truthFrom = 0;
  }
  get top() { return this.levels[this.levels.length - 1]; }
  setM(m) { this.ctx.setTransform(m[0], m[1], m[2], m[3], m[4] - this.ox, m[5] - this.oy); }
  begin(base) {
    this.ctx.save(); this.depth = 0;
    this.levels = [{ m: base.slice(), added: [], cleared: true, aa: true }];
    this.truthFrom = 0; this.setM(base);
  }
  // Canvas cannot drop a clip, so after a ResetClip lower canvas states are clip-free and must be
  // rebuilt (from the model) before the code returns to them.
  rebuild() {
    const ctx = this.ctx, L = this.levels;
    while (this.depth > 0) { ctx.restore(); this.depth--; }
    ctx.restore(); ctx.save();
    const top = L.length - 1;
    let j = top; while (j > 0 && !L[j].cleared) j--;
    for (let i = 0; i <= top; i++) {
      if (i > 0) { ctx.save(); this.depth++; }
      if (i >= j) for (const c of L[i].added) { this.setM(c.m); tracePath(ctx, c.path); ctx.clip(); }
      this.setM(L[i].m);
    }
    this.truthFrom = j;
  }
  save() {
    const t = this.top;
    this.levels.push({ m: t.m.slice(), added: [], cleared: false, aa: t.aa });
    this.ctx.save(); this.depth++;
  }
  restore() {
    if (this.levels.length <= 1) throw new Error("Restore without Save in frame");
    this.levels.pop(); this.ctx.restore(); this.depth--;
    if (this.levels.length - 1 < this.truthFrom) this.rebuild();
  }
  clip(segs, m = this.top.m) {
    this.top.added.push({ path: segs, m: m.slice() });
    this.setM(m); tracePath(this.ctx, segs); this.ctx.clip(); this.setM(this.top.m);
  }
  resetClip() { const t = this.top; t.cleared = true; t.added = []; this.rebuild(); }
  hasClip() {
    let j = this.levels.length - 1; while (j > 0 && !this.levels[j].cleared) j--;
    for (let i = j; i < this.levels.length; i++) if (this.levels[i].added.length) return true;
    return false;
  }
  end() {   // unwind everything, close the frame's own save
    while (this.levels.length > 1) this.restore();
    while (this.depth > 0) { this.ctx.restore(); this.depth--; }
    this.ctx.restore();
  }
  dispose() { while (this.depth > 0) { this.ctx.restore(); this.depth--; } this.ctx.restore(); }
}

export class IrCanvasRenderer {
  /**
   * @param canvas  an OffscreenCanvas / HTMLCanvasElement of width*scale x height*scale physical pixels
   * @param opts    {width, height (logical), scale, getBlob(name) -> Uint8Array (premultiplied BGRA)}
   */
  constructor(canvas, opts) {
    this.W = canvas.width; this.H = canvas.height;
    this.scale = opts.scale || 1;
    this.getBlob = opts.getBlob;
    this.main = new Target(canvas);
    this.t = this.main;
    this.base = [this.scale, 0, 0, this.scale, 0, 0];
    this.groups = [];
    this.alpha = 1; this.erase = null;
    this.images = new Map();
    this.stats = { ops: 0, canvasGroups: 0 };
    this.open = false;
  }

  // ---- frame structure (Cairo draw() / begin_frame() / end_frame())
  beginFrame() {
    if (this.open) throw new Error("beginFrame inside a frame");
    this.t = this.main; this.main.begin(this.base); this.open = true;
  }
  endFrame() { this.main.end(); this.open = false; }
  /** draw(): one whole frame. */
  drawFrame(ops) { this.beginFrame(); this.drawOps(ops); this.endFrame(); }

  drawOps(ops) {
    if (!this.open) this.beginFrame();           // script canvases: batches with no begin
    for (const op of ops) this.drawOp(op);
  }

  // ---- compositing (S-051/S-107): blend, opacity, shadow, erase
  static compositeOf(op) {
    let erase;
    if (op.op === "Image" || op.op === "FillPath" || op.op === "StrokePath") erase = op.erase;
    else erase = op.style ? op.style.erasing : undefined;
    if (erase !== undefined && erase !== null) return { blend: "erase", opacity: erase, shadow: null };
    if (op.op === "Image") {
      const blend = op.blend_mode || "normal", opacity = op.opacity ?? 255;
      return blend === "normal" && opacity === 255 ? null : { blend, opacity, shadow: null };
    }
    const src = op.style || op;
    const blend = src.blend_mode || "normal", opacity = src.opacity ?? 255, shadow = src.shadow || null;
    return blend === "normal" && opacity === 255 && !shadow ? null : { blend, opacity, shadow };
  }

  drawOp(op) {
    this.stats.ops++;
    const c = this.t.ctx;
    const comp = DRAWING.has(op.op) ? IrCanvasRenderer.compositeOf(op) : null;
    if (comp) this.beginComposite(op, comp);
    switch (op.op) {
      case "Clear": this.clear(op.color); break;
      case "Save": this.t.save(); break;
      case "Restore": this.t.restore(); break;
      case "Concat": { const t = this.t.top; t.m = mul(t.m, op.transform); this.t.setM(t.m); break; }
      case "ResetMatrix": { const t = this.t.top; t.m = this.base.slice(); this.t.setM(t.m); break; }
      case "ClipPath": this.t.clip(op.path); break;
      case "ResetClip": this.t.resetClip(); break;
      case "SetAntialias": this.t.top.aa = !!op.on; break;
      case "FillPath":
        tracePath(c, op.path); c.fillStyle = this.source(op.color, false); c.fill(); break;
      case "StrokePath":
        tracePath(c, op.path); c.strokeStyle = this.source(op.color, true); c.lineWidth = op.width;
        this.strokeStyle(op.cap ?? "round", op.join ?? "round", op.miter_limit ?? 10, op.dash ?? [], op.dash_offset ?? 0);
        c.stroke(); break;
      case "Circle":
        c.beginPath(); c.arc(op.x, op.y, Math.max(0, op.diameter / 2), 0, TWO_PI); this.paintStyle(op.style); break;
      case "Ellipse": this.ellipsePath(c, op.x, op.y, op.width / 2, op.height / 2); this.paintStyle(op.style); break;
      case "Rect":
        if (!this.t.top.aa && !op.path && this.noAaRect(op)) break;
        if (op.path) tracePath(c, op.path); else { c.beginPath(); c.rect(op.x, op.y, op.width, op.height); }
        this.paintStyle(op.style); break;
      case "Line":
        if (op.style.stroke) {
          c.beginPath(); c.moveTo(op.x1, op.y1); c.lineTo(op.x2, op.y2);
          c.strokeStyle = this.source(op.style.stroke, true); c.lineWidth = op.style.stroke_width;
          this.stateStroke(op.style); c.stroke();
        }
        break;
      case "Point":
        if (op.style.stroke) {
          c.beginPath(); c.arc(op.x, op.y, Math.max(0.5, op.style.stroke_width / 2), 0, TWO_PI);
          c.fillStyle = this.source(op.style.stroke, true); c.fill();
        }
        break;
      case "Text":
        if (!op.outlines) throw new Error("Text op without outlines: text must arrive shaped (never fillText)");
        for (const sub of op.outlines) { tracePath(c, sub.path); c.fillStyle = this.source(sub.color, false); c.fill(); }
        break;
      case "Image": this.drawImage(op); break;
      case "Pixels": this.drawPixels(op); break;
      case "BeginGroup": this.beginGroup(op); break;
      case "EndGroup": this.endGroup(); break;
      default: throw new Error(`IR op ${op.op} is not implemented by ir_canvas.js`);
    }
    if (comp) { this.t.ctx.restore(); this.alpha = 1; this.erase = null; }
  }

  beginComposite(op, comp) {
    const c = this.t.ctx;
    c.save();
    if (comp.blend === "erase") {
      c.globalCompositeOperation = "destination-out";
      this.erase = IrCanvasRenderer.eraseOf(op); this.alpha = 1; return;
    }
    c.globalCompositeOperation = BLEND[comp.blend];
    this.alpha = comp.opacity / 255;
    if (comp.shadow) this.drawShadow(op, comp.shadow);
  }
  static eraseOf(op) {
    if (op.op === "StrokePath") return [0, op.erase];
    if (op.op === "FillPath" || op.op === "Image") return [op.erase, 0];
    return op.style.erasing;
  }

  // ---- paint sources
  source(c, stroke) {
    if (this.erase) return `rgba(0,0,0,${this.erase[stroke ? 1 : 0] / 255})`;
    const k = this.alpha;
    if (c && !Array.isArray(c)) {                       // gradient, in user space at the moment of use
      const ctx = this.t.ctx, p = c.points;
      const g = c.gradient === "linear" ? ctx.createLinearGradient(p[0], p[1], p[2], p[3])
                                        : ctx.createRadialGradient(p[0], p[1], 0, p[0], p[1], p[2]);
      for (const [off, s] of c.stops) g.addColorStop(off, `rgba(${s[0]},${s[1]},${s[2]},${s[3] / 255 * k})`);
      return g;
    }
    return `rgba(${c[0]},${c[1]},${c[2]},${c[3] / 255 * k})`;
  }
  strokeStyle(cap, join, miter, dash, off) {
    const c = this.t.ctx;
    c.lineCap = cap === "butt" ? "butt" : cap === "square" ? "square" : "round";
    c.lineJoin = join === "miter" ? "miter" : join === "bevel" ? "bevel" : "round";
    c.miterLimit = miter; c.setLineDash(dash.slice()); c.lineDashOffset = off;
  }
  stateStroke(st) {
    this.strokeStyle(st.stroke_cap ?? "round", st.stroke_join ?? "round", st.miter_limit ?? 10, st.dash ?? [], st.dash_offset ?? 0);
  }
  paintStyle(st) {
    const c = this.t.ctx;
    if (st.fill) { c.fillStyle = this.source(st.fill, false); c.fill(); }
    if (st.stroke) {
      c.strokeStyle = this.source(st.stroke, true); c.lineWidth = st.stroke_width; this.stateStroke(st); c.stroke();
    }
  }
  ellipsePath(c, x, y, rx, ry) {
    c.beginPath();
    if (rx > 0 && ry > 0) c.ellipse(x, y, rx, ry, 0, 0, TWO_PI);
  }

  // no_smooth(): Canvas has no switch for path anti-aliasing. The one exact emulation: a filled,
  // axis-aligned rectangle (pixel centres rule), which is what pixel-art sketches draw.
  noAaRect(op) {
    const st = op.style, m = this.t.top.m;
    if (m[1] !== 0 || m[2] !== 0 || st.stroke || !st.fill || Array.isArray(st.fill) === false) return false;
    const [x0, y0] = apply(m, op.x, op.y), [x1, y1] = apply(m, op.x + op.width, op.y + op.height);
    const L = Math.ceil(Math.min(x0, x1) - 0.5), R = Math.ceil(Math.max(x0, x1) - 0.5);
    const T = Math.ceil(Math.min(y0, y1) - 0.5), B = Math.ceil(Math.max(y0, y1) - 0.5);
    const c = this.t.ctx;
    c.save(); c.setTransform(1, 0, 0, 1, -this.t.ox, -this.t.oy);
    c.fillStyle = this.source(st.fill, false); c.fillRect(L, T, R - L, B - T); c.restore();
    return true;
  }

  clear(color) {
    const run = () => {
      const c = this.t.ctx;
      c.save();                                          // Cairo paints under the current matrix (gradients follow it)
      c.globalCompositeOperation = "copy"; c.fillStyle = this.source(color, false);
      c.fillRect(-1e6, -1e6, 2e6, 2e6); c.restore();
    };
    if (!this.t.hasClip()) return run();
    this.t.save(); this.t.resetClip(); run(); this.t.restore();   // Cairo: save, reset_clip, paint SOURCE, restore
  }

  // ---- pictures (S-052/S-078)
  imageSource(file, pw, ph, tint) {
    const key = tint ? `${file}|${tint[0]},${tint[1]},${tint[2]}` : file;
    let cv = this.images.get(key);
    if (cv) return cv;
    const bgra = this.getBlob(file);
    const rgba = new Uint8ClampedArray(pw * ph * 4);
    for (let i = 0; i < pw * ph; i++) {
      let b = bgra[i * 4], g = bgra[i * 4 + 1], r = bgra[i * 4 + 2];
      const a = bgra[i * 4 + 3];
      if (tint) {                                       // premultiplied RGB x tint (pygame BLEND_RGB_MULT); alpha untouched
        r = (r * tint[0] + 255) >> 8; g = (g * tint[1] + 255) >> 8; b = (b * tint[2] + 255) >> 8;
      }
      if (a === 255) { rgba[i * 4] = r; rgba[i * 4 + 1] = g; rgba[i * 4 + 2] = b; rgba[i * 4 + 3] = 255; }
      else if (a > 0) {
        rgba[i * 4] = Math.min(255, Math.round(r * 255 / a)); rgba[i * 4 + 1] = Math.min(255, Math.round(g * 255 / a));
        rgba[i * 4 + 2] = Math.min(255, Math.round(b * 255 / a)); rgba[i * 4 + 3] = a;
      }
    }
    cv = makeCanvas(pw, ph);
    cv.getContext("2d").putImageData(new ImageData(rgba, pw, ph), 0, 0);
    this.images.set(key, cv);
    return cv;
  }

  drawImage(op) {
    const c = this.t.ctx;
    let alpha = this.alpha, tint = null;
    if (this.erase) alpha = this.erase[0] / 255;
    else if (op.tint) { tint = op.tint; alpha = alpha * op.tint[3] / 255; }
    const src = this.imageSource(op.file, op.pw, op.ph, tint);
    const nearest = !this.t.top.aa;
    c.save();
    c.imageSmoothingEnabled = !nearest; c.imageSmoothingQuality = "high";
    c.globalAlpha = alpha;
    if (op.sw === undefined || op.sw === null) {
      c.drawImage(src, op.x, op.y, op.width, op.height);
    } else {                                            // the source rectangle fills the box, clipped to it
      c.beginPath(); c.rect(op.x, op.y, op.width, op.height); c.clip();
      c.translate(op.x, op.y); c.scale(op.width / op.sw, op.height / op.sh);
      c.drawImage(src, -op.sx, -op.sy, op.lw, op.lh);
    }
    c.restore();
  }

  // ---- pixel blocks (S-079): replace, ignoring transform, clip, tint, opacity and blend mode
  drawPixels(op) {
    const b = op.block, s = b.scale;
    const src = this.imageSource(op.file, b.w, b.h, null);
    let m = mul(this.base, [1 / s, 0, 0, 1 / s, b.x / s, b.y / s]);
    if (Math.abs(m[0] - 1) < 1e-9 && Math.abs(m[3] - 1) < 1e-9 && Math.abs(m[2]) < 1e-9 && Math.abs(m[1]) < 1e-9) {
      const r = (v) => (Math.abs(v - Math.round(v)) < 1e-6 ? Math.round(v) : v);
      m = [1, 0, 0, 1, r(m[4]), r(m[5])];
    }
    const t = this.t;
    t.save(); t.resetClip();
    const c = t.ctx;
    t.setM(m);
    // Canvas "copy" also clears outside the shape, so clip to the block's rectangle and copy inside it.
    c.beginPath(); c.rect(0, 0, b.w, b.h); c.clip();
    c.imageSmoothingEnabled = false;
    c.globalCompositeOperation = "copy"; c.globalAlpha = 1;
    c.drawImage(src, 0, 0);
    t.restore();
  }

  // ---- groups (S-132, K2)
  newGroupTarget(device) {                              // device = [x0, y0, x1, y1] in absolute device pixels
    const [x0, y0, x1, y1] = device;
    const gt = new Target(makeCanvas(x1 - x0, y1 - y0), x0, y0);
    gt.ctx.save(); gt.depth = 0;
    gt.levels = this.t.levels.map((l) => ({ m: l.m.slice(), added: l.added.slice(), cleared: l.cleared, aa: l.aa }));
    gt.rebuild();
    this.stats.canvasGroups++;
    return gt;
  }
  beginGroup(op) {
    const parent = this.t;
    parent.save();
    let dev = [0, 0, this.W, this.H];
    if (op.bounds && op.bounds.length) {
      const [x, y, w, h] = op.bounds, m = parent.top.m;
      const cs = [apply(m, x, y), apply(m, x + w, y), apply(m, x, y + h), apply(m, x + w, y + h)];
      const x0 = Math.floor(Math.min(...cs.map((p) => p[0]))) - 1, y0 = Math.floor(Math.min(...cs.map((p) => p[1]))) - 1;
      const x1 = Math.ceil(Math.max(...cs.map((p) => p[0]))) + 1, y1 = Math.ceil(Math.max(...cs.map((p) => p[1]))) + 1;
      parent.clip(rectSegs(x0, y0, x1 - x0, y1 - y0), IDENT);
      dev = [Math.max(0, x0), Math.max(0, y0), Math.min(this.W, x1), Math.min(this.H, y1)];
      if (dev[2] <= dev[0] || dev[3] <= dev[1]) dev = [0, 0, 1, 1];
    }
    const gt = this.newGroupTarget(dev);
    this.groups.push({ op, parent, target: gt, dev });
    this.t = gt;
  }
  endGroup() {
    const g = this.groups.pop();
    g.target.dispose();
    this.t = g.parent;
    this.pasteGroup(g.target, g.dev, BLEND[g.op.blend_mode || "normal"], g.op.opacity ?? 1);
    this.t.restore();                                   // the save in beginGroup: clip and size
  }
  pasteGroup(target, dev, gco, alpha) {
    const c = this.t.ctx;
    c.save(); c.setTransform(1, 0, 0, 1, 0, 0);
    c.globalCompositeOperation = gco; c.globalAlpha = alpha; c.imageSmoothingEnabled = false;
    c.drawImage(target.canvas, dev[0] - this.t.ox, dev[1] - this.t.oy);
    c.restore();
  }

  // ---- shadows (S-051): layers of the shape grown outward, each painted as one group
  geometry(op, c) {
    const st = op.style;
    switch (op.op) {
      case "FillPath": return [{ make: () => tracePath(c, op.path), filled: true, width: null }];
      case "StrokePath": return [{ make: () => tracePath(c, op.path), filled: false, width: op.width }];
      case "Text": return (op.outlines || []).map((sub) => ({ make: () => tracePath(c, sub.path), filled: true, width: null }));
      case "Point": {
        if (!st.stroke) return [];
        const r = Math.max(0.5, st.stroke_width / 2);
        return [{ make: () => { c.beginPath(); c.arc(op.x, op.y, r, 0, TWO_PI); }, filled: true, width: null }];
      }
      case "Line":
        return st.stroke ? [{ make: () => { c.beginPath(); c.moveTo(op.x1, op.y1); c.lineTo(op.x2, op.y2); }, filled: false, width: st.stroke_width }] : [];
    }
    let make;
    if (op.op === "Circle") make = () => { c.beginPath(); c.arc(op.x, op.y, Math.max(0, op.diameter / 2), 0, TWO_PI); };
    else if (op.op === "Ellipse") make = () => this.ellipsePath(c, op.x, op.y, op.width / 2, op.height / 2);
    else make = () => { if (op.path) tracePath(c, op.path); else { c.beginPath(); c.rect(op.x, op.y, op.width, op.height); } };
    return [{ make, filled: !!st.fill, width: st.stroke ? st.stroke_width : null }];
  }

  drawShadow(op, shadow) {
    const [dx, dy, blur, col] = shadow;
    const t = this.t, outer = t.ctx, saved = t.top.m;
    if (!this.geometry(op, outer).length) return;
    const [ddx, ddy] = applyDist(this.base, dx, dy);
    const bd = applyDist(this.base, 1, 0), ud = invDist(saved, bd[0], bd[1]);
    const perPx = Math.hypot(ud[0], ud[1]);
    const total = (col[3] / 255) * this.alpha;
    const n = blur <= 0 ? 1 : Math.max(1, Math.min(MAX_SHADOW_LAYERS, Math.ceil(blur)));
    const shifted = saved.slice(); shifted[4] += ddx; shifted[5] += ddy;   // device offset, after the CTM
    const gco = outer.globalCompositeOperation;
    const solid = `rgb(${col[0]},${col[1]},${col[2]})`;
    const layer = (k) => {                              // layer k: the shape grown by blur*(n-k+1)/n, as one solid group
      const grow = blur > 0 ? (blur * (n - k + 1) / n) * perPx : 0;
      const gt = this.newGroupTarget([0, 0, this.W, this.H]);   // like push_group: same clip, operator inherited
      gt.top.m = shifted.slice(); gt.setM(gt.top.m);
      const c = gt.ctx;
      c.lineJoin = "round"; c.lineCap = "round"; c.setLineDash([]);
      c.fillStyle = solid; c.strokeStyle = solid; c.globalCompositeOperation = gco;
      for (const p of this.geometry(op, c)) {
        if (p.filled) {
          p.make(); c.fill();
          if (grow > 0) { c.lineWidth = 2 * grow; c.stroke(); }
        }
        if (p.width !== null) { p.make(); c.lineWidth = p.width + 2 * grow; c.stroke(); }
      }
      gt.dispose();
      return gt;
    };
    if (gco === "source-over" && n > 1) {
      // Cairo paints n layers at alpha (total/n)/(1 - total(k-1)/n) so that k overlapping layers end at k/n of
      // the shadow's alpha. Canvas quantises every low alpha to 8 bits (CPU raster darkens the core by ~8 %), so
      // instead the layers are added into one group in whole-number steps whose running sum tracks k*total*255/n.
      const acc = this.newGroupTarget([0, 0, this.W, this.H]);
      acc.ctx.globalCompositeOperation = "lighter"; acc.ctx.imageSmoothingEnabled = false;
      acc.setM(IDENT);
      const D = total * 255 / n;
      for (let k = 1; k <= n; k++) {
        const inc = Math.round(k * D) - Math.round((k - 1) * D);
        if (inc <= 0) continue;
        const gt = layer(k);
        acc.ctx.save(); acc.ctx.setTransform(1, 0, 0, 1, 0, 0);
        acc.ctx.globalAlpha = inc / 255; acc.ctx.drawImage(gt.canvas, 0, 0); acc.ctx.restore();
      }
      acc.dispose();
      outer.save(); outer.setTransform(1, 0, 0, 1, 0, 0);
      outer.globalAlpha = 1; outer.imageSmoothingEnabled = false;
      outer.drawImage(acc.canvas, -t.ox, -t.oy);
      outer.restore();
      return;
    }
    for (let k = 1; k <= n; k++) {
      const gt = layer(k);
      const layerAlpha = (total / n) / (1 - total * (k - 1) / n);
      outer.save(); outer.setTransform(1, 0, 0, 1, 0, 0);
      outer.globalCompositeOperation = gco; outer.globalAlpha = layerAlpha; outer.imageSmoothingEnabled = false;
      outer.drawImage(gt.canvas, -t.ox, -t.oy);
      outer.restore();
    }
  }
}

/** Convenience: a renderer for a case document (see tools/export_ir.py), replaying all of its steps. */
export function replayCase(renderer, doc) {
  let open = false;
  for (const s of doc.steps) {
    if (s.k === "frame") renderer.drawFrame(s.ops);
    else if (s.k === "begin") { renderer.beginFrame(); open = true; }
    else if (s.k === "batch") renderer.drawOps(s.ops);
    else if (s.k === "end") { renderer.endFrame(); open = false; }
  }
  if (renderer.open) renderer.endFrame();
  if (doc.overlay) renderer.drawFrame(doc.overlay);
}

/** Replay only the final frame of a case (its last "frame" step or its last begin..end run). */
export function finalFrameSteps(doc) {
  let i = doc.steps.length - 1;
  while (i > 0 && doc.steps[i].k !== "frame" && doc.steps[i].k !== "begin") i--;
  return doc.steps.slice(Math.max(0, i));
}
