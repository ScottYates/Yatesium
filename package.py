#!/usr/bin/env python3
"""Packages the compiled browser as a portable zip.

Reads Chromium's own Windows file list (chrome/tools/build/win/FILES.cfg),
drops installers, tests, symbols and remote-desktop components, and zips what
remains under a top-level "Yatesium" folder.

Usage: package.py --build-dir <dir used by build.py>
"""

import argparse
import glob
import re
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent

# Entries in FILES.cfg that do not belong in a portable browser folder.
EXCLUDE = re.compile(
    r'(\.pdb$|\.lib$|\.h$|\.xml$|\.msi$|\.rc$|\.7z$|_tests\.exe$|^gen/'
    r'|^remot|^gcp_|^gaia|^gcapi|^zucchini|^setup\.exe$|^mini_installer'
    r'|^updater\.zip$|^policy_templates\.zip$|^hyphens-data\.zip$'
    r'|^chromedriver|^chromoting|^First Run$)', re.IGNORECASE)

# The package is rejected if any of these is missing.
REQUIRED = ('chrome.exe', 'chrome.dll', 'chrome_elf.dll', 'resources.pak',
            'icudtl.dat', 'v8_context_snapshot.bin', 'locales/en-US.pak')

README = '''Yatesium %(version)s (portable)

Start the browser with chrome.exe.

All browser data (profile, settings, extensions, cache) is stored in the
"Data" folder next to chrome.exe. The folder is created on first start.
To update, extract a newer Yatesium zip over this folder. "Data" is kept.
To start fresh, close the browser and delete "Data".

Yatesium is built from Chromium %(chromium)s. See about:credits in the browser
for the licenses of Chromium and its components.
'''


def read_text(name):
    return (ROOT / name).read_text(encoding='utf-8').strip()


def list_files(files_cfg, out_dir):
    scope = {}
    exec(files_cfg.read_text(encoding='utf-8'), scope)  # Chromium's file list
    selected = {}
    for entry in scope['FILES']:
        name = entry['filename']
        if 'official' not in entry.get('buildtype', ()):
            continue
        if 'arch' in entry and '64bit' not in entry['arch']:
            continue
        if EXCLUDE.search(name):
            continue
        for match in glob.glob(str(out_dir / name)):
            path = Path(match)
            if path.is_file():
                selected[path.relative_to(out_dir).as_posix()] = path
    return selected


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build-dir', required=True, type=Path)
    args = parser.parse_args()

    src = args.build_dir / 'src'
    out_dir = src / 'out' / 'Default'
    files = list_files(src / 'chrome' / 'tools' / 'build' / 'win' / 'FILES.cfg',
                       out_dir)

    present = {name.lower() for name in files}
    missing = [name for name in REQUIRED if name.lower() not in present]
    if missing:
        sys.exit('Build output is missing required files: ' +
                 ', '.join(missing))

    chromium = read_text('chromium_version.txt')
    version = '%s-%s' % (chromium, read_text('revision.txt'))
    dist = args.build_dir / 'dist'
    dist.mkdir(parents=True, exist_ok=True)
    zip_path = dist / ('Yatesium-%s-win-x64.zip' % version)

    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED,
                         compresslevel=9) as archive:
        for name in sorted(files):
            archive.write(files[name], 'Yatesium/' + name)
        archive.writestr('Yatesium/README.txt',
                         README % {'version': version, 'chromium': chromium})
    print('Packaged %d files into %s (%.0f MB)' %
          (len(files) + 1, zip_path, zip_path.stat().st_size / 1e6))


if __name__ == '__main__':
    main()
