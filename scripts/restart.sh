#!/usr/bin/env bash
set -euo pipefail

BASE_DIR="$(cd "$(dirname "$0")/.." && pwd)"

"$BASE_DIR/scripts/stop.sh"
sleep 1
"$BASE_DIR/scripts/start.sh"
