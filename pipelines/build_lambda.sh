#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

out=build/chaos-lab-etl-issue-17.zip
stage=$(mktemp -d)
trap 'rm -rf "$stage"' EXIT

grep -viE '^(boto3|pytest)' requirements.txt >"$stage/requirements.txt"
uv pip install --quiet --only-binary :all: --target "$stage/package" --python-version 3.13 \
  --python-platform x86_64-manylinux2014 --requirement "$stage/requirements.txt"
cp -r pipelines/retail_etl "$stage/package/"
find "$stage/package" -name __pycache__ -prune -exec rm -rf {} +

mkdir -p build
rm -f "$out"
(cd "$stage/package" && zip -qr "$OLDPWD/$out" .)
ls -l "$out"
