"""Normalize Windows aapt2 ZIP separators before signing the generated APK.

AssetManager opens POSIX asset paths. Some Windows aapt2 builds emit backslashes
for nested assets, which leaves the app page working but every model returning 404.
This edits only unsigned build artifacts, never model bytes or source files.
"""
import copy
import sys
import zipfile
from pathlib import Path

source, target = map(Path, sys.argv[1:])
if source.resolve() == target.resolve():
    raise SystemExit('Use a distinct unsigned output path')
seen = set()
with zipfile.ZipFile(source) as before, zipfile.ZipFile(target, 'w') as after:
    for original in before.infolist():
        entry = copy.copy(original)
        entry.filename = original.filename.replace('\\', '/')
        if entry.filename in seen or '..' in entry.filename.split('/'):
            raise SystemExit('Unsafe or duplicate APK entry: ' + entry.filename)
        seen.add(entry.filename)
        after.writestr(entry, before.read(original))
print(f'Normalized {len(seen)} unsigned APK ZIP paths')
