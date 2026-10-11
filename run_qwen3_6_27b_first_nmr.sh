#!/usr/bin/env bash
set -Eeuo pipefail

ROOT=/home/tony/LLaMA-Factory
TRAINING="$ROOT/examples/train_lora"
ENV_BIN=/home/tony/.local/share/mamba/envs/llamafactory/bin
SESSION=${TMUX_SESSION:-qwen35-nmr-train}
LOG_DIR="$ROOT/saves/qwen3_6-27b-first/nmr/logs"

CONFIGS=(
  "$TRAINING/qwen3_6_27b_first_01_line_sft.yaml"
  "$TRAINING/qwen3_6_27b_first_02_block_sft.yaml"
  "$TRAINING/qwen3_6_27b_first_03_whole_sft.yaml"
  "$TRAINING/qwen3_6_27b_first_04_dpo.yaml"
)
OUTPUTS=(
  "$ROOT/saves/qwen3_6-27b-first/nmr/01-line"
  "$ROOT/saves/qwen3_6-27b-first/nmr/02-block"
  "$ROOT/saves/qwen3_6-27b-first/nmr/03-whole"
  "$ROOT/saves/qwen3_6-27b-first/nmr/04-dpo"
)

usage() {
  printf 'Usage: %s [--foreground] [--from 1-4] [--force]\n' "$0"
}

FOREGROUND=0
FROM=1
FORCE=0
while (($#)); do
  case "$1" in
    --foreground) FOREGROUND=1; shift ;;
    --from) FROM=${2:?missing stage}; shift 2 ;;
    --force) FORCE=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) printf 'Unknown argument: %s\n' "$1" >&2; usage; exit 2 ;;
  esac
done
[[ "$FROM" =~ ^[1-4]$ ]] || { printf '%s\n' '--from must be 1-4' >&2; exit 2; }

if ((FOREGROUND == 0)); then
  command -v tmux >/dev/null || { printf '%s\n' 'tmux not found' >&2; exit 1; }
  if tmux has-session -t "$SESSION" 2>/dev/null; then
    printf 'Session already exists: %s\nAttach: tmux attach -t %s\n' "$SESSION" "$SESSION"
    exit 1
  fi
  args=(--foreground --from "$FROM")
  ((FORCE)) && args+=(--force)
  tmux new-session -d -s "$SESSION" "$0 ${args[*]}"
  printf 'Started tmux session: %s\nAttach: tmux attach -t %s\nLogs: %s\n' "$SESSION" "$SESSION" "$LOG_DIR"
  exit 0
fi

export PATH="$ENV_BIN:$PATH"
export PYTHONPATH="$ROOT/src${PYTHONPATH:+:$PYTHONPATH}"
export CUDA_VISIBLE_DEVICES=${CUDA_VISIBLE_DEVICES:-0,1,2,3}
export FORCE_TORCHRUN=1
export NNODES=1
export NODE_RANK=0
export NPROC_PER_NODE=${NPROC_PER_NODE:-4}
export MASTER_ADDR=${MASTER_ADDR:-127.0.0.1}
export MASTER_PORT=${MASTER_PORT:-29501}
export TOKENIZERS_PARALLELISM=false

mkdir -p "$LOG_DIR"
cd "$ROOT"

ARCHIVER_SESSION=qwen35-nmr-checkpoints
ARCHIVER="$TRAINING/archive_nmr_checkpoints.sh"
if ! tmux has-session -t "$ARCHIVER_SESSION" 2>/dev/null; then
  [[ -x "$ARCHIVER" ]] || { printf 'Checkpoint archiver missing: %s\n' "$ARCHIVER" >&2; exit 1; }
  tmux new-session -d -s "$ARCHIVER_SESSION" "$ARCHIVER"
fi

[[ -x "$ENV_BIN/llamafactory-cli" ]] || { printf '%s\n' 'LLaMA-Factory environment missing' >&2; exit 1; }
[[ -d /mnt/d1/tony/qwen3.627b ]] || { printf '%s\n' 'Base model missing' >&2; exit 1; }

IFS=',' read -ra gpu_ids <<< "$CUDA_VISIBLE_DEVICES"
[[ ${#gpu_ids[@]} -eq "$NPROC_PER_NODE" ]] || {
  printf 'Expected %d GPUs, got CUDA_VISIBLE_DEVICES=%s\n' "$NPROC_PER_NODE" "$CUDA_VISIBLE_DEVICES" >&2
  exit 1
}
mapfile -t free_memory < <(nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits)
for gpu in "${gpu_ids[@]}"; do
  [[ "$gpu" =~ ^[0-9]+$ && -n "${free_memory[$gpu]:-}" ]] || {
    printf 'Invalid GPU id: %s\n' "$gpu" >&2
    exit 1
  }
  ((free_memory[gpu] >= 45000)) || {
    printf 'GPU %s has only %s MiB free; require 45000 MiB. Stop other GPU jobs first.\n' \
      "$gpu" "${free_memory[$gpu]}" >&2
    exit 1
  }
done

python -m json.tool data/dataset_info.json >/dev/null
for path in \
  data/nmr_line.jsonl \
  data/nmr_block_high_confidence.jsonl \
  data/nmr_whole_multistyle_train.jsonl \
  data/nmr_whole_multistyle_eval.jsonl \
  data/nmr_pulse_program_dpo_5120.jsonl; do
  [[ -r "$path" ]] || { printf 'Dataset missing: %s\n' "$path" >&2; exit 1; }
done

for i in "${!CONFIGS[@]}"; do
  stage=$((i + 1))
  ((stage < FROM)) && continue
  config=${CONFIGS[$i]}
  output=${OUTPUTS[$i]}
  log="$LOG_DIR/$(basename "${config%.yaml}").log"

  if [[ -f "$output/train_results.json" && $FORCE -eq 0 ]]; then
    printf '[stage %d/4] complete, skipping: %s\n' "$stage" "$output"
    continue
  fi

  if ((stage > 1)); then
    previous=${OUTPUTS[$((i - 1))]}
    [[ -f "$previous/adapter_config.json" ]] || {
      printf 'Previous stage adapter missing: %s\n' "$previous" >&2
      exit 1
    }
  fi

  if ((FORCE)) && [[ -d "$output" ]]; then
    printf 'Refusing to delete existing output automatically: %s\n' "$output" >&2
    printf '%s\n' 'Move/remove it manually, then rerun --force.' >&2
    exit 1
  fi

  printf '\n[%(%F %T)T] stage %d/4 starting: %s\n' -1 "$stage" "$config" | tee -a "$log"
  llamafactory-cli train "$config" 2>&1 | tee -a "$log"
  [[ -f "$output/train_results.json" ]] || {
    printf 'Stage %d exited without train_results.json\n' "$stage" >&2
    exit 1
  }
  printf '[%(%F %T)T] stage %d/4 complete\n' -1 "$stage" | tee -a "$log"
done

printf '\nAll requested stages complete. Final adapter: %s\n' "${OUTPUTS[3]}"
