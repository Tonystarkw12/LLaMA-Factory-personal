#!/usr/bin/env bash
# v3 Phase C(+2ep→8总): 等B成功完成后自动接续; 失败60s自动重启; 状态写/tmp/v3c.status
while [ ! -f /tmp/v3_train.status ]; do sleep 60; done
if [ "$(cat /tmp/v3_train.status)" != "0" ]; then
  echo "B_failed" > /tmp/v3c.status
  exit 1
fi
docker stop big-bear-ollama-nvidia 2>/dev/null
export PATH=/home/tony/.local/share/mamba/envs/llamafactory/bin:$PATH
export SWANLAB_MODE=disabled
cd /home/tony/LLaMA-Factory
rm -f /tmp/v3c.status /tmp/v3c_train.log
FORCE_TORCHRUN=1 llamafactory-cli train examples/train_lora/qwen3_6_27b_third_03_extend_sft.yaml >> /tmp/v3c_train.log 2>&1
echo $? > /tmp/v3c.status
