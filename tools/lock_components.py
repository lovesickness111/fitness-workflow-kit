"""Maintainer command: intentionally update a component's version and content digest."""
import argparse
import subprocess
from manage import ROOT, digest, read_json, write_json

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--component',choices=['video-use','publisher','workflow','motion-broll','fitness-explainer','codex-image'],required=True)
    p.add_argument('--version',required=True)
    p.add_argument('--upstream-commit')
    args=p.parse_args()
    manifest=read_json(ROOT/'skills.lock.json')
    component=manifest['components'][args.component]
    component['version']=args.version
    if args.upstream_commit:
        if len(args.upstream_commit)!=40 or any(c not in '0123456789abcdef' for c in args.upstream_commit.lower()):
            p.error('Expected a full 40-character upstream commit')
        component['upstreamCommit']=args.upstream_commit
    component['sha256']=digest(ROOT,component['paths'])
    write_json(ROOT/'skills.lock.json',manifest)
    print(args.component,component['version'],component['sha256'])

if __name__=='__main__': main()
