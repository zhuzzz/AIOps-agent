"""路由层：命中 / 竞争 / 拒识 / 误路由 四类都要能被正确判定。"""

from pathlib import Path

import yaml

from routing.grade_routing import RouteVerdict, grade_route, summarize
from routing.router import route

CASES = (
    Path(__file__).resolve().parents[1] / "cases" / "routing" / "router_cases.yaml"
)


def test_routing_verdicts() -> None:
    cases = yaml.safe_load(CASES.read_text(encoding="utf-8"))
    by_id: dict[str, RouteVerdict] = {}
    verdicts: list[RouteVerdict] = []
    for c in cases:
        decision = route(c["alarm_text"], c.get("resource_type", ""))
        verdict = grade_route(decision, c["expected_skill"])
        by_id[c["id"]] = verdict
        verdicts.append(verdict)
        print(f"\n{c['id']:28s} -> route={decision.skill!s:14s} verdict={verdict.value}")

    assert by_id["route-efs-io-001"] is RouteVerdict.HIT
    assert by_id["route-db-competition-001"] is RouteVerdict.HIT
    assert by_id["route-reject-vague-001"] is RouteVerdict.CORRECT_REJECT
    # 过度自信误路由：仅因撞到 'QOS' 就把无关告警塞给 efs-diagnosis
    assert by_id["route-misroute-qos-001"] is RouteVerdict.MISROUTE

    s = summarize(verdicts)
    assert s.hit == 2
    assert s.misroute == 1
    assert s.accuracy == 0.75
