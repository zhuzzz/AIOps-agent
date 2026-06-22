"""MCP 工具录制-回放层（拦截面 1），同时充当轨迹记录器。

设计要点（对应评测方案 §4.2）：

1. **按调用精确匹配键**，而非按 tool_name——``monitor_cmc_get_tenant_metric_data``
   在一次诊断里被调几十次，键必须含 name_space + metric：
   ``cmc__{name_space}__{metric}.json``，否则后写覆盖先写、回放直接坏掉。
2. **一文件含全部实例，按 instance_id 过滤**，解决"多实例撞键"。
3. **fail-closed**：缺录制响应直接抛错并提示缺哪个键，绝不静默返回空。
4. **proxy 即 trace 记录器**：每次 call 落一条 ToolCall，零侵入抓轨迹。

真实接入：把 relay 的 ``mcp_tool_proxy`` 在回放模式下指向本类的 ``call`` 即可，
agent 代码无需改动（拦截发生在工具边界）。
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .trace import ToolCall, Trace

_INSTANCE_RE = re.compile(r"instance_id=([^,}]+)")


def build_key(tool_name: str, params: dict[str, Any]) -> str:
    """把 (工具名, 参数) 映射到录制文件名（不含扩展名）。

    指标类工具按 name_space + metric 细分，其余工具按工具名归一。
    """
    if tool_name == "monitor_cmc_get_tenant_metric_data":
        return f"cmc__{params['name_space']}__{params['metric']}"
    if tool_name == "monitor_cma_get_current_alarms":
        return "cma__current_alarms"
    if tool_name == "monitor_cma_get_history_alarms":
        return "cma__history_alarms"
    if tool_name == "monitor_smarttopo_get_efs_topology":
        return "smarttopo__topology"
    if tool_name == "monitor_cma_get_all_alarms_by_instanceId":
        return "cma__alarms_by_instance"
    return tool_name


def _extract_token(instance_id: str | None) -> str | None:
    """从 ``{cluster_id=..,instance_id=ecs-02}`` 这类串里抽出内层 instance id。"""
    if not instance_id:
        return None
    m = _INSTANCE_RE.search(instance_id)
    if m:
        return m.group(1).strip()
    return instance_id.strip().strip("{}")


def _max_value(content: list[dict[str, Any]]) -> float | None:
    """从过滤后的指标内容里取代表值（max），用于轨迹复核。"""
    vals: list[float] = []
    for item in content:
        if isinstance(item.get("max"), (int, float)):
            vals.append(float(item["max"]))
        elif isinstance(item.get("datapoints"), list):
            for dp in item["datapoints"]:
                v = dp.get("value")
                if isinstance(v, (int, float)):
                    vals.append(float(v))
    return max(vals) if vals else None


class MissingResponseError(FileNotFoundError):
    """缺少录制响应文件——回放必须 fail-closed。"""


class ToolProxy:
    """录制-回放 + 轨迹记录。"""

    def __init__(self, responses_dir: Path | str, trace: Trace) -> None:
        self.responses_dir = Path(responses_dir)
        self.trace = trace

    def call(self, tool_name: str, params: dict[str, Any]) -> dict[str, Any]:
        """回放一次工具调用：装载录制响应、按实例过滤、记录轨迹、返回数据。"""
        key = build_key(tool_name, params)
        f = self.responses_dir / f"{key}.json"
        if not f.exists():
            raise MissingResponseError(
                f"[tool_proxy] 缺少录制响应: {f.name}（tool={tool_name}, "
                f"name_space={params.get('name_space')}, metric={params.get('metric')}）"
            )
        data: dict[str, Any] = json.loads(f.read_text(encoding="utf-8"))

        token = _extract_token(params.get("instance_id"))
        content = data.get("origin_response", {}).get("content")
        observed: float | None = None
        if token and isinstance(content, list):
            hit = [
                c
                for c in content
                if token == str(c.get("instance_id"))
                or token in str(c.get("instance_id"))
                or str(c.get("instance_id")) in token
            ]
            if hit:
                content = hit
                data = {
                    "origin_response": {"description": "tool执行结果", "content": hit}
                }
        if isinstance(content, list):
            observed = _max_value(content)

        self.trace.add(
            ToolCall(
                seq=self.trace.next_seq(),
                tool=tool_name,
                name_space=params.get("name_space"),
                metric=params.get("metric"),
                instance_id=token,
                params=dict(params),
                observed_value=observed,
                surface="tool",
            )
        )
        return data
