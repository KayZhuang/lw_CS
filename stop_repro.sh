#!/usr/bin/env bash
# 停止 repro_like_dashboard.sh 启动的 tester 进程
set -euo pipefail

echo "[INFO] killing tester.py client/orch ..."
pkill -f "tester.py client" || true
pkill -f "tester.py orch" || true

echo "[INFO] remaining tester processes:"
pgrep -af "tester.py" || true


