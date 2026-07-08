#!/usr/bin/env bash
# Convenience wrapper. Edit UA to your own email, then: ./run_screen.sh
set -e
UA="Moat personal screener you@example.com"
python3 -m moat.screen --tickers watchlist.txt --stooq --user-agent "$UA" --out results.json
echo "Wrote results.json"
