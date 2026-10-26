#!/usr/bin/env node
// Generate or edit one raster image with Codex CLI's built-in image_gen tool.
// Billing goes to the ChatGPT plan that Codex is logged into (`codex login`); no OPENAI_API_KEY.
//
//   node codex_image.mjs --out <file.png> (--prompt "<text>" | --prompt-file <file>)
//        [--aspect 1:1|3:2|2:3] [--ref <image> ...] [--model gpt-5.6-luna] [--timeout 300]
//
// Codex runs lean (no user config, plugins or MCP servers, read-only sandbox, low reasoning) and
// only calls the tool; the image is picked up from $CODEX_HOME/generated_images/<thread_id>/.
// Prints one JSON line: { path, width, height, thread_id, usage, agent_credits }.
import { spawn } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

// Credits per 1M tokens (Codex rate card, standard speed). Image tokens are billed separately
// and are not reported by `codex exec`, so agent_credits covers only the orchestrating model.
const RATES = {
  'gpt-5.6-luna': { input: 5, cached: 0.5, output: 30 },
  'gpt-5.6-terra': { input: 50, cached: 5, output: 300 },
  'gpt-5.6-sol': { input: 100, cached: 10, output: 500 },
};

function fail(message) {
  console.error(`codex-image: ${message}`);
  process.exit(1);
}

function parseArgs(argv) {
  const args = { refs: [], aspect: '', model: process.env.CODEX_IMAGE_MODEL || 'gpt-5.6-luna', timeout: 300 };
  for (let i = 0; i < argv.length; i++) {
    const key = argv[i];
    const value = () => (i + 1 < argv.length ? argv[++i] : fail(`${key} needs a value`));
    if (key === '--out') args.out = value();
    else if (key === '--prompt') args.prompt = value();
    else if (key === '--prompt-file') args.prompt = fs.readFileSync(value(), 'utf8');
    else if (key === '--aspect') args.aspect = value();
    else if (key === '--ref') args.refs.push(value());
    else if (key === '--model') args.model = value();
    else if (key === '--timeout') args.timeout = Number(value());
    else fail(`unknown argument ${key}`);
  }
  if (!args.out) fail('--out is required');
  if (!args.prompt?.trim()) fail('--prompt or --prompt-file is required');
  if (path.extname(args.out).toLowerCase() !== '.png') fail('--out must end with .png');
  for (const ref of args.refs) if (!fs.existsSync(ref)) fail(`reference image not found: ${ref}`);
  return args;
}

function pngSize(file) {
  const head = fs.readFileSync(file).subarray(0, 24);
  if (head.toString('latin1', 1, 4) !== 'PNG') return { width: null, height: null };
  return { width: head.readUInt32BE(16), height: head.readUInt32BE(20) };
}

function instructions({ prompt, aspect, refs }) {
  const lines = [
    'Call your built-in image generation tool exactly once, then reply with just the word DONE.',
    'Do not read skill files, run commands, write code or view the result.',
    'If the tool refuses or fails, reply with FAILED: and the reason instead.',
  ];
  if (refs.length) lines.push(`The ${refs.length} attached image(s) are references for the edit or generation.`);
  lines.push('', 'Image prompt:', prompt.trim());
  if (aspect) lines.push(`Aspect ratio: ${aspect}.`);
  return lines.join('\n');
}

const args = parseArgs(process.argv.slice(2));
const codexHome = process.env.CODEX_HOME || path.join(os.homedir(), '.codex');
const workdir = fs.mkdtempSync(path.join(os.tmpdir(), 'codex-image-'));
// Options taking several values (--image) must not sit right before the trailing "-" (prompt on stdin).
const cliArgs = ['exec', ...args.refs.flatMap((ref) => ['--image', path.resolve(ref)]), '--json', '--ephemeral',
  '--ignore-user-config', '--skip-git-repo-check', '-s', 'read-only', '-C', workdir, '-m', args.model,
  '-c', 'model_reasoning_effort=low', '-'];

// CODEX_BIN points at codex.exe when it is not on PATH (the npm codex.cmd shim cannot be spawned without a shell).
const child = spawn(process.env.CODEX_BIN || 'codex', cliArgs, { stdio: ['pipe', 'pipe', 'pipe'], windowsHide: true });
child.on('error', (e) => fail(`cannot start codex (${e.message}); install Codex CLI and run \`codex login\``));
const timer = setTimeout(() => child.kill(), args.timeout * 1000);
let stdout = '';
let stderr = '';
child.stdout.on('data', (d) => (stdout += d));
child.stderr.on('data', (d) => (stderr += d));
child.stdin.end(instructions(args));

child.on('close', (code) => {
  clearTimeout(timer);
  fs.rmSync(workdir, { recursive: true, force: true });
  const events = stdout.split('\n').filter(Boolean).flatMap((line) => {
    try {
      return [JSON.parse(line)];
    } catch {
      return [];
    }
  });
  const threadId = events.find((e) => e.type === 'thread.started')?.thread_id;
  const usage = events.find((e) => e.type === 'turn.completed')?.usage || null;
  const reply = events.filter((e) => e.item?.type === 'agent_message').map((e) => e.item.text).join('\n').trim();
  const errors = [...new Set(events.filter((e) => e.type === 'turn.failed' || e.type === 'error')
    .map((e) => e.error?.message || e.message).filter(Boolean))];
  const dir = threadId && path.join(codexHome, 'generated_images', threadId);
  const images = dir && fs.existsSync(dir)
    ? fs.readdirSync(dir).filter((f) => f.toLowerCase().endsWith('.png'))
      .map((f) => path.join(dir, f)).sort((a, b) => fs.statSync(a).mtimeMs - fs.statSync(b).mtimeMs)
    : [];
  if (!images.length) {
    const why = errors.join('; ') || reply || stderr.trim().split('\n').slice(-3).join(' ') || `codex exited ${code}`;
    fail(`no image was generated: ${why}`);
  }
  const out = path.resolve(args.out);
  fs.mkdirSync(path.dirname(out), { recursive: true });
  fs.copyFileSync(images[images.length - 1], out);
  const rate = RATES[args.model];
  const agentCredits = rate && usage
    ? +(((usage.input_tokens - usage.cached_input_tokens) * rate.input + usage.cached_input_tokens * rate.cached
      + usage.output_tokens * rate.output) / 1e6).toFixed(3)
    : null;
  console.log(JSON.stringify({ path: out, ...pngSize(out), thread_id: threadId, usage, agent_credits: agentCredits }));
});
