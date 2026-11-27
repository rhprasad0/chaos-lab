#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
out="$(realpath -m "${1:-build/chaos-lab-etl.zip}")"
stage="$(mktemp -d)"
trap 'rm -rf "$stage"' EXIT
uv pip install -q --target "$stage" --python-platform x86_64-manylinux2014 --python-version 3.13 \
  --only-binary :all: openpyxl pyarrow "psycopg[binary]"
cp -r pipelines/retail_etl "$stage/"
find "$stage" -name __pycache__ -prune -exec rm -rf {} +
mkdir -p "$(dirname "$out")"
rm -f "$out"
(cd "$stage" && python3 -m zipfile -c "$out" .)
