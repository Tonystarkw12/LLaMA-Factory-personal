#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="${PROJECT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
API_PORT="${API_PORT:-8181}"
LOG_DIR="${LOG_DIR:-${PROJECT_DIR}/logs}"
PID_FILE="${PID_FILE:-${LOG_DIR}/qwen3_6_27b_api.pid}"

stopped=0

stop_pid() {
  local pid="$1"
  if [[ -z "${pid}" ]]; then
    return 0
  fi
  if ! kill -0 "${pid}" 2>/dev/null; then
    return 0
  fi

  echo "Stopping pid=${pid}"
  kill "${pid}" 2>/dev/null || true

  for _ in {1..20}; do
    if ! kill -0 "${pid}" 2>/dev/null; then
      stopped=1
      return 0
    fi
    sleep 0.5
  done

  echo "Force killing pid=${pid}"
  kill -9 "${pid}" 2>/dev/null || true
  stopped=1
}

if [[ -f "${PID_FILE}" ]]; then
  stop_pid "$(<"${PID_FILE}")"
  rm -f "${PID_FILE}"
fi

while IFS= read -r pid; do
  stop_pid "${pid}"
done < <(pgrep -f "llamafactory-cli api .*qwen3_6_27b_first_lora_api.yaml" || true)

while IFS= read -r pid; do
  stop_pid "${pid}"
done < <(pgrep -f "API_PORT=${API_PORT}.*llamafactory-cli api" || true)

if command -v fuser >/dev/null 2>&1; then
  while IFS= read -r pid; do
    stop_pid "${pid}"
  done < <(fuser "${API_PORT}/tcp" 2>/dev/null | tr ' ' '\n' | sed '/^$/d' || true)
fi

if [[ "${stopped}" -eq 0 ]]; then
  echo "No matching qwen3_6_27b API process found."
else
  echo "Stopped qwen3_6_27b API. GPU memory should release after process exit."
fi
