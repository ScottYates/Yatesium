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

    def done(self, step):
        return (self.state / step).exists()

    def mark(self, step):
        self.state.mkdir(parents=True, exist_ok=True)
        (self.state / step).write_text(read_version(), encoding='utf-8')

    # -- steps ------------------------------------------------------------

    def get_depot_tools(self):
        if (self.depot_tools / 'gclient.bat').exists():
            return
        log('Getting depot_tools')
        self.run('git', 'clone', '--depth', '1', DEPOT_TOOLS_URL,
                 self.depot_tools)
        # First run downloads depot_tools' own Python and git.
        self.env['DEPOT_TOOLS_UPDATE'] = '1'
        self.run('gclient.bat', '--version')
        self.env['DEPOT_TOOLS_UPDATE'] = '0'

    def checkout(self):
        if self.done('checkout'):
            return
        version = read_version()
        log('Checking out Chromium %s' % version)
        if not (self.src / '.git').exists():
            self.run('git', 'clone', '--depth', '1', '--branch', version,
                     CHROMIUM_URL, self.src)
        self.run('gclient.bat', 'sync', '--no-history', '--nohooks', '-D',
                 '--jobs', '8')
        self.run('gclient.bat', 'runhooks')
        self.mark('checkout')

    def apply_changes(self):
        if self.done('patched'):
            return
        patches = sorted((ROOT / 'patches').glob('*.patch'))
        log('Checking %d patches' % len(patches))
        for patch in patches:
            self.run('git', 'apply', '--check', '--whitespace=nowarn', patch,
                     cwd=self.src)
        for patch in patches:
            log('Applying ' + patch.name)
            self.run('git', 'apply', '--whitespace=nowarn', patch,
                     cwd=self.src)

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
                shutil.copyfile(path, target)
                count += 1
        log('Copied %d branding files' % count)
        self.mark('patched')

    def remove_git_dirs(self):
        """Frees disk space on CI. The checkout is not updated afterwards."""
        if self.done('git_removed'):
            return
        log('Removing .git directories to save disk space')

        def on_error(func, path, _):
            os.chmod(path, stat.S_IWRITE)
            func(path)

        for dirpath, dirnames, _ in os.walk(self.src):
            if '.git' in dirnames:
                shutil.rmtree(os.path.join(dirpath, '.git'), onerror=on_error)
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
            sys.exit('Compile failed with exit code %d.' % code)
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
