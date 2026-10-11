#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="${PROJECT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
MAMBA_PROFILE="${MAMBA_PROFILE:-${HOME}/.local/share/mamba/etc/profile.d/mamba.sh}"
CONDA_PROFILE="${CONDA_PROFILE:-${HOME}/pymol/etc/profile.d/conda.sh}"
ENV_NAME="${ENV_NAME:-llamafactory}"
API_HOST="${API_HOST:-0.0.0.0}"
API_PORT="${API_PORT:-8181}"
API_MODEL_NAME="${API_MODEL_NAME:-qwen3_6_27b_first_sft}"
API_CONFIG="${API_CONFIG:-${PROJECT_DIR}/examples/inference/qwen3_6_27b_first_lora_api.yaml}"
LOG_DIR="${LOG_DIR:-${PROJECT_DIR}/logs}"
LOG_FILE="${LOG_FILE:-${LOG_DIR}/qwen3_6_27b_api.log}"
PID_FILE="${PID_FILE:-${LOG_DIR}/qwen3_6_27b_api.pid}"

mkdir -p "${LOG_DIR}"

if [[ -f "${PID_FILE}" ]]; then
  old_pid="$(<"${PID_FILE}")"
  if [[ -n "${old_pid}" ]] && kill -0 "${old_pid}" 2>/dev/null; then
    echo "API already running: pid=${old_pid}"
    echo "Log: ${LOG_FILE}"
    exit 0
  fi
  rm -f "${PID_FILE}"
fi

if [[ -f "${MAMBA_PROFILE}" ]]; then
  # shellcheck disable=SC1090
  source "${MAMBA_PROFILE}"
elif [[ -f "${CONDA_PROFILE}" ]]; then
  # shellcheck disable=SC1090
  source "${CONDA_PROFILE}"
else
  echo "Cannot find mamba/conda profile." >&2
  exit 1
fi

mamba activate "${ENV_NAME}"
cd "${PROJECT_DIR}"

export API_HOST API_PORT API_MODEL_NAME
nohup llamafactory-cli api "${API_CONFIG}" >"${LOG_FILE}" 2>&1 &
pid="$!"
echo "${pid}" >"${PID_FILE}"

echo "Started qwen3_6_27b API"
echo "PID: ${pid}"
echo "URL: http://${API_HOST}:${API_PORT}"
echo "Models: http://127.0.0.1:${API_PORT}/v1/models"
echo "Log: ${LOG_FILE}"
