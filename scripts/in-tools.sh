#!/usr/bin/env bash
# Run a command inside the tools image with the standard mounts.
#
#   scripts/in-tools.sh lio-bench data status
#   scripts/in-tools.sh pytest -q
#
# The data root is mounted read-only unless the command writes to it
# (`lio-bench data download|verify|convert`, `lio-bench inspect`, or LIO_DATA_RW=1).
# Settings come from the environment, overridden by .env if present: LIO_DATA_ROOT
# (required), LIO_RUNS_ROOT, WANDB_MODE/ENTITY/PROJECT/API_KEY (passed through when set).
set -euo pipefail

repo="$(cd "$(dirname "$0")/.." && pwd)"
image="${LIO_TOOLS_IMAGE:-lio-benchmark/tools:dev}"

set -a; [ -f "$repo/.env" ] && . "$repo/.env"; set +a

data_root="${LIO_DATA_ROOT:?set LIO_DATA_ROOT (see .env.example)}"
runs_root="${LIO_RUNS_ROOT:-$repo/runs}"
mkdir -p "$runs_root"

mode=ro
if [ "${LIO_DATA_RW:-0}" = "1" ]; then
  mode=rw
elif [ "${1:-}" = "lio-bench" ]; then
  case "${2:-} ${3:-}" in
    "data download"|"data verify"|"data convert"|"inspect "*) mode=rw ;;
  esac
fi

tty=(); [ -t 0 ] && [ -t 1 ] && tty=(-it)

exec docker run --rm "${tty[@]}" \
  --user "$(id -u):$(id -g)" \
  -v "$repo:/workspaces/lio-benchmark" \
  -v "$data_root:/data/hilti22:$mode" \
  -v "$runs_root:/runs" \
  -e WANDB_MODE="${WANDB_MODE:-offline}" -e WANDB_ENTITY -e WANDB_PROJECT -e WANDB_API_KEY \
  "$image" "$@"
