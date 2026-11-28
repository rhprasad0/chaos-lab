#!/usr/bin/env bash
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
source "$here/reference.sh"
build="$here/build"
package="$build/package"
rm -rf "$build"
mkdir -p "$package"
fetch_reference "$build/reference"
cp -r "$build/reference/retail" "$build/reference/config.toml" "$here/etl.py" "$here/contract.py" "$here/contracts" "$package/"
sed -i 's/^sha256 = .*/sha256 = ""/' "$package/config.toml"
uv pip install -q --target "$package" --python-version 3.13 --python-platform x86_64-manylinux_2_34 --only-binary :all: \
  duckdb==1.5.6 pandas==3.0.6 numpy==2.5.4 python-calamine==0.9.0 "psycopg[binary]==3.3.2" pyyaml==6.0.4
{ git -C "$here" rev-parse HEAD 2>/dev/null || echo unknown; } >"$package/GIT_SHA"
curl -fsSL --retry 3 -o "$package/rds-ca-bundle.pem" https://truststore.pki.rds.amazonaws.com/global/global-bundle.pem
(cd "$package" && zip -qr "$build/etl.zip" .)
echo "$(du -sb "$package" | cut -f1) bytes unzipped, $(stat -c %s "$build/etl.zip") zipped"
