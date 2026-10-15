#!/usr/bin/env bash
set -euo pipefail
echo 'A database reset cannot be rolled back using an old application release. Choose and review a compatible version before rollback.' >&2
exit 2
