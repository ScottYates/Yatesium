# Yatesium

Yatesium is a Chromium fork for Windows x64. It is current stable Chromium
plus a small patch set:

- Manifest V2 extensions work. Upstream Chromium disables them.
- Extensions install from any site or store, not only the Chrome Web Store.
- Portable. All browser data lives in a `Data` folder next to
  `yatesium.exe`. The folder is created on first start.
- Its own identity: Yatesium name and logo, `yatesium.exe` and matching
  file names, `yatesium://` internal pages, and no Chrome or Chromium product
  name in the interface. See "Identity" below for what is left.
- No telemetry, no ad-tracking APIs and no Safe Browsing. See "Telemetry and
  ad tracking" below.
- Standard Chromium features otherwise, including H.264/AAC media support.

The pinned Chromium version is in `chromium_version.txt`.

## Status

The patches are checked against the pinned Chromium source: every patch
applies cleanly and the string rebrand keeps all translations
(`scripts/check_patches.py`). Patches 0001 to 0010 have been compiled, on
GitHub Actions and locally. A patch added after that is uncompiled until the
next build finishes.

## Building on GitHub Actions

1. Create a public GitHub repository and push this folder to it. The
   repository must be public. A build uses many hours of runner time and tens
   of GB of artifact storage, which is free only for public repositories.
2. Open the Actions tab, select the `build` workflow and choose "Run
   workflow".
3. Wait. The build is split into stages of up to 6 hours that run one after
   another. A full build takes several stages.
4. Download the `yatesium-portable` artifact from the finished run.

If a run fails after the Chromium checkout, it still saves its build folder
for 3 days. To continue from it after pushing a fix, run the workflow again
and enter the failed run's number (from its URL) in "resume_run_id". Changed
patches are swapped in and only the affected files are recompiled.

To publish a release instead, push a tag such as `v157.0.8103.79-1`. The same
workflow runs and attaches the zip to a GitHub release.

Optional: for Google sign-in and sync, create your own Google API keys and add
them as repository secrets named `GOOGLE_API_KEY`, `GOOGLE_DEFAULT_CLIENT_ID`
and `GOOGLE_DEFAULT_CLIENT_SECRET`. Without them the browser works but cannot
sign in to a Google account for sync.

## Using the portable build

Extract the zip anywhere and run `Yatesium\yatesium.exe`.

- Data is stored in `Yatesium\Data` instead of `%LOCALAPPDATA%`.
- To update, extract a newer zip over the folder. `Data` is kept.
- `--user-data-dir=<path>` still overrides the data location.
- If the folder is read-only, Yatesium falls back to the normal Chromium
  location under `%LOCALAPPDATA%\Yatesium`.

Limits:

- Chromium writes a few small values to the registry under
  `HKCU\Software\Yatesium`. No files are written outside the folder, apart
  from temporary files and your downloads.
- Saved passwords and cookies are encrypted with a key tied to the Windows
  user account. If you move the folder to another PC or account, bookmarks,
  history, settings and extensions come along, but saved passwords and
  logged-in sessions do not.
- There is no auto-update. Update by building and extracting a new zip.

## Where settings can come from

Yatesium is meant to be carried around, so a setting changes only when the
user changes it in the browser, an installed extension changes it, or the user
passes a command-line switch. The other sources Chromium has are removed:

- Policy. No policy source is created: not the Windows registry (Group
  Policy), not cloud management, not the `--policy` switch. Nothing can force
  or lock a setting, and `yatesium://policy` stays empty.
- Experiments. The browser never downloads an experiment configuration, and
  the experiment list built into Chromium is turned off
  (`disable_fieldtrial_testing_config` in `flags.gn`). Every feature keeps the
  default written in the source. `yatesium://flags` still works, because that
  is the user's own choice.
- Extensions added from outside. Other programs cannot add extensions through
  the registry, an `external_extensions.json` file or policy. Extensions are
  installed only from inside the browser.

Still present: the `initial_preferences` file read on a profile's first run,
and Chromium's prompts that offer to reset settings it thinks were tampered
with.

## Telemetry and ad tracking

Removed or turned off in the source:

- Usage statistics (UMA and UKM). Reporting cannot be turned on, including by
  the `--force-enable-metrics-reporting` switch.
- Crash report upload. Consent is always "no", and the consent lookup in the
  registry is gone.
- Domain Reliability, which reports connection errors for Google sites.
- Safe Browsing. It reads as off everywhere, so no URL, download or password
  checks are sent to Google and the blocklists are not downloaded. The
  setting in `yatesium://settings/security` has no effect. Yatesium does not
  warn about phishing or malware sites; a blocking extension can cover that.
- The Reporting API and Network Error Logging, which let a site ask the
  browser to send it error and crash reports. Off by default; to turn them
  back on, start with `--enable-features=Reporting,NetworkErrorLogging`.
- Link `ping` tracking (hyperlink auditing). Off by default.
- Ad APIs. Chromium 157 no longer contains Topics, Protected Audience or
  Attribution Reporting. The two switches left over for them are set to off.

Not changed, because they are features and not reporting:

- Third-party cookies follow the Chromium default and the user's setting.
- Requests to Google services that a feature needs: search suggestions for
  the chosen search engine, translate, online spellcheck, and the component
  updater.

## Identity

What is renamed:

- Program files: `yatesium.exe`, `yatesium.dll`, `yatesium_elf.dll`,
  `yatesium_wer.dll`, `yatesium_proxy.exe`, `yatesium_pwa_launcher.exe` and
  the `yatesium_*_percent.pak` resource files, including the names in their
  Windows file properties.
- Interface text in every language. "Chrome", "Google Chrome" and "Chromium"
  become "Yatesium". "Chrome Web Store" becomes "Web Store".
- The address bar shows `yatesium://settings` and accepts `yatesium://` URLs.

What still says Chrome or Chromium, and why:

- The user agent keeps its `Chrome/<version>` token, and `navigator` brand
  data keeps "Chromium". Many websites check these and break or serve a
  degraded page without them.
- Extensions use the `chrome.*` API and `chrome-extension://` URLs. Renaming
  either would break every existing extension.
- Internally the pages are still `chrome://`. The text inside some internal
  pages and the developer tools shows that form.
- The copyright line and the open-source credit on the About page, and the
  license list at `yatesium://credits`. Chromium's license requires its
  notices to ship with the browser.
- The Web Store website itself, which is Google's.
- Names of other products, such as ChromeOS and Chromecast.
- Internal identifiers that are not shown in the interface, such as window
  class names and some file names inside the `Data` folder.

## Installing extensions

- Web Store (Google's Chrome Web Store): works as in Chromium. Google removed
  all Manifest V2 extensions from the store in August 2026, so it only has
  Manifest V3.
- Any `.crx` link: opening it shows the normal install prompt. This covers
  other stores and direct downloads, for example:
  - Microsoft Edge Add-ons:
    `https://edge.microsoft.com/extensionwebstorebase/v1/crx?response=redirect&x=id%3D<EXTENSION_ID>%26installsource%3Dondemand%26uc`
  - Opera add-ons: `https://addons.opera.com/extensions/download/<name>/`
  - `.crx` files attached to GitHub releases.
- Unpacked folders and zips (how most Manifest V2 extensions are distributed
  now): open `yatesium://extensions`, turn on Developer mode and use "Load
  unpacked", or drag a `.crx` file onto the page.

Extensions keep updating from the `update_url` in their manifest.

Because any site can now offer an extension, read the install prompt before
accepting it.

## Updating to a new Chromium version

The `update` workflow runs weekly. It looks up the latest stable Chromium for
Windows, checks that the patches still apply, then commits the new version,
tags it and starts a build. If a patch no longer applies the run fails and
nothing changes. Fix the patch, then run it again.

To check by hand: `python scripts/check_patches.py <version>`.

Manifest V2 support depends on code that upstream still ships but no longer
uses. Upstream may delete more of it in later versions. When that happens,
`patches/0001-restore-manifest-v2.patch` has to grow to put it back.

## Building locally

On Windows 10/11 x64, double-click `Build Yatesium.cmd`. It downloads and runs
`local-build.ps1` from this repository, which:

1. Checks memory (16 GB or more) and disk space (about 110 GB free).
2. Installs what is missing: Git, Python, Visual Studio 2022 Build Tools with
   the C++ workload and ATL, and the Windows SDK version Chromium needs with
   Debugging Tools. Windows asks for administrator approval for the installs.
3. Clones this repository to `<drive>:\yatesium` and builds in `<drive>:\y`,
   on C: if it has room and otherwise on the drive with the most free space
   (`-Drive X:` picks another).
4. Writes the portable zip to `<drive>:\y\dist`.

The first run downloads about 40 GB of source and compiles for several hours.
The build runs as a hidden process and writes to `<drive>:\y\build-output.log`.
Closing the window does not stop it.

The window is a small controller. It reads one-word requests from
`<drive>:\y\control\request.txt` and writes its state to `status.txt` in the
same folder:

| Request | Effect |
| --- | --- |
| `build` | `git pull`, then start or resume the build |
| `stop` | Stop the running build |
| `quit` | Stop the build and close the controller |
| `copy` | Copy the newest zip in `dist` to the folder named in `control\share.txt` |

Any other text is ignored. `copy` creates the destination folder if needed and
writes the outcome, with the copy's SHA-256, to `control\copy-result.txt`.
Start the script with `-NoBuild` to open the controller without starting a
build. After a pull, changed patches are swapped in and
only the files they touch are recompiled.

## Layout

| Path | Purpose |
| --- | --- |
| `patches/` | Source patches, applied in name order |
| `branding/` | Logo files copied over the Chromium originals |
| `scripts/rebrand.py` | Renames the product in UI strings and translations |
| `patches/0006`, `0007` | Binary file names and the `yatesium://` address bar |
| `patches/0008`-`0010` | No policy, no remote experiments, no outside extension installs |
| `patches/0011`, `0012` | No telemetry, no Safe Browsing |
| `scripts/make_branding.py` | Regenerates the files in `branding/` |
| `scripts/check_patches.py` | Checks the changes against a Chromium version |
| `flags.gn` | Build arguments |
| `build.py`, `package.py` | Build and packaging |
| `.github/workflows/` | CI build and weekly update |

## License

The files in this repository are under the BSD 3-Clause license in `LICENSE`.
Chromium and its components have their own licenses, shown at
`yatesium://credits` in the browser.
