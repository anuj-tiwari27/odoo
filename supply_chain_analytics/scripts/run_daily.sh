#!/usr/bin/env bash
# Daily scheduled run: pull Acumatica GIs, refresh the warehouse, compute
# coverage + ETAs, and print the exception digest.
#
# cron example (06:00 every weekday):
#   0 6 * * 1-5  /path/to/supply_chain_analytics/scripts/run_daily.sh >> /var/log/sca.log 2>&1
#
# Windows Task Scheduler: point an action at python with the same args.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$HERE"

# Secrets must be present in the environment.
: "${ACUMATICA_USER:?set ACUMATICA_USER}"
: "${ACUMATICA_PASSWORD:?set ACUMATICA_PASSWORD}"

CONFIG="${SCA_CONFIG:-config.yaml}"

python -m sca.cli -c "$CONFIG" run
