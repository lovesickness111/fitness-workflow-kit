"""Run a bundled helper with local configuration, without copying secrets into vendor."""
from pathlib import Path
import os
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]

def load_env():
    env = os.environ.copy()
    file = ROOT / 'local/secrets.env'
    if file.exists():
        for line in file.read_text(encoding='utf-8-sig').splitlines():
            if not line.strip() or line.lstrip().startswith('#') or '=' not in line:
                continue
            key, value = line.split('=', 1)
            env.setdefault(key.strip(), value.strip().strip('"').strip("'"))
    return env

if __name__ == '__main__':
    if len(sys.argv) < 2:
        sys.exit('Usage: run_video_use.py <helper.py> [arguments]')
    base = ROOT / '.agents/skills/video-use/helpers'
    helper = (base / sys.argv[1]).resolve()
    if helper.parent != base.resolve() or helper.suffix != '.py' or not helper.is_file():
        sys.exit('Select a .py helper directly inside video-use/helpers.')
    sys.exit(subprocess.call([sys.executable, str(helper), *sys.argv[2:]], env=load_env()))
