#!/usr/bin/env bash
set -euo pipefail

# Creates a Decky plugin zip following the template's distribution layout:
# <name>-v<version>.zip
#   <name>/
#     dist/index.js
#     plugin.json
#     package.json
#     main.py
#     README.md (optional)
#     LICENSE

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

NAME="$(node --input-type=module -e "import fs from 'fs'; console.log(JSON.parse(fs.readFileSync('package.json','utf8')).name)")"
VERSION="$(node --input-type=module -e "import fs from 'fs'; console.log(JSON.parse(fs.readFileSync('package.json','utf8')).version)")"

if [[ -z "$NAME" || -z "$VERSION" ]]; then
  echo "Failed to read name/version from package.json" >&2
  exit 1
fi

if [[ ! -f "dist/index.js" ]]; then
  echo "dist/index.js not found. Run the build first." >&2
  exit 1
fi

OUT_DIR="$ROOT_DIR/out"
TMP_DIR="$ROOT_DIR/.package-tmp"
PKG_DIR="$TMP_DIR/$NAME"
ZIP_NAME="$NAME-v$VERSION.zip"

rm -rf "$TMP_DIR"
mkdir -p "$PKG_DIR" "$OUT_DIR"

cp -R dist "$PKG_DIR/dist"
cp plugin.json package.json main.py LICENSE "$PKG_DIR/"

if [[ -f README.md ]]; then
  cp README.md "$PKG_DIR/"
fi

export PKG_DIR
export OUT_DIR
export ZIP_NAME

# Use python for consistent zipping across environments.
python3 - <<'PY'
import os
import zipfile

root = os.environ["PKG_DIR"]
out_dir = os.environ["OUT_DIR"]
zip_name = os.environ["ZIP_NAME"]

zip_path = os.path.join(out_dir, zip_name)

with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as z:
    for base, dirs, files in os.walk(root):
        for f in files:
            full = os.path.join(base, f)
            rel = os.path.relpath(full, os.path.dirname(root))
            z.write(full, rel)

print(zip_path)
PY

rm -rf "$TMP_DIR"
