"""一键演示：对 efs-ecs-cpu-001 跑四种 agent 行为，打印结果×轨迹四象限看板。

    python run_demo.py        # 在 eval/ 目录下直接运行

无需 pytest，便于快速向人演示"同一条 case、同一套评分器，如何把
真通过 / 蒙对 / 走对路结论错 / 门禁失败 区分开"。
"""

from __future__ import annotations

from pathlib import Path

from agents.sim_efs_agent import SimEfsAgent
from harness.runner import run_case

CASE = Path(__file__).resolve().parent / "cases" / "efs-ecs-cpu-001"

_BEHAVIORS = [
    ("faithful", "忠实走完链路，看到 cpu_util 越界"),
    ("skip_decisive", "跳过 Step8，凭经验猜 ECS_CPU（蒙对）"),
    ("wrong_instance", "看了 cpu 证据却报错实例 ecs-01"),
    ("contradiction", "正确 + 多报一条矛盾的 QOS限流"),
]


def main() -> None:
    print("#" * 76)
    print("# efs-diagnosis 评测内核演示 — case: efs-ecs-cpu-001 (ECS CPU 瓶颈)")
    print("#" * 76)
    for behavior, desc in _BEHAVIORS:
        report = run_case(CASE, SimEfsAgent(behavior))
        print(f"\n>>> agent 行为 = {behavior}  ({desc})")
        print(report.summary())
        print(f"    回归门禁 passed = {report.passed}")
    print("\n" + "#" * 76)


if __name__ == "__main__":
    main()
