"""装载 case → 跑 agent → 三层评分 → 出四象限报告。

agent 通过 ``agents.base.Agent`` 协议解耦：评测环境跑模拟 agent（sim），
生产接 relay 的 ReActAgent 适配器，两者实现同一 ``run`` 签名、复用同一套 proxy 与评分器。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol

import yaml

from .graders import grade_outcome, grade_rules, grade_trajectory
from .report import EvalReport, classify
from .script_proxy import ScriptProxy
from .tool_proxy import ToolProxy
from .trace import Trace


class AgentLike(Protocol):
    """被测 agent 协议：吃 case + 两个 proxy，吐 Step10 根因 JSON。"""

    def run(
        self, case: dict[str, Any], tools: ToolProxy, scripts: ScriptProxy
    ) -> dict[str, Any]: ...


def load_case(case_dir: Path | str) -> dict[str, Any]:
    """读取 ``case.yaml``。"""
    case_dir = Path(case_dir)
    with (case_dir / "case.yaml").open(encoding="utf-8") as fp:
        case: dict[str, Any] = yaml.safe_load(fp)
    case["_dir"] = str(case_dir)
    return case


def grade(
    case: dict[str, Any],
    trace: Trace,
    *,
    f1_gate: float = 1.0,
    decisive_gate: float = 1.0,
) -> EvalReport:
    """对一条已执行的 trace 跑三层评分并分类。可独立用于合成 trace 的单测。"""
    rules = grade_rules(trace.final_output, trace, case.get("rules", {}))
    trajectory = grade_trajectory(trace, case.get("reference_trajectory", []))
    expected = case.get("expected_root_cause", {}).get("causes", [])
    must_mention = case.get("expected_conclusion", {}).get("must_mention", [])
    outcome = grade_outcome(trace.final_output, expected, must_mention)
    status, attribution = classify(
        rules, trajectory, outcome, f1_gate=f1_gate, decisive_gate=decisive_gate
    )
    return EvalReport(
        case_id=case.get("case_id", "unknown"),
        status=status,
        attribution=attribution,
        rules=rules,
        trajectory=trajectory,
        outcome=outcome,
        trace_dict=trace.to_dict(),
    )


def run_case(
    case_dir: Path | str,
    agent: AgentLike,
    *,
    f1_gate: float = 1.0,
    decisive_gate: float = 1.0,
) -> EvalReport:
    """端到端跑一个 case 目录。"""
    case = load_case(case_dir)
    responses_dir = Path(case["_dir"]) / "responses"
    trace = Trace(case_id=case.get("case_id", "unknown"))
    tools = ToolProxy(responses_dir, trace)
    scripts = ScriptProxy(responses_dir, trace)

    final_output = agent.run(case, tools, scripts)
    trace.final_output = final_output
    trace.totals = {"n_tool_calls": len(trace.tool_calls)}

    return grade(case, trace, f1_gate=f1_gate, decisive_gate=decisive_gate)
