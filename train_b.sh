#!/usr/bin/env bash
# v3 Phase B: whole训练, 挂01-primer adapter; systemd宿主, 失败60s自动重启
docker stop big-bear-ollama-nvidia 2>/dev/null
export PATH=/home/tony/.local/share/mamba/envs/llamafactory/bin:$PATH
export SWANLAB_MODE=disabled
cd /home/tony/LLaMA-Factory
rm -f /tmp/v3_train.status /tmp/v3b_train.log
FORCE_TORCHRUN=1 llamafactory-cli train examples/train_lora/qwen3_6_27b_third_02_whole_sft.yaml >> /tmp/v3b_train.log 2>&1
echo $? > /tmp/v3_train.status
