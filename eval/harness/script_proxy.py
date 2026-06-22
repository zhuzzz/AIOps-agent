"""脚本 / metrics_url 录制-回放层（拦截面 2）。

为什么需要它：efs-diagnosis 的 Step 7/9/10/11 不是 MCP 工具调用，而是
``python scripts/*.py`` 子进程，且 Step 7.2 返回一个 ``metrics_url`` 再由
``check_metric_result.py`` 去拉取解析。tool-proxy 只能拦 MCP 工具，**拦不到
这条脚本/URL 链路**。若不覆盖，回放在 EVS 分支必断。

本层把"脚本读取 metrics_url 后产出的异常节点 map"作为录制对象，stub 成读取
``responses/evs__disk_await.json``，并照样落一条 ToolCall（surface=script）入轨迹，
使 EVS 分支也能进入评分。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .trace import ToolCall, Trace


class ScriptProxy:
    """脚本/URL 面的录制-回放。"""

    def __init__(self, responses_dir: Path | str, trace: Trace) -> None:
        self.responses_dir = Path(responses_dir)
        self.trace = trace

    def check_evs_metric_result(self, threshold_ms: float = 10.0) -> dict[str, Any]:
        """模拟 ``scripts/check_metric_result.py {metrics_url} {threshold}``。

        返回 ``{instance_id: {metric: max_value}}`` 形式的异常节点 map（只含越界项）。
        录制源：``responses/evs__disk_await.json``。
        """
        f = self.responses_dir / "evs__disk_await.json"
        if not f.exists():
            # EVS 分支无录制数据时视为"无 EVS 异常"，不阻断主链路。
            self.trace.scripts_invoked.append("check_metric_result.py(no-fixture)")
            return {}

        data: dict[str, Any] = json.loads(f.read_text(encoding="utf-8"))
        content = data.get("origin_response", {}).get("content", [])
        abnormal_map: dict[str, Any] = {}
        worst: float | None = None
        for item in content:
            iid = str(item.get("instance_id"))
            for metric, value in item.get("metrics", {}).items():
                worst = value if worst is None else max(worst, value)
                if value > threshold_ms:
                    abnormal_map.setdefault(iid, {})[metric] = value

        self.trace.scripts_invoked.append("check_metric_result.py")
        self.trace.add(
            ToolCall(
                seq=self.trace.next_seq(),
                tool="scripts/check_metric_result.py",
                name_space="SYS.EVS",
                metric="disk_device_await",
                params={"threshold_ms": threshold_ms},
                abnormal=bool(abnormal_map),
                observed_value=worst,
                threshold=threshold_ms,
                surface="script",
            )
        )
        return abnormal_map
