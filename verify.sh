#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

if [[ -z "${LAB_PROJECT:-}" ]]; then
  LAB_PROJECT="verify-$$"
  export LAB_PROJECT
  trap 'docker compose -f lab/compose.yaml -p "$LAB_PROJECT" down -v --remove-orphans >/dev/null 2>&1' EXIT
  docker compose -f lab/compose.yaml -p "$LAB_PROJECT" up --detach --wait --quiet-pull
fi

bin/lab python3 -m pytest -p no:cacheprovider -q /workspace/chaos-lab/tests "$@"
