"""被测 agent 协议 + 真实 relay 接入说明（seam）。

评测内核只依赖一个极薄的协议：``run(case, tools, scripts) -> Step10 根因 JSON``。
这样"模拟 agent"（本仓库用于自测内核）与"真实 relay agent"（生产）可以无缝互换。

真实接入怎么做（不改 skill、不改 agent 推理逻辑）::

    class RelayAgentAdapter:
        def run(self, case, tools, scripts):
            # 1) 把 relay 的 mcp_tool_proxy 切到"回放模式"，其后端指向本评测的
            #    ToolProxy.call —— 即所有 MCP 工具调用都从 case/responses/ 取录制响应，
            #    且每次调用自动落一条 ToolCall 入 trace（拦截面 1）。
            # 2) 把 skill 里 `python scripts/*.py` 与 metrics_url 拉取，重定向到
            #    ScriptProxy（拦截面 2）。
            # 3) 用 case['input'] 触发 relay 跑 efs-diagnosis skill，温度/种子固定。
            # 4) 取 skill 的 Step10 输出（show_type=recommended_root_cause）原样返回。
            ...

关键：trace 不是 agent 自报的，而是在工具/脚本边界**被动抓取**的，agent 无法伪造。
"""

from __future__ import annotations

from typing import Any, Protocol

from harness.script_proxy import ScriptProxy
from harness.tool_proxy import ToolProxy


class Agent(Protocol):
    def run(
        self, case: dict[str, Any], tools: ToolProxy, scripts: ScriptProxy
    ) -> dict[str, Any]: ...
