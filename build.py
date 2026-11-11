#!/usr/bin/env python3
"""Builds Yatesium for Windows x64 from Chromium source.

Steps, each skipped if already done:
  1. Get depot_tools.
  2. Check out Chromium at the version in chromium_version.txt.
  3. Apply patches/*.patch, rebrand strings, copy branding/ assets.
  4. Generate the build directory from flags.gn.
  5. Compile.
  6. Package the portable zip (package.py).

Local use:   python build.py
CI use:      python build.py --ci --stop-after-minutes 210

With --stop-after-minutes the compile is stopped after that many minutes and
the script exits with code 124. Running it again resumes the compile.

Requirements: Windows 10/11 x64, Visual Studio 2022 with "Desktop development
with C++", the Windows SDK version named in src/build/vs_toolchain.py
(including "Debugging Tools for Windows"), git, and about 100 GB free disk.
"""

import argparse
import ctypes
import os
import re
import shutil
import signal
import stat
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TIMEOUT_EXIT_CODE = 124
DEPOT_TOOLS_URL = 'https://chromium.googlesource.com/chromium/tools/depot_tools.git'
CHROMIUM_URL = 'https://chromium.googlesource.com/chromium/src.git'

GCLIENT_CONFIG = '''solutions = [
  {
    "name": "src",
    "url": "%s",
    "managed": False,
    "custom_deps": {},
    "custom_vars": {
      "checkout_pgo_profiles": True,
    },
  },
]
target_os = ["win"]
''' % CHROMIUM_URL


def log(message):
    print('[yatesium] ' + message, flush=True)


def read_version():
    return (ROOT / 'chromium_version.txt').read_text(encoding='utf-8').strip()


class Builder:
    def __init__(self, args):
        self.args = args
        self.build_dir = Path(args.build_dir).resolve()
        self.src = self.build_dir / 'src'
        self.depot_tools = self.build_dir / 'depot_tools'
        self.state = self.build_dir / 'state'
        self.out = self.src / 'out' / 'Default'
        self.env = dict(os.environ)
        self.env['DEPOT_TOOLS_WIN_TOOLCHAIN'] = '0'
        self.env['DEPOT_TOOLS_UPDATE'] = '0'
        self.env['PATH'] = str(self.depot_tools) + os.pathsep + self.env['PATH']
        # Keep compiler temp files inside the build folder.
        tmp = self.build_dir / 'tmp'
        tmp.mkdir(parents=True, exist_ok=True)
        self.env['TMP'] = self.env['TEMP'] = str(tmp)
        # Git settings Chromium needs on Windows, applied to every git call
        # made by this script and by gclient without touching global config.
        git_config = (('core.autocrlf', 'false'), ('core.filemode', 'false'),
                      ('core.longpaths', 'true'))
        self.env['GIT_CONFIG_COUNT'] = str(len(git_config))
        for index, (key, value) in enumerate(git_config):
            self.env['GIT_CONFIG_KEY_%d' % index] = key
            self.env['GIT_CONFIG_VALUE_%d' % index] = value

    # -- helpers ----------------------------------------------------------

    def run(self, *cmd, cwd=None):
        log('> ' + ' '.join(str(c) for c in cmd))
        # depot_tools commands are .bat files, so go through the shell.
        subprocess.run(subprocess.list2cmdline([str(c) for c in cmd]),
                       cwd=str(cwd or self.build_dir), env=self.env,
                       shell=True, check=True)

    def run_with_retries(self, *cmd, cwd=None, cleanup=None, attempts=4):
        """Runs a network command, retrying after server or network errors."""
        for attempt in range(1, attempts + 1):
            try:
                self.run(*cmd, cwd=cwd)
                return
            except subprocess.CalledProcessError:
                if attempt == attempts:
                    raise
                delay = 60 * attempt
                log('Command failed (attempt %d of %d). Retrying in %d s.' %
                    (attempt, attempts, delay))
                if cleanup:
                    cleanup()
                time.sleep(delay)

    def remove_tree(self, path):
        def on_error(func, failed_path, _):
            os.chmod(failed_path, stat.S_IWRITE)
            func(failed_path)

        if Path(path).exists():
            shutil.rmtree(path, onerror=on_error)

    def done(self, step):
        marker = self.state / step
        if not marker.exists():
            return False
        saved = marker.read_text(encoding='utf-8').strip()
        if saved != read_version():
            sys.exit('The build folder holds Chromium %s but chromium_version.txt '
                     'says %s. Start with an empty build folder.' %
                     (saved, read_version()))
        return True

    def mark(self, step):
        self.state.mkdir(parents=True, exist_ok=True)
        (self.state / step).write_text(read_version(), encoding='utf-8')

    # -- steps ------------------------------------------------------------

    def get_depot_tools(self):
        if (self.depot_tools / 'gclient.bat').exists():
            return
        log('Getting depot_tools')
        self.run_with_retries(
            'git', 'clone', '--depth', '1', DEPOT_TOOLS_URL, self.depot_tools,
            cleanup=lambda: self.remove_tree(self.depot_tools))
        # First run downloads depot_tools' own Python and git.
        self.env['DEPOT_TOOLS_UPDATE'] = '1'
        self.run_with_retries('gclient.bat', '--version')
        self.env['DEPOT_TOOLS_UPDATE'] = '0'

    def checkout(self):
        if self.done('checkout'):
            return
        version = read_version()
        log('Checking out Chromium %s' % version)
        if not (self.src / '.git').exists():
            # A failed clone leaves a partial folder behind. Remove it
            # before trying again.
            self.run_with_retries(
                'git', 'clone', '--depth', '1', '--branch', version,
                CHROMIUM_URL, self.src,
                cleanup=lambda: self.remove_tree(self.src))
        self.run_with_retries('gclient.bat', 'sync', '--no-history',
                              '--nohooks', '-D', '--jobs', '8')
        self.run_with_retries('gclient.bat', 'runhooks')
        self.mark('checkout')

    def apply_changes(self):
        patches = sorted((ROOT / 'patches').glob('*.patch'))
        applied_dir = self.state / 'applied_patches'
        applied = sorted(applied_dir.glob('*.patch'))
        if (self.done('patched') and
                [(p.name, p.read_bytes()) for p in patches] ==
                [(p.name, p.read_bytes()) for p in applied]):
            return

        # Files any old or new patch touches, with their current time stamp
        # and content. A file that ends up with the same content gets its
        # time stamp back, so only real changes are recompiled.
        touched = {}
        for patch in applied + patches:
            for name in re.findall(r'^diff --git a/(\S+) b/',
                                   patch.read_text(encoding='utf-8'), re.M):
                path = self.src / name
                if path.is_file():
                    touched[path] = (path.stat().st_mtime_ns, path.read_bytes())

        if applied:
            # The build folder was patched by an earlier run and the patches
            # have changed since. Take the old ones out, newest first, so the
            # new set applies to pristine files.
            log('Patches changed. Reverting the %d applied before.' %
                len(applied))
            for patch in reversed(applied):
                self.run('git', 'apply', '-R', '--whitespace=nowarn', patch,
                         cwd=self.src)
                patch.unlink()
        if (self.state / 'patched').exists():
            (self.state / 'patched').unlink()

        log('Applying %d patches' % len(patches))
        applied_dir.mkdir(parents=True, exist_ok=True)
        for patch in patches:
            self.run('git', 'apply', '--whitespace=nowarn', patch,
                     cwd=self.src)
            shutil.copyfile(patch, applied_dir / patch.name)

        for path, (mtime_ns, content) in touched.items():
            if path.is_file() and path.read_bytes() == content:
                os.utime(path, ns=(mtime_ns, mtime_ns))

        log('Rebranding strings')
        subprocess.run([sys.executable, str(ROOT / 'scripts' / 'rebrand.py'),
                        str(self.src)], check=True)

        branding = ROOT / 'branding'
        count = 0
        for path in branding.rglob('*'):
            if path.is_file():
                target = self.src / path.relative_to(branding)
                if not target.exists():
                    sys.exit('branding/%s has no counterpart in the Chromium '
                             'tree.' % path.relative_to(branding).as_posix())
                if target.read_bytes() != path.read_bytes():
                    shutil.copyfile(path, target)
                    count += 1
        log('Updated %d branding files' % count)
        self.mark('patched')

    def remove_git_dirs(self):
        """Frees disk space on CI. The checkout is not updated afterwards."""
        if self.done('git_removed'):
            return
        log('Removing .git directories to save disk space')
        for dirpath, dirnames, _ in os.walk(self.src):
            if '.git' in dirnames:
                self.remove_tree(os.path.join(dirpath, '.git'))
                dirnames.remove('.git')
        self.mark('git_removed')

    def generate(self):
        if self.done('generated') and (self.out / 'build.ninja').exists():
            return
        flags = (ROOT / 'flags.gn').read_text(encoding='utf-8')
        # Optional Google API keys (needed for Google sign-in and sync).
        for env_name, gn_name in (
                ('GOOGLE_API_KEY', 'google_api_key'),
                ('GOOGLE_DEFAULT_CLIENT_ID', 'google_default_client_id'),
                ('GOOGLE_DEFAULT_CLIENT_SECRET', 'google_default_client_secret')):
            value = os.environ.get(env_name, '').strip()
            if value:
                if '"' in value or '\\' in value or '$' in value:
                    sys.exit(env_name + ' contains an unsupported character.')
                flags += '%s = "%s"\n' % (gn_name, value)
        self.out.mkdir(parents=True, exist_ok=True)
        (self.out / 'args.gn').write_text(flags, encoding='utf-8')
        self.run('gn.bat', 'gen', 'out/Default', '--fail-on-unused-args',
                 cwd=self.src)
        self.mark('generated')

    def compile(self):
        cmd = ['autoninja.bat', '-C', 'out/Default']
        if self.args.jobs:
            cmd += ['-j', str(self.args.jobs)]
        cmd.append('chrome')
        log('> ' + ' '.join(cmd))

        deadline = None
        if self.args.stop_after_minutes:
            deadline = self.args.start_time + self.args.stop_after_minutes * 60
            remaining = deadline - time.time()
            if remaining < 300:
                log('No time left for compiling in this run.')
                return False
            log('Compile will be stopped in %d minutes.' % (remaining / 60))

        proc = subprocess.Popen(
            subprocess.list2cmdline(cmd), cwd=str(self.src), env=self.env,
            shell=True, creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
        try:
            code = proc.wait(None if deadline is None else
                             max(1, deadline - time.time()))
        except subprocess.TimeoutExpired:
            log('Time limit reached. Stopping the compile.')
            for _ in range(3):
                ctypes.windll.kernel32.GenerateConsoleCtrlEvent(
                    signal.CTRL_BREAK_EVENT, proc.pid)
                time.sleep(2)
            try:
                proc.wait(120)
            except subprocess.TimeoutExpired:
                pass
            subprocess.run(['taskkill', '/F', '/T', '/PID', str(proc.pid)],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return False
        if code != 0:
            log('Compile failed with exit code %d.' % code)
            sys.exit(1)
        return True

    def package(self):
        subprocess.run([sys.executable, str(ROOT / 'package.py'),
                        '--build-dir', str(self.build_dir)], check=True)


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument('--build-dir', default=str(ROOT / 'build'),
                        help='Working folder. Use a short path, e.g. C:\\y.')
    parser.add_argument('-j', '--jobs', type=int,
                        help='Parallel compile jobs. Default: automatic.')
    parser.add_argument('--ci', action='store_true',
                        help='Delete .git folders after checkout to save disk.')
    parser.add_argument('--stop-after-minutes', type=float,
                        help='Stop compiling this many minutes after '
                        '--start-time and exit with code 124.')
    parser.add_argument('--start-time', type=float, default=time.time(),
                        help='Unix time the run started. Default: now.')
    args = parser.parse_args()

    if sys.platform != 'win32':
        sys.exit('This script builds on Windows only.')

    # Chromium sources use LF line endings. A patch converted to CRLF by git
    # (core.autocrlf) does not apply, so catch that before the long checkout.
    for patch in sorted((ROOT / 'patches').glob('*.patch')):
        if b'\r\n' in patch.read_bytes():
            sys.exit('%s has CRLF line endings. Re-clone this repository with '
                     '"git config core.autocrlf false".' % patch.name)

    builder = Builder(args)
    builder.build_dir.mkdir(parents=True, exist_ok=True)
    # autoninja and gclient locate the checkout through this file.
    (builder.build_dir / '.gclient').write_text(GCLIENT_CONFIG,
                                                encoding='utf-8')
    builder.get_depot_tools()
    builder.checkout()
    builder.apply_changes()
    if args.ci:
        builder.remove_git_dirs()
    builder.generate()
    if not builder.compile():
        sys.exit(TIMEOUT_EXIT_CODE)
    builder.package()
    log('Done.')


if __name__ == '__main__':
    main()
