// Fitness scene runtime. window.SCENE is written by tools/fitness/scenes.py.
// Every visual property is a pure function of t: seek(t) may be called in any order.
(function () {
  const S = window.SCENE, W = S.W, H = S.H, T = S.T, P = S.palette;
  const clamp = (x, a = 0, b = 1) => Math.min(b, Math.max(a, x));
  const eo = x => 1 - Math.pow(1 - clamp(x), 3);
  const sine = x => -(Math.cos(Math.PI * clamp(x)) - 1) / 2;
  const back = x => { x = clamp(x); const c1 = 1.70158, c3 = c1 + 1; return 1 + c3 * Math.pow(x - 1, 3) + c1 * Math.pow(x - 1, 2); };
  const px = v => `${v.toFixed(2)}px`;
  // Slots as fractions of the frame. Kinetic text and bars share the info slot: text hides while bars show.
  // 9:16 keeps key content out of the top 8% and bottom 20% used by TikTok/Shorts UI.
  const LAYOUT = {
    '9:16': { pose: [.04, .225, .92, .555], tag: [.06, .078], tagged: { badge: [.06, .108], text: [.06, .142, .88, .085], bars: [.07, .142, .86] },
      badge: [.06, .085], text: [.06, .112, .88, .1], center: [.06, .36, .88, .24],
      below: [.06, .66, .88, .1], title: [.06, .3, .88, .26], timer: [.665, .225, .27], bars: [.07, .112, .86],
      warning: [.06, .705, .88], full: [.05, .14, .9, .5], inset: [.55, .235, .39, .3], insetText: null,
      barsDim: .55, textSize: .074, badgeSize: .034, warnSize: .034, barSize: .037 },
    '16:9': { pose: [.02, .05, .5, .93], tag: [.03, .042], tagged: { badge: [.035, .085] },
      badge: [.035, .06], text: [.53, .36, .43, .3], center: [.08, .3, .84, .38],
      below: [.08, .72, .84, .14], title: [.08, .26, .84, .38], timer: [.8, .07, .14], bars: [.53, .34, .42],
      warning: [.53, .8, .42], full: [.05, .12, .9, .57], inset: [.56, .08, .38, .58], insetText: [.53, .69, .43, .17],
      barsDim: 0, textSize: .046, badgeSize: .02, warnSize: .02, barSize: .019 },
  }[S.aspect];
  if (S.tag) Object.assign(LAYOUT, LAYOUT.tagged);  // the pinned tag owns the corner; the badge moves below it
  const shown = c => t => !c ? 0 : eo((t - c.at) / .35) * (c.until == null ? 1 : 1 - clamp((t - c.until) / .25));
  // bars, meter and the hold bar / angle / switch panels take over the info slot
  const barsShown = t => Math.max(shown(S.bars)(t), shown(S.meter)(t), shown(S.holdbar)(t), shown(S.angle)(t), shown(S.switch)(t));
  // Scene transition: in = blur | swipe | impact | fade | cut, out = blur | none (see scenes.py)
  const TR = S.transition || { in: 'fade', out: 'none' };
  const COLOR = name => P[name] || name || P.ink;
  const NUMBER = /^([+-]?)(\d+(?:\.\d+)?)(%|x|×|s)?$/;
  const countUp = (m, g) => m[1] + (parseFloat(m[2]) * g).toFixed((m[2].split('.')[1] || '').length) + (m[3] || '');
  const NS = 'http://www.w3.org/2000/svg';
  let glowId = 0;

  const stage = document.getElementById('stage');
  stage.style.width = px(W); stage.style.height = px(H);
  for (const [k, v] of Object.entries(P)) stage.style.setProperty(`--${k}`, v);
  const el = (tag, cls, parent = stage, html) => { const e = document.createElement(tag); if (cls) e.className = cls; if (html != null) e.innerHTML = html; parent.appendChild(e); return e; };
  const place = (e, r) => { e.style.left = px(r[0] * W); e.style.top = px(r[1] * H); if (r[2] != null) e.style.width = px(r[2] * W); if (r[3] != null) e.style.height = px(r[3] * H); };
  const updates = [];
  const waits = [document.fonts.ready];

  // Neon on accent words only: layered glow in the word's own colour; k > 1 while it flares in.
  const rgb = hex => { const m = /^#?([0-9a-f]{6})$/i.exec(hex || ''); if (!m) return null; const n = parseInt(m[1], 16); return [n >> 16, (n >> 8) & 255, n & 255]; };
  const rgba = (c, a) => `rgba(${c.join(',')},${clamp(a).toFixed(3)})`;
  function glow(color, k = 1) {
    const c = rgb(color); if (!c || S.glow === false) return '0 .06em .5em rgba(0,0,0,.95)';
    return [`0 0 .04em ${rgba(c, 1)}`, `0 0 ${(.12 + .08 * k).toFixed(3)}em ${rgba(c, .9)}`,
      `0 0 ${(.3 + .2 * k).toFixed(3)}em ${rgba(c, .7)}`, `0 0 ${(.7 + .5 * k).toFixed(3)}em ${rgba(c, .45 * k)}`, '0 .06em .5em rgba(0,0,0,.9)'].join(',');
  }
  // Flare of an accent word appearing at t0: the core burns toward white for ~0.1 s, then it settles and breathes.
  function flare(s, t0, t) {
    if (!s.dataset.kw || S.glow === false) return;
    const d = t - t0, f = d < 0 ? 0 : d < .12 ? d / .12 : Math.exp(-(d - .12) * 5);
    const k = .88 + .12 * Math.sin(Math.max(0, d) * 2 * Math.PI / 2.4) + .9 * f, c = rgb(s.dataset.kw);
    s.style.textShadow = glow(s.dataset.kw, k);
    if (c) s.style.color = `rgb(${c.map(v => Math.round(v + (255 - v) * .5 * f)).join(',')})`;
  }
  // Highlight words: [{word, color}] matched case-insensitively ignoring punctuation.
  function words(parent, text, accent) {
    const map = new Map((accent || []).map(a => [a.word.toLowerCase().replace(/[^\p{L}\p{N}%+-]/gu, ''), COLOR(a.color)]));
    const spans = [];
    text.split(/(\s+)/).forEach(part => {
      if (!part) return;
      if (/^\s+$/.test(part)) { parent.appendChild(document.createTextNode(' ')); return; }
      const s = el('span', 'w', parent); s.textContent = part;
      const key = part.toLowerCase().replace(/[^\p{L}\p{N}%+-]/gu, '');
      const color = map.get(key);
      s.style.color = color || P.ink;
      if (color) { s.dataset.kw = color; s.style.textShadow = glow(color); }
      spans.push(s);
    });
    return spans;
  }
  function fit(e, maxHeight, size, minScale = .55) {
    let s = size; e.style.fontSize = px(s);
    while (e.scrollHeight > maxHeight && s > size * minScale) { s *= .94; e.style.fontSize = px(s); }
    return s;
  }
  // Image fitted (contain) into a w×h box: returns {img, left, top, iw, ih}.
  function fitted(parent, image, w, h, anchor = 'center') {
    const k = Math.min(w / image.w, h / image.h), iw = image.w * k, ih = image.h * k;
    const left = (w - iw) / 2, top = anchor === 'bottom' ? h - ih : (h - ih) / 2;
    const img = el('img', '', parent); img.src = image.src;
    Object.assign(img.style, { position: 'absolute', left: px(left), top: px(top), width: px(iw), height: px(ih) });
    waits.push(img.decode());
    return { img, left, top, iw, ih };
  }
  // Pulsing red glows at normalized image positions; returns the per-frame update.
  function glowLayer(parent, box, spots, at) {
    const id = ++glowId, svg = document.createElementNS(NS, 'svg');
    Object.assign(svg.style, { position: 'absolute', left: px(box.left), top: px(box.top), width: px(box.iw), height: px(box.ih),
      overflow: 'visible', mixBlendMode: 'screen' });
    svg.setAttribute('viewBox', `0 0 ${box.iw} ${box.ih}`);
    svg.innerHTML = `<defs><radialGradient id="g${id}"><stop offset="0" stop-color="${P.highlight}" stop-opacity="1"/>` +
      `<stop offset=".5" stop-color="${P.highlight}" stop-opacity=".7"/><stop offset="1" stop-color="${P.highlight}" stop-opacity="0"/></radialGradient>` +
      `<filter id="b${id}" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="${(box.iw * .006).toFixed(2)}"/></filter></defs>`;
    parent.appendChild(svg);
    const glows = (spots || []).map(g => {
      const n = document.createElementNS(NS, 'g'), rx = g.rx * box.iw, ry = (g.ry ?? g.rx) * box.iw;
      n.innerHTML = `<ellipse rx="${rx * 1.6}" ry="${ry * 1.6}" fill="url(#g${id})"/><ellipse rx="${rx * .7}" ry="${ry * .7}" fill="${P.highlight}" filter="url(#b${id})"/>`;
      n.dataset.x = g.x * box.iw; n.dataset.y = g.y * box.ih; n.dataset.rot = g.rotate || 0;
      svg.appendChild(n); return n;
    });
    return t => {
      const appear = clamp((t - at) / .45);
      glows.forEach((n, i) => {
        const beat = .5 + .5 * Math.sin(2 * Math.PI * 1.35 * (t - at) - i * .9);
        const s = (.88 + .2 * beat) * (.6 + .4 * eo(appear));
        n.setAttribute('transform', `translate(${n.dataset.x} ${n.dataset.y}) rotate(${n.dataset.rot}) scale(${s.toFixed(4)})`);
        n.setAttribute('opacity', (eo(appear) * (.5 + .5 * beat)).toFixed(4));
      });
    };
  }
  const MARKS = {
    x: c => `<path d="M5 5 19 19M19 5 5 19" stroke="${c}" stroke-width="3.6" stroke-linecap="round"/>`,
    check: c => `<path d="M4 12.5 9.5 18 20 6" stroke="${c}" stroke-width="3.6" fill="none" stroke-linecap="round" stroke-linejoin="round"/>`,
    arrow: c => `<path d="M12 21V4M5 10.5 12 3.5l7 7" stroke="${c}" stroke-width="3.2" fill="none" stroke-linecap="round" stroke-linejoin="round"/>`,
  };
  // Callout labels and X/check/arrow marks placed at normalized positions of an image box (or the stage).
  function overlays(parent, box, labels, marks) {
    const items = [];
    for (const l of labels || []) {
      const e = el('div', 'callout', parent); words(e, l.text, l.accent);
      Object.assign(e.style, { left: px(box.left + l.x * box.iw), top: px(box.top + l.y * box.ih), color: COLOR(l.color),
        fontSize: px(LAYOUT.textSize * W * .42 * (l.size || 1)), textAlign: l.align || 'center' });
      items.push({ e, at: l.at, until: l.until });
    }
    for (const m of marks || []) {
      const size = (m.size || .06) * W, e = el('div', 'mark', parent);
      Object.assign(e.style, { left: px(box.left + m.x * box.iw - size / 2), top: px(box.top + m.y * box.ih - size / 2), width: px(size), height: px(size) });
      e.innerHTML = `<svg viewBox="0 0 24 24" width="100%" height="100%" style="transform:rotate(${m.rotate || 0}deg)">${MARKS[m.type || 'x'](COLOR(m.color || (m.type === 'check' ? 'accent' : 'highlight')))}</svg>`;
      items.push({ e, at: m.at, until: m.until, pop: true });
    }
    updates.push(t => items.forEach(({ e, at, until, pop }) => {
      const a = (t - at) / (pop ? .32 : .3), q = until == null ? 0 : clamp((t - until) / .2);
      e.style.opacity = (clamp(a * 2.5) * (1 - q)).toFixed(3);
      e.style.transform = `translate(${pop ? '0,0' : '-50%,-50%'}) scale(${((pop ? .3 : .8) + (pop ? .7 : .2) * back(a)).toFixed(4)})`;
    }));
  }

  // -- pose: Ken Burns, isometric jitter, tendon pulse -----------------------
  if (S.pose) {
    const p = S.pose, box = el('div', 'pose-box'); place(box, LAYOUT.pose);
    const cam = el('div', 'pose-cam', box);
    const image = fitted(cam, p, LAYOUT.pose[2] * W, LAYOUT.pose[3] * H, 'bottom');
    cam.style.transformOrigin = `${px(image.left + p.focus[0] * image.iw)} ${px(image.top + p.focus[1] * image.ih)}`;
    const glow = glowLayer(cam, image, p.tendons, p.tendonAt);
    overlays(cam, image, p.labels, p.marks);
    const z0 = p.zoom[0], z1 = p.zoom[1], A = p.jitter * W * .0042;
    updates.push(t => {
      const z = z0 + (z1 - z0) * sine(t / T);
      const strain = p.jitter ? clamp((t - p.jitterAt) / .6) : 0;
      const jx = A * strain * (Math.sin(t * 41.3) * .6 + Math.sin(t * 23.9 + 1.7) * .4);
      const jy = A * strain * (Math.sin(t * 37.1 + .5) * .6 + Math.sin(t * 19.7 + 2.3) * .4) * .7;
      const rot = strain * p.jitter * .18 * Math.sin(t * 29.3 + .9);
      cam.style.transform = `translate(${px(jx)},${px(jy)}) rotate(${rot.toFixed(3)}deg) scale(${z.toFixed(5)})`;
      box.style.opacity = ((TR.in === 'fade' ? eo(t / .25) : 1) * (1 - p.dim) * (1 - LAYOUT.barsDim * barsShown(t))).toFixed(4);
      glow(t);
    });
  }

  // -- full-stage components: split comparison, plan row, tier table ----------------
  const full = S.split || S.plan || S.table;
  const enter = (e, at, dy = .02) => t => {
    const a = eo((t - at) / .4);
    e.style.opacity = a.toFixed(3); e.style.transform = `translateY(${px((1 - a) * H * dy)})`;
  };
  function header(parent, c, size) {
    if (!c.title && !c.sub) return;
    const h = el('div', 'full-head', parent);
    if (c.title) { const m = el('div', 'main', h); words(m, c.title, c.accent); m.style.fontSize = px(size); }
    if (c.sub) { const s = el('div', 'sub', h); s.textContent = c.sub; s.style.fontSize = px(size * .55); }
    updates.push(enter(h, c.at));
  }
  if (S.split) {
    const c = S.split, e = el('div', 'abs split'); place(e, LAYOUT.full);
    const size = LAYOUT.textSize * W * .62; header(e, c, size);
    const row = el('div', 'panels', e); row.style.flexDirection = S.aspect === '9:16' ? 'column' : 'row';
    [c.left, c.right].forEach((panel, i) => {
      const card = el('div', 'panel', row); card.style.borderColor = COLOR(panel.color || 'muted');
      if (panel.label) { const k = el('div', 'kicker', card); k.textContent = panel.label; k.style.fontSize = px(size * .42); k.style.color = COLOR(panel.color || 'muted'); }
      if (panel.title) { const ti = el('div', 'ptitle', card); words(ti, panel.title, panel.accent); ti.style.fontSize = px(size * .62); }
      const media = el('div', 'media', card);
      let image = null;
      if (panel.image) {
        const mw = (S.aspect === '9:16' ? .8 : .4) * W, mh = (S.aspect === '9:16' ? .15 : .37) * H;
        Object.assign(media.style, { width: px(mw), height: px(mh) });
        image = fitted(media, panel.image, mw, mh);
        updates.push(glowLayer(media, image, panel.spots, panel.at));
      }
      let value = null, m = null;
      if (panel.value) { value = el('div', 'value', card); value.style.fontSize = px(size * 1.25); value.style.color = COLOR(panel.color || 'ink'); m = NUMBER.exec(panel.value); }
      if (panel.caption) { const cap = el('div', 'caption', card); cap.textContent = panel.caption; cap.style.fontSize = px(size * .4); }
      updates.push(t => {
        const a = eo((t - panel.at) / .45);
        card.style.opacity = a.toFixed(3); card.style.transform = `translateY(${px((1 - a) * H * .03)})`;
        if (value) value.textContent = m ? countUp(m, eo((t - panel.at - .3) / .9)) : panel.value;
      });
    });
  }
  if (S.plan) {
    const c = S.plan, e = el('div', 'abs plan'); place(e, LAYOUT.full);
    const size = LAYOUT.textSize * W * .62; header(e, c, size);
    const row = el('div', 'cards', e), n = c.items.length;
    const cw = (S.aspect === '9:16' ? .88 / Math.min(n, 3) : .84 / n) * W - 16, ch = (S.aspect === '9:16' ? .16 : .34) * H;
    c.items.forEach((item, i) => {
      const card = el('div', 'card', row); card.style.width = px(cw);
      const media = el('div', 'media', card); Object.assign(media.style, { width: px(cw - 16), height: px(ch) });
      fitted(media, item.image, cw - 16, ch, 'bottom');
      const lab = el('div', 'label', card); lab.textContent = item.label; lab.style.fontSize = px(size * .42);
      if (item.color) card.style.borderColor = COLOR(item.color);
      updates.push(enter(card, c.at + i * (c.stagger ?? .3), .03));
    });
  }
  if (S.table) {
    const c = S.table, e = el('div', 'abs table'); place(e, LAYOUT.full);
    const size = LAYOUT.textSize * W * .62; header(e, c, size);
    const grid = el('div', 'rows', e);
    c.rows.forEach((r, i) => {
      const row = el('div', 'row', grid); row.style.borderColor = COLOR(r.color || 'muted');
      const left = el('div', 'left', row); left.textContent = r.left; left.style.color = COLOR(r.color || 'ink'); left.style.fontSize = px(size * .8);
      const right = el('div', 'right', row); right.textContent = r.right; right.style.fontSize = px(size * .68);
      updates.push(enter(row, c.at + i * (c.stagger ?? .35), .015));
    });
  }
  if (S.stageMarks || S.stageLabels) overlays(stage, { left: 0, top: 0, iw: W, ih: H }, S.stageLabels, S.stageMarks);

  // -- inset: a framed close-up (anatomy, prop) beside the pose ------------------------
  if (S.inset) {
    const c = S.inset, r = LAYOUT.inset, e = el('div', 'abs inset'); place(e, r);
    const frame = el('div', 'frame', e), fh = r[3] * H - (c.label ? LAYOUT.textSize * W * .9 : 0);
    Object.assign(frame.style, { width: px(r[2] * W), height: px(fh) });
    const cam = el('div', 'pose-cam', frame), image = fitted(cam, c.image, r[2] * W, fh);
    const glow = glowLayer(cam, image, c.spots, c.at + .5);
    overlays(cam, image, c.labels, c.marks);
    if (c.label) { const l = el('div', 'label', e); words(l, c.label, c.accent); l.style.fontSize = px(LAYOUT.textSize * W * .42); }
    updates.push(t => {
      const a = eo((t - c.at) / .45), q = c.until == null ? 0 : clamp((t - c.until) / .25);
      e.style.opacity = (a * (1 - q) * (1 - barsShown(t))).toFixed(3); e.style.transform = `translateX(${px((1 - a) * W * .03)})`;
      cam.style.transform = `scale(${(1 + .05 * sine((t - c.at) / Math.max(T - c.at, 1))).toFixed(4)})`;
      glow(t);
    });
  }

  // -- effort meter (shares the info slot with bars) -------------------------------------
  if (S.meter) {
    const c = S.meter, e = el('div', 'abs meter'); place(e, LAYOUT.bars);
    const f = LAYOUT.barSize * W * 1.15; Object.assign(e.style, { fontSize: px(f), padding: px(f * .8) });
    const head = el('div', 'head', e); head.textContent = c.label || 'EFFORT';
    const num = el('div', 'num', e); num.style.fontSize = px(f * 2.2);
    const segs = el('div', 'segs', e), max = c.max || 10;
    const cells = Array.from({ length: max }, (_, i) => {
      const s = el('div', 'seg', segs); s.style.height = px(f * (.9 + i * .12)); return s;
    });
    const tone = i => i / max < .5 ? P.accent : (i / max < .8 ? P.warning : P.highlight);
    if (c.caption) { const cap = el('div', 'caption', e); cap.textContent = c.caption; cap.style.fontSize = px(f * .6); }
    updates.push(t => {
      const show = shown(c)(t); e.style.opacity = show.toFixed(3);
      const filled = c.value * eo((t - c.at - .2) / 1.0);
      cells.forEach((s, i) => { s.style.background = i < filled - .001 ? tone(i) : '#262626'; });
      num.textContent = `${Math.round(filled)}/${max}`;
      num.style.color = tone(Math.max(0, Math.ceil(filled) - 1));
    });
  }

  // -- hold bar: big live seconds over one segment per second; optional fail ("touch = stop") ------
  if (S.holdbar) {
    const c = S.holdbar, e = el('div', 'abs holdbar'); place(e, LAYOUT.bars);
    const f = LAYOUT.barSize * W * 1.1, goal = c.goal || 10;
    Object.assign(e.style, { fontSize: px(f), padding: px(f * .8) });
    el('div', 'head', e).textContent = c.label || 'HOLD';
    const num = el('div', 'num', e); num.style.fontSize = px(f * 3.2);
    const segs = el('div', 'segs', e), cells = Array.from({ length: goal }, () => el('div', 'seg', segs));
    const fail = el('div', 'fail', e); words(fail, c.stop_label || 'Touch = stop', [{ word: (c.stop_label || 'Touch = stop').split(' ')[0], color: 'highlight' }]);
    fail.style.fontSize = px(f * 1.1);
    updates.push(t => {
      e.style.opacity = shown(c)(t).toFixed(3);
      const end = c.stop_at ?? Infinity, sec = Math.min(goal, Math.max(0, Math.min(t, end) - c.run_at) * (c.speed || 1));
      const failed = t >= end, done = sec >= goal - 1e-6, col = failed ? P.highlight : done ? P.accent : P.ink;
      num.textContent = `${sec.toFixed(1)}s`; num.style.color = col;
      num.style.textShadow = failed || done ? glow(col, 1.2) : '0 .06em .5em rgba(0,0,0,.9)';
      cells.forEach((s, i) => { const k = clamp(sec - i); s.style.background = `linear-gradient(90deg, ${failed ? P.highlight : P.signature} ${k * 100}%, #1f1f1f ${k * 100}%)`; });
      const a = failed ? (t - end) / .25 : 0;
      fail.style.opacity = failed ? '1' : '0'; fail.style.transform = `scale(${(1.6 - .6 * eo(a)).toFixed(3)})`;
      if (failed) fail.querySelectorAll('.w').forEach(s => flare(s, end, t));
    });
  }

  // -- angle: a neon L; the vertical stroke draws, the leg swings to each step's angle ----------
  if (S.angle) {
    const c = S.angle, e = el('div', 'abs angle'); place(e, LAYOUT.bars);
    const D = Math.min(LAYOUT.bars[2] * W * .55, H * .32), sw = D * .08;
    e.innerHTML = `<svg width="${D * 1.1}" height="${D * 1.25}" viewBox="${-sw} ${-sw} ${D * 1.1} ${D * 1.25}" style="overflow:visible"><line class="up" stroke-linecap="round" stroke-width="${sw}"/><line class="leg" stroke-linecap="round" stroke-width="${sw}"/></svg>`;
    const up = e.querySelector('.up'), leg = e.querySelector('.leg');
    const deg = el('div', 'deg', e); deg.style.fontSize = px(D * .12);
    const lab = c.label ? el('div', 'lab', e) : null;
    const lspans = lab ? words(lab, c.label, c.accent) : [];
    if (lab) lab.style.fontSize = px(D * .13);
    updates.push(t => {
      e.style.opacity = shown(c)(t).toFixed(3);
      let d = -90;
      for (const st of c.steps) d += (st.deg - d) * (t < st.at ? 0 : back((t - st.at) / .5));
      const draw = eo((t - c.at) / .4), len = D * eo((t - c.at - .25) / .35), r = d * Math.PI / 180, lit = d > -8;
      const col = lit ? P.highlight : '#bdbdbd';
      up.setAttribute('x1', 0); up.setAttribute('y1', D * (1 - draw)); up.setAttribute('x2', 0); up.setAttribute('y2', D); up.setAttribute('stroke', P.ink);
      leg.setAttribute('x1', 0); leg.setAttribute('y1', D); leg.setAttribute('x2', len * Math.cos(r)); leg.setAttribute('y2', D - len * Math.sin(r)); leg.setAttribute('stroke', col);
      leg.style.filter = `drop-shadow(0 0 ${px(sw * (lit ? 1.2 : .3))} ${col})`;
      deg.textContent = `${Math.round(90 + d)}°`; deg.style.color = col;
      if (lab) { lab.style.marginTop = px(Math.max(0, -len * Math.sin(r) - D * .1)); lab.style.opacity = eo((t - c.at - .5) / .3).toFixed(3); lspans.forEach(s => flare(s, c.at + .5, t)); }
    });
  }

  // -- switch: EASIER / HARDER; the knob slides to the active side and that side's text shows ------
  if (S.switch) {
    const c = S.switch, e = el('div', 'abs switch'); place(e, LAYOUT.bars);
    const f = LAYOUT.barSize * W * 1.1; e.style.fontSize = px(f);
    const row = el('div', 'row', e), easy = el('span', 'side', row); easy.textContent = c.easy_label || 'EASIER';
    const track = el('span', 'track', row), knob = el('span', 'knob', track), hard = el('span', 'side', row); hard.textContent = c.hard_label || 'HARDER';
    const lines = c.steps.map(st => { const l = el('div', 'line', e); return { st, l, spans: words(l, st.text, st.accent) }; });
    updates.push(t => {
      e.style.opacity = shown(c)(t).toFixed(3);
      const cur = [...c.steps].reverse().find(st => t >= st.at) || c.steps[0], i = c.steps.indexOf(cur);
      const prev = i > 0 ? c.steps[i - 1].side : (cur.side === 'easy' ? 'hard' : 'easy'), side = s => (s === 'easy' ? 0 : 1);
      const k = side(prev) + (side(cur.side) - side(prev)) * back((t - cur.at) / .35), col = cur.side === 'easy' ? P.accent : P.highlight;
      knob.style.left = `${(6 + k * 52).toFixed(2)}%`; knob.style.background = col; knob.style.boxShadow = `0 0 .6em ${col}`;
      easy.style.color = cur.side === 'easy' ? P.accent : '#666'; hard.style.color = cur.side === 'hard' ? P.highlight : '#666';
      lines.forEach(({ st, l, spans }) => { const on = st === cur; l.style.display = on ? 'block' : 'none'; if (on) { l.style.opacity = eo((t - st.at) / .25).toFixed(3); spans.forEach(s => flare(s, st.at, t)); } });
    });
  }

  // -- dose chip: stopwatch + "20–30s × 3" + set dots, in the timer corner ---------------------------
  if (S.dose) {
    const c = S.dose, D = LAYOUT.timer[2] * W, e = el('div', 'abs dose');
    place(e, [LAYOUT.timer[0] - (S.aspect === '9:16' ? .12 : .1), LAYOUT.timer[1]]); e.style.fontSize = px(D * .2);
    e.innerHTML = `<svg width="${D * .42}" height="${D * .42}" viewBox="-42 -42 84 84"><circle r="34" fill="none" stroke="#555" stroke-width="6"/><rect x="-7" y="-46" width="14" height="8" rx="2" fill="#bbb"/><line class="hand" x1="0" y1="0" x2="0" y2="-26" stroke="${P.highlight}" stroke-width="5" stroke-linecap="round"/><circle r="5" fill="#fff"/></svg>`;
    const box = el('div', 'txt', e), main = el('div', 'main', box); main.textContent = c.main;
    const dots = el('div', 'dots', box), cells = Array.from({ length: c.sets || 0 }, () => el('span', 'dot', dots));
    if (c.note) { const n = el('span', 'note', dots); n.textContent = c.note; }
    const hand = e.querySelector('.hand');
    updates.push(t => {
      const a = (t - c.at) / .4, q = c.until == null ? 0 : clamp((t - c.until) / .25);
      e.style.opacity = (clamp(a * 2.5) * (1 - q)).toFixed(3); e.style.transform = `scale(${(.6 + .4 * back(a)).toFixed(4)})`;
      hand.setAttribute('transform', `rotate(${((t - c.at) * 120 % 360).toFixed(1)})`);
      cells.forEach((s, i) => { const on = t > c.at + .5 + i * .35; s.style.background = on ? P.accent : '#333'; s.style.boxShadow = on ? `0 0 .4em ${P.accent}` : 'none'; });
    });
  }

  // -- pinned heading tag: static within a main idea, so it stays put across scene cuts ------
  // Where a new main idea starts (S.tagFrom set), the old line slides out and the new one slides in.
  if (S.tag) {
    const e = el('div', 'abs tag'); place(e, LAYOUT.tag);
    const size = W * (S.aspect === '9:16' ? .024 : .0125);
    e.style.fontSize = px(size);
    el('span', 'bar', e);
    const lines = el('span', 'lines', e), now = el('span', 'text', lines); now.textContent = S.tag;
    if (S.tagFrom != null) {
      const old = S.tagFrom ? el('span', 'text old', lines) : null;
      if (old) old.textContent = S.tagFrom;
      updates.push(t => {
        const out = eo((t - .05) / .22), into = eo((t - .18) / .35);
        if (old) { old.style.opacity = (1 - out).toFixed(3); old.style.transform = `translateY(${px(-out * size * .9)})`; }
        now.style.opacity = into.toFixed(3); now.style.transform = `translateX(${px((1 - into) * size * 1.6)})`;
        if (!old) e.style.opacity = into.toFixed(3);  // after a scene without a tag, the bar arrives with the line
      });
    }
  }

  // -- title card ------------------------------------------------------------
  if (S.title) {
    const c = S.title, e = el('div', 'abs title'); place(e, LAYOUT.title);
    const main = el('div', 'main', e); const spans = words(main, c.text, c.accent);
    const sub = c.sub ? el('div', 'sub', e) : null; if (sub) { sub.textContent = c.sub; sub.style.fontSize = px(LAYOUT.textSize * W * .42); sub.style.marginTop = px(W * .02); }
    fit(main, LAYOUT.title[3] * H * .8, LAYOUT.textSize * W * 1.5);
    updates.push(t => {
      const q = c.until == null ? 0 : clamp((t - c.until) / .25);
      spans.forEach((s, i) => { const a = (t - c.at - i * .06) / .42; s.style.opacity = (clamp(a * 2.5) * (1 - q)).toFixed(3); s.style.transform = `translateY(${px((1 - eo(a)) * H * .03)}) scale(${(.7 + .3 * back(a)).toFixed(4)})`; flare(s, c.at + i * .06, t); });
      if (sub) sub.style.opacity = (eo((t - c.at - .35) / .4) * (1 - q)).toFixed(3);
    });
  }

  // -- badge ------------------------------------------------------------------
  if (S.badge) {
    const c = S.badge, e = el('div', 'abs badge'); place(e, LAYOUT.badge); e.style.fontSize = px(LAYOUT.badgeSize * W);
    if (c.kicker) el('span', 'kicker', e).textContent = c.kicker;
    el('span', 'dot', e); el('span', 'title', e).textContent = c.title;
    updates.push(t => { const a = eo((t - c.at) / .4); e.style.opacity = a.toFixed(3); e.style.transform = `translateX(${px((1 - a) * -W * .05)})`; });
  }

  // -- circular timer -----------------------------------------------------------
  if (S.timer) {
    const c = S.timer, D = LAYOUT.timer[2] * W, e = el('div', 'abs timer');
    place(e, [LAYOUT.timer[0], LAYOUT.timer[1]]); Object.assign(e.style, { width: px(D), height: px(D) });
    const sw = D * .075, r = D / 2 - sw, C = 2 * Math.PI * r;
    e.innerHTML = `<svg viewBox="0 0 ${D} ${D}"><circle cx="${D / 2}" cy="${D / 2}" r="${r}" fill="rgba(0,0,0,.55)" stroke="#262626" stroke-width="${sw}"/>` +
      `<circle class="arc" cx="${D / 2}" cy="${D / 2}" r="${r}" fill="none" stroke="${P.accent}" stroke-width="${sw}" stroke-linecap="round" stroke-dasharray="${C}" stroke-dashoffset="${C}"/></svg>`;
    const num = el('div', 'num', e); num.style.fontSize = px(D * .34);
    const lab = el('div', 'lab', e); lab.style.fontSize = px(D * .085); lab.textContent = c.label || 'SECONDS';
    const arc = e.querySelector('.arc');
    updates.push(t => {
      const prog = clamp((t - c.at) / c.over), a = (t - c.at) / .4;
      arc.setAttribute('stroke-dashoffset', (C * (1 - prog)).toFixed(2));
      num.textContent = String(Math.min(c.count, Math.floor(prog * c.count + 1e-6)));
      const done = prog >= 1 ? .5 + .5 * Math.sin((t - c.at - c.over) * 9) : 0;
      e.style.opacity = clamp(a * 2).toFixed(3);
      e.style.transform = `scale(${((.6 + .4 * back(a)) * (1 + done * .035)).toFixed(4)})`;
      e.style.filter = done ? `drop-shadow(0 0 ${px(D * .08 * done)} ${P.accent})` : 'none';
    });
  }

  // -- comparison bars -------------------------------------------------------------
  if (S.bars) {
    const c = S.bars, e = el('div', 'abs bars'); place(e, LAYOUT.bars);
    const f = LAYOUT.barSize * W; Object.assign(e.style, { fontSize: px(f), padding: px(f * .9), gap: px(f * .75) });
    if (c.title) el('div', 'head', e).textContent = c.title;
    const rows = c.items.map(b => {
      const row = el('div', 'row', e), lab = el('div', 'lab', row), val = el('div', 'val', row);
      lab.textContent = b.label; const fill = el('div', 'fill', el('div', 'track', row));
      const m = /^([+-]?)(\d+(?:\.\d+)?)(%|x|×)?$/.exec(b.display || '');
      return { b, val, fill, m };
    });
    if (c.sources) { const s = el('div', 'src', e); s.style.fontSize = px(f * .48); s.textContent = c.sources; }
    updates.push(t => {
      const a = eo((t - c.at) / .35), q = c.until == null ? 0 : clamp((t - c.until) / .25);
      e.style.opacity = (a * (1 - q)).toFixed(3); e.style.transform = `translateY(${px((1 - a) * H * .02)})`;
      rows.forEach((r, i) => {
        const g = eo((t - c.at - .25 - i * .18) / .9);
        r.fill.style.width = `${(r.b.value * 100 * g).toFixed(2)}%`;
        r.fill.style.background = r.val.style.color = COLOR(r.b.color || 'accent');
        if (r.m) { const digits = (r.m[2].split('.')[1] || '').length; r.val.textContent = r.m[1] + (parseFloat(r.m[2]) * g).toFixed(digits) + (r.m[3] || ''); }
        else r.val.textContent = r.b.display || '';
        r.val.style.opacity = clamp(g * 1.6).toFixed(3);
      });
    });
  }

  // -- safety warning ----------------------------------------------------------------
  if (S.warning) {
    const c = S.warning, e = el('div', 'abs warning'); place(e, LAYOUT.warning);
    const f = LAYOUT.warnSize * W; Object.assign(e.style, { fontSize: px(f), padding: `${px(f * .65)} ${px(f * .8)}` });
    e.innerHTML = `<svg width="${f * 1.7}" height="${f * 1.5}" viewBox="0 0 24 21"><path d="M12 1 23 20H1Z" fill="${P.warning}"/>` +
      `<rect x="11" y="7" width="2" height="7" rx="1" fill="#000"/><circle cx="12" cy="16.6" r="1.25" fill="#000"/></svg>`;
    el('div', '', e).textContent = c.text;
    updates.push(t => {
      const a = eo((t - c.at) / .4), q = c.until == null ? 0 : clamp((t - c.until) / .25);
      e.style.opacity = (a * (1 - q)).toFixed(3); e.style.transform = `translateY(${px((1 - a) * H * .025)})`;
    });
  }

  // -- kinetic phrases ------------------------------------------------------------------
  if (S.text && S.text.length) {
    const band = full ? LAYOUT.below : (S.inset && LAYOUT.insetText) ? LAYOUT.insetText
      : S.pose ? LAYOUT.text : (S.title ? LAYOUT.below : LAYOUT.center);
    const e = el('div', 'abs kinetic'); place(e, band);
    const size = LAYOUT.textSize * W * (full ? .75 : S.pose ? 1 : (S.title ? .8 : 1.25));
    updates.push(t => { e.style.opacity = (1 - barsShown(t)).toFixed(3); });
    const phrases = S.text.map(c => {
      const ph = el('div', 'phrase', e); const spans = words(ph, c.text, c.accent);
      fit(ph, band[3] * H, size); ph.style.top = '50%';
      return { c, ph, spans };
    });
    updates.push(t => phrases.forEach(({ c, ph, spans }) => {
      const on = t >= c.at - .001 && t < c.until + .2;
      ph.style.visibility = on ? 'visible' : 'hidden';
      if (!on) return;
      const q = clamp((t - c.until) / .18);
      ph.style.opacity = (1 - q).toFixed(3);
      ph.style.transform = `translateY(-50%) scale(${(1 + q * .06).toFixed(4)})`;
      spans.forEach((s, i) => {
        const a = (t - c.at - i * .045) / .34;
        s.style.opacity = clamp(a * 3).toFixed(3);
        s.style.transform = `translateY(${px((1 - eo(a)) * H * .018)}) scale(${(.62 + .38 * back(a)).toFixed(4)})`;
        flare(s, c.at + i * .045, t);
      });
    }));
  }

  // -- scene transition (applied to the whole stage; the cut sits between two scenes' blurs) -------------
  // blur: defocus in 0.22 s (default, the reference channel's cut); swipe: rises from below with vertical motion blur;
  // impact: 3 frames of inverted manga flash with speed lines, then a zoom-blur slam; out blur: defocus over the last 0.14 s.
  {
    const svg = document.createElementNS(NS, 'svg');
    svg.setAttribute('width', 0); svg.setAttribute('height', 0); svg.style.position = 'absolute';
    svg.innerHTML = '<filter id="vblur" x="-5%" y="-30%" width="110%" height="160%"><feGaussianBlur id="vblurdev" stdDeviation="0 0"/></filter>';
    document.body.appendChild(svg);
    const dev = svg.querySelector('#vblurdev');
    const lines = el('div', 'speedlines', document.body);
    Object.assign(lines.style, { position: 'absolute', left: 0, top: 0, width: px(W), height: px(H), display: 'none', pointerEvents: 'none' });
    updates.push(t => {
      let blur = 0, ty = 0, scale = 1, vb = 0, invert = false;
      if (TR.in === 'blur') blur += 14 * (1 - eo(t / .22));
      if (TR.in === 'swipe') { const a = eo(t / .32); ty = (1 - a) * H * .16; vb = 28 * (1 - a); }
      if (TR.in === 'impact') {
        if (t < .1) invert = true;
        else { const a = eo((t - .1) / .35); scale = 1 + .14 * (1 - a); blur += 10 * (1 - a); }
      }
      if (TR.out === 'blur') blur += 12 * clamp((t - (T - .14)) / .14);
      const filters = [];
      if (invert) filters.push('invert(1) contrast(1.4)');
      if (blur > .05) filters.push(`blur(${px(blur)})`);
      if (vb > .2) { dev.setAttribute('stdDeviation', `0 ${vb.toFixed(1)}`); filters.push('url(#vblur)'); }
      stage.style.filter = filters.join(' ') || 'none';
      stage.style.transform = ty || scale !== 1 ? `translateY(${px(ty)}) scale(${scale.toFixed(4)})` : 'none';
      lines.style.display = invert ? 'block' : 'none';
    });
  }

  window.DURATION = T;
  window.seek = t => { for (const u of updates) u(t); };
  window.READY = Promise.all(waits).then(() => { window.seek(0); return true; });
})();
