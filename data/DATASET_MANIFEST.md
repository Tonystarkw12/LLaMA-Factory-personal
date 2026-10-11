# NMR 数据集集中管理清单

来源只复制不移动，原件未动。2026-09-09 整合，66 文件 / 516MB，已逐文件 cmp 校验一致。

## pp2label/ ← /home/tony/pp2label

| 目标 | 源 | 内容 |
|---|---|---|
| `pp2label/training/` | `training/*.jsonl` (7) | 核心 SFT/DPO：line, blocks_high_confidence, pulse_program_dpo_{5120,final,over_5120}, whole_multistyle_{train,eval} |
| `pp2label/fileslabel/` | `fileslabel/*.jsonl` | whole_extended, whole_high_confidence |
| `pp2label/fileslabel/comparison/` | 同名 | alpaca_high_quality (388K 版) |
| `pp2label/fileslabel/data/raw/` | 同名 (6) | 原始标签：labels, instruct, pulse_programs_sft, examples… |
| `pp2label/fileslabel/data/pipeline/` | 同名 (6) | alpaca 流水线各阶段：alpaca→filtered→cleaned→expanded→final→excluded |
| `pp2label/fileslabel/data/scored/` | 同名 (6) | 打分集：alpaca_scored{,_new}, alpaca_b_plus{,_new}, alpaca_high_quality (42M 版), llamafactory_train |
| `pp2label/lineslabel/instruction_dataset_v7/` | 同名 | training.jsonl + audit.jsonl（当前版 v7；v1–v6 留在源目录） |
| `pp2label/moduleslabel/` | 同名 | blocks_high_confidence + data/modules_pulprog |
| `pp2label/error_correct_examples/` | `error-correct/examples/*.jsonl` (8) | DPO 全套：final, full, full_v2, excluded, 原始版 + audit_sample |
| `pp2label/error_correct_examples/samepulse{,_full,_full_v2}/` | 同名 | pairs.jsonl + scores{,_v1}.jsonl |
| `pp2label/error_correct_examples/selected_pps/` | 同名 | batch_report.jsonl |

## batch_ai_comparison/ ← /home/tony/batch_AI_comparison/results/dataset

| 目标 | 内容 |
|---|---|
| `batch_ai_comparison/final_finetune_dataset/` | blocks_high_confidence + whole_extended + whole_high_confidence + metadata.json |
| `batch_ai_comparison/training_tiers/` | tier_{A,A_verified,B,C,exclude,quarantine,scores} + duplicates + summary |

## 未复制（有意跳过）

- `pp2label/moduleslabel/gpt56_labels_v3/`（3782 个单程序中间标签文件）
- `pp2label/lineslabel/output/instruction_dataset_v1–v6/`（历史版本，各 ~40M）
- `batch_AI_comparison/results/{alpaca,labels,judge,quality}/`（模型对比评测输出，非训练集）
- `.pp` 语料（full_corpus / selected_pps / samepulse 对）
- 代码、日志、pptx

## 注意

- `data/` 下原 `nmr_*.jsonl` 符号链接已于 2026-09-09 替换为实体文件（逐个 cmp 校验一致），文件名未变，`dataset_info.json` 引用不受影响。其中 `nmr_whole_extended.jsonl` 原链接已断（目标不在 training/），从 `pp2label/fileslabel/whole_extended.jsonl` 补齐。
- 新副本未注册进 `dataset_info.json`；训练引用前需登记（文件名 + `file_name` 相对路径即可）。
- `alpaca_high_quality.jsonl` 有两个不同版本：`fileslabel/comparison/`（388K）与 `fileslabel/data/scored/`（42M），按源路径分别保留。
