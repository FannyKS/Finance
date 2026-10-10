#!/bin/zsh
# Runs the daily mutual fund report. Invoked by launchd on weekday evenings.
cd /Users/fannyng/src/Finance || exit 1
{
  echo "----- $(date '+%Y-%m-%d %H:%M:%S %Z') -----"
  /usr/bin/python3 fetch_report.py
} >> /Users/fannyng/src/Finance/data/run.log 2>&1
