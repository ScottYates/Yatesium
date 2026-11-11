#!/usr/bin/env python3
"""Renames the product to Yatesium in UI strings.

Usage: rebrand.py <chromium src dir> [--name Yatesium]

Edits the string files (.grd, .grdp) in place. Translation files (.xtb) are
keyed by a hash of the English text, so after the English text changes this
script recomputes the IDs with grit (from the source tree) and rewrites the
.xtb files. Translations are kept for every language.

Left unchanged on purpose:
  - the copyright and open-source credit lines on the About page,
  - names of other products (ChromeOS, Chromebook, Chromecast, ChromeVox,
    Chrome Remote Desktop, Chrome Enterprise, Chrome for Testing).

The script is idempotent: a second run finds nothing to replace.
"""

import argparse
import re
import sys
from pathlib import Path

# (grd file, glob of its .xtb files). Files pulled in with <part> are found
# automatically.
STRING_SETS = (
    ('chrome/app/chromium_strings.grd',
     'chrome/app/resources/chromium_strings_*.xtb'),
    ('chrome/app/generated_resources.grd',
     'chrome/app/resources/generated_resources_*.xtb'),
    ('components/components_chromium_strings.grd',
     'components/strings/components_chromium_strings_*.xtb'),
    ('components/components_strings.grd',
     'components/strings/components_strings_*.xtb'),
    ('extensions/strings/extensions_strings.grd',
     'extensions/strings/extensions_strings_*.xtb'),
)

# The store keeps working but is no longer named after another browser.
STORE_RE = re.compile(r'(?:Google )?Chrome Web Store')

# "Chrome", "Google Chrome" or "Chromium" used as the name of this browser.
PRODUCT_RE = re.compile(
    r'(?:Google )?Chrom(?:e|ium)'
    r'(?![A-Za-z])'                        # ChromeOS, Chromebook, ChromeVox...
    r'(?!\s?OS\b)'                         # Chrome OS, Chromium OS
    r'(?!\sAuthors)'                       # copyright holder
    r'(?!\sopen[ -]source)'                # credit line
    r'(?!<ph name="END_LINK_CHROMIUM")'    # credit link to the project
    r'(?!\s(?:Remote Desktop|Enterprise|for Testing))')

PART_RE = re.compile(r'<part\s+file="([^"]+)"')
ID_RE = re.compile(r'(<translation id=")(\d+)(")')


class _AnyDefines(dict):
    """A grit defines dict in which every variable exists and is False."""

    def __contains__(self, key):
        return True

    def __missing__(self, key):
        return False

    def get(self, key, default=None):
        return False


def message_ids(src, grd):
    """Returns the translation ID of every <message> in |grd|, in file order."""
    from grit import grd_reader
    # Message IDs are assigned while parsing and do not depend on <if>
    # conditions, so validation (which needs every build-time grit variable
    # defined) is skipped and unknown variables read as False.
    root = grd_reader.Parse(str(src / grd), debug=False,
                            defines=_AnyDefines(),
                            skip_validation_checks=True)
    ids = []
    for node in root.Preorder():
        if node.name != 'message':
            continue
        cliques = node.GetCliques()
        ids.append(cliques[0].GetId() if cliques else None)
    return ids


def text_files(src, grd):
    """Returns |grd| and every file it includes with <part>, recursively."""
    found = []
    pending = [src / grd]
    while pending:
        path = pending.pop()
        if path in found:
            continue
        found.append(path)
        for part in PART_RE.findall(path.read_text(encoding='utf-8')):
            pending.append((path.parent / part).resolve())
    return found


def rename(text, name):
    return PRODUCT_RE.sub(name, STORE_RE.sub('Web Store', text))


def replace_in_file(path, name):
    text = path.read_text(encoding='utf-8')
    new_text = rename(text, name)
    if new_text == text:
        return 0
    path.write_bytes(new_text.encode('utf-8'))
    return len(STORE_RE.findall(text)) + len(
        PRODUCT_RE.findall(STORE_RE.sub('Web Store', text)))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('src', type=Path)
    parser.add_argument('--name', default='Yatesium')
    args = parser.parse_args()
    src = args.src.resolve()
    if not re.fullmatch(r'[A-Za-z][A-Za-z0-9]*', args.name):
        sys.exit('The product name must be letters and digits only.')

    sys.path.insert(0, str(src / 'tools' / 'grit'))

    for grd, xtb_glob in STRING_SETS:
        before = message_ids(src, grd)
        replaced = sum(replace_in_file(path, args.name)
                       for path in text_files(src, grd))
        after = message_ids(src, grd)
        if len(before) != len(after):
            sys.exit('%s: message count changed during rebrand' % grd)

        # Old ID -> new ID for messages whose text changed. If the new text
        # is identical to another message, that message's translation already
        # applies and the old entry is left alone.
        taken = set(before)
        id_map = {}
        for old, new in zip(before, after):
            if old and new and old != new and new not in taken:
                id_map[old] = new
                taken.add(new)

        def swap_id(match):
            return match.group(1) + id_map.get(match.group(2),
                                               match.group(2)) + match.group(3)

        xtb_count = 0
        for xtb in sorted(src.glob(xtb_glob)):
            text = xtb.read_text(encoding='utf-8')
            new_text = rename(ID_RE.sub(swap_id, text), args.name)
            if new_text != text:
                xtb.write_bytes(new_text.encode('utf-8'))
                xtb_count += 1
        print('%s: %d replacements, %d message IDs changed, %d .xtb files '
              'updated' % (grd, replaced, len(id_map), xtb_count))


if __name__ == '__main__':
    main()
