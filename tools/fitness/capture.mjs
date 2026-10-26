// Frame-exact capture of a fitness scene page (window.SCENE/READY/seek).
//   node capture.mjs video  <scene.html> <out.mp4> <fps> [crf]
//   node capture.mjs stills <scene.html> <out-prefix> <t1,t2,...>
// NODE_PATH must contain playwright (see `fitness_video.py setup`).
import { createRequire } from 'node:module';
import { spawn } from 'node:child_process';
import { pathToFileURL } from 'node:url';
import path from 'node:path';

const require = createRequire(path.join(process.env.NODE_PATH || process.cwd(), 'noop.js'));
const { chromium } = require('playwright');
const [mode, html, out, arg, crfArg] = process.argv.slice(2);
if (!['video', 'stills'].includes(mode) || !html || !out || !arg) {
  console.error('usage: capture.mjs video|stills <scene.html> <out> <fps|times> [crf]');
  process.exit(2);
}

const browser = await chromium.launch();
const errors = [];
try {
  const page = await browser.newPage({ viewport: { width: 1080, height: 1920 }, deviceScaleFactor: 1 });
  page.on('pageerror', e => errors.push(e.message));
  page.on('console', m => { if (m.type() === 'error') errors.push(m.text()); });
  await page.goto(pathToFileURL(path.resolve(html)).href);
  await page.waitForFunction(() => window.READY !== undefined, null, { timeout: 30000 });
  await page.evaluate(() => window.READY);
  const info = await page.evaluate(() => ({ W: window.SCENE.W, H: window.SCENE.H, T: window.SCENE.T }));
  await page.setViewportSize({ width: info.W, height: info.H });
  const shot = () => page.screenshot({ type: 'jpeg', quality: 95, clip: { x: 0, y: 0, width: info.W, height: info.H } });

  if (mode === 'stills') {
    for (const t of arg.split(',').map(Number)) {
      await page.evaluate(t => window.seek(t), t);
      await page.screenshot({ path: `${out}-${t.toFixed(2)}s.png`, clip: { x: 0, y: 0, width: info.W, height: info.H } });
    }
  } else {
    const fps = Number(arg), frames = Math.round(info.T * fps);
    const ff = spawn('ffmpeg', ['-hide_banner', '-loglevel', 'error', '-y', '-f', 'image2pipe', '-framerate', String(fps),
      '-c:v', 'mjpeg', '-i', '-', '-c:v', 'libx264', '-preset', 'medium', '-crf', crfArg || '18', '-pix_fmt', 'yuv420p',
      '-r', String(fps), '-movflags', '+faststart', out]);
    ff.stderr.on('data', d => process.stderr.write(d));
    let code = null;
    const closed = new Promise(r => ff.on('close', c => { code = c; r(); }));
    ff.stdin.on('error', () => {});
    for (let f = 0; f < frames && code === null; f++) {
      await page.evaluate(t => window.seek(t), f / fps);
      if (!ff.stdin.write(await shot())) await Promise.race([new Promise(r => ff.stdin.once('drain', r)), closed]);
    }
    ff.stdin.end();
    await closed;
    if (code !== 0) throw new Error(`ffmpeg failed (exit ${code}); ${out} is incomplete`);
    console.log(`rendered ${out} ${frames} frames`);
  }
} finally {
  await browser.close();
}
if (errors.length) {
  console.error('page errors:\n' + errors.join('\n'));
  process.exit(1);
}
