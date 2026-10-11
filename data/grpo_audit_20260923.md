# GRPO 数据检查记录

检查对象：`/mnt/d1/tony/outputs/grpo_data`。所有 JSONL 均只读检查，未修改。

## 文件结构

| 文件 | 实际行数 | 结果 |
| --- | ---: | --- |
| `grpo_train.jsonl` | 10,543 | 字段可解析；静态分析字段完整 |
| `grpo_val.jsonl` | 291 | 字段可解析；静态分析字段完整 |
| `gate8_materials.jsonl` | 1,801 | DPO 材料 |
| `gate9_materials.jsonl` | 2,000 | DPO/材料扩展 |
| `gate10_singles_test.jsonl` | 300 | 测试材料 |
| `gate10_doubles_test.jsonl` | 300 | 测试材料 |
| `gate11_singles_train.jsonl` | 800 | DPO 训练材料 |
| `rm_run3_train.jsonl` | 4,601 | reward-model 训练材料 |

所有文件 JSON 解析通过，ID 无重复，必需字段存在。`grpo_train` 中 2,471 条没有额外 `input`，但 instruction 完整，这是允许的空上下文，不是坏样本。

## 必须注意的问题

1. `build_stats.json` 声称 train=8,962、val=291，但当前 `grpo_train.jsonl` 实际为 **10,543** 条。说明统计文件和当前训练文件不是同一次最终产物；启动训练前必须以实际 JSONL 重新生成统计并确认行数。

2. `grpo_train` 与 `grpo_val` 存在程序重复：按完整输出精确匹配为 **280/291** 条；只去除首尾空白后为 **291/291** 条。当前验证集不能作为独立程序泛化测试。

3. GRPO 训练集包含上一轮 SFT 已隔离的 253 条质量问题记录：训练集 **238** 条、验证集 **15** 条。它们的具体来源行和原因记录在 `grpo_audit_details.json`。这些记录不应直接进入正式训练集。

4. 与独立 gate 测试的程序重叠很高：`gate10_singles_test` 和 `gate10_doubles_test` 的 300/300 条程序输出都在 `grpo_train` 中出现。因此 gate10 不能作为 GRPO 训练后的独立泛化测试；它更像回归测试集。

5. 1,861 条训练记录和 34 条验证记录 `engine_support=false`，同时没有 `ref_sleepy`；这与字段逻辑一致，代表引擎不支持或没有可用睡眠模拟结果。`ref_prodopy` 在更多记录中为空（训练 4,052、验证 132），需要确认 GRPO reward 是否允许缺失该奖励，不能默认按零分处理。

6. 静态字段本身都能解析，但有 922 条训练、52 条验证的 instruction 包含 `gradient-selection`，静态提取的 gradient 列表为空。这只是人工复核队列：宏、include 或语义分析可能使静态列表漏报，不能直接判为错误。

## 结论

GRPO 文件的 JSON 结构和辅助字段总体可用，但当前目录**还不能直接作为严格的 train/validation/test 数据集**。主要阻塞项是训练行数与 `build_stats` 不一致、train/val 程序重复、SFT 已隔离问题记录回流，以及 gate10 测试与训练程序重合。建议先重新生成最终 GRPO manifest，按程序族重新划分，并排除已确认的 253 条记录；完成后再启动 GRPO。

可复核产物：

- `/mnt/d1/tony/outputs/grpo_data/grpo_audit_summary.json`
- `/mnt/d1/tony/outputs/grpo_data/grpo_audit_details.json`
- `grpo_audit_20260923.py`
- `grpo_audit_detail_20260923.py`

主文件 SHA-256 已记录在 `grpo_audit_summary.json` 的 `source_hashes` 中。
