#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$SCRIPT_DIR/_common.sh"
parse_options "$@"
require_prereqs
if [[ "$CHECK_ONLY" == 1 ]]; then echo "启动前检查通过。"; exit 0; fi
start_all
print_status
