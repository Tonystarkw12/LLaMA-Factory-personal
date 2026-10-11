#!/usr/bin/env bash
# train_v3.sh — v3两阶段训练标准启动器（tmux内运行；本地swanlab，免网络依赖）
# 用法: tmux new-session -d -s v3train 'bash /home/tony/LLaMA-Factory/train_v3.sh'
set -uo pipefail

# ollama停卡防抢GPU
docker stop big-bear-ollama-nvidia 2>/dev/null

# mamba activate 在非交互shell失效 → env bin全路径；swanlab固定本地模式
export PATH=/home/tony/.local/share/mamba/envs/llamafactory/bin:$PATH
export SWANLAB_MODE=local   # 本地dashboard，免疫多rank init崩溃，图表照常生成

cd /home/tony/LLaMA-Factory
rm -f /tmp/v3_train.status
FORCE_TORCHRUN=1 llamafactory-cli train examples/train_lora/qwen3_6_27b_third_01_primer_sft.yaml > /tmp/v3a_train.log 2>&1 \
  && FORCE_TORCHRUN=1 llamafactory-cli train examples/train_lora/qwen3_6_27b_third_02_whole_sft.yaml > /tmp/v3b_train.log 2>&1
echo $? > /tmp/v3_train.status
