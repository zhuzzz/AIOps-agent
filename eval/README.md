# eval/ — efs-diagnosis 自动化评测内核（最小可运行）

relay AIOps 平台 **efs-diagnosis skill** 的回归测试内核。它把"业界成熟的诊断 Agent 评测范式"
（注入/盖章 oracle + 录制回放 + 三层评分 + 决定性证据轨迹）落成一套**今天就能 `pytest` 跑绿/跑红**
的代码。配两份文档：

- 📄 **`EVALUATION_PLAN.md`** — 完整评测方案（目标/标准/架构/数据/评分/路由/门禁/落地路线）。
- 📄 **`INDUSTRY_SURVEY.md`** — 业界如何为运维/Agent 场景做评测（AIOpsLab / ITBench / SREGym /
  RCAEval / τ-bench / TRAJECT-Bench / MCP-Bench / OTel / record-replay …，含引用）。

---

## 快速开始

```bash
cd eval
python -m pip install -r requirements.txt      # pytest + pyyaml

python run_demo.py        # 看四象限看板（无需 pytest）
pytest -s -v              # 10 个用例，全绿
```

`run_demo.py` 对**同一条 case、同一套评分器**喂入四种 agent 行为，输出：

| agent 行为 | 判定 | 含义 |
|---|---|---|
| 忠实诊断、看到 cpu_util 越界 | 🟢 GREEN | 真通过（门禁 ✅） |
| 跳过决定性步骤却猜对根因 | 🟡 YELLOW | **蒙对**：结果对但没走到证据（门禁 ❌） |
| 看了证据却报错实例 | 🔵 BLUE | 走对路结论错（门禁 ❌） |
| 正确但多报矛盾根因 | 🔴 RED | Tier1 门禁拦截（门禁 ❌） |

> 命门是**区分力**：只比最终答案的评测会把"蒙对"误判为通过；本内核准确标成 YELLOW 并挡在门外。

---

## 目录结构

```
eval/
├── EVALUATION_PLAN.md          # 完整方案
├── INDUSTRY_SURVEY.md          # 业界调研（含引用）
├── run_demo.py                 # 一键四象限演示
├── requirements.txt
├── pytest.ini
│
├── harness/                    # 评测内核
│   ├── trace.py                #   轨迹数据模型（对齐 OTel GenAI）
│   ├── tool_proxy.py           #   拦截面1：MCP 工具录制回放 + trace 记录器
│   ├── script_proxy.py         #   拦截面2：scripts/*.py + metrics_url 录放
│   ├── graders.py              #   三层评分：规则 / 轨迹 / 结果
│   ├── report.py               #   结果×轨迹四象限 + 分层归因
│   └── runner.py               #   装载 case → 跑 agent → 评分 → 报告
│
├── agents/
│   ├── base.py                 #   被测 agent 协议 + 真实 relay 接入说明(seam)
│   └── sim_efs_agent.py        #   模拟 agent（自测内核；生产用 RelayAgentAdapter 替换）
│
├── routing/                    # 路由层评测（评"是否选对 skill"）
│   ├── router.py               #   关键词/资源类型路由器（可换向量召回+LLM 仲裁）
│   └── grade_routing.py        #   HIT/MISS/MISROUTE/CORRECT_REJECT
│
├── cases/
│   ├── efs-ecs-cpu-001/        # 第一条黄金 case（ECS CPU 瓶颈）
│   │   ├── case.yaml           #   输入 + SRE盖章根因 + 参考轨迹 + 规则 + 门禁
│   │   ├── responses/*.json    #   11 个录制响应（仅 1 个决定性越界，其余应抓真实）
│   │   └── MANIFEST.md
│   └── routing/router_cases.yaml
│
└── tests/
    ├── test_efs_ecs_cpu_001.py        # 端到端 GREEN
    ├── test_graders_discrimination.py # 四象限区分力 + 门禁 + 集合评分
    └── test_routing.py                # 路由四类判定
```

---

## 三条设计铁律（区别于"管道对、评测无效"的方案）

1. **ground truth 由 SRE 盖章，绝不从告警指标反推**——告警指标只是症状（IO 时延高），
   根因要靠下游 cpu_util/await/qos 判定。反推 = 循环论证。
2. **必评轨迹、盯决定性证据**——只比最终答案无法区分"真通过"与"蒙对"。
3. **按调用精确匹配键 + 双拦截面**——`cmc__{ns}__{metric}` 解决撞键；`ScriptProxy` 覆盖
   tool-proxy 拦不到的 `scripts/*.py` + `metrics_url`。

---

## 接入真实 relay

把 `SimEfsAgent` 换成实现同一 `run(case, tools, scripts)` 协议的 `RelayAgentAdapter`
（见 `agents/base.py`）：把 relay 的 `mcp_tool_proxy` 切回放模式指向 `ToolProxy.call`、
脚本与 `metrics_url` 指向 `ScriptProxy`，触发 skill、取 Step10 输出即可。
**评分器、case、四象限、门禁全部不变。**
