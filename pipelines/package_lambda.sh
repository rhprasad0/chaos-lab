#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
build="$root/dist/build"
rm -rf "$build" "$root/dist/etl-issue-19.zip"
mkdir -p "$build"
grep -vi '^boto3' "$root/requirements.txt" >"$root/dist/lambda-requirements.txt"
python3 -m pip install --quiet --target "$build" --platform manylinux2014_x86_64 \
  --python-version 3.13 --implementation cp --only-binary=:all: \
  -r "$root/dist/lambda-requirements.txt"
cp -r "$root/pipelines/retail_etl" "$build/retail_etl"
find "$build" -name __pycache__ -type d -prune -exec rm -rf {} +
(cd "$build" && python3 -m zipfile -c "$root/dist/etl-issue-19.zip" .)
