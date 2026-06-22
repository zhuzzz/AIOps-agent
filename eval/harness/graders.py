"""三层评分器：规则（Tier1）/ 轨迹（Tier2）/ 结果（Tier3）。

核心立场（对应评测方案 §5）：
- Tier1 规则：与具体根因**无关**的通用断言（输出结构、禁词、禁用工具）。是硬门禁。
- Tier2 轨迹：是否走到**决定性证据**（decisive）、是否覆盖**必经**工具（necessary）。
- Tier3 结果：根因**实例集合**的 precision/recall/F1（闭集，精确匹配，无需 judge）。

把"是否蒙对"留给 report 层的"结果×轨迹四象限"，本模块只产出可量化指标。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from .trace import Trace

_INSTANCE_IN_OUTPUT_RE = re.compile(r"instance_id:\s*\[([^\]]+)\]")


def extract_conclusion_text(final_output: dict[str, Any] | None) -> str:
    """把 Step10 根因 JSON 里的所有 content/advice 文本拼起来，供关键词断言。"""
    if not final_output:
        return ""
    parts: list[str] = []
    data = final_output.get("data", {})
    for row in data.get("data", []) if isinstance(data, dict) else []:
        if isinstance(row, dict):
            parts.append(str(row.get("content", "")))
            add = row.get("addition", {})
            if isinstance(add, dict):
                parts.append(str(add.get("advice", "")))
    return "\n".join(parts)


def extract_resource_set(final_output: dict[str, Any] | None) -> set[str]:
    """从根因输出里抽出所有 ``instance_id:[...]`` 的实例 id 集合。"""
    text = extract_conclusion_text(final_output)
    ids: set[str] = set()
    for m in _INSTANCE_IN_OUTPUT_RE.finditer(text):
        for piece in m.group(1).split(","):
            piece = piece.strip()
            if piece:
                ids.add(piece)
    return ids


# ----------------------------- Tier1: 规则 ----------------------------- #


@dataclass
class RuleResult:
    passed: bool
    failures: list[str] = field(default_factory=list)


def grade_rules(
    final_output: dict[str, Any] | None,
    trace: Trace,
    spec: dict[str, Any],
) -> RuleResult:
    """通用规则断言（与根因无关）。

    Args:
        final_output: agent 的 Step10 根因 JSON。
        trace: 执行轨迹（用于禁用工具检查）。
        spec: case 的 ``rules`` 段，含 ``must_not`` / ``forbidden_tools`` /
            ``require_instance_id`` / ``schema``。
    """
    failures: list[str] = []
    text = extract_conclusion_text(final_output)

    # 1) 输出结构
    if spec.get("schema") == "recommended_root_cause":
        if not final_output or final_output.get("show_type") != "recommended_root_cause":
            failures.append("schema: 缺少 show_type=recommended_root_cause")
        else:
            rows = final_output.get("data", {}).get("data")
            if not isinstance(rows, list) or not rows:
                failures.append("schema: data.data 必须为非空列表")

    # 2) 必须给出实例 id（禁止"等N个实例"概括）
    if spec.get("require_instance_id", True) and not extract_resource_set(final_output):
        failures.append("output: 根因未给出任何 instance_id:[...]")

    # 3) 禁词（出现即判错——通常是相互矛盾/幻觉的根因类别）
    for term in spec.get("must_not", []):
        if term in text:
            failures.append(f"must_not: 出现禁词 '{term}'")

    # 4) 禁用工具
    called = {c.tool for c in trace.tool_calls}
    for tool in spec.get("forbidden_tools", []):
        if tool in called:
            failures.append(f"forbidden_tool: 调用了禁用工具 '{tool}'")

    return RuleResult(passed=not failures, failures=failures)


# --------------------------- Tier2: 轨迹 --------------------------- #


@dataclass
class TrajectoryResult:
    decisive_coverage: float
    necessary_recall: float
    missing_decisive: list[str] = field(default_factory=list)
    missing_necessary: list[str] = field(default_factory=list)
    matched: list[str] = field(default_factory=list)


def _step_label(step: dict[str, Any]) -> str:
    bits = [step["tool"]]
    if step.get("name_space"):
        bits.append(step["name_space"])
    if step.get("metric"):
        bits.append(step["metric"])
    return ":".join(bits)


def grade_trajectory(
    trace: Trace,
    reference_trajectory: list[dict[str, Any]],
) -> TrajectoryResult:
    """轨迹评分：不强制顺序，只看必经/决定性步骤是否覆盖。

    decisive 步骤额外要求轨迹中对应调用 ``abnormal=True``，即真的"看到"了越界证据。
    """
    decisive_total = 0
    decisive_hit = 0
    necessary_total = 0
    necessary_hit = 0
    missing_decisive: list[str] = []
    missing_necessary: list[str] = []
    matched: list[str] = []

    for step in reference_trajectory:
        calls = trace.find(step["tool"], step.get("name_space"), step.get("metric"))
        label = _step_label(step)

        if step.get("necessary"):
            necessary_total += 1
            if calls:
                necessary_hit += 1
                matched.append(label)
            else:
                missing_necessary.append(label)

        if step.get("decisive"):
            decisive_total += 1
            if any(c.abnormal for c in calls):
                decisive_hit += 1
            else:
                missing_decisive.append(label)

    return TrajectoryResult(
        decisive_coverage=decisive_hit / decisive_total if decisive_total else 1.0,
        necessary_recall=necessary_hit / necessary_total if necessary_total else 1.0,
        missing_decisive=missing_decisive,
        missing_necessary=missing_necessary,
        matched=matched,
    )


# --------------------------- Tier3: 结果 --------------------------- #


@dataclass
class OutcomeResult:
    precision: float
    recall: float
    f1: float
    predicted: set[str] = field(default_factory=set)
    expected: set[str] = field(default_factory=set)
    extra: set[str] = field(default_factory=set)
    missing: set[str] = field(default_factory=set)
    category_keywords_ok: bool = True
    missing_keywords: list[str] = field(default_factory=list)


def grade_outcome(
    final_output: dict[str, Any] | None,
    expected_causes: list[dict[str, Any]],
    must_mention: list[str] | None = None,
) -> OutcomeResult:
    """结果评分：根因实例集合的 precision/recall/F1（闭集，无需 judge）。

    Args:
        final_output: agent 的 Step10 根因 JSON。
        expected_causes: SRE 盖章的期望根因列表，每项含 ``resource_id``。
        must_mention: 期望出现的类别关键词（如 CPU / cpu_util / 80），作为结果的二级确认。
    """
    predicted = extract_resource_set(final_output)
    expected = {c["resource_id"] for c in expected_causes}

    inter = predicted & expected
    precision = len(inter) / len(predicted) if predicted else 0.0
    recall = len(inter) / len(expected) if expected else 1.0
    f1 = (
        2 * precision * recall / (precision + recall)
        if (precision + recall) > 0
        else 0.0
    )

    text = extract_conclusion_text(final_output)
    missing_keywords = [kw for kw in (must_mention or []) if kw not in text]

    return OutcomeResult(
        precision=precision,
        recall=recall,
        f1=f1,
        predicted=predicted,
        expected=expected,
        extra=predicted - expected,
        missing=expected - predicted,
        category_keywords_ok=not missing_keywords,
        missing_keywords=missing_keywords,
    )
