---
name: codex-image
description: Generate or edit a raster image (illustration, character pose, thumbnail, cover) by delegating to the Codex CLI built-in image tool, billed to the ChatGPT plan Codex is logged into instead of an API key. Used by the fitness-explainer pose pipeline (with Gemini as backup) and for ad-hoc images when no native image tool is available.
---

# Codex image

`scripts/codex_image.mjs` runs `codex exec` in a lean mode: no user config, plugins or MCP servers, a read-only sandbox, low reasoning. Codex calls its image tool once. The script copies the PNG from `$CODEX_HOME/generated_images/<thread_id>/` to `--out` and prints one JSON line:

```json
{"path":"...png","width":1536,"height":1024,"thread_id":"...","usage":{...},"agent_credits":0.1}
```

## Requirements

- Node 18+, and the Codex CLI on PATH. `setup/setup.ps1` installs it with winget (`OpenAI.Codex`) when it is missing.
- The npm package's `codex.cmd` shim cannot be spawned directly. If only that exists, set `CODEX_BIN` to a `codex.exe`.
- Codex must be logged in with **the user's own** ChatGPT account. `codex login status` should print `Logged in using ChatGPT`.
- To log in, the user double-clicks `4-Dang-nhap-Codex.cmd` (or runs `codex login`) themselves. Never handle their credentials.
- Images count against that plan's limits or credits.

## Usage

```bash
node .agents/skills/codex-image/scripts/codex_image.mjs --out <file.png> --aspect 3:2 --prompt "<full image prompt>"
node .agents/skills/codex-image/scripts/codex_image.mjs --out <file.png> --prompt-file prompt.txt
# keep a character consistent: attach references and say what stays and what changes
node .agents/skills/codex-image/scripts/codex_image.mjs --out <file.png> --ref ref.png --aspect 2:3 --prompt "Same character, same face and outfit, now doing a calf raise"
```

| Option | Meaning |
|---|---|
| `--out` | Destination `.png`, required. Parent folders are created. |
| `--prompt` / `--prompt-file` | Image prompt; one of the two is required. |
| `--aspect` | `1:1` (1024×1024), `3:2` (1536×1024) or `2:3` (1024×1536). |
| `--ref` | Reference or edit image. Repeat for several images. |
| `--model` | Agent model. Defaults to `gpt-5.6-luna` or `CODEX_IMAGE_MODEL`. |
| `--timeout` | Seconds. Defaults to 300. |

- A call takes about 30–40 s and makes one image. Exit code 1 means no image; the message carries Codex's error or refusal.
- For other ratios, generate the nearest native size with space around the subject, then centre-crop. The fitness pipeline does this automatically.

## Prompting and checks

- Write prompts in English: subject and action, the props the pose needs, style or medium, composition, lighting.
- End with "no text, no logos, no watermark" unless text is wanted; if it is, quote the exact words.
- Always `Read` the output and check it before use. Regenerate with one targeted change when something is wrong (for example a missing prop).
- Never depict real, identifiable people. The only exception is the user, from their own photos, when they ask.

## Cost (Codex rate card, credits)

- **Agent:** about 0.1 credit per call with `gpt-5.6-luna`, reported as `agent_credits`. Keep Luna; other models make the agent part 10–20 times more expensive.
- **Image:** image tokens come on top and are not reported. Expect about 1 credit at medium quality and about 4 at high quality for 1536×1024. Quality cannot be chosen.
- **Limits:** image generation uses a plan's included limits about 3–5 times faster than coding.

## In this kit

- Save outputs under `projects/<project>/` (see `AGENTS.md`), never inside this skill folder.
- fitness-explainer uses this skill when `channel.image.provider` is `codex`.
  - `fallback: gemini` takes over when Codex is missing, logged out, refuses or fails.
  - Each pose records which provider drew it. Approvals stay digest-bound.
- For a single ad-hoc image with the channel character, pass the files in `local/fitness/characters/<id>/` with `--ref`.
