#!/usr/bin/env python3
"""Rename the product from Chromium to Yatesium in UI strings.

Usage: rebrand.py <chromium src dir> [--name Yatesium]

Edits the product-name string files in place. Translation files (.xtb) are
keyed by a hash of the English text, so after the English text changes this
script recomputes the IDs with grit (from the source tree) and rewrites the
.xtb files. Translations are kept for every language.

The script is idempotent: a second run finds nothing to replace.
"""

import argparse
import re
import sys
from pathlib import Path

# (grd file that grit parses, files whose text is edited, glob of .xtb files)
STRING_SETS = (
    ('chrome/app/chromium_strings.grd',
     ('chrome/app/chromium_strings.grd',
      'chrome/app/settings_chromium_strings.grdp'),
     'chrome/app/resources/chromium_strings_*.xtb'),
    ('components/components_chromium_strings.grd',
     ('components/components_chromium_strings.grd',),
     'components/strings/components_chromium_strings_*.xtb'),
    ('extensions/strings/extensions_strings.grd',
     ('extensions/strings/extensions_chromium_strings.grdp',),
     'extensions/strings/extensions_strings_*.xtb'),
)

# "Chromium" as a product name. Left alone: "Chromium OS"/"ChromiumOS",
# "The Chromium Authors", "Chromium open source project" and compound
# identifiers such as "ChromiumUpdater".
PRODUCT_RE = re.compile(
    r'Chromium(?![A-Za-z])(?!\s?OS\b)(?!\sAuthors)(?!\sopen[ -]source)')


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


def replace_in_file(path, name):
    text = path.read_text(encoding='utf-8')
    new_text, count = PRODUCT_RE.subn(name, text)
    if count:
        path.write_bytes(new_text.encode('utf-8'))
    return count


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('src', type=Path)
    parser.add_argument('--name', default='Yatesium')
    args = parser.parse_args()
    src = args.src.resolve()
    if not re.fullmatch(r'[A-Za-z][A-Za-z0-9]*', args.name):
        sys.exit('The product name must be letters and digits only.')

    sys.path.insert(0, str(src / 'tools' / 'grit'))

    for grd, text_files, xtb_glob in STRING_SETS:
        before = message_ids(src, grd)
        replaced = sum(replace_in_file(src / f, args.name) for f in text_files)
        after = message_ids(src, grd)
        if len(before) != len(after):
            sys.exit('%s: message count changed during rebrand' % grd)
        id_map = {old: new for old, new in zip(before, after)
                  if old and new and old != new}
        if set(id_map.values()) & set(before):
            sys.exit('%s: a new message ID collides with an existing one' % grd)

        id_re = re.compile(r'(<translation id=")(\d+)(")')

        def swap_id(match):
            return match.group(1) + id_map.get(match.group(2),
                                               match.group(2)) + match.group(3)

        xtb_count = 0
        for xtb in sorted(src.glob(xtb_glob)):
            text = xtb.read_text(encoding='utf-8')
            new_text = PRODUCT_RE.sub(args.name, id_re.sub(swap_id, text))
            if new_text != text:
                xtb.write_bytes(new_text.encode('utf-8'))
                xtb_count += 1
        print('%s: %d replacements, %d message IDs changed, %d .xtb files '
              'updated' % (grd, replaced, len(id_map), xtb_count))


if __name__ == '__main__':
    main()
