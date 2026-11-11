#!/usr/bin/env python3
"""Checks that the Yatesium changes apply to a Chromium version.

Downloads only the files the patches and the rebrand script touch (a partial
clone of the Chromium GitHub mirror, under 1 GB), applies every patch,
runs the string rebrand and verifies the branding overlay. Takes a few
minutes. Run it before starting a multi-hour build on a new Chromium version.

Usage: check_patches.py [chromium version] [--keep DIR]
"""

import argparse
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MIRROR = 'https://github.com/chromium/chromium'

# Paths the rebrand script reads or writes, in addition to patched files.
REBRAND_PATHS = (
    '/tools/grit/',
    '/chrome/app/*.grd',
    '/chrome/**/*.grdp',
    '/chrome/app/resources/chromium_strings_*.xtb',
    '/chrome/app/resources/generated_resources_*.xtb',
    '/components/*.grd',
    '/components/**/*.grdp',
    '/components/strings/components_chromium_strings_*.xtb',
    '/components/strings/components_strings_*.xtb',
    '/extensions/strings/',
    '/extensions/*.grd*',
)


def git(*args, cwd):
    subprocess.run(('git', ) + args, cwd=str(cwd), check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('version', nargs='?', default=(
        ROOT / 'chromium_version.txt').read_text(encoding='utf-8').strip())
    parser.add_argument('--keep', type=Path,
                        help='Use this folder and keep it afterwards.')
    args = parser.parse_args()
    if not re.fullmatch(r'\d+\.\d+\.\d+\.\d+', args.version):
        sys.exit('Not a Chromium version: ' + args.version)

    patches = sorted((ROOT / 'patches').glob('*.patch'))
    branding = [p for p in (ROOT / 'branding').rglob('*') if p.is_file()]
    paths = set(REBRAND_PATHS)
    for patch in patches:
        for line in patch.read_text(encoding='utf-8').splitlines():
            match = re.match(r'diff --git a/(\S+) b/', line)
            if match:
                paths.add('/' + match.group(1))
    for path in branding:
        paths.add('/' + path.relative_to(ROOT / 'branding').as_posix())

    work = args.keep or Path(tempfile.mkdtemp(prefix='yatesium-check-'))
    work.mkdir(parents=True, exist_ok=True)
    try:
        if not (work / '.git').exists():
            git('init', '-q', cwd=work)
            git('remote', 'add', 'origin', MIRROR, cwd=work)
            git('config', 'extensions.partialClone', 'origin', cwd=work)
            git('config', 'remote.origin.promisor', 'true', cwd=work)
            git('config', 'remote.origin.partialclonefilter', 'blob:none',
                cwd=work)
            git('config', 'core.autocrlf', 'false', cwd=work)
            git('sparse-checkout', 'init', '--no-cone', cwd=work)
        (work / '.git' / 'info' / 'sparse-checkout').write_text(
            '\n'.join(sorted(paths)) + '\n', encoding='utf-8')
        git('fetch', '-q', '--depth', '1', '--filter=blob:none', 'origin',
            'tag', args.version, cwd=work)
        git('checkout', '-q', '-f', 'FETCH_HEAD', cwd=work)

        for patch in patches:
            git('apply', '--check', '--whitespace=nowarn', str(patch),
                cwd=work)
        for patch in patches:
            git('apply', '--whitespace=nowarn', str(patch), cwd=work)
            print('applies: ' + patch.name)

        subprocess.run([sys.executable, str(ROOT / 'scripts' / 'rebrand.py'),
                        str(work)], check=True)

        for path in branding:
            relative = path.relative_to(ROOT / 'branding')
            if not (work / relative).exists():
                sys.exit('branding/%s has no counterpart in Chromium %s' %
                         (relative.as_posix(), args.version))
        print('branding: %d files match' % len(branding))
        print('OK: Yatesium changes apply to Chromium ' + args.version)
    finally:
        if not args.keep:
            shutil.rmtree(work, ignore_errors=True)


if __name__ == '__main__':
    main()
