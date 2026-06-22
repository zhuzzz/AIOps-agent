"""端到端：忠实 agent 在 efs-ecs-cpu-001 上应判 GREEN（证明内核能跑绿）。"""

from pathlib import Path

from agents.sim_efs_agent import SimEfsAgent
from harness.report import Status
from harness.runner import run_case

CASE = Path(__file__).resolve().parents[1] / "cases" / "efs-ecs-cpu-001"


def test_faithful_agent_is_green() -> None:
    report = run_case(CASE, SimEfsAgent("faithful"))
    print("\n" + report.summary())

    assert report.status is Status.GREEN
    assert report.passed
    assert report.outcome.f1 == 1.0
    assert report.outcome.predicted == {"ecs-02"}
    assert report.trajectory.decisive_coverage == 1.0
    assert report.trajectory.necessary_recall == 1.0
    # 决定性证据那次调用确实观测到越界
    cpu_calls = [
        c
        for c in report.trace_dict["tool_calls"]
        if c["metric"] == "cpu_util" and c["instance_id"] == "ecs-02"
    ]
    assert cpu_calls and cpu_calls[0]["abnormal"] is True
