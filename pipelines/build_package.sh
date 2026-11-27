#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
out=build/package
rm -rf build
mkdir -p "$out"
python3 -m pip install --quiet --target "$out" --platform manylinux2014_x86_64 --python-version 3.13 \
  --implementation cp --only-binary=:all: openpyxl pyarrow "psycopg[binary]"
cp -r pipelines/retail_etl "$out/"
rm -rf "$out/pyarrow/include" "$out/pyarrow/tests"
find "$out/retail_etl" -name __pycache__ -prune -exec rm -rf {} +
(cd "$out" && python3 -m zipfile -c ../retail_etl.zip *)
