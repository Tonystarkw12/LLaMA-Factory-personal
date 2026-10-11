# whole_v3 v10：液态程序风格补条（确定性重渲染）

目标：在 v9（4,661 行 / 2,002 程序）基础上，只对**液态**（class 不含 solid）且条数 < min(原条数, 3) 的程序，
用已验收行的槽位**确定性重渲染**出缺失的模板风格，不调用大模型生成文本。`output` 不动；v9 及更早文件只读；不改 `data/dataset_info.json`。

## 现状数字（2026-10-11 普查）

- 液态程序 2,641，已覆盖 1,833；其中 719 个低于 min(原条数,3)，缺口 1,033 行。
- 719 个里 524 个有可用源行（v9 中 zh/en_template 且 coverage ≥ 0.99）；195 个只有 free_form 源 → 本轮不做。
- v9 模板句式（zh_template）主要三类：
  - F1 `写一个 {dim} {phase} {name} Bruker TopSpin pulse program，{子句，…}。`
  - F2 `生成一个 {name} pulse program，要求：{dim} 维度、{phase} 相位模式、{子句、…}。`
  - F3 `请设计一个{前置子句}的{dim} {phase} {name} pulse program，{子句，…}。`

## 步骤

### S24 渲染器 `fix/s24_rerender.py`
- 输入：v9、`clauses/parse_clauses.py`、`facts/facts.jsonl`、`whole_v3.jsonl`（原条数）。
- 每个目标程序：选 1 条源行 → `parse()` 取 heading + 槽位（保留原 surface 值，如 `double INEPT`、`composite-pulse-decoupling`、`程序名为 X`）→ 渲染到该程序**尚未出现**的句式（F1/F2/F3），补到 min(原条数,3)。
- 句式内再做轻量变体（子句顺序固定、连接词 `并/以及/、` 轮换、空格有无），仅用于避免与现有 instruction 撞车。
- 不新增任何源行里没有的槽位，不删槽位。
- 验收：单测覆盖三种句式的 round-trip（渲染 → `parse()` → 槽位值集合与源一致、coverage ≥ 0.99、style = zh_template）。

### S25 确定性闸门（脚本内）
- round-trip 槽位集合 == 源槽位集合；coverage ≥ 0.99。
- `s12._kernel` 对新行 + 程序事实通过（与源行同结论）。
- 新 instruction 不与 v9 任何 instruction 重复（一条 instruction 只对应一个程序）；每程序 ≤ 5。
- 输出 `fix/s24_cands.jsonl`（含 src_instruction、frame、程序 key）+ `fix/s24_stats.json`（每闸门淘汰数）。

### S26 试点（约 50 个程序，~70 行）
- 抽样：HighRes 为主，混入 HighRes HWT / BB-Assign / IBS / 空 class；1D/2D/3D 都要有；源句式三种都要有。
- 双判：glm-5.2 全判 → glm clean 再判 kimi-k2.6（`s10_rejudge.py --rows`）。
- 主线程人工抽查 ≥ 20 行（对照源行与程序）。
- 过关标准：pair-clean ≥ 95%；所有 mismatch 逐条看，归因为渲染器问题的修渲染器后重跑试点，归因为源行本身的记录下来。

### S27 全量（试点过关后，需用户确认）
- 跑全部 524 个程序，双判同试点流程（kimi 约 17 行/分钟，预计 1 小时量级）。
- `fix/s27_build_v10.py`：v9 原样为前缀 + pair-clean 新行；断言前缀 == v9、instruction 唯一、每程序 ≤ 5、keys = {instruction,input,output}、outputs ⊆ v9 outputs。
- 产物：`whole_v3_v10.jsonl` / `_audit.jsonl` / `_stats.json`；REPORT.md 与本计划补结果节。

## 不做
- Solids/BioSolids 程序；195 个只有 free_form 源的程序；未覆盖的 1,104 个程序；大模型生成文本。
- 简化版短指令（如只写 `写一个 2D HSQC pulse program`）：会让一条 instruction 对应多个程序，违反规则。
