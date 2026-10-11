# whole_v3 被剔行 FP 回收（2026-10-09）

范围：只回收 judge/规则误杀的行，不重写 instruction，不动 dataset_info.json、clean_v6/v7、block 系列。
工作目录：`data/nmr_v3/clef_screen_20261003/fp_recovery/`（所有新脚本与产物放这里，原文件只读）。

背景数字：whole_v3 9,253 行 / 2,247 程序 → v6 3,595 行 / 1,517 程序（730 程序整体丢失）。
被剔审计：v2 213 / v3 738（梯度规则）/ v4 296（规则）/ v5 2,593（含 verify_mismatch 2,260）/ v6 2,114（deepseek yes 桶 mismatch）。
已知坑：v3/v4 审计 id 为 int，v5/v6 为 str；evidence 截断在 300 字符；join 前打印 type。
**id 索引的是剔除前那一版（已验证全量前缀匹配）**：v2_removed→whole_v3、v3_removed→whole_v3_v2、v4/v5_removed→whole_v3_v3、v6_removed→whole_v3_v5。S5 按 (instruction+output) 内容哈希映射回 whole_v3 顺序。

## 方向调整（2026-10-09）：从"回收误杀"改为"整批修 instruction"
S1 规则只确认 85 条 + S2 2 条，其余 judge 指控规则无法裁决 → 改为：解析出程序事实 → 校正 instruction 子句 → glm-5.2 最小改写兜底 → deepseek-v4.1-flash 复检 → 抽检 → v7。
- 事实来源：graphpulse-master（`sys.path.insert(0,"/home/tony/graphpulse-master/package/python")`，`PpAstParser(filepath).parse()`，只吃文件路径，~1.8s/程序，只解析唯一 output）。
  - 可靠：channel_routing、GradientElement、DecouplingElement(go=)、PulseElement.shaped、fnmode/indirect_dimensions(EA/PH)、条件分支。
  - 不可靠：ndim（4D/5D→1，读 `$DIM`）、has_gradients（子串误报）、`#define NAME value` 标志丢失（23/5709 行）、反斜杠续行解析失败（2/300）→ 标"解析不可信"，走文本规则。
  - 没有：溶剂抑制、constant-time、INEPT → 文本规则。
- 多样性约束：一个程序对应多条 instruction 是设计（原始中位数 3、p90 5），修复后每唯一 output 最多 5 条，规范化后重复的去掉，超限时优先保留原本 clean 的，再按改动量从小到大，兼顾中英比例。按 output 内容哈希分组（程序名首行不可靠）。
- glm-5.2 已用真实大小 prompt 探测可用（/v1/chat/completions，2.8s）。二审/改写用 glm-5.2，复检用 deepseek-v4.1-flash（改写与复检不同模型）。
- 新增步骤：S6 事实缓存（fp_recovery/facts/）、S7 instruction 子句解析（fp_recovery/clauses/）、S8 50 条试点。

S2 结果（2026-10-09 完成）：729 real_no_gradient / 7 ambiguous（仅 Grad.incl，无梯度脉冲，不回收）/ 2 高置信回收（8555、8947，GRAD() 宏）。

## S1 FP 分类器（v6 2,114 + v5 verify_mismatch 2,260）
- 目标：把 judge 指控按"被指控的要求"分类，并判断该要求是否真的出现在 instruction 里（幻觉 = 指控的要求 instruction 未提）。
- 已知 FP 型：4755 型幻觉（instruction 只说 decoupled，judge 引述成 correlation）、通道号过严（X 放 f3 vs f2 功能等价）、EA 幻觉、四步相位表误判、go=2/loop 误判。
- 文件：读 `whole_v3_v{5,6}_removed.jsonl`、`whole_v5_yes_judge.jsonl`、`whole_partial_verify.jsonl`（full evidence/note）、`whole_v3.jsonl`（按 id join 拿 output）。
- 产物：`fp_recovery/s1_classify.py`、`s1_candidates.jsonl`（id, source, fp_type, reason）、`s1_stats.md`。
- 验收：id→whole_v3 行 join 校验（instruction 前缀全匹配）；每 FP 型给计数 + 3 条样例；不剔除/不写任何原文件。

## S2 梯度规则复核（v3 738）
- 目标：找出用非 `gp` 命名实现梯度的程序（gron/groff、calgrad、gpnam、UNBLKGRAD+梯度块、`grad` 宏等），这些是规则误杀。
- 文件：`whole_v3_v3_removed.jsonl`（int id）、`whole_v3.jsonl`。
- 产物：`fp_recovery/s2_gradient_recheck.py`、`s2_candidates.jsonl`、`s2_stats.md`。
- 验收：每类梯度写法计数 + 样例代码行；对 3 个确认无梯度的行做负对照。

## S3 二审裁决（S1+S2 候选）——模型待用户确认
- 换与原 judge（deepseek-v4.1-flash）不同的模型，prompt 给 instruction + program + 原指控，只判"指控是否成立（instruction 显式要求 ↔ 程序矛盾）"。
- 回收条件：规则判 FP 且二审判指控不成立。
- 产物：`s3_adjudicate.py`、`s3_results.jsonl`。验收：0 err、可断点续传、systemd-run 跑后台。

## S4 主线程抽检
- 回收抽 20 + 维持剔除抽 10，读码人工判。误回收率 >10% 则收紧 S1 规则重跑。

## S5 生成 whole_v3_v7
- v7 = v6 + 回收行，按 whole_v3 原顺序；审计 `whole_v3_v7_recovered.jsonl`；逐行重建校验；REPORT.md 加一节。
