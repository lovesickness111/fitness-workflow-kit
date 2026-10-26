# Video Workflow Kit (Claude Desktop / Claude Code)

@AGENTS.md

- Skills live in `.agents/skills/`. Each `.claude/skills/<name>/SKILL.md` is a pointer, so Claude Code finds them; always follow the canonical file it names.
- The person using this kit may be non-technical. Answer in their language and give one concrete next step at a time.
  - Prefer the double-click launchers at the kit root: `1-Cai-dat.cmd` (install), `2-Nhap-key.cmd` (hidden key entry), `3-Kiem-tra.cmd` (check), `4-Dang-nhap-Codex.cmd` (optional ChatGPT login for images).
- Run kit Python as `.venv/Scripts/python.exe ...` and PowerShell scripts as `powershell -ExecutionPolicy Bypass -File ...`. Do not install tools globally beyond what `setup/setup.ps1` does.
- Never type, paste or store a key for the user. Ask them to double-click `2-Nhap-key.cmd`; it saves keys to the ignored `local/secrets.env`. Never log in to Codex, Zernio or any platform on the user's behalf.
