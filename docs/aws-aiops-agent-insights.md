# AWS 运维(AIOps/DevOps)智能体体系深度洞察

> **文档类型**:技术 + 产品洞察报告
> **覆盖范围**:AWS 运维智能体的产品/技术分层、与云服务的交互机制、业界趋势、通用 Agent 对比
> **数据时效**:2024–2026 年公开资料(AWS re:Invent 2024/2025、官方文档/博客/What's New)
> **最后更新**:2026-06-26

---

## 关于本报告的方法与置信度

本报告由多源检索 + 对抗式事实核查生成:

- **AWS 自身体系(第一~三章)**:基于 106 个检索子任务、24 个一手来源、25 条经 **3 票对抗式验证**(需 2/3 反驳才否决,最终 25/25 确认)的高置信结论,主要引自 **AWS 官方文档 / 博客 / What's New**。标记为 **【高置信】**。
- **业界对比与通用趋势(第四~五章)**:来自抓取阶段提取、但未进入最终验证批次的一手来源(Microsoft / Google / Datadog / PagerDuty 官方页 + Anthropic / Linux Foundation / arXiv)+ 行业公开资料。标记为 **【中置信】**。
- **厂商自报性能数字**(如"MTTR 降低 X%""RCA 准确率 Y%")**未经独立基准验证**,本报告刻意不作为结论。
- **GA 日期口径**在不同 AWS 渠道存在表述差异,以官方为准。

完整来源列表见[附录 A](#附录-a来源清单)。

---

## 目录

1. [摘要(TL;DR)](#摘要tldr)
2. [产品形态与分层](#一产品形态与分层)
3. [技术形态与分层](#二技术形态与分层)
4. [AWS 云服务与运维智能体的关系 ——「手和眼」](#三aws-云服务与运维智能体的关系--手和眼)
5. [业界运维/AIOps 智能体趋势](#四业界运维aiops-智能体趋势)
6. [通用智能体趋势 vs 云厂商运维智能体](#五通用智能体趋势-vs-云厂商运维智能体)
7. [对 AIOps-agent 项目的启示](#六对-aiops-agent-项目的直接启示)
8. [附录:置信度、来源与未决问题](#附录)

---

## 摘要(TL;DR)

AWS 没有「一个运维智能体」,而是一套 **四层栈**。理解它的关键是分清「谁是平台、谁是运行时、谁是面向人的助手、谁是干活的场景 Agent」:

```
┌─────────────────────────────────────────────────────────────────────┐
│  L4 场景智能体   AWS DevOps Agent(7×24 自主 SRE 队友,re:Invent'25   │
│  (Scenario)      预览 / 2026 GA)、CloudWatch investigations(RCA)    │
├─────────────────────────────────────────────────────────────────────┤
│  L3 面向用户助手  Amazon Q Developer / Q Business(对话式助手)        │
│  (Assistant)     DevOps Guru(ML 异常检测,前代 AIOps)               │
├─────────────────────────────────────────────────────────────────────┤
│  L2 Agent 运行时  Amazon Bedrock AgentCore(2025-10 GA)               │
│  (Runtime)       Runtime/Memory/Gateway/Identity/Observability        │
│                  /Browser/Code-Interpreter + Policy/Evaluations        │
├─────────────────────────────────────────────────────────────────────┤
│  L1 模型平台      Amazon Bedrock(Claude/Nova/Llama/Mistral... 托管)  │
│  (Model)                                                              │
└─────────────────────────────────────────────────────────────────────┘
        ↓ 通过 IAM(身份/权限)+ CloudWatch(眼)+ SSM(手)+ Gateway(工具)
┌─────────────────────────────────────────────────────────────────────┐
│  云控制面 & 数据面:IAM · CloudWatch · SSM · EC2/EKS · Lambda · ...    │
└─────────────────────────────────────────────────────────────────────┘
```

**一句话**:Bedrock 提供模型,AgentCore 提供企业级 Agent 运行时(记忆/网关/身份/观测/护栏),Amazon Q 是面向人的对话助手,而 **AWS DevOps Agent** 是构建在 AgentCore 之上、把 **CloudWatch 当眼睛、SSM 当手、IAM 当权限边界** 的具体运维场景智能体。

**核心判断**:AWS 的差异化不在「模型多聪明」,而在 **把 Agent 焊死在云原生控制面上**——原生身份(IAM)、原生观测(CloudWatch)、原生执行(SSM)、原生护栏(Policy→Cedar)。这是纯第三方 Agent 在结构上做不到的「特权视角」。

---

## 一、产品形态与分层

### 1.1 四层各是什么

| 层 | 产品 | 形态 | 定位 | 状态 |
|---|---|---|---|---|
| **L1 模型平台** | **Amazon Bedrock** | 托管基础模型 API | 提供 Claude、Nova、Llama、Mistral 等模型推理 | GA |
| **L2 Agent 运行时** | **Amazon Bedrock AgentCore** | 模型/框架无关的 Agent 基础设施(7+ 模块化服务) | 企业级「造 Agent / 跑 Agent / 运营 Agent」的底座 | **2025-10 GA** |
| **L3 面向用户助手** | **Amazon Q Developer / Q Business** | 对话式 Copilot | 给「人」用的 AI 助手(编码、问答、运维问询) | GA |
| | **Amazon DevOps Guru** | ML 异常检测服务 | 前代 AIOps:无 LLM 的统计/ML 异常与告警 | GA(老一代) |
| **L4 场景智能体** | **AWS DevOps Agent** | 自主多步 Agent | 7×24 自主分诊/RCA/提议修复的「SRE 队友」 | **re:Invent'25 预览,2026 GA** |
| | **Amazon CloudWatch investigations**(前 *Amazon Q Developer operational investigations*) | 运维调查 Agent | 在 CloudWatch 内做 RCA、关联信号、建议补救 | **2024-12 预览 → 2025-06 GA 改名** |

### 1.2 几个最容易混淆的点(重点澄清)【高置信】

**① AgentCore ≠ 老的「Bedrock Agents」。**
Bedrock 早期有一个 "Agents for Bedrock" 功能;2025 年 AWS 把企业级 Agent 能力独立成 **AgentCore** 一整套服务(运行时、记忆、网关、身份、观测、浏览器、代码解释器),而且 **模型和框架无关**——可以跑 CrewAI / LangGraph / LlamaIndex / Strands,模型可以是 Claude/Nova/Llama/Mistral/OpenAI/Gemini,**无论是否在 Bedrock 内**。这是它从「Bedrock 的一个子功能」升级为「通用 Agent 平台」的关键。

**② "Amazon Q Developer operational investigations" 已经改名了。**
这个生成式 AI 运维调查能力 2024-12 以 Q Developer 预览,**2025-06 GA 时更名为 "Amazon CloudWatch investigations"**——能力下沉成了 CloudWatch 的原生 AI。所以同一个东西在不同时间点有两个名字。

**③ AWS DevOps Agent 是一个独立产品,不是 Amazon Q 的一个模式。**
它有独立产品页、独立定价、独立 FAQ,被 AWS 定位为 "frontier agent"。它聚焦 **运维/SRE(MTTR、可靠性)**,而 Q Developer 是 **编码助手**——在 DevOps Agent 的工作流里,Q Developer 只是被当作「生成代码修复」的互补工具被调用。

**④ DevOps Guru 是「前 LLM 时代」的 AIOps。**
它靠 ML/统计做异常检测和告警,没有 LLM 推理、不会自主多步调查。它和 DevOps Agent 是两代东西——DevOps Guru 是「报警器」,DevOps Agent 是「会自己去查案的侦探」。

### 1.3 产品竞争力

- **生态绑定即护城河**:AWS 的运维 Agent 天然能访问你已经在用的 IAM、CloudWatch、SSM、EKS——这是纯第三方 Agent 拿不到的「特权视角」(详见第三章)。
- **覆盖面**:DevOps Agent 明确覆盖 **AWS + 多云 + 本地(on-prem)**,不是只锁 AWS。
- **人审护栏内建**:生产环境的修复是「提议 → 人审 → 走既有变更流程执行」,而非莽撞自动执行——对企业可靠性是卖点而非短板。

---

## 二、技术形态与分层

### 2.1 AgentCore 的模块化技术栈(技术核心)【高置信】

AgentCore 把「做一个生产级 Agent 需要的非模型部分」拆成独立服务,**可单独用、可组合用**:

| 模块 | 作用 | 运维场景意义 |
|---|---|---|
| **Runtime** | Agent 执行运行时(会话隔离、扩缩容) | 跑长时调查任务、并发事件处理 |
| **Memory** | 短期 + 长期记忆 | 跨事件记住历史、拓扑、过往 RCA |
| **Gateway** | 把 API/Lambda/Smithy → **MCP 工具** | 把 AWS 服务变成 Agent 能调的「手」(关键) |
| **Identity** | OAuth/IAM 身份与授权 | 入站/出站双层鉴权,权限边界 |
| **Observability** | 追踪/调试/监控,落 CloudWatch,OTEL 兼容 | 看 Agent 自己干了什么(可审计) |
| **Browser** | 托管无头浏览器 | 操作 Web 控制台/无 API 的系统 |
| **Code Interpreter** | 沙箱代码执行 | 跑分析脚本、数据处理 |
| **Policy**(2025-12 预览→2026 GA) | 自然语言→**Cedar** 策略,**实时拦截每次工具调用** | Agent 不越权的实时护栏 |
| **Evaluations**(2025-12 预览) | 13 个内置评估器 + 自定义打分 | Agent 质量回归、可信度度量 |

> **AWS DevOps Agent 就是直接构建在 AgentCore 之上**,复用它的 Memory、Policy、Evaluations、Observability、Identity、Gateway——这就是「L2 运行时 → L4 场景 Agent」的真实依赖关系。

### 2.2 工具调用 / MCP / A2A 三件套【高置信】

- **Gateway = 把 AWS 变成工具的转换器**:把现有 **REST API(OpenAPI)、Smithy 模型(AWS 服务的原生 IDL)、Lambda 函数** 自动转成 **MCP 兼容工具**,自己充当集中式 MCP 工具服务器,并内置常见 AWS 服务的 Smithy 模型。**这就是「AWS API 如何暴露成 Agent 工具」的官方机制。** Gateway 支持 OpenAPI / Smithy / Lambda 三类工具输入。
- **原生 MCP 支持**:Gateway 原生支持 Model Context Protocol(从 `2025-03-26` 版本起,现已扩展到 `2025-06-18`/`2025-11-25`),用 streamable HTTP 传输,自己是 MCP 授权流里的 **OAuth resource server**;还能通过 `SynchronizeGatewayTargets` API **把外部 MCP server 注册进来**(协议握手 + `tools/list` 分页索引),聚合成单一 MCP 端点。
- **A2A(Agent-to-Agent)**:DevOps Agent 可通过 **A2A 协议** 连接你自己的子 Agent(Bedrock 或第三方框架构建的);headless 模式下还能被你已有的工具/Agent 经 A2A 或 MCP 反向调用。

> **技术含义**:**MCP 解决「Agent↔工具」,A2A 解决「Agent↔Agent」**,AWS 两个都接,把运维 Agent 放进了开放的 agentic 协议生态。

### 2.3 可观测性:CloudWatch 是观测主干,但开放 OTEL【高置信】

AgentCore Observability 提供生产级 **逐步可视化 Agent 执行路径、审计中间输出、定位瓶颈/失败**;指标/追踪/日志 **默认落到 Amazon CloudWatch**(关键指标:session count、latency、duration、token usage、error rates),同时以 **标准 OTEL 兼容格式**(经 AWS Distro for OpenTelemetry / OTLP)导出,可对接 Langfuse、Datadog 等第三方栈。**既绑生态又不锁死。**

### 2.4 技术竞争力小结

| | 内容 |
|---|---|
| **强** | 模块化(按需取用)、模型/框架无关、原生 MCP+A2A、IAM 级权限护栏、Policy 实时拦截、观测落 CloudWatch 又兼容 OTEL |
| **弱/待证** | Memory 在长事件链中的机制细节、端到端「自主执行」的边界(生产仍以人审为主)、厂商自报性能数字缺独立验证 |

---

## 三、AWS 云服务与运维智能体的关系 ——「手和眼」

> 本章是本报告重点。AWS 运维 Agent 的本质是:**用 LLM 做推理/规划,用云原生服务做感知和执行。**

```
                        ┌──────────────────────────┐
                        │   运维 Agent(LLM 推理)   │
                        │  观察→假设→检验→行动→复盘  │
                        └─────────────┬────────────┘
              ┌──────────────┬────────┼────────┬──────────────┐
              ▼ 眼           ▼ 手      ▼ 边界   ▼ 工具暴露      ▼ 自审
        ┌──────────┐  ┌──────────┐ ┌──────┐ ┌──────────┐ ┌──────────┐
        │CloudWatch│  │   SSM    │ │ IAM  │ │ Gateway  │ │  Agent   │
        │指标/日志 │  │Automation│ │ Role │ │ →MCP工具 │ │ Observ.  │
        │/告警/X-Ray│ │/RunCommand│ │+SigV4│ │+ MCPserver│ │ →CloudW. │
        └────┬─────┘  └────┬─────┘ └──┬───┘ └────┬─────┘ └──────────┘
             ▼             ▼          ▼          ▼
        ┌────────────────────────────────────────────────────┐
        │  资源:EC2 / EKS·K8s / 容器 / Lambda / DynamoDB...  │
        └────────────────────────────────────────────────────┘
```

### 3.1 IAM = 身份与权限边界(谁能干什么)【高置信】

- AgentCore Identity 用 **OAuth 标准** 做工具访问鉴权;Gateway 实现 **双层鉴权**:
  - **入站**(进 Gateway):OAuth 验证,支持 3LO(授权码流)与 2LO(客户端凭证流)。
  - **出站**(到 Lambda / Smithy 等 AWS 目标):**基于 IAM 的授权**——Gateway 假定一个你配置的 **IAM 角色**,用 **SigV4 签名** 请求,凭证经 AgentCore Identity 的 resource credentials provider 管理。
- 对外部 MCP server 的出站授权支持四种:No-auth(不推荐)、OAuth(2LO/3LO)、**IAM(SigV4,用 gateway 服务角色)**、API key。
- 网络面支持 **VPC + AWS PrivateLink** 保证私密。

> **这就是「原生 IAM 身份/权限边界被接进 Agent 工具调用路径」的技术实现。** Agent 不是拿一把万能钥匙,而是带着一个被 IAM 策略约束的角色去调用——越权在 IAM 层就被拒。

### 3.2 CloudWatch = 眼(感知/观测)【高置信】

- **被观测对象**:指标、日志组、告警、(配合 X-Ray)追踪。
- **触发器**:典型链路里,**CloudWatch 告警(如 5xx 升高)就是 Agent 调查的起点**。
- **Agent 自身可观测**:AgentCore Observability 把 Agent 的执行轨迹也写回 CloudWatch——既看被运维的系统,也看 Agent 自己。
- **MCP 封装**:AWS 还发布了 **CloudWatch MCP server 和 Application Signals MCP server**,把「读指标/日志/告警」标准化成 MCP 工具(这是「用 MCP server 封装 AWS 服务」的官方实例)。

### 3.3 SSM(Systems Manager)= 手(执行/补救)【高置信】

- **执行层是 SSM Automation runbook**:CloudWatch investigations 在补救阶段,会针对它的假设 **提议 SSM Automation runbook**,取材自 AWS 库中 **400+ AWS 编写 + 数千客户编写** 的 runbook;用户可「View runbook」、审参数、预览执行后再跑。
- 每个 runbook 定义了 SSM 实际执行的动作(重启、扩容、回滚、改配置…)。
- **为什么是 SSM 而不是 SSH**:SSM 走 IAM 鉴权、有审计、不需要开 22 端口、对 EC2/混合节点统一——**它是 AWS 给 Agent 准备的「安全的手」**。

### 3.4 EC2 / EKS / 容器 = 被观测、被操作的对象【高置信】

- DevOps Agent 通过 **自动发现跨账户云资源**(容器、网络组件、日志组、CloudWatch 告警、部署)**构建应用资源拓扑**。
- 对 **Kubernetes/EKS 集群、Pod 日志、集群事件** 做 **特权内省**(覆盖公有 + 私有环境)——这是外部第三方工具拿不到的视角。
- **Agent Spaces** 提供跨账户资源访问与调查。

### 3.5 端到端技术交互链路(把上面串起来)【高置信】

以官方演示的事件为例:

```
① CloudWatch 告警:5xx 错误升高              ← 眼(CloudWatch)
        ↓ 触发
② 自动发现资源拓扑(容器/EKS/日志组/告警/部署) ← 眼(资源发现 + 特权内省)
        ↓
③ 跨日志/指标/部署历史 系统化检验假设         ← 推理(LLM,经 Memory 记上下文)
        ↓ 定位
④ DynamoDB 写限流,由近期一次代码部署引起      ← 关联
        ↓ 关联代码
⑤ 查 GitHub/GitLab/Azure DevOps 近期合并,
   对齐部署时间戳与指标异常                   ← 工具(经 Gateway/MCP/A2A)
        ↓ 产出
⑥ 把完整 RCA + 缓解建议(扩容或回滚)发到 Slack ← 输出
        ↓ 提议(非自动执行)
⑦ 工程师审核/精炼 → 走既有变更管理流程执行     ← 手(SSM runbook)+ 人审护栏
   (全过程演示约 4 分钟;每次工具调用受 Policy→Cedar 实时拦截)
```

**贯穿全程的护栏**:AgentCore **Policy** 把团队用自然语言写的治理策略自动转成 **Cedar**(AWS 开源、已入 CNCF 的授权语言),在 Gateway 上 **实时拦截每一次工具调用** 确保不越界;**Evaluations**(13 个内置评估器)持续打分,结果汇到 CloudWatch 仪表盘。

---

## 四、业界运维/AIOps 智能体趋势

> **置信度:中。** 以下来自抓取阶段提取的一手来源(Microsoft / Google / Datadog / PagerDuty 官方),但未进入本轮 25 条对抗式验证批次,数字以官方页为准。

### 4.1 三大云的运维 Agent 几乎「同形态收敛」

| 厂商 | 产品 | 关键事实 | 眼(观测) | 手/护栏 |
|---|---|---|---|---|
| **AWS** | DevOps Agent + CloudWatch investigations | 构建在 AgentCore;预览'25/GA'26 | CloudWatch | SSM runbook;Policy(Cedar);人审 |
| **Microsoft** | **Azure SRE Agent** | **2026-03-10 GA**,"AI 运维队友" | Azure Monitor / Log Analytics / App Insights,受 **Azure RBAC** 角色约束 | **两级自治**:Autonomous mode 有权限时可自主缓解;可经 **Remote MCP** 接 Dynatrace/NewRelic/Datadog |
| **Google** | **Gemini Cloud Assist** | 配 **Gemini 3**,从基础设施信号关联到应用代码 | Cloud Logging/Monitoring | 经 **tool calls 并行检验多假设** 做 RCA |

**关键观察:三家结构惊人一致**——都是「告警触发 → 关联遥测 → 并行检验假设 → RCA → 提议/执行补救」,都用 **各自的 RBAC/IAM 做权限边界**,都用 **各自的监控栈做眼睛**,都在 **接 MCP 接第三方**。AWS 用 IAM+CloudWatch+SSM,Azure 用 RBAC+Azure Monitor,GCP 用 IAM+Cloud Ops。**云厂商运维 Agent 的「形态战争」已经收敛,差异在生态深度和自治胆量。**

> 值得注意:**Azure SRE Agent 明确给了 "Autonomous mode"(有权限时自主改资源)**,在「自主执行」上比 AWS 当前公开的「提议+人审」更激进——这是一个真实的产品哲学分叉点。

### 4.2 运维平台(非云厂商)也在 Agent 化

- **Datadog Bits AI SRE**:自主 on-call 队友,**被 page 后无需任何初始 prompt 就自主开查**,常在工程师打开电脑前就给出疑似根因。
- **PagerDuty**:把 Operations Cloud 定位为 agentic 运维的「**system of intelligence and action**」,新增 **30+ AI 伙伴(11 类)**、扩展 **700+ 集成**——走「事件指挥 + Agent 生态聚合」路线。
- **ServiceNow**(综合公开资料,置信度中):用 **Now Assist / AI Agents** 把 ITSM 工单、变更、CMDB 与 Agent 编排打通,强在「流程/工单」侧而非「基础设施信号」侧。

**趋势判断**:监控平台(Datadog)从「看板」走向「自主 on-call」;事件平台(PagerDuty)从「叫人」走向「编排 Agent 群」;ITSM(ServiceNow)从「开单」走向「自动履约」。**每一类运维工具都在长出 Agent。**

---

## 五、通用智能体趋势 vs 云厂商运维智能体

> **置信度:中**(通用趋势部分有一手来源:Anthropic 工程博客、Linux Foundation、arXiv;对比分析为综合判断)。

### 5.1 通用 Agent 的技术趋势(方向盘)

1. **Agentic 架构成熟**:从「单次问答」到「观察 → 规划 → 行动 → 反思」的多步自主循环。
2. **多 Agent 协作(orchestrator-worker)**:Anthropic 公开的多 Agent 研究系统用 **主 Agent(Opus 4)规划 + 派生 3–5 个子 Agent(Sonnet 4)并行探索**,内部评测 **比单 Agent 高 90.2%**——「主管+工人」成为复杂任务的主流范式。
3. **协议标准化**:**MCP 成为事实标准**(被调研的 30 个 agentic 产品里 **20/30 支持 MCP**,被称为「AI 的 USB-C」);**A2A 仍偏早期**(仅 **6/30 支持,且全是企业平台**)。**MCP 解决工具,A2A 解决 Agent 互联**,后者刚起步。
4. **中立标准化推进**:Linux Foundation 于 **2025-12-09 成立 Agentic AI Foundation(AAIF)**,托管开源 agentic 项目——信号是「去厂商锁定」。
5. **长期记忆 + reasoning/planning**:记忆从「上下文窗口」走向「持久化检索」,推理走向显式规划与自我纠错。

### 5.2 通用 Agent vs 云厂商运维 Agent —— 异同对比

| 维度 | 通用 Agent | 云厂商运维 Agent | 差异本质 |
|---|---|---|---|
| **身份/权限** | API key / OAuth,粒度粗 | **原生 IAM/RBAC 角色 + SigV4 + Policy(Cedar)** | 运维 Agent **把权限焊在云控制面**,最小权限 + 可审计 |
| **可观测性** | 自建或第三方,通用 | **原生 CloudWatch/Azure Monitor**,且 Agent 自身轨迹也落同一栈 | 运维 Agent **观测对象和自我观测同源** |
| **与服务集成** | 靠 MCP/插件「够得着」 | **特权内省**(EKS/Pod/跨账户),外部工具拿不到 | 运维 Agent 有 **生态特权视角** |
| **执行/护栏** | 多为建议,执行靠人接 | **SSM runbook 等结构化执行 + 人审/Policy 实时拦截** | 运维 Agent 在 **高风险面更强调可逆与审计** |
| **可靠性诉求** | 尽力而为 | **MTTR/可用性是 KPI**,错一次代价高 | 运维 Agent **不能「创造性发挥」** |
| **协议** | MCP 普及、A2A 早期 | 同样收敛到 MCP+A2A | **趋同**——这是融合点 |

### 5.3 核心判断

- **通用 Agent 的「上限」由模型推理决定;运维 Agent 的「下限」由权限边界、可逆性和可审计决定。** 后者宁可少做、做对、可回滚,也不要莽撞。
- **二者正在「协议层融合、信任层分叉」**:都用 MCP/A2A 连工具连 Agent(融合);但运维 Agent 多压了一层「IAM 身份 + Policy 护栏 + 人审 + 结构化执行」(分叉)。
- **云厂商的真护城河不是模型,是「特权视角 + 原生控制面」**:Agent 能以一个受 IAM 约束的角色,既看到你账户里的一切(CloudWatch/EKS 内省),又能通过 SSM 安全地动手——这是纯第三方 Agent 结构上做不到的。

---

## 六、对 AIOps-agent 项目的直接启示

结合本仓库 `CLAUDE.md` 规划的架构(`tools/`、`integrations/`、`llm/`、Agent loop),可借鉴:

1. **把「权限边界」当一等公民**:学 AWS 的双层鉴权——入站认证 + 出站用 **受限角色 + SigV4** 调云 API。不要让 Agent 持长期宽权限凭证。
2. **工具层走 MCP**:把对 CloudWatch/SSM/K8s 的访问封成 **MCP server**(AWS 已有 CloudWatch / Application Signals MCP server 可直接复用),而不是手写一堆 SDK 胶水——和 `tools/` 的设计天然契合。
3. **「眼-手」分离 + 人审护栏**:观测(只读)与执行(可写)分权,执行走 **结构化 runbook + 人审**,而非让 LLM 直接拼 shell——这也呼应 `CLAUDE.md` 的安全规范(「never execute unsanitized input,用参数列表」)。
4. **Agent 自身可观测**:把 Agent 的执行轨迹(每步工具调用、token、延迟)也落进可观测栈(OTEL 兼容),便于审计和回归。
5. **关注 A2A**:若未来要做「主管 Agent 派生子 Agent」,MCP(工具)+ A2A(Agent 互联)是正在收敛的标准,值得预留接口。

---

## 附录

### 附录 A:来源清单

**高置信(AWS 核心,经 3 票对抗验证)主要来源:**

- AWS DevOps Agent 产品页 — https://aws.amazon.com/devops-agent/
- 《Leverage Agentic AI for Autonomous Incident Response with AWS DevOps Agent》(AWS DevOps Blog) — https://aws.amazon.com/blogs/devops/leverage-agentic-ai-for-autonomous-incident-response-with-aws-devops-agent/
- 《Amazon Bedrock AgentCore is now generally available》(AWS ML Blog) — https://aws.amazon.com/blogs/machine-learning/amazon-bedrock-agentcore-is-now-generally-available/
- AgentCore 开发者文档(What is / Gateway / Observability / MCP targets / Outbound auth) — https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/what-is-bedrock-agentcore.html
- 《Introducing Amazon Bedrock AgentCore Gateway》(AWS ML Blog) — https://aws.amazon.com/blogs/machine-learning/introducing-amazon-bedrock-agentcore-gateway-transforming-enterprise-ai-agent-tool-development/
- AgentCore Gateway — 外部 MCP server 集成文档 — https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/gateway-target-MCPservers.html
- AgentCore Observability 文档 — https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/observability.html
- 《Investigate and remediate operational issues with Amazon Q Developer》(AWS Blog) — https://aws.amazon.com/blogs/aws/investigate-and-remediate-operational-issues-with-amazon-q-developer/
- CloudWatch investigations GA(What's New,改名证据) — https://aws.amazon.com/about-aws/whats-new/2025/06/ga-accelerate-troubleshooting-amazon-cloudwatch-investigations/
- AgentCore Policy & Evaluations 预览(What's New) — https://aws.amazon.com/about-aws/whats-new/2025/12/amazon-bedrock-agentcore-policy-evaluations-preview/
- AgentCore Policy 自然语言→Cedar 文档 — https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/policy-natural-language.html
- 《Enhance your AIOps: CloudWatch and Application Signals MCP servers》(AWS Cloud Ops Blog) — https://aws.amazon.com/blogs/mt/enhance-your-aiops-introducing-amazon-cloudwatch-and-application-signals-mcp-servers/
- AWS DevOps Agent 自定义 Agent(What's New,A2A/headless) — https://aws.amazon.com/about-aws/whats-new/2026/06/aws-devops-agent-custom-agents/
- AgentCore GA(What's New) — https://aws.amazon.com/about-aws/whats-new/2025/10/amazon-bedrock-agentcore-available/

**中置信(业界 / 通用,未进最终验证批)来源:**

- Azure SRE Agent GA — https://techcommunity.microsoft.com/blog/appsonazureblog/announcing-general-availability-for-the-azure-sre-agent/4500682
- Azure SRE Agent 自动化/集成/扩展 — https://techcommunity.microsoft.com/blog/appsonazureblog/reimagining-ai-ops-with-azure-sre-agent-new-automation-integration-and-extensibi/4462613
- Gemini Cloud Assist(Google Cloud Blog) — https://cloud.google.com/blog/products/application-development/gemini-cloud-assist-at-next26
- Datadog Bits AI SRE — https://www.datadoghq.com/blog/bits-ai-sre/
- PagerDuty AI 生态扩展 — https://www.pagerduty.com/newsroom/pagerduty-expands-ai-ecosystem-to-supercharge-ai-agents/
- Anthropic《How we built our multi-agent research system》 — https://www.anthropic.com/engineering/multi-agent-research-system
- Linux Foundation Agentic AI Foundation(AAIF) — https://www.linuxfoundation.org/press/linux-foundation-announces-the-formation-of-the-agentic-ai-foundation
- arXiv(MCP / agentic 互操作综述) — https://arxiv.org/html/2505.02279v1

### 附录 B:重要边界(别被带偏)

- DevOps Agent 生产环境修复是 **「提议 + 人审执行」**,不是全自主。
- **GA 日期口径有出入**:AgentCore 2025-10 GA 确切;DevOps Agent 各渠道表述 2026-03/04/06 不一,以官方为准。
- 厂商自报数字(MTTR、RCA 准确率)**未经独立验证**,本报告未采纳为结论。
- Gateway 出站 IAM/SigV4 仅适用于 **原生校验 SigV4 的 AWS 目标**(AgentCore Runtime/Gateway、API Gateway、Lambda Function URL),**直连 EC2/ALB 不支持**。
- 预览期精确品牌为 "Amazon Q Developer operational investigations"(Q Developer 内的能力),而非整条 "Amazon Q Developer" 产品线。

### 附录 C:未决问题(若要深挖建议补研究)

1. **业界横向对比缺口**:Azure / GCP / Datadog / PagerDuty / ServiceNow 的 agent 化能力在 **权限模型与护栏** 上的细节,缺独立交叉验证。
2. **Memory 机制**:AgentCore Memory 在 DevOps Agent 长事件链中如何承载跨事件长期记忆/上下文(短/长期、事件历史检索、跨账户隔离)。
3. **自主闭环边界**:DevOps Agent 从「提议」走向「自主执行」补救的 **条件 / 账户 / 变更窗口** 与审批流如何落地;headless 模式与 Agent Spaces 的权限模型。

---

*本报告基于 2024–2026 年公开资料生成,关键事实已对抗式核查。AWS 产品演进迅速,使用前请以官方文档为准。*
