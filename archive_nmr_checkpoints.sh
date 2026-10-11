#!/usr/bin/env bash
set -Eeuo pipefail

ROOT=/home/tony/LLaMA-Factory/saves/qwen3_6-27b-first/nmr
ARCHIVE="$ROOT/checkpoint-archive"
SSD_ARCHIVE=/mnt/d1/tony/qwen3_5-27b-nmr-checkpoints
LOG="$ROOT/checkpoint-archive.log"
STAGES=(01-line 02-block 03-whole 04-dpo)
mkdir -p "$ARCHIVE" "$SSD_ARCHIVE"

copy_to_ssd() {
  local stage=$1 name=$2 source target
  source="$ARCHIVE/$stage/$name"
  target="$SSD_ARCHIVE/$stage/$name"
  [[ -f "$target/.archive-complete" ]] && return 0
  mkdir -p "$SSD_ARCHIVE/$stage"
  rm -rf "$target.tmp"
  cp -a "$source" "$target.tmp"
  touch "$target.tmp/.archive-complete"
  rm -rf "$target"
  mv "$target.tmp" "$target"
  printf '[%(%F %T)T] copied to SSD %s/%s\n' -1 "$stage" "$name" | tee -a "$LOG"
}

archive_checkpoint() {
  local stage=$1 source=$2 name target shard_count
  name=$(basename "$source")
  target="$ARCHIVE/$stage/$name"
  if [[ -d "$target" ]]; then
    copy_to_ssd "$stage" "$name"
    return 0
  fi
  [[ -f "$source/trainer_state.json" && -f "$source/adapter_model.safetensors" ]] || return 0
  shard_count=$(find "$source" -type f -name '*optim_states.pt' | wc -l)
  ((shard_count == 4)) || return 0
  mkdir -p "$ARCHIVE/$stage"
  cp -al "$source" "$target.tmp"
  mv "$target.tmp" "$target"
  printf '[%(%F %T)T] archived %s/%s\n' -1 "$stage" "$name" | tee -a "$LOG"
  copy_to_ssd "$stage" "$name"
}

while :; do
  for stage in "${STAGES[@]}"; do
    [[ -d "$ROOT/$stage" ]] || continue
    for checkpoint in "$ROOT/$stage"/checkpoint-*; do
      [[ -d "$checkpoint" ]] || continue
      archive_checkpoint "$stage" "$checkpoint"
    done
  done

  if [[ -f "$ROOT/04-dpo/train_results.json" ]]; then
    printf '[%(%F %T)T] all stages complete; archiver exiting\n' -1 | tee -a "$LOG"
    exit 0
  fi
  sleep 30
done
