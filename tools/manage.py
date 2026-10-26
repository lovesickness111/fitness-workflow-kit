"""Local readiness, component update/rollback, and source-only release packaging."""
from pathlib import Path
from datetime import datetime, timezone
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
EXCLUDE = {'.git', '__pycache__', 'node_modules', 'dist', '.venv'}

def read_json(p):
    return json.loads(Path(p).read_text(encoding='utf-8-sig'))

def write_json(p, value):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + '.tmp')
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8', newline='\n')
    os.replace(tmp, p)

def safe(base, relative):
    base = Path(base).resolve()
    p = (base / relative).resolve()
    if p == base or base not in p.parents:
        raise ValueError('Path escapes expected workspace')
    return p

def digest(base, paths):
    result = hashlib.sha256()
    files = []
    for relative in paths:
        p = safe(base, relative)
        if not p.exists():
            raise ValueError(f'Missing component path: {relative}')
        files.extend([p] if p.is_file() else [f for f in p.rglob('*') if f.is_file() and not any(x in EXCLUDE for x in f.relative_to(p).parts)])
    for p in sorted(files, key=lambda f: f.relative_to(base).as_posix()):
        if p.is_symlink():
            raise ValueError('Symlinks are not supported in component snapshots')
        result.update(p.relative_to(base).as_posix().encode())
        result.update(b'\0')
        data = p.read_bytes()
        # Line endings depend on how the kit was obtained (Git checkout, ZIP, Windows editor); text hashes ignore them.
        result.update(data if b'\0' in data else data.replace(b'\r\n', b'\n'))
        result.update(b'\0')
    return result.hexdigest()

def checked(args, **kwargs):
    subprocess.run([str(a) for a in args], check=True, **kwargs)

def refresh_dependencies(component):
    if component == 'video-use':
        py = ROOT / '.venv/Scripts/python.exe'
        if py.exists():
            checked([py, '-m', 'pip', 'install', '-r', ROOT/'config/python-requirements.txt'])
    if component == 'publisher' and (ROOT/'tools/publisher/node_modules').exists():
        npm = shutil.which('npm.cmd') or shutil.which('npm')
        if not npm:
            raise ValueError('npm missing; cannot rebuild publisher')
        checked([npm, 'ci', '--ignore-scripts'], cwd=ROOT/'tools/publisher')
        checked([npm, 'run', 'build'], cwd=ROOT/'tools/publisher')

def copy_paths(source, target, paths):
    for relative in paths:
        src, dst = safe(source, relative), safe(target, relative)
        dst.parent.mkdir(parents=True, exist_ok=True)
        if src.is_dir():
            shutil.copytree(src, dst, ignore=shutil.ignore_patterns(*EXCLUDE))
        else:
            shutil.copy2(src, dst)

def remove_paths(base, paths):
    for relative in paths:
        p = safe(base, relative)
        if p.is_dir():
            shutil.rmtree(p)
        elif p.exists():
            p.unlink()

def install_component(source, name, rollback=False):
    manifest = read_json(ROOT/'skills.lock.json')
    other = read_json(source/'skills.lock.json')
    if manifest['kitFormat'] != other['kitFormat']:
        raise ValueError('Kit format changed. Use a full kit upgrade with maintainer guidance.')
    current = manifest['components'][name]
    incoming = other['components'][name]
    if current['paths'] != incoming['paths']:
        raise ValueError('Component layout changed; requires a full kit upgrade.')
    paths = current['paths']
    if digest(ROOT, paths) != current['sha256']:
        raise ValueError('Local component was modified. Preserve/reconcile changes before update or rollback.')
    if digest(source, paths) != incoming['sha256']:
        raise ValueError('Source component does not match its lock file.')
    backup = ROOT/'local/backups'/name/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    backup.mkdir(parents=True)
    copy_paths(ROOT, backup, paths)
    write_json(backup/'skills.lock.json', manifest)
    try:
        remove_paths(ROOT, paths)
        copy_paths(source, ROOT, paths)
        refresh_dependencies(name)
        manifest['components'][name] = incoming
        write_json(ROOT/'skills.lock.json', manifest)
    except Exception:
        remove_paths(ROOT, paths)
        copy_paths(backup, ROOT, paths)
        write_json(ROOT/'skills.lock.json', read_json(backup/'skills.lock.json'))
        refresh_dependencies(name)
        raise
    if not rollback:
        write_json(ROOT/f'local/backups/{name}/latest.json', {'directory': str(backup)})
    print(f'{name}: installed {incoming["version"]}. Previous files saved under local/backups. Local secrets and projects retained.')

def update(args):
    runs = ROOT/'local/runs'
    if runs.exists() and list(runs.glob('*.lock')):
        raise ValueError('A publish run is locked. Finish or reconcile it before updating.')
    if args.rollback:
        if args.source or args.version:
            raise ValueError('Rollback cannot be combined with source or version.')
        receipt = read_json(ROOT/f'local/backups/{args.component}/latest.json')
        source = Path(receipt['directory']).resolve()
        if (ROOT/'local/backups').resolve() not in source.parents:
            raise ValueError('Invalid rollback receipt')
        install_component(source, args.component, rollback=True)
        return
    if args.source:
        if args.version:
            raise ValueError('Use either source or version')
        source = Path(args.source).resolve()
        if source == ROOT:
            raise ValueError('Choose a different extracted release folder')
        install_component(source, args.component)
        return
    if not args.version or not args.version.startswith('v') or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.-' for c in args.version):
        raise ValueError('Provide an approved release tag using --version vX.Y.Z, or --source.')
    repository = read_json(ROOT/'skills.lock.json')['repository']
    if not repository.startswith('https://github.com/') or '..' in repository:
        raise ValueError('Expected the approved GitHub kit URL in skills.lock.json')
    with tempfile.TemporaryDirectory(prefix='video-workflow-update-') as temp:
        source = Path(temp)/'kit'
        checked(['git','clone','--depth','1','--branch',args.version,'--',repository,source])
        install_component(source,args.component)

def doctor():
    results = []
    for command in ['git','ffmpeg','ffprobe','node']:
        executable = shutil.which(command)
        results.append((command,bool(executable),'found' if executable else 'missing'))
    node = shutil.which('node')
    if node:
        ok = subprocess.run([node,'-e','process.exit(Number(process.versions.node.split(".")[0])>=22?0:1)'],capture_output=True).returncode == 0
        results.append(('Node >=22',ok,'version requirement'))
    ff = shutil.which('ffmpeg')
    if ff:
        result = subprocess.run([ff,'-hide_banner','-filters'],capture_output=True,text=True,errors='replace')
        results.append(('FFmpeg subtitles',result.returncode==0 and ' subtitles ' in result.stdout,'libass subtitle filter'))
    py=ROOT/'.venv/Scripts/python.exe'
    ok=py.exists() and subprocess.run([str(py),'-c','import requests,librosa,matplotlib,PIL,numpy'],capture_output=True).returncode==0
    results.append(('Python dependencies',bool(ok),'isolated .venv'))
    results.append(('Publisher build',(ROOT/'tools/publisher/dist/cli.js').is_file(),'run setup if missing'))
    env_file=ROOT/'local/secrets.env'
    env={}
    if env_file.exists():
        for line in env_file.read_text(encoding='utf-8-sig').splitlines():
            if '=' in line and not line.lstrip().startswith('#'):
                k,v=line.split('=',1); env[k.strip()]=v.strip().strip('"').strip("'")
    for key,use in [('ELEVENLABS_API_KEY','transcribing your own footage'),('ZERNIO_API_KEY','publishing')]:
        present=bool(os.environ.get(key) or env.get(key))
        results.append((key,present,'present locally; not remotely validated' if present else f'missing: double-click 2-Nhap-key.cmd (needed only for {use})'))
    accounts=ROOT/'local/accounts.json'
    try:
        profiles=read_json(accounts)['profiles']
        count=sum(len(p['platforms']) for p in profiles.values())
        results.append(('Account destinations',count>0,f'{count} configured; run publisher check for remote validation' if count else
                        'none yet: needed only for publishing; ask Claude to set it up before the first post'))
    except (OSError,ValueError,KeyError,TypeError):
        results.append(('Account destinations',False,'configure local/accounts.json'))
    lock=read_json(ROOT/'skills.lock.json')
    for name,component in lock['components'].items():
        results.append((name+' snapshot',digest(ROOT,component['paths'])==component['sha256'],'matches component lock'))
    for label,ok,note in results:
        print(f'{"OK" if ok else "ACTION"} | {label} | {note}')
    print('Local checks only. No transcription, media upload or publishing performed.')
    return 0 if all(ok for _,ok,_ in results) else 2

def package(output):
    # git archive exports exactly tracked source, never local secrets/runtime or ignored files.
    checked(['git','-C',ROOT,'diff','--exit-code','HEAD','--'])
    output=Path(output).resolve()
    output.parent.mkdir(parents=True,exist_ok=True)
    checked(['git','-C',ROOT,'archive','--format=zip','--prefix=video-workflow-kit/','--output',output,'HEAD'])
    with zipfile.ZipFile(output) as archive:
        forbidden={'.git','local','projects','.venv','node_modules','dist','release'}
        for name in archive.namelist():
            parts=Path(name).parts[1:]
            if set(parts)&(forbidden-{'projects'}) or (parts and parts[0]=='projects' and parts[-1]!='.gitkeep' and not name.endswith('/')):
                output.unlink()
                raise ValueError('Release archive contains runtime files')
        with tempfile.TemporaryDirectory(prefix='video-workflow-package-') as temp:
            archive.extractall(temp)
            kit = Path(temp)/'video-workflow-kit'
            lock = read_json(kit/'skills.lock.json')
            stale = [n for n,c in lock['components'].items() if digest(kit,c['paths'])!=c['sha256']]
    if stale:
        output.unlink()
        raise ValueError('Release archive does not match skills.lock.json for: '+', '.join(stale)+'. Relock and commit first.')
    print(f'ZIP: {output}')
    print('SHA256: '+hashlib.sha256(output.read_bytes()).hexdigest())

def main():
    p=argparse.ArgumentParser()
    subs=p.add_subparsers(dest='command',required=True)
    subs.add_parser('doctor')
    u=subs.add_parser('update'); u.add_argument('--component',choices=['video-use','publisher','workflow','motion-broll','fitness-explainer','codex-image'],required=True)
    u.add_argument('--version');u.add_argument('--source');u.add_argument('--rollback',action='store_true')
    z=subs.add_parser('package');z.add_argument('--output',required=True)
    a=p.parse_args()
    if a.command=='doctor': return doctor()
    if a.command=='update': update(a)
    if a.command=='package': package(a.output)
    return 0

if __name__=='__main__':
    try: sys.exit(main())
    except (ValueError,OSError,subprocess.CalledProcessError) as error:
        print(str(error),file=sys.stderr);sys.exit(1)
