# NMR Pulse Program Fine-tuning Guide

## 快速开始

```bash
cd /home/tony/LLaMA-Factory
./run_qwen3_6_27b_first_nmr.sh
```

或使用 nohup 后台运行：
```bash
nohup ./run_qwen3_6_27b_first_nmr.sh > run_qwen3_6_27b_first_nmr.log 2>&1 &
```

## 配置详情

| 参数 | 值 | 说明 |
|------|-----|------|
| **Model** | /mnt/d1/tony/qwen3.627b | Qwen3.5-27B |
| **Method** | QLoRA (4-bit) + ZeRO-3 | 量化微调 |
| **LoRA Rank** | 64 | 强表达能力 |
| **LoRA Alpha** | 128 | 2×rank |
| **GPUs** | 4× RTX 4090 (48GB) | ~25GB/GPU |
| **Dataset** | nmr_pulse_program | 4884 样本 |
| **Cutoff Length** | 4096 tokens | 完整覆盖 |
| **Batch Size** | 1×4×4 = 16 | per_device×grad_accum×GPUs |
| **Learning Rate** | 5e-5 | 稳定收敛 |
| **Epochs** | 10 | 充分训练 |
| **Total Steps** | 2900 | ~6 天 |
| **Speed** | ~180s/step | |

## 监控训练

**SwanLab:** https://swanlab.cn/@tonykw12/LLaMA-Factory

**GPU 状态:**
```bash
watch -n 10 nvidia-smi
```

**训练日志:**
```bash
tail -f saves/qwen3_6-27b-first/lora/sft/trainer_log.jsonl
```

## 输出位置

- **LoRA Adapter:** `saves/qwen3_6-27b-first/lora/sft/`
- **Checkpoints:** 每 200 步保存
- **Training Log:** `saves/qwen3_6-27b-first/lora/sft/trainer_log.jsonl`

## 训练完成后

**合并 LoRA:**
```bash
llamafactory-cli export \
  --model_name_or_path /mnt/d1/tony/qwen3.627b \
  --adapter_name_or_path saves/qwen3_6-27b-first/lora/sft \
  --template qwen3_5_nothink \
  --finetuning_type lora \
  --export_dir models/nmr-pulse-program-merged \
  --export_size 2 \
  --export_legacy_format false
```

**推理测试:**
```bash
llamafactory-cli chat \
  --model_name_or_path models/nmr-pulse-program-merged \
  --template qwen3_5_nothink
```

## 文件位置

- **启动脚本:** `/home/tony/LLaMA-Factory/run_qwen3_6_27b_first_nmr.sh`
- **训练配置:** `/home/tony/LLaMA-Factory/examples/train_lora/qwen3_6_27b_first_lora_sft.yaml`
- **数据集:** `/home/tony/LLaMA-Factory/data/nmr_pulse_program.jsonl`
- **数据集注册:** `/home/tony/LLaMA-Factory/data/dataset_info.json`

## 注意事项

1. **显存占用:** 每 GPU ~25GB，确保 Ollama 等进程不冲突
2. **训练时间:** ~6 天，建议用 nohup 或 tmux/screen
3. **断点续训:** 如中断，设置 `resume_from_checkpoint: saves/qwen3_6-27b-first/lora/sft/checkpoint-xxx`
4. **效果验证:** 训练后在测试集上评估 BLEU/ROUGE 分数
