"""轨迹（trace）数据模型。

一条 trace 完整记录 agent 在单个 case 上的执行：调用了哪些工具、每次调用的
关键参数（name_space / metric / instance）、是否观测到越界（decisive 证据的核心）、
以及最终诊断输出。评分器只读 trace，不关心 agent 内部实现。

字段刻意做成可 JSON 序列化，便于落盘、回归对比、以及对接 OTel GenAI span。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class ToolCall:
    """一次工具/脚本调用的记录。

    Attributes:
        seq: 调用序号（从 1 开始），保留顺序信息但评分默认不强制顺序。
        tool: 工具名（如 ``monitor_cmc_get_tenant_metric_data``）或脚本名。
        name_space: 指标命名空间（如 ``SYS.ECS``），非指标类工具为 None。
        metric: 指标名（如 ``cpu_util``），非指标类工具为 None。
        instance_id: 本次调用过滤到的实例 id（已从 ``{instance_id=..}`` 里抽出）。
        params: 原始调用参数，用于复盘。
        abnormal: agent 是否把该信号判定为越界——decisive 证据是否被"看到"的关键位。
        observed_value: 过滤后内容里的代表值（取 max），便于复核。
        threshold: agent 当时使用的判定阈值（如 80 或 diagnosis_threshold）。
        latency_ms: 调用耗时（回放下为录制值或 0）。
        surface: 拦截面，``tool``（MCP 工具）或 ``script``（脚本/URL）。
    """

    seq: int
    tool: str
    name_space: str | None = None
    metric: str | None = None
    instance_id: str | None = None
    params: dict[str, Any] = field(default_factory=dict)
    abnormal: bool = False
    observed_value: float | None = None
    threshold: float | None = None
    latency_ms: int = 0
    surface: str = "tool"


@dataclass
class Trace:
    """单个 case 的完整执行轨迹。"""

    case_id: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    scripts_invoked: list[str] = field(default_factory=list)
    final_output: dict[str, Any] | None = None
    totals: dict[str, Any] = field(default_factory=dict)

    def add(self, call: ToolCall) -> ToolCall:
        """追加一次调用记录并返回它（便于调用方回填 abnormal 等字段）。"""
        self.tool_calls.append(call)
        return call

    @property
    def last(self) -> ToolCall:
        """最近一次调用记录。"""
        return self.tool_calls[-1]

    def mark_last(
        self,
        *,
        abnormal: bool,
        observed_value: float | None = None,
        threshold: float | None = None,
    ) -> None:
        """回填最近一次调用的越界判定（agent 算完阈值后调用）。"""
        call = self.tool_calls[-1]
        call.abnormal = abnormal
        if observed_value is not None:
            call.observed_value = observed_value
        if threshold is not None:
            call.threshold = threshold

    def find(
        self,
        tool: str,
        name_space: str | None = None,
        metric: str | None = None,
    ) -> list[ToolCall]:
        """查找匹配 (tool[, name_space][, metric]) 的所有调用。

        name_space / metric 传 None 表示该维度不约束。
        """
        out: list[ToolCall] = []
        for c in self.tool_calls:
            if c.tool != tool:
                continue
            if name_space is not None and c.name_space != name_space:
                continue
            if metric is not None and c.metric != metric:
                continue
            out.append(c)
        return out

    def next_seq(self) -> int:
        """下一个调用序号。"""
        return len(self.tool_calls) + 1

    def to_dict(self) -> dict[str, Any]:
        """转为可 JSON 序列化的 dict。"""
        return asdict(self)
