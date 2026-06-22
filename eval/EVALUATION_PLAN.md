# efs-diagnosis 自动化评测方案（完整版）

> 范围：relay AIOps 平台 **efs-diagnosis skill**（SFS Turbo IO 异常根因诊断，6 类根因）。
> 定位：relay 的**回归测试**——改 prompt / 换底座模型 / 改工具时，自动发现诊断退化。
> 配套：本目录 `eval/` 是该方案的**最小可运行内核**；`INDUSTRY_SURVEY.md` 是业界范式对照。

---

## 0. TL;DR（给赶时间的人）

- **评什么**：① 是否路由到正确 skill（路由层）→ ② 选定 skill 后是否定位到正确根因（结果）
  → ③ 是否**走到决定性证据**（轨迹）→ ④ 多跑是否**稳定**（蒙对率/pass^k）。
- **怎么评**：录制回放冻结"世界状态" → agent 跑诊断 → 三层评分器（规则/轨迹/结果）→
  **结果×轨迹四象限**（GREEN 真通过 / YELLOW 蒙对 / BLUE 走对路结论错 / RED 跑偏）→ 回归门禁。
- **ground truth 铁律**：根因由 **SRE 盖章**，**绝不从告警指标反推**（那是循环论证）。
- **可运行证据**：`python run_demo.py` 即见四象限被正确区分；`pytest` 10 用例全绿。

---

## 1. 评测目标（6 条）

| # | 目标 | 说明 |
|---|---|---|
| 1 | 回归保护 | 第一性目的：版本变更时自动发现诊断能力退化 |
| 2 | 结果正确性 | 根因**实例集合**命中（多根因按集合 P/R/F1，非单串匹配） |
| 3 | 轨迹有效性 | 是否走到**决定性证据**，而非蒙对——诊断里蒙对的结论极脆弱 |
| 4 | 路由正确性 | 告警是否**根本就该触发** efs-diagnosis（路由层 vs 诊断层分层归因） |
| 5 | 确定性可复现 | 同输入→同判定，方能进 CI；外部遥测必须冻结 |
| 6 | 成本可观测 | token / 工具调用数 / 时延 作为回归副指标（防 agent "越跑越多步"） |

## 2. 合格标准（验收基线）

| 维度 | 合格线 | 本仓库落点 |
|---|---|---|
| ground truth 可信 | SRE 盖章，不从告警反推 | `case.yaml: expected_root_cause`（人工盖章字段） |
| 确定性回放 | 工具响应录盘冻结，按调用精确匹配键 | `harness/tool_proxy.py: build_key` = `cmc__{ns}__{metric}` |
| 多维评分 | 结果 + 轨迹 + 组件三层 | `harness/graders.py` 三个 grade_* |
| 区分力 | 蒙对/走偏必须与真通过区分 | `harness/report.py: classify` 四象限 + 测试验证 |
| 可归因 | 失败能定位到 路由/步/工具/LLM | 四象限归因文案 + 路由层先判 |
| 抗 LLM 抖动 | 固定种子/温度、多跑、关键词而非脆正则 | 见 §8 |
| 可维护 + CI | 加 case 成本低、运行期零人工 | 一 case 一文件夹、纯文件、pytest |

---

## 3. 总体架构

```
                         ┌──────────────────────────────────────────────┐
  告警(csn) ─► 路由层 ──► │  选定 skill = efs-diagnosis ?  (router.py)     │
                  │       └──────────────────────────────────────────────┘
                  │  路由错 → 直接失败，归因"路由层"，不进诊断
                  ▼
          ┌─────────────────────────────────────────────────────────────┐
          │                     诊断层评测闭环                            │
          │                                                              │
          │  case.yaml (输入 + SRE盖章根因 + 参考轨迹 + 规则)             │
          │        │                                                     │
          │        ▼                                                     │
          │  ┌── 拦截面1: ToolProxy ──┐   ┌── 拦截面2: ScriptProxy ──┐   │
          │  │ MCP工具录制回放        │   │ scripts/*.py + metrics_url│   │
          │  │ 按 ns+metric 精确匹配  │   │ 录制回放                  │   │
          │  │ + 兼做 trace 记录器    │   │ + 兼做 trace 记录器        │   │
          │  └───────────┬───────────┘   └────────────┬──────────────┘   │
          │              ▼                            ▼                   │
          │           被测 agent (sim 或 relay 适配器) ── 产出 ──► trace  │
          │                                                     │        │
          │                                                     ▼        │
          │   三层评分器:  grade_rules / grade_trajectory / grade_outcome │
          │                                  │                           │
          │                                  ▼                           │
          │              结果×轨迹四象限分类 + 分层归因 (report.py)        │
          │                                  │                           │
          │                                  ▼                           │
          │           回归门禁(仅GREEN过) + 看板(蒙对率/pass^k趋势)        │
          └─────────────────────────────────────────────────────────────┘
```

**两个拦截面缺一不可**：efs-diagnosis 的 Step7/9/10/11 是 `python scripts/*.py` 子进程、
Step7.2 还经 `metrics_url` 中转——这些**不是 MCP 工具，tool-proxy 拦不到**。若只覆盖
MCP 面，EVS 分支必断。本方案用 `ScriptProxy` 专门覆盖第二面。

---

## 4. 数据与 case 规范

### 4.1 黄金 case 五要素（五问填空法）

| 要素 | 问 | 在 case.yaml |
|---|---|---|
| 输入 | 告警长啥样 | `input.csn` |
| 根因 | SRE 认定的真相是什么 | `expected_root_cause.causes[]`（**盖章字段**） |
| 决定性 | 哪一步证据区分了它与其它候选 | `reference_trajectory[].decisive: true` |
| 必经 | 哪些工具必须调到 | `reference_trajectory[].necessary: true` |
| 禁止 | 结论里绝不该出现什么 | `rules.must_not` |

### 4.2 ground truth 怎么标（draft → 盖章 → 三方交叉）

**绝不从告警指标反推根因**（那是循环论证，且 efs-diagnosis 的告警指标只是"IO 时延高"
这个**症状**，根因要靠下游 cpu_util/await/qos 判定）。标注流水线：

```
真实 run ──► 预填 draft（自动）：抓取轨迹、把疑似越界指标列出、根因留空
                │
                ▼
          SRE 一分钟盖章：只确认/修正"根因实例 + 决定性指标"这一项
                │
                ▼
   三方交叉校验（自动打标）：数据扫描结论 × agent 结论 × 工单记录根因 三者是否一致
                │  不一致 → 标 conflict，人工复核
                ▼
            冻结为黄金 case（含 SRE 签名/时间戳）
```

成本测算：预填把 SRE 的工作压到"看一眼、点确认"，单 case ≈ 1 分钟；100 条 case
≈ 2 小时 SRE 投入，可摊到多次回归复用。

### 4.3 录制回放与匹配键

- **一 case 一文件夹、纯文件、零数据库**（YAGNI）。
- 匹配键由 `tool_proxy.build_key` 生成：指标类按 `cmc__{name_space}__{metric}.json` 细分，
  **解决同一工具几十次调用按 tool_name 撞键**的问题；一文件含全部实例、按 `instance_id` 过滤。
- **fail-closed**：缺录制响应直接抛错并提示缺哪个键，绝不静默返回空（静默会把"漏调用"
  伪装成"正常"）。

### 4.4 阈值耦合（易踩坑）

efs-diagnosis 的"异常"= `diagnosis_threshold = alarm_observed_value × 50%` 的**相对量**。
所以**一条指标响应只在特定告警下才算越界**——必须把告警响应与指标响应**绑在同一个 case
文件夹**里当作"同一个世界"。按根因分目录、把告警与步响应拆开（某些外部方案的做法）会
破坏这种一致性。

### 4.5 case 的两条派生腿

1. **skill 分支派生**：按 6 类根因 × 各 Step 判断分支造 case，保覆盖、可造边界值
   （阈值刚下 / 刚上 / 多根因并发）。
2. **工单派生**：从已闭环工单取真实分布、暴露盲区。
> 两条腿都要：分支派生保"覆盖率"，工单派生保"真实性"。

### 4.6 负样本与拒识（别只造正例）

- 诊断负例：链路全正常 → 期望"未发现 scope 内异常 / 升级"。
- 路由负例：本不该触发 efs-diagnosis 的告警（见 `cases/routing/route-misroute-qos-001`）。

---

## 5. trace + 三层评分 + 四象限 + 门禁

### 5.1 trace schema（对齐 OTel GenAI，见 `harness/trace.py`）

```
Trace { case_id, tool_calls[ ToolCall ], scripts_invoked[], final_output, totals }
ToolCall { seq, tool, name_space, metric, instance_id, params,
           abnormal, observed_value, threshold, latency_ms, surface }
```
关键：`abnormal` 是"agent 是否**看到**该信号越界"——决定性证据是否被命中的核心位。
**trace 在工具/脚本边界被动抓取，agent 无法伪造**。

### 5.2 三层评分器（`harness/graders.py`）

| Tier | 函数 | 评什么 | 指标 |
|---|---|---|---|
| Tier1 规则 | `grade_rules` | 与根因**无关**的通用断言 | schema 合法、必有 instance_id、禁词、禁用工具 |
| Tier2 轨迹 | `grade_trajectory` | 必经/决定性覆盖（**不强制顺序**） | `decisive_coverage`、`necessary_recall` |
| Tier3 结果 | `grade_outcome` | 根因**实例集合**（闭集，**无需 judge**） | `precision/recall/F1` + 类别关键词 |

decisive 步骤额外要求该调用 `abnormal=True`——即"真的看到了越界证据"，而非只是调了一下。

### 5.3 结果×轨迹四象限（`harness/report.py`）

```
                    决定性证据命中            决定性证据未命中
   结论正确      🟢 GREEN  真通过         🟡 YELLOW 蒙对(脆弱)
   结论错误      🔵 BLUE   走对路结论错    🔴 RED    跑偏
```
- Tier1 任一失败 → 直接 **RED（门禁）**，归因 `tier1`。
- **YELLOW（蒙对）必须与 GREEN 分开**：结论对但没走到证据，是最危险的"假绿"——
  换个数据就翻车。**蒙对率要单独上看板并设趋势告警**。

### 5.4 指标口径与门禁

| 指标 | 口径 | 用途 |
|---|---|---|
| `root_cause_hit` (F1) | 实例集合 P/R/F1，gate=1.0 | **回归硬门禁** |
| `decisive_coverage` | 命中决定性 / 全部决定性，gate=1.0 | 区分真通过/蒙对 |
| `necessary_recall` | 命中必经 / 全部必经 | 轨迹完整度 |
| `蒙对率` | YELLOW / (GREEN+YELLOW) | **趋势告警**（升高=越来越靠运气） |
| `pass^k` | k 次全 GREEN 的比例 | 稳定性门禁（见 §8） |
| 成本 | tokens / n_tool_calls / latency | 副指标，回归对比 |

> 门禁建议：**root_cause F1 与 decisive_coverage 双 1.0 才算 GREEN 通过**；蒙对率不卡硬门
> 但纳入趋势告警；成本指标设"不显著劣化"软门。

---

## 6. 路由层评测（`routing/`）

诊断对不对是一回事，**选没选对 skill 是另一回事**。路由层 ground truth 比诊断根因好标
（可从 skill 的 `keywords`/`resource_types`/`hypotheses` 半自动反查，SRE 仅边界盖章），
且**不依赖诊断回放，适合先行起步**。

四类判定（`routing/grade_routing.py`）：

| 判定 | 含义 | 危险度 |
|---|---|---|
| HIT | 该路由且路由对 | — |
| MISS | 该路由却漏了/给错 | 中（漏诊） |
| **MISROUTE** | **不该路由却路由了（过度自信）** | **高**（拿错 skill 一本正经误诊） |
| CORRECT_REJECT | 不该路由且正确拒识 | — |

指标：混淆矩阵 P/R/F1、top-1/top-k（多 skill 竞争）、**误路由率单列**。

---

## 7. 端到端分层归因

```
收到告警
   │
   ├─ 路由层判定 ──► 路由错 ─► 失败，归因「路由层」，不再评诊断
   │                   │
   │                 路由对
   │                   ▼
   └─ 诊断层四象限 ──► GREEN  → 真通过
                      YELLOW → 归因「诊断层·蒙对」，盯轨迹
                      BLUE   → 归因「诊断层·结论」，下钻是哪步阈值/聚合错
                      RED    → 归因「诊断层·跑偏 或 Tier1 门禁」
```
好处：一条 case 挂了，看板能直接告诉你**赖路由还是赖诊断、赖哪一步**，而不是只有一个红叉。

---

## 8. 抗 LLM 抖动（两份外部方案都漏了的维度）

即使工具响应冻结，LLM 本身仍随机。对策：

1. **固定温度/种子**（能固定则固定），降低无谓抖动。
2. **轨迹只比"必经集合、不强制顺序"**——容忍 agent 并行/换序，避免脆性失败（已实现）。
3. **结论用关键词断言（must_mention/must_not）+ 实例集合**，不用脆弱正则抠根因。
4. **每 case 多跑 N 次、用 pass^k 而非单发判定**——单跑通过不代表稳定；ITBench 每任务 3 跑、
   τ-bench 用 pass^k 就是这个道理。回归门禁可设"pass^k ≥ 阈值"。
5. **蒙对率纳入趋势**：同一 case 多跑里 YELLOW 占比升高 = 正在从"会诊断"滑向"靠运气"。

---

## 9. 语料策略与规模

- 5–10 / 7 条只够**冒烟**。6 类根因 × 多分支，要：每分支多条 + 边界值（阈值刚下/刚上）+
  多根因组合 + 负样本/拒识。现实量级 **几十到上百**。
- 起步顺序：**路由层先行**（case 便宜、不依赖回放）→ 诊断层每类根因先 1 条打通 →
  扩边界值与多根因 → 接工单派生补真实分布。

---

## 10. CI / 看板 / 回归门禁

- **CI**：`pytest eval/` 进流水线；root_cause F1 与 decisive_coverage 双门禁，未达 GREEN 阻断合并
  （DeepEval/Promptfoo 式 code-first gating）。
- **看板**：按根因类别 × 版本，画 通过率 / 蒙对率 / 平均 decisive_coverage / 成本 趋势
  （可对接 Braintrust/LangSmith/Arize 做回归追踪与合并阻断）。
- **轨迹存档**：每次 run 的 trace 落盘（对齐 OTel GenAI span），供 A/B、回放新版 agent 于旧轨迹。

---

## 11. 维护（技能演进下别让评测腐化）

- skill 改 Step/阈值 → 录制 fixture 与参考轨迹可能过期：需**重录 + 重盖章**流程与"fixture 漂移"检测。
- 切忌"定期重新采集"却不重新盖章——那会把循环论证又引回来。
- 每条黄金 case 带 SRE 签名 + 时间戳 + skill 版本号，skill 升版本时批量复核受影响 case。

---

## 12. 与本仓库代码的映射

| 方案部件 | 文件 |
|---|---|
| trace schema | `harness/trace.py` |
| 拦截面1（MCP 工具录放 + trace 记录） | `harness/tool_proxy.py` |
| 拦截面2（脚本/URL 录放） | `harness/script_proxy.py` |
| 三层评分器 | `harness/graders.py` |
| 四象限分类 + 归因 | `harness/report.py` |
| runner（装载→跑→评分→报告） | `harness/runner.py` |
| 被测 agent 协议 + relay 接入 seam | `agents/base.py` |
| 模拟 agent（自测内核用） | `agents/sim_efs_agent.py` |
| 路由器 + 路由评分 | `routing/router.py`, `routing/grade_routing.py` |
| 黄金 case（ECS-CPU） | `cases/efs-ecs-cpu-001/` |
| 路由 case | `cases/routing/router_cases.yaml` |
| 区分力/路由/端到端 测试 | `tests/` |
| 一键演示 | `run_demo.py` |

---

## 13. 落地路线（优先级）+ 接入真实 relay

### 13.1 优先级

| 优先级 | 事项 |
|---|---|
| **P0** | ① 打通一条端到端"活"case（**本仓库已完成**：sim + 双拦截面 + 三层评分 + 四象限，pytest 绿）<br>② 覆盖 script/URL 面（已含 `ScriptProxy`）<br>③ 重写外部方案 `curate.py`：删 `root_cause_map` 反推，改预填+留空待盖章+三方交叉 |
| **P1** | ④ 抗抖动与门禁：固定种子、pass^k 多跑、门禁阈值<br>⑤ 阈值耦合：告警与指标响应绑同一 case<br>⑥ 蒙对率看板聚合 |
| **P2** | ⑦ 语料扩规模：每根因多条 + 边界值 + 多根因 + 负样本<br>⑧ 维护闭环：重录/重盖章/漂移检测 |

### 13.2 把模拟 agent 换成真实 relay（唯一要写的胶水）

本仓库用 `SimEfsAgent` 自证内核可跑；生产只需实现一个同签名适配器（见 `agents/base.py`）：

```python
class RelayAgentAdapter:                       # 实现 run(case, tools, scripts) -> Step10 JSON
    def run(self, case, tools, scripts):
        # 1) relay 的 mcp_tool_proxy 切回放模式，后端指向 tools.call（拦截面1，自动抓 trace）
        # 2) skill 里 scripts/*.py 与 metrics_url 重定向到 scripts（拦截面2）
        # 3) 用 case['input'] 触发 relay 跑 efs-diagnosis，固定温度/种子
        # 4) 取 skill Step10 (show_type=recommended_root_cause) 原样返回
        ...
```
**评分器、case、四象限、门禁全部不变**——这正是"换内核不换管道"的落地形态。

---

## 附：本 worked example 的运行结果

`python run_demo.py`（同 `pytest -s`）对**同一条 case、同一套评分器**喂入四种 agent 行为：

| agent 行为 | 状态 | 说明 | 门禁 |
|---|---|---|---|
| 忠实走链路、看到 cpu_util 越界 | 🟢 GREEN | 真通过 | ✅ pass |
| 跳过 Step8 但仍猜对 ECS_CPU | 🟡 YELLOW | **蒙对**：结果对 F1=1，但 decisive_coverage=0 | ❌ 不通过 |
| 看了 cpu 证据却报错实例 ecs-01 | 🔵 BLUE | 走对路结论错：decisive=1 但 F1=0 | ❌ 不通过 |
| 正确 + 多报矛盾的 QOS限流 | 🔴 RED | Tier1 门禁拦下禁词 | ❌ 不通过 |

> 这证明了评测的**命门——区分力**：一个只比最终答案的评测会把"蒙对"误判为通过；
> 本内核把它准确标成 YELLOW 并挡在门外。
