"""路由评分：把单条路由判定归入混淆四类，并聚合成可门禁的指标。

四类（对应评测方案 §6）：
- HIT           正确命中（该路由且路由对）
- MISS          漏路由 / 路由错（该路由 X 却给了 None 或别的）
- MISROUTE      误路由（不该路由却路由了——过度自信，最危险）
- CORRECT_REJECT 正确拒识（不该路由且拒识）
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from .router import RouteDecision


class RouteVerdict(str, Enum):
    HIT = "HIT"
    MISS = "MISS"
    MISROUTE = "MISROUTE"
    CORRECT_REJECT = "CORRECT_REJECT"


def grade_route(decision: RouteDecision, expected_skill: str | None) -> RouteVerdict:
    """单条路由判定 → 四类之一。expected_skill=None 表示"本不该路由到任何 skill"。"""
    if expected_skill is None:
        return (
            RouteVerdict.CORRECT_REJECT
            if decision.skill is None
            else RouteVerdict.MISROUTE
        )
    if decision.skill == expected_skill:
        return RouteVerdict.HIT
    return RouteVerdict.MISS


@dataclass
class RoutingSummary:
    total: int = 0
    counts: dict[str, int] = field(default_factory=dict)

    @property
    def hit(self) -> int:
        return self.counts.get(RouteVerdict.HIT.value, 0)

    @property
    def misroute(self) -> int:
        return self.counts.get(RouteVerdict.MISROUTE.value, 0)

    @property
    def accuracy(self) -> float:
        good = self.hit + self.counts.get(RouteVerdict.CORRECT_REJECT.value, 0)
        return good / self.total if self.total else 0.0


def summarize(verdicts: list[RouteVerdict]) -> RoutingSummary:
    s = RoutingSummary(total=len(verdicts))
    for v in verdicts:
        s.counts[v.value] = s.counts.get(v.value, 0) + 1
    return s
