"""区分力：评分器必须把"真通过/蒙对/走对路结论错/跑偏/门禁失败"分开。

这是整套评测的命门——一个只会比最终答案的评测，无法区分 GREEN 与 YELLOW(蒙对)。
"""

from pathlib import Path

import pytest

from agents.sim_efs_agent import SimEfsAgent, build_root_cause_output
from harness.report import Status
from harness.runner import grade, load_case, run_case
from harness.trace import ToolCall, Trace

CASE = Path(__file__).resolve().parents[1] / "cases" / "efs-ecs-cpu-001"


@pytest.mark.parametrize(
    "behavior, expected",
    [
        ("faithful", Status.GREEN),  # 结论对 + 走到决定性证据
        ("skip_decisive", Status.YELLOW),  # 结论对但没看证据 → 蒙对
        ("wrong_instance", Status.BLUE),  # 看了证据却报错实例 → 走对路结论错
        ("contradiction", Status.RED),  # 多报矛盾根因 → Tier1 门禁
    ],
)
def test_four_quadrants(behavior: str, expected: Status) -> None:
    report = run_case(CASE, SimEfsAgent(behavior))
    print(f"\n[behavior={behavior}]\n" + report.summary())
    assert report.status is expected


def test_only_green_passes_gate() -> None:
    assert run_case(CASE, SimEfsAgent("faithful")).passed is True
    # 蒙对绝不能算通过——否则回归门禁形同虚设
    assert run_case(CASE, SimEfsAgent("skip_decisive")).passed is False


def test_tier1_gate_catches_forbidden_term() -> None:
    """即使结果对、轨迹对，输出里混入矛盾根因(QOS限流)也必须被 Tier1 拦下。"""
    report = run_case(CASE, SimEfsAgent("contradiction"))
    assert report.status is Status.RED
    assert "tier1" in report.attribution
    assert any("QOS限流" in f for f in report.rules.failures)


def test_outcome_is_set_based_not_substring() -> None:
    """合成 trace：结果评分按实例集合 P/R/F1，不靠子串。"""
    case = load_case(CASE)
    trace = Trace(case_id="synthetic-green")
    trace.add(ToolCall(seq=1, tool="monitor_cma_get_current_alarms"))
    trace.add(ToolCall(seq=2, tool="monitor_smarttopo_get_efs_topology"))
    trace.add(
        ToolCall(
            seq=3,
            tool="monitor_cmc_get_tenant_metric_data",
            name_space="SYS.ECS",
            metric="cpu_util",
            instance_id="ecs-02",
            abnormal=True,
            observed_value=92,
            threshold=80,
        )
    )
    trace.final_output = build_root_cause_output(
        [
            {
                "label": "CPU使用率异常",
                "ids": ["ecs-02"],
                "metric": "cpu_util",
                "value": "92%",
                "threshold": "80%",
            }
        ]
    )
    report = grade(case, trace)
    assert report.status is Status.GREEN
    assert report.outcome.precision == 1.0
    assert report.outcome.recall == 1.0
    assert report.outcome.f1 == 1.0
    assert report.trajectory.necessary_recall == 1.0


def test_multi_root_cause_recall_penalised() -> None:
    """漏报一个根因 → recall<1 → 不再 GREEN（验证多根因按集合评）。"""
    case = load_case(CASE)
    # 人为把期望根因扩成两个，制造漏报
    case["expected_root_cause"]["causes"].append(
        {"category": "EVS_AWAIT", "resource_id": "evs-09", "evidence": "demo"}
    )
    trace = Trace(case_id="synthetic-miss")
    trace.add(
        ToolCall(
            seq=1,
            tool="monitor_cmc_get_tenant_metric_data",
            name_space="SYS.ECS",
            metric="cpu_util",
            instance_id="ecs-02",
            abnormal=True,
        )
    )
    trace.final_output = build_root_cause_output(
        [
            {
                "label": "CPU使用率异常",
                "ids": ["ecs-02"],
                "metric": "cpu_util",
                "value": "92%",
                "threshold": "80%",
            }
        ]
    )
    report = grade(case, trace)
    assert report.outcome.recall == 0.5
    assert report.outcome.missing == {"evs-09"}
    assert report.status is not Status.GREEN
