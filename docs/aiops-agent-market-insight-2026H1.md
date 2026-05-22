# AIOps Agent 市场与技术洞察报告

**洞察周期**: 2025年11月 — 2026年5月
**报告生成**: 2026-05-22
**调研方法**: 4-Agent并行情报采集 (海外传统观测厂商 / AI-Native初创 / 中国厂商 / 底层框架与协议)

---

## 第一部分 · 总览 (Executive Summary)

### 1.1 一句话结论

> **AIOps Agent 已经从"AI 加持的告警面板"跨入"自主 SRE 工作者"阶段。胜负手不再是模型本身，而是数据底座 (Knowledge Graph + Topology + 历史故障)、协议标准 (MCP / A2A / OTel-GenAI)、以及深度集成的工作流执行权。**

### 1.2 关键判断（六条主线）

| # | 判断 | 证据强度 |
|---|---|---|
| ① | 从 "Chat Copilot" → "Autonomous SRE Agent" 的范式跃迁已完成 | ★★★★★ Datadog Bits AI SRE / Dynatrace Agentic Workflows / PagerDuty 自治响应路线图均明确进入 H2 2026 |
| ② | MCP 成为事实标准，9 家可观测厂商已发布官方 MCP Server | ★★★★★ Datadog/New Relic/Splunk/Dynatrace/Grafana/Honeycomb/PagerDuty/IBM/Sentry |
| ③ | "纯 LLM 推理"已被市场放弃；**确定性图 + 概率性 LLM 混合**成为 RCA 主流 | ★★★★☆ Dynatrace Causal AI、Traversal World Model、Causely 因果图、SynergyRCA 学术架构 |
| ④ | Multi-Agent (Planner + Specialist) 取代 Single-Agent 成为新基线 | ★★★★☆ Resolve.ai 并行假设搜索、Komodor Klaudia 50+ SME Agents、ServiceNow Otto / IBM Concert |
| ⑤ | **持久化记忆 (Memory)** 是新护城河——把每次故障转化为可复用 Skill | ★★★★☆ Cleric "self-learning SRE"、PagerDuty "16 年故障数据飞轮"、Resolve AI Labs |
| ⑥ | 中国市场以 **DeepSeek + 行业大模型 + 信创私有化栈** 为差异化主轴 | ★★★★★ 华为盘古 5.5、火山×中移 ArkClaw、银联私有化 DeepSeek-V4、阿里 OI 范式 |

### 1.3 ROI 收敛区间（独立验证）

- **MTTR 缩短**：25%–50%（New Relic 25%、ServiceNow 50%、Traversal/Amex 32%、火山×中石油 10× 运营效率）
- **告警降噪**：~84%–99%（火山 84%、ServiceNow 99.2%）
- **故障预防**：30%–70% 中断减少（Dynatrace ADT、ServiceNow ITOM）
- **工程师工时节省**：单组织 5,000–10,000 小时/月（ServiceNow ~9,500h、NeuBird 12k h/year）

---

## 第二部分 · 核心技术趋势与价值

### 趋势 1：底层模型选型 — "深度推理 > 速度" 优先

| 模型层级 | 代表 | 在 Ops 中的角色 |
|---|---|---|
| 旗舰推理模型 | **Claude Opus 4.7 / Sonnet 4.6** | 复杂级联故障的多步推理、长上下文 RCA。Rootly SRE-skills-bench 显示 Sonnet 4.6 较 4.5 提升 4+ 分 |
| 强开源推理 | **DeepSeek-V3/R1**、**Qwen3** | 私有化、信创、金融政务场景；R1-Distill-Qwen-8B 可单卡部署 |
| 端模型/小模型 | Haiku 4.5、Qwen3-小、自研轻量 | 日志摘要、轻量分类、Tool Router |
| 专用基础模型 | Datadog **Toto** (时序)、Cisco **Foundation-sec-8B** (安全) | 数值预测、领域判别 (不是对话用) |

**为什么重要**：Ops 错误成本高、不可逆。**Adaptive Thinking Budget** (Claude 4.6+) 解决"简单 CrashLoopBackOff 秒级响应 vs 跨服务级联故障多分钟深思"的双峰分布。

### 趋势 2：协议层 — MCP 成为"运维总线"

| 协议 | 用途 | Ops 适配现状 |
|---|---|---|
| **MCP (Model Context Protocol)** | Agent ↔ Tool/Data | 9 家观测厂商已发布；Azure SRE Agent / AWS DevOps Agent (均 2026/4 GA) 全栈基于 MCP |
| **A2A (Agent2Agent)** | Agent ↔ Agent (跨厂商) | Linux Foundation 治理；NeuBird、IBM watsonx Orchestrate 已采纳 |
| **OpenTelemetry GenAI Semconv** | Agent 自身的可观测 | semconv 1.40.0；Datadog/Honeycomb/New Relic 已原生发射 |

**技术价值**：Ops 数据源平均 30+，MCP 消除了 N×M 集成爆炸；同时让 Agent 与 Agent (厂商 A 的"调查 Agent" 把上下文交棒给厂商 B 的"响应 Agent") 协作可行。**这是观测厂商真正在押注的"赢家通吃"层。**

### 趋势 3：架构层 — Planner / Executor + Knowledge Graph 混合

```
                ┌─────────────────────────────────────┐
                │  Planner (Opus / Sonnet 4.6 / R1)   │
                │   - Hypothesis Generation           │
                │   - Plan Decomposition              │
                └────────┬────────────┬───────────────┘
                         │            │
              ┌──────────▼──┐    ┌────▼────────┐
              │ SME Agent A │    │ SME Agent B │   (并行)
              │  (K8s)      │    │  (DB / SQL) │
              └──────┬──────┘    └────┬────────┘
                     │                │
                     ▼                ▼
        ┌─────────────────────────────────────────┐
        │   Deterministic Layer                   │
        │   - Production Knowledge Graph          │
        │   - Causal/Topology Constraints         │
        │   - Risk-Tier Gate (auto/HITL/block)    │
        └─────────────────────────────────────────┘
                     │
                     ▼
              MCP Tool Surface
   (kubectl / Prometheus / Loki / PagerDuty / Terraform)
```

- **Plan-Execute** 较纯 ReAct 节省 ~30% Token；LLMCompiler 实现 3.6× 加速
- **RP-ReAct** (arxiv 2512.03560)：Opus 级规划器监督廉价执行器，适合 ops 高分支 RCA
- **Risk-Tier Gate**：风险 <30 自动执行 / 30–70 二次校验 / >70 HITL；**EU AI Act 2026/08 deadline** 让 HITL 从最佳实践变法律义务

### 趋势 4：数据层 — 从 RAG 到 "Production World Model"

| 范式 | 代表 | 局限 |
|---|---|---|
| RAG over Runbooks | 早期 Bits AI / 文心 / 蓝鲸 | 无法表达拓扑、因果、状态 |
| **Live Knowledge Graph** | Resolve.ai、Dynatrace Smartscape | 实时 Diff + 实时 Embedding |
| **Causal World Model** | Traversal、Causely | 约束 LLM 假设空间，杜绝幻觉因果链 |
| **持久化运维记忆** | Cleric、PagerDuty Memory | 把每一次事故转化为可复用 Skill |

**关键洞察**：扁平向量检索无法承载生产环境的拓扑/因果关系。**头部厂商在押注"World Model 是新的 RAG"**，并把它做成不可外迁的数据资产 (i.e. 真正的护城河)。

### 趋势 5：评估层 — 真正的 Ops Benchmark 出现

| Benchmark | 来源 | 意义 |
|---|---|---|
| **SREGym** | arxiv 2605.07161 | 端到端故障场景，可扩展 |
| **SRE-skills-bench** | Rootly + 实际 SRE 验证 | 选择题，覆盖 AWS/Azure/GCP |
| **o11y-bench** | Grafana Labs (开源，2026/04) | 可观测任务 Agent 公开评测 |
| **OEP (Operational Eval Protocol)** | GIRA paper | 引入"未授权动作率、爆炸半径"指标 |
| **OpenSec** | arxiv 2601.21083 | 对抗性证据下的校准 |

**为什么关键**：SWE-bench 风格的"补丁是否合入"无法度量 ops 特有的失败模式——"自信的错误动作 + 大爆炸半径"。新一代 benchmark **以执行结果 + 安全权重为核心**。

### 趋势 6：开源生态 — HolmesGPT 成为新基准线

- **HolmesGPT** (CNCF Sandbox, 2025/10)：30+ 数据源、Operator Mode 24/7 后台、Skills 可扩展
- **K8sGPT**：规则扫描 + LLM 解释，作用域更窄
- **Kagent**：K8s 上的"宿主框架"，可托管 HolmesGPT 等子 Agent
- **OpenHands**：当修复=代码改动时的事实标准 (~77% SWE-Bench Verified)
- **AIEvo** (蚂蚁开源)：多 Agent 框架，SRE 7×24 待命场景

---

## 第三部分 · 厂商分阵营洞察

### 3.1 海外传统观测厂商 (Top 7)

| 厂商 | 旗舰产品 | 核心架构 | 差异化护城河 |
|---|---|---|---|
| **Datadog** | Bits AI SRE / Dev / Security (2025/12 LA, 2026/3 GA) | 多模型 + 自研 Toto 时序基模型 + Datadog MCP Server | 一手遥测数据广度 + Toto |
| **Dynatrace** | Davis CoPilot GA (2026/01) + Agentic Workflows | **Hypermodal AI** = Causal AI (Smartscape 拓扑) + Predictive + 生成式 | 拓扑图约束的因果 RCA，最强金融/合规市场 |
| **New Relic** | SRE Agent + Agentic Platform (2026/02/24) | 因果图 + 历史事故记忆 + 反模式库 + 原生 MCP | 最开放：no-code Agent Builder + Azure SRE Agent 集成 |
| **Splunk / Cisco** | AI Assistant + MCP Server GA (2026/02/04) + Cisco Foundation AI | Cisco Foundation-sec-8B + GPT-OSS + Data Fabric | 网络层遥测 + 安全调优自研模型 |
| **ServiceNow** | **Otto** (Knowledge 2026) + AIOps/SRE/Observability Agent | 多 Agent + Now Platform 工作流执行 + Moveworks 推理引擎 + AI Control Tower | **CMDB + 工作流 = 真正的执行权** (而非仅推荐) |
| **IBM** | watsonx Orchestrate + **Concert** + Bob (Think 2026) | 多厂商 Agent 编排 (A2A) + Concert Observe (Instana) + Operate (Cloud Pak) | "BYO Agent 治理"——唯一定位为控制平面 |
| **Elastic** | Elastic AI Agent (替代 AI Assistant) | LLM 无关 + Bedrock Claude + 索引 RAG | 开源分发 + 搜索基础 |

**这一阵营的共同动作 (2025-11 至 2026-05)**：
1. 全部上线 MCP Server
2. 全部把 "Chat 助手" 升级为"独立命名的 Agent" (Bits AI SRE / Davis CoPilot / Otto…)
3. 全部从"推荐"走向"自动执行 + 风险闸门"

### 3.2 AI-Native 初创阵营 (估值领跑者)

| 厂商 | 融资 | 最强招式 | 押注 |
|---|---|---|---|
| **Resolve AI** | A 轮 + 扩展共 $190M+，**估值 $1.5B** (Sequoia/Lightspeed/DST/Salesforce) | 多 Agent 并行假设 + Live Production Knowledge Graph + Resolve AI **Labs** | 域专模型 + 实时知识图谱 > 通用模型 + RAG |
| **Traversal** | $53M (Sequoia/Kleiner、**Amex Ventures**) | Production World Model™ + Causal Search Engine™ | 因果约束 > 纯 LLM 推理；金融场景 90%+ 准确率 |
| **Cleric** | $9.8M seed (Vertex/Zetta) | 自学习 SRE — 把每次事故抽象为环境无关 Skill | 持久化运维记忆是新护城河 |
| **NeuBird (Hawkeye)** | $19.3M (Xora) | A2A 协议 + 数据虚拟化 + 进 Azure SRE Agent 作 MCP server | 开放 Agent 生态 > 围墙花园 |
| **Parity** | n/a | K8s 专精 SRE Agent | 垂直深度 > 水平广度 |
| **OpenObserve / Hyground** | $10M / €3M | "Observability 3.0" / 主权数据 EU AI SRE | 主权数据合规、欧洲市场 |
| **PagerDuty** (incumbent-but-pivoted) | 上市公司 | Advance 多 Agent 套件 + SRE Agent (H2 2026 全自治)  | 16 年事故数据 + 排班/升级工作流 |
| **Aisera** | 已上市 / 私募 | Studio (Prompt/Event/Workflow) | 让客户在其平台上**自建** Agent |
| **Komodor (Klaudia)** | n/a | 50+ Specialized SME Agents 的扩展框架 | "微服务化的 Agent" |
| **Honeycomb** | n/a | Query Assistant + MCP | 增强 > 自治 (反主流选择) |
| **Grafana Labs** | 上市/估值 ~$6B | Cloud + AI 可观测 + **o11y-bench** + GCX CLI | 做"被任意 Agent 调用"的基础底座 |
| **Causely** | $8.8M seed (645 Ventures) | 边缘因果模型 + 隐私保留架构 | 因果图 > 关联分析 |
| **Edge Delta** | n/a | Telemetry Pipelines 4 月起免费 + AI Teammates | 重定价：按存储+Token，不按流量 |
| **Robusta/HolmesGPT** | CNCF Sandbox | 开源、LLM-agnostic、Operator Mode | 云原生 + 模型可移植 |

### 3.3 中国厂商阵营

#### 云厂商

| 厂商 | 产品/平台 | 大模型 | 关键战绩 |
|---|---|---|---|
| **阿里云** | Operation Intelligence (OI) + SLS + ARMS + 百炼 + **Qoder CN** | 通义 Qwen3 + DeepSeek | 6,000+ 企业部署，大客户 MTTR <15 min |
| **华为云** | 盘古 5.5 + **GaussDB Doer** 运维基模型 + 五大行业大模型 | 自研盘古 (昇腾算力) | 故障定位秒级，人效 +40%；信创全栈 |
| **腾讯云** | **bk-lite** (AI-first 蓝鲸) + 嘉为蓝鲸信创版 | 混元 + DeepSeek | 游戏 (IEG)、金融 (嘉为) |
| **百度智能云** | BCM + **ERNIE 5.1** (2026/05) 智能体平台 | 文心 5.1 (预训练成本仅同类 6%) | 千帆私有化交付 |
| **火山引擎** | **火山安全智能体** + **ArkClaw** (与中移联合) | 豆包 (日 50T Token) | **中石油运营效率 10×**；2026 MaaS 百亿目标 |

#### 专业厂商

| 厂商 | 旗舰 | 看点 |
|---|---|---|
| **擎创科技** | 夏洛克 AIOps (6 次 Gartner 入选) | 头部券商落地，告警-指标-日志-决策一体化 |
| **云智慧** | OMP 平台 + **Owl 大模型** + **Owl-Bench** (开源评测) | 联合北航；社区生态 (aiops.cn) |
| **博睿数据** | Bonree ONE 春季版接入 DeepSeek | 模型迭代效率 +40%、故障恢复 +60% |
| **必示科技 BizSeer** | 根因分析 + 自愈 | 清华裴丹团队，方法论领先 |
| **新华三 H3C** | U-Center 智能运维 | 信创基础设施"运维大脑" |
| **中兴 ZTE** | 网络/核心网运维大模型 | 通信行业 (运营商核心网故障机器人) |
| **蚂蚁集团** | AntMonitor + **AIEvo** (开源多 Agent 框架) | 100+ 业务域，峰值 20TB/min |
| **亚信科技** | AISWare AIOps Agents (白皮书) | 组件化、场景化输出 |

#### 金融行业重量级用例

- **中国银联** 私有化 **DeepSeek-V4** (2026/04, 昇腾)
- **江苏银行** 对账 Agent: 效率 +80%，年省 2,000 万；合同审核 4h → 15min
- **恒生电子** DeepSeek-R1 用于交易系统自愈

---

## 第四部分 · 共同点 vs. 差异化

### 4.1 全球共同点 (Convergence)

1. **Agent 命名独立化**: 所有厂商都给 Agent 起了名字 (Bits AI / Davis / Otto / Bob / Hawkeye / Klaudia / 夏洛克 / 盘古 Doer)，标志认知层从"功能"升级到"虚拟员工"
2. **MCP 标配** + **A2A 萌芽**
3. **多 Agent (Planner-Executor) 取代 Single Agent**
4. **Deterministic + LLM 混合**: 拓扑图 / 因果引擎 / 工作流引擎做约束层
5. **HITL 风险闸门**: 不是"是否"而是"哪一级"
6. **MTTR 25-50% 是新基准线**

### 4.2 海外 vs 中国 差异化

| 维度 | 海外 | 中国 |
|---|---|---|
| **部署形态** | SaaS 优先 | **私有化/信创为默认** (政务、金融、央企必备) |
| **底层模型** | 闭源 Claude/GPT | **多模型并存**: DeepSeek + Qwen + 盘古 + 文心 + 豆包 |
| **行业大模型** | 通用 + Prompt | **五大行业大模型** (华为)、安全垂直 (火山)、金融国企 (ArkClaw) |
| **集成深度** | OTel + MCP 标准协议 | + **CMDB + ITIL + 蓝鲸生态** + 知识图谱深耦合 |
| **数据资产** | 客户数据 | **国资云 / 自主可控**优先 |
| **价格模型** | Token + Seat | **打包年费**为主，按需调用为辅 |

### 4.3 海外内部分化 (三条路线)

- **数据派** (Datadog / Splunk-Cisco / Elastic)：靠一手遥测和领域基模型取胜
- **图论派** (Dynatrace / Traversal / Causely)：拓扑+因果约束 LLM
- **工作流派** (ServiceNow / IBM / PagerDuty)：占据"行动权"，让 Agent 真正闭环

---

## 第五部分 · 技术价值与"非显性竞争力"识别

针对 `/goal` 要求，深挖到价值点明确为止：

### 5.1 表层价值（已被市场普遍采纳，已不是差异化）

- 告警降噪 / NL 查询 / 摘要 / 文档生成 / 基础 RCA 建议

### 5.2 中层价值（当前竞争主战场）

| 价值点 | 谁在做 | 难度 |
|---|---|---|
| 自治响应 (Auto-Triage → Auto-Mitigate) | Datadog/Dynatrace/PagerDuty/ServiceNow | ★★★ |
| 多 Agent 并行假设 | Resolve, Komodor | ★★★ |
| MCP 工具生态 | 所有头部 | ★★ (已标准化) |
| 因果图 RCA | Dynatrace/Traversal/Causely | ★★★★ |

### 5.3 **深层价值（真正的护城河，未来 12-24 个月的胜负点）**

#### ① **Production World Model**（生产世界模型）
不是文档 RAG，不是日志 vector search，而是一个**持续更新的、机器可读的、覆盖代码/拓扑/部署/配置/历史故障**的统一模型。Resolve、Traversal、Dynatrace Smartscape、华为 GaussDB Doer 都在这条赛道。**它一旦建成，模型可以换，但数据资产无法被复制。**

#### ② **可复用的 Operational Memory**
不是"上次故障日志"的存储，而是**把每次事故抽象为环境无关的 Skill** (Cleric 范式) / **故障数据飞轮** (PagerDuty 16 年数据)。这种记忆的价值随时间复利增长，且**新进入者无法快速追上**。

#### ③ **执行权 (Action Authority) + 治理框架**
ServiceNow、IBM Concert、华为 "盘古 + ITIL" 的核心洞察：**真正难的不是诊断，而是被允许在生产系统上自动执行。** 拥有 CMDB、变更管理、ITIL 流程的人，才能让 Agent 真正闭环。这也是**为什么 ServiceNow 用 $2.85B 收购 Moveworks**——补齐推理层，自己已有执行权。

#### ④ **Agent 自身的可观测 (Meta-Observability)**
当 Agent 拥有 root 等价的权限时，**对 Agent 自身的监控就是新一代核心安全/运维需求**。OpenTelemetry GenAI Semconv + AgentSight (eBPF 边界追踪，<3% overhead) 是这个方向的开端。**会催生新的细分赛道：AgentOps。**

#### ⑤ **风险分级闸门 + 合规可追溯**
EU AI Act 2026/08 + 国内监管 → 任何接触生产的 Agent 必须可审计、可回滚、可分级授权。**GIRA / OEP 框架**会成为采购清单的硬指标。

#### ⑥ **领域 RL 后训练 + Skill 蒸馏**
Resolve AI Labs 公开宣布投入"domain-specific models, post-training systems, evaluation infrastructure"。**通用模型的能力提升放缓后，ops 专属的 SFT/RLHF/RL 微调将成为下一个差异化轴。**

### 5.4 价值点四象限（给本项目的战略锚点）

```
                    高重要 / 高壁垒
                          ▲
              ① World Model
              ② Operational Memory
              ③ Action Authority
              ⑥ Domain RL
       低易复制 ◄───┼───► 高易复制
              ⑤ Risk Gate
              ④ AgentOps               (中重要 / 中壁垒)
                          ▼
              MCP集成 / Chat Q&A / NL Query   (低壁垒，已商品化)
```

---

## 第六部分 · 对 AIOps-agent 项目的可执行启示

> 这一段是给本仓库 (`/home/user/AIOps-agent`) 的具体建议，不是市场报告内容。

1. **架构骨架**: LangGraph (工作流 + checkpointing) + Claude Agent SDK (深推理节点) 是当前 production-grade 组合。蚂蚁开源的 AIEvo 也可参考。
2. **模型策略**: 默认 Claude Sonnet 4.6 + Adaptive Thinking；深度 RCA 路径升级 Opus 4.7；私有化场景预留 DeepSeek-R1-Distill-Qwen-8B 通道。
3. **数据底座是最高优先级**: 在 `src/aiops_agent/models/` 下尽早规划 **Topology Graph** / **Incident Memory** schema，比写更多 tools 重要 10 倍。
4. **MCP 优先**: 所有外部集成 (Prometheus、kubectl、Slack、PagerDuty) 都通过 MCP server 暴露，而不是写 Python wrapper。
5. **HITL 风险闸门** 必须从第一版就内建，不能后加。参考 GIRA 论文的 risk-tier 设计。
6. **加一个 `evals/` 目录**: 接 SREGym / o11y-bench，不要等到模型选型时再补。
7. **观察自己的 Agent**: 用 OpenTelemetry GenAI Semconv 发射 `invoke_agent` / `execute_tool` span，这是合规、Debug、未来商业化都需要的资产。

---

## 附录 · 信息来源汇总

### 海外
- [Datadog Bits AI SRE](https://www.datadoghq.com/blog/bits-ai-sre-deeper-reasoning/)
- [Dynatrace Davis CoPilot GA](https://www.dynatrace.com/news/blog/announcing-general-availability-of-davis-copilot-your-new-ai-assistant/)
- [New Relic SRE Agent](https://docs.newrelic.com/docs/agentic-ai/sre-agent/overview/)
- [Splunk MCP Server](https://www.splunk.com/en_us/blog/platform/splunk-platform-building-the-data-foundation-for-agentic-ai.html)
- [ServiceNow Knowledge 2026 / Otto](https://newsroom.servicenow.com/press-releases/details/2026/ServiceNow-turns-enterprise-AI-chaos-into-control-with-the-platform-for-governed-autonomous-work/default.aspx)
- [IBM Think 2026 / Concert](https://www.ibm.com/new/announcements/ibm-announcements-at-think-2026)
- [Resolve AI Labs](https://resolve.ai/news/Series-A-extension-and-Resolve-AI-Labs)
- [Traversal x Amex](https://siliconangle.com/2026/03/04/exclusive-american-express-partners-invests-ai-operations-startup-traversal/)
- [Cleric self-learning SRE](https://cleric.ai/blog/cleric-launches-the-first-self-learning-ai-sre)
- [PagerDuty Memory Architecture](https://www.pagerduty.com/blog/ai/we-built-an-sre-agent-with-memory-and-its-transforming-incident-response/)
- [Grafana o11y-bench / GrafanaCON 2026](https://grafana.com/press/2026/04/21/grafana-labs-targets-the-ai-blind-spot-with-new-observability-tools-announced-at-grafanacon-2026/)
- [HolmesGPT CNCF](https://www.cncf.io/blog/2026/01/07/holmesgpt-agentic-troubleshooting-built-for-the-cloud-native-era/)

### 协议与学术
- [OpenTelemetry GenAI Semconv](https://opentelemetry.io/docs/specs/semconv/gen-ai/)
- [Rootly Sonnet 4.6 benchmark](https://rootly.com/blog/claude-sonnet-4-6-benchmark-results-and-lessons-for-ai-sre)
- [Anthropic SRE Claude postmortem (The Register)](https://www.theregister.com/2026/03/19/anthropic_claude_sre)
- [SREGym (arxiv 2605.07161)](https://arxiv.org/html/2605.07161v1)
- [GIRA / OEP (OpenReview)](https://openreview.net/forum?id=LBt5eX6OKx)
- [AgentSight eBPF (arxiv 2508.02736)](https://arxiv.org/abs/2508.02736)

### 中国
- [阿里云 OI 范式](https://www.cnblogs.com/alisystemsoftware/p/19605440)
- [华为盘古 5.5](https://www.huaweicloud.com/intl/zh-cn/news/20250620101057482.html)
- [博睿接入 DeepSeek](https://blog.csdn.net/BJ_Bonree/article/details/147050244)
- [文心 ERNIE 5.1 发布](https://ernie.baidu.com/blog/posts/ernie-5.1-0508-release/)
- [蚂蚁 AIEvo 开源](https://blog.csdn.net/SOFAStack/article/details/145293234)
- [银联 DeepSeek-V4](https://www.163.com/dy/article/KRM64L9S0514R9OJ.html)
- [中移 ArkClaw](https://finance.sina.cn/stock/jdts/2026-05-08/detail-inhxewef4216704.d.html)
- [2025 CCF AIOps 挑战赛](https://competition.aiops.cn/)
- [信通院 AI+运维报告](https://www.sohu.com/a/898043962_121757514)

---

*报告由 4-Agent 并行情报团队生成 (海外传统厂商 / AI-Native 初创 / 中国厂商 / 底层框架协议) ，最终由主 Agent 综合归纳。*
