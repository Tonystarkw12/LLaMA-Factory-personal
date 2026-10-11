# whole_v3 v10：为未覆盖液态程序生成 instruction

替代 `whole_style_rerender_v10.md`（模板重渲染对 SFT 收益低，搁置）。

目标：whole_v3 中液态（class 不含 solid）、v9 中没有任何 instruction 的程序，以程序本身为唯一事实来源生成新 instruction，经确定性闸门 + 双判收录。`output` 不动；v9 及更早文件只读；不改 `data/dataset_info.json`。

质量原则：物理正确性优先于新增数量。宁可丢弃无法确定的程序和声明，也不把未经验证的细节写入 SFT；目标发布集约 90% 以上工程置信度，不承诺所有候选或所有未覆盖程序达到该比例。

## 范围（2026-10-11 普查）
- 液态未覆盖 808 个程序；排除 facts `error` / `parse_unreliable` / `ndim_mismatch` → 约 720 个。
- 每程序保留 min(原条数, 3) 条，预计上限约 1,800 行。

## 风格（对齐 v9 现有分布：zh 模板 74%、英文自然描述 26%）
- `zh_template`：`写一个/生成一个/请设计一个 {dim} {phase} {name} Bruker TopSpin pulse program，{子句}。`
- `en_generate`：`Generate a ...` 英文详细描述
- `en_request`：`I need ... / A ... is required.` 英文需求式

## 已完成的 v1 试点（仅保留作对照）
- 51 个程序、153 个候选；S31 确定性闸门通过 124 条。
- glm-5.2：104 clean、20 mismatch。
- glm clean 的 104 条中，kimi-k2.6：24 clean、72 mismatch、8 次 err；人工抽查 kimi mismatch 约 4 真错、3 两可、5 误判。
- mimo-v2.6-flash：101 条完成，100 条在 glm clean 子集上 pair-clean，1 条 mismatch；但放过已人工确认的细节错误（idx 1076、7452、38、161），不能作为严格判官。
- 结论：不是简单替换判官。v1 生成器把步骤顺序、计数、可选功能、注释功能和具体通道写得过细；glm 偏松，kimi 偏严。先降低生成风险，再校准判定。

## 步骤
### S30 生成 v1 `fix/s30_gen.py`（已完成，对照保留）
- 生成模型 deepseek-v4.1-flash（与判官 glm/kimi 不同）。输入：程序全文 + 事实摘要。**不给旧 instruction**。
- 输出 `s30_gen_pilot.jsonl` / `s30_gen_all.jsonl`，不覆盖。

### S30v2 证据约束生成（当前步骤）
- 新脚本和产物使用 `s30v2_*` 命名，不能覆盖 v1 产物。
- 先由模型返回有限声明清单；每条声明必须携带程序中的逐字证据行。
- 确定性检查证据必须出现在程序中，且不属于注释行；维度、梯度、shaped、采集去耦、fnmode 等结构性声明还必须与 facts 一致。
- 只用通过检查的声明生成三种短 instruction；禁止步骤顺序、计数、具体参数/延迟公式/相位循环、`optional`、注释掉的功能、缺失特征列表。
- 若模型输出声明不合格，丢弃该声明，不让整程序失败；最终文本再过现有 S31 闸门。
- 涉及文件：`fix/s30_gen_v2.py`、必要时 `fix/s31_gate.py` 的只读兼容入口。
- 验收：51 个 pilot 程序 JSON 合法；声明证据通过率可统计；候选不得出现 v1 已发现的高风险类别。

### S33v2 试点
- 同一批 51 个程序，重新生成并跑确定性闸门。
- 判官暂用 glm-5.2 → kimi-k2.6；mimo 只作诊断，不参与收录。
- 主线程人工逐条核查至少 30 条，重点检查步骤顺序、计数、注释功能、采集去耦、通道和实验维度。
- 过关线：pair-clean ≥ 85%，且人工核查不得发现系统性细节错误。若低于 85%，继续收紧声明白名单，不跑全量。

### S34 全量 + 构建 v10（试点过关后，需用户确认）
- `fix/s34_build_v10.py`：v9 原样为前缀 + 新行；断言前缀、instruction 唯一、每程序 ≤ 5、keys、outputs ⊆ whole_v3 outputs。
- 产物 `whole_v3_v10.jsonl` / `_audit.jsonl` / `_stats.json`；REPORT.md 补节。

## 不做
- Solids/BioSolids 程序；未覆盖的错误或不可靠解析程序；大模型错误说明数据集（B，暂缓）。
- 在 v1 试点没有解决前，直接跑约 721 个程序的全量生成。

## 最终结果（2026-10-11，用户已批准构建）
- 判官定为 glm-5.2 + deepseek-v4.1-flash（句子由脚本渲染，deepseek 不再自评）。kimi 过严，mimo 过松。
- 全量：720 目标，439 渲染，365 程序 / 1095 候选，pair-clean 914（83.5%），355 程序存活。人工审计 30 个程序，机械错误 0。
- v10 = v9 前缀 4661 行 + 625 新行（355 程序，270 个程序 2 行、85 个 1 行），共 5286 行 / 2357 程序。
  新行风格：zh 265 / en_request 200 / en_generate 160；新行中文占比 42.4%（v9 为 73.9%）。
- 新行指令偏短（中位 114 字符）。whole_v3 里这 234 行的程序 input 本来就整程序为空；已用参考脚本 pp2label/fileslabel/labeling/batch_labels.py 的 generate_label_from_text 从程序头部补齐（维度冲突则留空，实际 0 例），现在新行 input 全部非空。
- 产物：data/nmr_v3/whole_v3_v10.jsonl / _audit.jsonl / _stats.json；dataset_info.json 未改。
