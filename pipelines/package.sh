#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

out="${1:-build/retail_etl.zip}"
stage="$(mktemp -d)"
trap 'rm -rf "$stage"' EXIT

grep -Ev '^(boto3|xlsxwriter)' requirements.txt >"$stage/requirements.txt"
uv pip install --quiet --target "$stage/package" --python-platform x86_64-manylinux_2_28 \
  --python-version 3.13 --only-binary :all: -r "$stage/requirements.txt"
cp -r pipelines/retail_etl "$stage/package/"
find "$stage/package" -name __pycache__ -prune -exec rm -rf {} +

mkdir -p "$(dirname "$out")"
rm -f "$out"
(cd "$stage/package" && python3 -m zipfile -c "$(cd - >/dev/null && realpath "$out")" .)
