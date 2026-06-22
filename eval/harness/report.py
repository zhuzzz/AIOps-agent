"""结果×轨迹四象限分类 + 分层归因。

四象限（对应评测方案 §5.3）：

                  决定性证据命中            决定性证据未命中
    结论正确    🟢 GREEN  真通过        🟡 YELLOW 蒙对(脆弱)
    结论错误    🔵 BLUE   走对路结论错   🔴 RED    跑偏

Tier1 规则是进入四象限前的硬门禁：任一通用规则失败 → 直接 RED，归因 tier1。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from .graders import OutcomeResult, RuleResult, TrajectoryResult


class Status(str, Enum):
    GREEN = "GREEN"  # 真通过
    YELLOW = "YELLOW"  # 蒙对：结论对但没走到决定性证据，脆弱
    BLUE = "BLUE"  # 走对路结论错：看到了证据却下错结论
    RED = "RED"  # 跑偏 / 规则门禁失败


_CN = {
    Status.GREEN: "真通过",
    Status.YELLOW: "蒙对(脆弱)",
    Status.BLUE: "走对路结论错",
    Status.RED: "跑偏/门禁失败",
}


@dataclass
class EvalReport:
    case_id: str
    status: Status
    attribution: str
    rules: RuleResult
    trajectory: TrajectoryResult
    outcome: OutcomeResult
    trace_dict: dict[str, Any]

    @property
    def passed(self) -> bool:
        """回归门禁：仅 GREEN 视为通过。"""
        return self.status is Status.GREEN

    def summary(self) -> str:
        o = self.outcome
        t = self.trajectory
        return (
            f"[{self.status.value}] {self.case_id} — {_CN[self.status]}\n"
            f"  结果  root_cause F1={o.f1:.2f} "
            f"(P={o.precision:.2f} R={o.recall:.2f}) "
            f"预测={sorted(o.predicted)} 期望={sorted(o.expected)}\n"
            f"  轨迹  decisive_coverage={t.decisive_coverage:.2f} "
            f"necessary_recall={t.necessary_recall:.2f} "
            f"缺失决定性={t.missing_decisive}\n"
            f"  规则  passed={self.rules.passed} {self.rules.failures}\n"
            f"  归因  {self.attribution}"
        )


def classify(
    rules: RuleResult,
    trajectory: TrajectoryResult,
    outcome: OutcomeResult,
    *,
    f1_gate: float = 1.0,
    decisive_gate: float = 1.0,
) -> tuple[Status, str]:
    """把三层评分汇成四象限状态 + 归因文案。"""
    if not rules.passed:
        return Status.RED, f"tier1规则门禁失败: {'; '.join(rules.failures)}"

    outcome_ok = outcome.f1 >= f1_gate
    decisive_ok = trajectory.decisive_coverage >= decisive_gate

    if outcome_ok and decisive_ok:
        return Status.GREEN, "结果对且走到决定性证据"
    if outcome_ok and not decisive_ok:
        return (
            Status.YELLOW,
            f"结论对但未命中决定性证据(蒙对/脆弱): 缺 {trajectory.missing_decisive}",
        )
    if not outcome_ok and decisive_ok:
        return (
            Status.BLUE,
            "走到决定性证据却下错结论(诊断层缺陷): "
            f"多报={sorted(outcome.extra)} 漏报={sorted(outcome.missing)}",
        )
    return (
        Status.RED,
        "结论错且未走到决定性证据(跑偏): "
        f"多报={sorted(outcome.extra)} 漏报={sorted(outcome.missing)} "
        f"缺决定性={trajectory.missing_decisive}",
    )
