#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

dirs=()
for dir in tests pipelines/tests; do
  [[ -d "$dir" ]] && dirs+=("$dir")
done
if ((${#dirs[@]} == 0)); then
  echo "verify: no tests yet"
  exit 0
fi
python3 -m pytest -p no:cacheprovider -q "${dirs[@]}"
