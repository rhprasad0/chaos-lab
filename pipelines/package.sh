#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

build=build/lambda
rm -rf build
mkdir -p "$build"
grep -v '^boto3' requirements.txt >build/requirements.txt
python3 -m pip install --quiet --target "$build" --platform manylinux2014_x86_64 \
  --implementation cp --python-version 3.13 --only-binary=:all: -r build/requirements.txt
cp -r pipelines/retail_etl "$build/"
find "$build" -name __pycache__ -prune -exec rm -rf {} +
(cd "$build" && zip -qr ../chaos-lab-etl.zip .)
echo "build/chaos-lab-etl.zip"
