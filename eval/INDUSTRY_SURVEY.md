# 业界如何为"运维/诊断 Agent"构建评测系统

> 面向 relay efs-diagnosis 这类**多步、调工具、走决策树的诊断 Agent**。结论先行：
> 业界已经收敛出一套相当一致的范式——**三层评测（结果/轨迹/组件）+ 可靠性多跑（pass^k）
> + 确定性回放 + 可信 oracle**。relay 的设计本质上是这套范式在"单 skill、录制回放、
> SRE 盖章 oracle"下的一个落地实例。

---

## 1. 通用范式：评 Agent 不能只比最终答案

业界（Google ADK、τ-bench、TRAJECT-Bench 等）已形成共识，Agent 评测要分层：

| 层 | 评什么 | 对应到 relay |
|---|---|---|
| **结果 Outcome** | 最终答案/世界状态是否正确 | 根因实例集合是否命中 |
| **轨迹 Trajectory** | 工具是否选对、参数对不对、顺序/依赖满足否 | 是否走到**决定性证据** |
| **组件/单步 Component** | 单步决策、子模块质量 | 单步阈值判断、路由打分 |
| **可靠性 Reliability** | 多次重跑是否**稳定**正确 | 蒙对率、pass^k |

Google ADK 把评测明确拆成"trajectory/tool-use"与"final response"两块，并指出**轨迹评测
本质是逻辑/回归测试**。TRAJECT-Bench 进一步指出：以往大量工作只看最终答案、忽略工具使用
轨迹（是否正确选择、参数化、排序），这正是它要补的洞——并给出 Exact Match / Inclusion /
Tool Usage 等轨迹级指标，暴露"相似工具混淆""参数盲选"等失败模式。

**可靠性维度**最值得单列：Sierra 的 τ-bench 提出 **pass^k**（k 次全对才算对），与常见的
pass@k（k 次至少一次对）相反——一个 pass@1=90% 的 agent，在 k=8 时一致性只剩 ~57%。
对"回归测试"而言，我们要的就是 pass^k 式的稳定性，而不是偶尔蒙对。

---

## 2. 运维/SRE 专项基准：oracle 从"注入故障"而来

这是对 relay 最直接的参照。它们的共同套路：**搭真实/仿真系统 → 注入已知故障 →
agent 诊断 → 用注入时就确定的 oracle 当 ground truth**。注意：oracle 是"注入故障时
就知道的真相"，**不是从症状反推**——这正是 relay"根因必须 SRE 盖章、不能从告警反推"
那条铁律的工业版本。

| 基准 | 出品方 | 规模 | ground truth 怎么来 | 关键点 |
|---|---|---|---|---|
| **AIOpsLab** | Microsoft Research | 多场景 | 细粒度故障注入，保持语义完整与依赖关系 | Agent-Cloud Interface(ACI) 统一交互面；任务含 检测/定位/RCA/缓解；集成 ReAct/AutoGen/TaskWeaver |
| **ITBench / ITBench-AA** | IBM Research + Artificial Analysis | 59 SRE 任务(40 真实 K8s 事件模板 + 19 held-out) | K8s 故障快照 + 注入真相；**每任务重跑 3 次** | agent 须产出**结构化 JSON 根因实体**(deployment/service/pod/...)；前沿模型通过率 <50%；公开 ITBench-Trajectories 轨迹数据集 |
| **SREGym** | UIUC 等 | 90 问题(含 AIOpsLab+ITBench 全集) | problem = 应用 + 故障 + **oracle**；注入后用 oracle 判 | 活系统 + 故障/噪声注入器；含 元稳态/并发/关联 故障与"环境噪声" |
| **RCAEval** | 学界(FSE/WWW/ASE) | 735 真实故障 case，11 类故障 | 每 case 标注**根因服务 + 根因指标** | 覆盖 metric/trace/multi-source RCA；15 个可复现 baseline；分粗粒度/细粒度 |

**对 relay 的迁移要点**：华为云生产环境**不能像 AIOpsLab/SREGym 那样随意注入故障**，
所以 relay 改用"**录制回放 + 从闭环工单重建 oracle**"——等价于把"注入时已知的真相"
换成"SRE 对历史真实故障盖章"。RCAEval 的"根因服务 + 根因指标"标注法，几乎就是 relay
"根因实例 + 决定性指标"的同构；ITBench 的"结构化 JSON 根因实体 + 精确匹配 + 多次重跑"
就是 relay"recommended_root_cause + 集合 P/R/F1 + pass^k"的模板。

---

## 3. 通用工具/MCP Agent 基准：轨迹与 MCP 接入怎么评

| 基准 | 评测重点 | 对 relay 的借鉴 |
|---|---|---|
| **τ-bench / τ²-bench** (Sierra) | 工具-用户-策略；用**数据库最终状态**判结果；**pass^k** 可靠性；τ² 双控 + 电信排障域 | 用"世界最终状态"而非措辞判对错；蒙对率/pass^k 单列 |
| **TRAJECT-Bench** | 轨迹级：工具选择 / 参数正确性 / 顺序依赖；1228 个生产 API | 轨迹评分用"必经集合 + 决定性"，不强制全序 |
| **MCP-Bench** (Salesforce, 28 server/250 tool) / **MCP-Universe** (6 域/11 server/231 任务) | 直连**真实 MCP server**，多步、跨工具协同、参数控制、长程 | relay 既然走 MCP，评测拦截面就落在 MCP 工具边界 |
| **T-Eval / AgentBoard** | 把工具调用能力拆成 plan/reason/retrieve/understand 等细粒度维度；多轮过程式评测 | 组件层指标的拆法参考 |

---

## 4. 工程化落地：四件套

业界把"评测"工程化为四个可复用部件，relay 已具备其中三件的雏形：

1. **确定性回放（record-replay / VCR cassette）**——先录一次真实工具/LLM 交互到"磁带"，
   之后离线、确定性重放。好处：测试只在"喂给 LLM 的输入变了"时才失败，专抓 prompt/agent
   回归；可把新版 agent 跑在旧轨迹上做 A/B。已有 `vcrpy`、`agent-vcr`（专为 MCP 录放）等。
   → relay 的 `/tmp/relay_mcp_responses/` 落盘 + `mcp_tool_proxy` 就是现成的录放底座。

2. **标准化轨迹（OpenTelemetry GenAI 语义约定）**——OTel 已为 LLM 调用、agent 调用、
   工具执行、token、时延定义标准 span schema，Datadog/Honeycomb 等已支持，LangChain/CrewAI
   原生发射。**但 OTel 只管"记录"，不管"评分"**——输出质量评估要你自己在其上построить grader。
   → relay 已有 OTel GenAI 观测，trace schema 应对齐它。

3. **评分框架（code-first gating + 平台）**——业界普遍**组合**两类：
   - 轻量、pytest 风格、进 CI 当门禁：**DeepEval / Promptfoo / RAGAS**；
   - 回归追踪 + 人工标注 + 看板 + 合并阻断：**Braintrust / LangSmith / Arize**。
   → 本仓库 `eval/` 走的就是"DeepEval 风格 code-first 门禁"路线（pytest + 三层 grader）。

4. **LLM-as-Judge（仅用于开放式输出）**——当答案是闭集（如 relay 的 6 类根因）时，
   **精确/集合匹配即可，不需要 judge**；只有处置建议这类自由文本才动用 judge，且必须治理
   **位置偏置**：交换顺序跑两遍取一致（position-consistency）、显式 rubric、用校准集量化偏置。
   → relay 核心指标(根因/轨迹)都是闭集，**核心评测无需 judge**，把 judge 的不确定性挡在门外。

---

## 5. 提炼：业界共识范式 → relay 的 7 条

把上面所有东西蒸馏成可执行原则（也是 `EVALUATION_PLAN.md` 的骨架）：

1. **oracle 来自"注入/盖章"，绝不从症状反推**（AIOpsLab/SREGym 注入；RCAEval 标注；relay 用 SRE 盖章）。
2. **结构化、闭集的结果断言**（ITBench JSON 实体 + 精确匹配；relay 根因实例集合 P/R/F1）。
3. **轨迹必评，且看"必经 + 决定性"而非全序**（TRAJECT-Bench；relay decisive evidence）。
4. **可靠性多跑、单列蒙对率/pass^k**（τ-bench pass^k；ITBench 每任务 3 跑）。
5. **确定性回放冻结世界**（VCR/agent-vcr；relay record-replay + tool-proxy）。
6. **轨迹对齐 OTel GenAI，评分建在其上**（OTel 只记录、grader 才评分）。
7. **闭集免 judge，自由文本用 judge 且治理位置偏置**。

> 一句话：relay 要做的不是发明新范式，而是把 AIOpsLab/ITBench/RCAEval 这套
> "注入→诊断→oracle 判定"的成熟范式，**在不能注入故障的生产前提下**，用
> "录制回放 + SRE 盖章 oracle + 决定性证据轨迹"复刻出来。本仓库 `eval/` 即其最小可运行内核。

---

## Sources

**运维/SRE 基准**
- [AIOpsLab — Microsoft Research blog](https://www.microsoft.com/en-us/research/blog/aiopslab-building-ai-agents-for-autonomous-clouds/) ·
  [AIOpsLab arXiv 2501.06706](https://arxiv.org/html/2501.06706)
- [ITBench-AA — IBM Research × Artificial Analysis (HF blog)](https://huggingface.co/blog/ibm-research/itbench-aa) ·
  [ITBench-AA Leaderboard](https://artificialanalysis.ai/evaluations/itbench-aa) ·
  [ITBench-Trajectories dataset](https://huggingface.co/datasets/ibm-research/ITBench-Trajectories) ·
  [ITBench SRE Agent (GitHub)](https://github.com/IBM/ITBench-SRE-Agent)
- [SREGym arXiv 2605.07161](https://arxiv.org/abs/2605.07161) · [SREGym (GitHub)](https://github.com/SREGym/SREGym) · [sregym.com/docs](https://sregym.com/docs)
- [RCAEval arXiv 2412.17015](https://arxiv.org/abs/2412.17015) · [RCAEval (GitHub)](https://github.com/phamquiluan/RCAEval)

**通用工具/MCP/轨迹基准**
- [τ-bench arXiv 2406.12045](https://arxiv.org/abs/2406.12045) · [τ²-bench arXiv 2506.07982](https://arxiv.org/pdf/2506.07982) · [tau2-bench (GitHub)](https://github.com/sierra-research/tau2-bench)
- [TRAJECT-Bench arXiv 2510.04550](https://arxiv.org/abs/2510.04550)
- [MCP-Bench arXiv 2508.20453](https://arxiv.org/abs/2508.20453) · [MCP-Universe](https://mcp-universe.github.io/) · [MCP-Universe (GitHub)](https://github.com/SalesforceAIResearch/MCP-Universe)
- [Why evaluate agents — Google ADK](https://adk.dev/evaluate/) · [ADK 评测 criteria](https://google.github.io/adk-docs/evaluate/criteria/)

**工程化**
- [OpenTelemetry GenAI agent span 语义约定](https://opentelemetry.io/docs/specs/semconv/gen-ai/gen-ai-agent-spans/) · [Datadog 支持 OTel GenAI](https://www.datadoghq.com/blog/llm-otel-semantic-convention/)
- [agent-vcr：MCP 录制回放](https://github.com/Jarvis2021/agent-vcr) · [用 VCR 消除 LLM flaky 测试](https://anaynayak.medium.com/eliminating-flaky-tests-using-vcr-tests-for-llms-a3feabf90bc5)
- [LLM-as-a-Judge 实践指南 (TDS)](https://towardsdatascience.com/llm-as-a-judge-a-practical-guide/) · [LLM 评委位置偏置：测量与缓解](https://mbrenndoerfer.com/writing/position-bias-in-llm-judges)
- [LLM 评测工具对比 (Confident AI)](https://www.confident-ai.com/knowledge-base/compare/best-llm-evaluation-tools) · [LangSmith vs Braintrust](https://www.braintrust.dev/articles/langsmith-vs-braintrust)
