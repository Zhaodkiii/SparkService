#!/usr/bin/env bash
set -euo pipefail
curl -fsS --max-time 15 https://diary.dreamwhale.top/health/
curl -fsS --max-time 15 https://diary.dreamwhale.top/ >/dev/null
