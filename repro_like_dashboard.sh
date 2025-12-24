#!/usr/bin/env bash
# 复现类似监控图：client/orch 的 Recv_Q/Send_Q 台阶型堆积
#
# 用法（在发压测的机器上跑）：
#   chmod +x repro_like_dashboard.sh
#   ./repro_like_dashboard.sh
#
# 说明：
# - 会启动多条 orch 订阅连接（:55559 legacy）+ 多条 client 连接疯狂发消息（:15623 legacy）
# - 通过“分阶段启动”制造平台/台阶
# - 需要确保：client-id 不重复，否则 CommServer 会 override 连接，堆不出多条曲线
#
# 停止：运行 stop_repro.sh 或手动 pkill -f "tester.py (client|orch)"

set -euo pipefail

###############################################################################
# 需要按你的环境改的参数
###############################################################################
COMM_SERVER_IP="${COMM_SERVER_IP:-192.168.0.143}"
CLIENT_PORT="${CLIENT_PORT:-15623}"   # CommServer client legacy port
ORCH_PORT="${ORCH_PORT:-55559}"       # CommServer orch legacy port

# client 侧消息参数（按需改成 401/635 等）
CUSTOMER_ID="${CUSTOMER_ID:-120}"
CLIENT_TYPE="${CLIENT_TYPE:-401}"
CLIENT_LEN="${CLIENT_LEN:-200}"
CLIENT_GAP="${CLIENT_GAP:-0}"         # 0=不sleep，最猛

# 并发规模（按机器承载能力调整）
ORCH_TOTAL="${ORCH_TOTAL:-50}"        # orch 连接总数
CLIENT_TOTAL="${CLIENT_TOTAL:-200}"   # client 连接总数

# 分阶段启动：每阶段启动多少个连接，每阶段间隔（秒）
ORCH_PER_PHASE="${ORCH_PER_PHASE:-10}"
CLIENT_PER_PHASE="${CLIENT_PER_PHASE:-50}"
PHASE_INTERVAL_SEC="${PHASE_INTERVAL_SEC:-60}"

# id 起始值（避免与线上真实 id 冲突，且避免重复）
ORCH_ID_BASE="${ORCH_ID_BASE:-5000}"
CLIENT_ID_BASE="${CLIENT_ID_BASE:-100000}"

# tester.py 所在目录（本机路径）
TEST_DIR="${TEST_DIR:-/lw_client/lw_CS/lw_communication/server/test}"

# 日志目录
LOG_DIR="${LOG_DIR:-/tmp/lw_repro}"

###############################################################################

mkdir -p "$LOG_DIR"
cd "$TEST_DIR"

echo "[INFO] CommServer=${COMM_SERVER_IP} client_port=${CLIENT_PORT} orch_port=${ORCH_PORT}"
echo "[INFO] ORCH_TOTAL=${ORCH_TOTAL} CLIENT_TOTAL=${CLIENT_TOTAL}"
echo "[INFO] phases: ORCH_PER_PHASE=${ORCH_PER_PHASE} CLIENT_PER_PHASE=${CLIENT_PER_PHASE} interval=${PHASE_INTERVAL_SEC}s"
echo "[INFO] logs: ${LOG_DIR}"

start_orch_one() {
  local idx="$1"
  local orch_id=$((ORCH_ID_BASE + idx))
  # NOTE: range 不用写 401-401（有些环境会拒绝 from==to）；用 0-1023 覆盖 401
  nohup ./tester.py orch "${COMM_SERVER_IP}:${ORCH_PORT}" \
    --legacy \
    --orch-id="${orch_id}" \
    --range 0 1023 0 0 0 0 \
    >"${LOG_DIR}/orch_${orch_id}.log" 2>&1 &
}

start_client_one() {
  local idx="$1"
  local client_id=$((CLIENT_ID_BASE + idx))
  nohup ./tester.py client "${COMM_SERVER_IP}:${CLIENT_PORT}" \
    --legacy \
    --customer-id="${CUSTOMER_ID}" \
    --client-id="${client_id}" \
    --type="${CLIENT_TYPE}" \
    --len="${CLIENT_LEN}" \
    --count=-1 \
    --gap="${CLIENT_GAP}" \
    >"${LOG_DIR}/client_${client_id}.log" 2>&1 &
}

echo "[INFO] Phase 1: start orch connections..."
orch_started=0
while [ "$orch_started" -lt "$ORCH_TOTAL" ]; do
  batch=0
  while [ "$batch" -lt "$ORCH_PER_PHASE" ] && [ "$orch_started" -lt "$ORCH_TOTAL" ]; do
    start_orch_one "$orch_started"
    orch_started=$((orch_started + 1))
    batch=$((batch + 1))
  done
  echo "[INFO] orch started: ${orch_started}/${ORCH_TOTAL}; sleep ${PHASE_INTERVAL_SEC}s"
  sleep "${PHASE_INTERVAL_SEC}"
done

echo "[INFO] Phase 2: start client connections (traffic generators)..."
client_started=0
while [ "$client_started" -lt "$CLIENT_TOTAL" ]; do
  batch=0
  while [ "$batch" -lt "$CLIENT_PER_PHASE" ] && [ "$client_started" -lt "$CLIENT_TOTAL" ]; do
    start_client_one "$client_started"
    client_started=$((client_started + 1))
    batch=$((batch + 1))
  done
  echo "[INFO] client started: ${client_started}/${CLIENT_TOTAL}; sleep ${PHASE_INTERVAL_SEC}s"
  sleep "${PHASE_INTERVAL_SEC}"
done

echo "[INFO] DONE. Processes are running in background."
echo "[INFO] To stop: ./stop_repro.sh (in the same directory) or pkill -f \"tester.py (client|orch)\""
echo "[INFO] To observe on CommServer host:"
echo "  watch -n 1 \"ss -tn | egrep ':${CLIENT_PORT}|:${ORCH_PORT}' | grep ESTAB | head -50\""
echo "  watch -n 1 \"/bin/appex/CommServer stats | egrep 'Client\\.Send\\.MsgBytes|Client\\.Recv\\.MsgBytes|Subscriber\\.Send\\.MsgBytes|Subscriber\\.Recv\\.MsgBytes|QueueFullDiscards|ConnCnt'\""


