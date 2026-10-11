# whole_v3 修复计划 → whole_v3_v7（2026-10-09，2026-10-10 更新）

接替 `Plans/whole_fp_recovery.md`。原则：output 是官方程序不动，只修 instruction；
先修规则能确认的，其余桶明确排除、后续分阶段处理；v6 现有 3,595 行一律不动。
工作目录：`data/nmr_v3/clef_screen_20261003/fp_recovery/`。

## 结果（已完成）

`data/nmr_v3/whole_v3_v7.jsonl` = v6 3,595 + 回收 **720** = **4,315** 行。
审计 `data/nmr_v3/whole_v3_v7_audit.jsonl`（含原句、新句、删除的子句），统计 `whole_v3_v7_stats.json`。

`data/nmr_v3/whole_v3_v8.jsonl` = 同 4,315 行，把 v6 继承的 205 组一对多 instruction
拆开（第一份原样，其余 355 加真实差分子句 / 官方程序名）。instruction 全部唯一。
审计 `whole_v3_v8_audit.jsonl`。未改 `dataset_info.json`。v7 文件保留不动。
（S19 首版有文本规则误报和程序名误提，已修并重建，详见 REPORT.md v8 修正；
13 行落到 hash 兜底，已按用户决定丢弃 → v8 实为 4,302 行。）

`data/nmr_v3/whole_v3_v9.jsonl` = v8 4,302 + B 桶回收 **359** = **4,661** 行（当前交付），
覆盖 2,002 个独立程序（原 whole_v3 共 3,106 个）。
碰撞池实为 1,079 行；S20 拆分 + 内核 + 收紧得 724 候选，glm-5.2 → kimi-k2.6 双判，
两家都 clean 的并入。审计 `whole_v3_v9_audit.jsonl`。

## 验收口径（四模型一致）

一行被采纳，当且仅当：
1. 规则修复（S8/S13：删掉程序事实不支持的子句）+ 内核校验（S12：核种存在、correlation 核种子集、
   phase-mode 残留、实验家族相容、无残留被驳子句、特殊元素在程序中）；
2. 收紧（S15：删掉"采集期去耦"但 go= 行无去耦的子句；删掉 QF-only 程序上的 States-TPPI/TPPI 子句）；
3. 四个校准判官全部判 clean：glm-5.2、glm-5.3、deepseek-v4.1-flash、kimi-k2.6。

S15 通过 1,374 行；四判官一致 clean = 720 行；再经碰撞/重复/多样性过滤（每唯一 output ≤5 条 instruction）得 720。
在 S9 人工抽检的 19 行（含 5 行已知真问题）上，采纳集命中 14/14 正确、0 真问题。

## 账目（被剔 5,658 行）

| 桶 | 行数 | 结果 |
|---|---|---|
| A 规则修复通过验收 | 1,041 | 619 → 收紧 → 四判官采纳 |
| C/D 无规则信号或结构性（S13 覆盖） | 3,691 中 template 可用 1,980 | 765 → 收紧 → 四判官采纳 |
| B 修后撞别的程序 | 503 | 排除 |
| E 非模板/英文散文 | 874 + 5 | 排除 |
| F 解析不可信 | 52 | 排除 |
| G 修后信息量为零/标题被改 | 约 80 | 排除 |

## 判官校准（关键）

原始 v5/v6 judge 用 deepseek-v4.1-flash 单一模型，误杀多。逐模型校准后：
- 原 prompt：glm-5.2 clean 189/1041（过严，含 f1/f3 通道号、semi-CT 等误判）。
- 校准 rubric（S10，明确列出 7 类真失配 + 5 类不算失配）：glm-5.2 clean 859。
- kimi-k2.6 明显最严，对 S16 已过三判官的 1,173 行仍挑出 443 mismatch，其中约 334 条指向真问题
  （核种通道实为另一核、TROSY 变体 vs 纯 INEPT、CPD vs CW、1D 用 States-TPPI 等）。
- 结论：单模型不可信；四模型一致 + 确定性内核才能到 ~95%。

## 后续（未做）

- B 桶 503 行：换 instruction 变体/槽位组合后可再试。
- kimi 单独挑出、其余三判官放行的 443 行：人工复核后可作为第二批。
- v6 自身 205 条重复 instruction（涉 560 行）：是否清理另议。

## 风险

- 修后 instruction 子句变少，难度低于原模板；训练时需注意。
- "通过"均为判官判定 + 确定性规则，非物理验证。
