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
4. Download the zip from the repository's Releases page. A build that
   finishes publishes it there, as `v<Chromium version>-<revision>`. The same
   zip is also the `yatesium-portable` artifact of the run.

If a run fails after the Chromium checkout, it still saves its build folder
for 3 days. To continue from it after pushing a fix, run the workflow again
and enter the failed run's number (from its URL) in "resume_run_id". Changed
patches are swapped in and only the affected files are recompiled.

The revision is the number in `revision.txt`. Raise it when the patches
change, so the new build gets its own release. Building the same revision
again replaces the zip of that release.

To publish the zip of an earlier run without building again, run the
`publish` workflow and enter that run's number.

Google sign-in and sync need your own Google API credentials. They are entered
in the browser, not built in. See "Google sign-in and sync" below.

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
- It updates itself from this repository's releases. See "Updates" below.

## Importing from another browser

`yatesium://import` lists what it finds in other Chromium-based browsers of
the same Windows account (Brave, Chrome, Edge, Vivaldi, Chromium) and imports
what you tick. On the first run the page opens by itself if one of those
browsers has data on the computer. Open it again at any time to import more.

Each browser profile is shown with checkboxes and an "Import selected"
button:

- Bookmarks. Added to a new folder "Imported from ..." on the bookmark bar.
- Web apps (PWAs). Installed in Yatesium with their name, icon, address and
  window setting. The other browser's Start menu and desktop shortcuts for
  an imported app are removed and Yatesium creates its own. Taskbar pins are
  not changed. Sign-ins and stored data of the app stay in the other browser.
- Extensions. Not ticked to begin with; choose the ones you want. The files
  are copied from the other browser, so Manifest V2 extensions that the store
  no longer offers come along. An extension keeps its id and permissions.
  Its settings are not copied.

Things already present in Yatesium are left out of the list. Nothing is read
from another browser until the page is opened, and nothing is imported
without the button. The other browser can stay open during the import.

A web app window does not show the "Uninstall" button that Chromium puts in
the title bar on the first start of a new app. "Uninstall" is in the
window's three-dot menu.

After an import, open `yatesium://apps` to see the web apps that are now
installed. Each app there can be started, and its right-click menu creates or
removes its desktop and Start menu shortcuts. Imported extensions are listed
on `yatesium://extensions`.

## Settings file (backup and restore)

`yatesium://import` also saves this browser's setup to one file and reads it
back.

"Export to a settings file" asks where to save, shows a progress bar while it
works, and writes a zip that holds:

- bookmarks
- browser settings
- the search engines you added
- installed web apps, with their icons
- extensions, with the data they stored (their settings, filter lists,
  scripts and databases)

It does not hold history, saved passwords, cookies or sign-ins, or the
entries of `yatesium://flags`. Data that an extension keeps in
the page-style "localStorage" is not included either.

"Import from a settings file" asks for the file, shows what it holds, and
offers two ways to use it:

- "Replace everything and relaunch". The browser restarts and then matches
  the file in those areas. What was there before is overwritten, including
  bookmarks, search engines, web apps and extensions that the file does not
  have. The search engine that is currently the default is never removed.
  History, saved passwords and sign-ins are kept.
- "Add to this browser". A list with checkboxes, like the one for other
  browsers. Ticked bookmarks, web apps and extensions are added to what is
  already here. "Settings" applies the file's settings over the current ones;
  only the settings that Chromium would sync between installations are taken.
  "Search engines" adds the ones from the file; one whose keyword is already
  in use is skipped.
  An extension brings its stored data along if this browser has none for it.

Notes:

- The file is a plain zip and is not encrypted. It contains the list of your
  bookmarks and extensions.
- The browser is running while it exports. A file it is writing at that
  moment can be missed; export again if something looks incomplete.
- After "Replace everything" on another computer, web apps are installed but
  their desktop and Start menu shortcuts may be missing. Create them from
  `yatesium://apps`.

## Google sign-in and sync

Google only lets a browser sign in and sync with credentials that belong to
that browser's maker. Yatesium ships without any, so sign-in is off until you
enter your own on the flags page. Nothing needs to be rebuilt.

Get the credentials (once, free):

1. With the Google account you will use, subscribe to the
   `chromium-dev@chromium.org` group (email delivery can be turned off).
   Google shows the Chrome APIs only to members of that group.
2. Join `google-browser-signin-testaccounts@chromium.org` with every Google
   account that should be able to sign in to Yatesium. Without this, Google
   refuses to hand out sign-in tokens to a self-made browser.
3. In the Google Cloud console, create a project.
4. Under "APIs and Services", "Library", enable the Chrome Sync API. The
   Chromium instructions list more APIs that other features use.
5. Under "Credentials", create an "OAuth client ID" of type "Desktop app"
   (set up the consent screen if asked). Note the client ID and the client
   secret.
6. Under "Credentials", create an "API key". Note it.

Google's own instructions, which may be newer than this list:
https://www.chromium.org/developers/how-tos/api-keys/

Enter them in Yatesium:

1. Open `yatesium://flags` and search for "Google".
2. Fill in the three text fields:
   - "Google API key" (`yatesium://flags/#google-api-key`)
   - "Google OAuth client ID" (`yatesium://flags/#google-oauth-client-id`)
   - "Google OAuth client secret"
     (`yatesium://flags/#google-oauth-client-secret`)
3. Relaunch. The sign-in and sync option in the profile menu now uses your
   credentials.

To turn it off again, clear the three fields and relaunch.

Things to know:

- The values are stored encrypted in `Data\User Data\Local State`, using
  Windows data protection (DPAPI). Only your Windows account on this computer
  can decrypt them. If the folder moves to another computer or account, the
  three fields come up empty and have to be entered again.
- The values never appear on a command line: not the browser's own, not on
  `yatesium://version`, and not in the processes the browser starts.
- The client secret is not shown again once it is stored. Its field reads
  "already entered". Type a new secret to replace it, or clear the field to
  remove it. The API key and client ID stay readable on the flags page.
- Google's terms say the credentials are for your own use. Do not put them
  into a build you hand to others. The build can still take them from
  `GOOGLE_API_KEY`, `GOOGLE_DEFAULT_CLIENT_ID` and
  `GOOGLE_DEFAULT_CLIENT_SECRET` (environment or repository secrets), but
  this repository's releases are public, so do not set those here.
- With a client ID set, signing in to a Google website also tries to sign the
  browser in.

## Updates

On start the browser runs `yatesium_update.exe --auto` from its own folder,
with no window. The updater does this:

1. At most once a day, downloads `latest.txt` from the latest release of this
   repository. The file holds the release's version and the SHA-256 of its
   zip. This is the only request made when there is nothing new.
2. If the release is newer than `version.txt`, downloads the zip to
   `Data\Update` and checks it against that SHA-256. A zip that does not
   match is discarded.
3. Waits until every `yatesium.exe` from this folder has closed, then moves
   the old program files out and the new ones in. If that fails part way,
   the old files are moved back. `Data` is not touched.

The next start runs the new version. `Data\Update\update.log` records what
happened.

- To check right away, open the About page (`yatesium://settings/help`, or
  "Help", "About Yatesium" in the menu). It checks as soon as it opens, shows
  "Checking for updates", the download progress, and then either "Yatesium is
  up to date" or a "Relaunch" button. "Relaunch" closes the browser, installs
  the update and starts the browser again with its tabs.
- The About page also shows the Yatesium build next to the Chromium version:
  version with revision, the commit it was built from, and the build date.
- Running `yatesium_update.exe` by hand does the same check and reports in a
  console window.
- To turn automatic updates off, create an empty file `Data\no-update.txt`.
  The About page still checks when you open it. Deleting
  `yatesium_update.exe` turns both off.

The updater is a small C++ program built with the browser
(`chrome/yatesium_update` in patch 0013). It uses the Windows API and the zip
reader from zlib, and nothing else.

The update is trusted because it comes from this repository over HTTPS and
matches the published hash. The zip is not code-signed.

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
- The update check: one small download a day from this repository's releases. See "Updates".
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
| `patches/0013` | The updater program, and the browser change that starts it |
| `patches/0014` | Flags for the user's own Google API credentials |
| `patches/0015` | The import page: other browsers, and export to and import from a settings file |
| `patches/0016` | No "Uninstall" button in the title bar of web app windows |
| `patches/0017` | Update check and build information on the About page |
| `scripts/make_branding.py` | Regenerates the files in `branding/` |
| `scripts/check_patches.py` | Checks the changes against a Chromium version |
| `flags.gn` | Build arguments |
| `build.py`, `package.py` | Build and packaging |
| `.github/workflows/` | CI build and weekly update |

## License

The files in this repository are under the BSD 3-Clause license in `LICENSE`.
Chromium and its components have their own licenses, shown at
`yatesium://credits` in the browser.
