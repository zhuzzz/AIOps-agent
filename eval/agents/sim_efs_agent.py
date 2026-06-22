"""模拟 efs-diagnosis agent —— 用于自测评测内核（证明能跑绿/跑红）。

它**真的**按 skill 的判定逻辑、对着录制响应走一遍诊断链路（Step0→1→2→3→4→6→7→8），
按 diagnosis_threshold / 固定阈值判越界，产出 Step10 根因 JSON + 轨迹。
因此当我们喂入"ecs-02 cpu_util=92、其余正常"的世界时，它应当干净地落到 ECS CPU 根因，
并在 trace 中留下"看到了 cpu_util 越界"这条决定性证据。

``behavior`` 用于注入缺陷，制造四象限的不同结果，证明评分器有区分力：
- ``faithful``        : 完整走链路 → GREEN
- ``skip_decisive``   : 跳过 Step8 但仍猜 ECS_CPU/ecs-02 → 结论对、没看证据 → YELLOW（蒙对）
- ``wrong_instance``  : 看了 cpu 证据却报错实例 ecs-01 → BLUE（走对路结论错）
- ``contradiction``   : 正确 + 多报一条 QOS限流 → 触发 must_not → RED（门禁）

生产环境用 ``RelayAgentAdapter`` 替换本类即可（见 base.py），评分器与 case 不变。
"""

from __future__ import annotations

import re
from typing import Any

from harness.script_proxy import ScriptProxy
from harness.tool_proxy import ToolProxy

_ORIG = re.compile(r"original_data=(\{.*\})")
_KV = re.compile(r'"([^"]+):last\(\)>=(\d+(?:\.\d+)?)"\s*:\s*(\d+(?:\.\d+)?)')


def _series_max(data: dict[str, Any]) -> float | None:
    """从（已按实例过滤的）指标响应里取代表值。"""
    content = data.get("origin_response", {}).get("content")
    vals: list[float] = []
    if isinstance(content, list):
        for item in content:
            if isinstance(item.get("max"), (int, float)):
                vals.append(float(item["max"]))
            elif isinstance(item.get("datapoints"), list):
                vals += [
                    float(dp["value"])
                    for dp in item["datapoints"]
                    if isinstance(dp.get("value"), (int, float))
                ]
    return max(vals) if vals else None


def build_root_cause_output(causes: list[dict[str, Any]]) -> dict[str, Any]:
    """把根因列表组装成 skill Step10 的 recommended_root_cause JSON。

    每个 cause: ``{label, ids:[...], metric, value, threshold, advice?, confidence?}``。
    content 满足 skill 的格式约束：含 ``instance_id:[...]``、异常指标值。
    """
    rows: list[dict[str, Any]] = []
    for i, c in enumerate(causes, 1):
        ids = ",".join(c["ids"])
        content = (
            f"**{c['label']}**,instance_id:[{ids}],"
            f"异常指标值：{c['metric']}峰值{c['value']}(阈值{c['threshold']})"
        )
        rows.append(
            {
                "id": f"根因{i}",
                "content": content,
                "addition": {
                    "advice": c.get("advice", "（处置建议略）"),
                    "confidence": c.get("confidence", 0.85),
                },
            }
        )
    return {"show_type": "recommended_root_cause", "data": {"data": rows}}


class SimEfsAgent:
    """模拟 agent。"""

    def __init__(self, behavior: str = "faithful") -> None:
        self.behavior = behavior

    def run(
        self,
        case: dict[str, Any],
        tools: ToolProxy,
        scripts: ScriptProxy,
    ) -> dict[str, Any]:
        csn = case["input"]["csn"]

        # ---- Step 0：提取告警，算 diagnosis_threshold ----
        alarm = tools.call("monitor_cma_get_current_alarms", {"csn": csn})
        ac = alarm["origin_response"]["content"]
        region = ac.get("region", "cn-north-7")
        cluster_id = ac.get("cluster_id", "")
        observed = self._parse_observed_value(ac.get("additionalInformation", ""))
        diag_threshold = observed * 0.5

        # ---- Step 1：拓扑 ----
        topo = tools.call(
            "monitor_smarttopo_get_efs_topology", {"cluster_id": cluster_id}
        )
        tc = topo["origin_response"]["content"]
        nas = [i["resource_id"] for i in tc.get("nas_instances", [])]
        mds = [i["resource_id"] for i in tc.get("mds_instances", [])]
        space = [i["resource_id"] for i in tc.get("space_instances", [])]
        ecs = [i["resource_id"] for i in tc.get("ecs_instances", [])]

        causes: list[dict[str, Any]] = []

        # ---- Step 2：nas QOS / 网络时延 ----
        for rid in nas:
            for metric in ("d_nas_read3QOS", "d_nas_write3QOS"):
                v = self._metric(tools, region, cluster_id, rid, "SRE.EFS", metric)
                ab = v is not None and v != 0
                tools.trace.mark_last(abnormal=ab, observed_value=v, threshold=0)
                if ab:
                    causes.append(self._c("nas QOS限流", "NAS_QOS", rid, metric, v, 0))
            v = self._metric(
                tools, region, cluster_id, rid, "SRE.EFS", "d_nas_read3NT"
            )
            ab = v is not None and v > diag_threshold
            tools.trace.mark_last(abnormal=ab, observed_value=v, threshold=diag_threshold)

        # ---- Step 3：space 时延 ----
        for rid in space:
            v = self._metric(tools, region, cluster_id, rid, "SRE.EFS", "d_space_spRead")
            ab = v is not None and v > diag_threshold
            tools.trace.mark_last(abnormal=ab, observed_value=v, threshold=diag_threshold)

        # ---- Step 4：mds 元数据 ----
        for rid in mds:
            v = self._metric(
                tools, region, cluster_id, rid, "SRE.EFS", "avg_metaread_latency"
            )
            ab = v is not None and v > diag_threshold
            tools.trace.mark_last(abnormal=ab, observed_value=v, threshold=diag_threshold)
            s = self._metric(
                tools, region, cluster_id, rid, "SRE.EFS", "d_mds_process_survival_time"
            )
            sab = s is not None and s == 0
            tools.trace.mark_last(abnormal=sab, observed_value=s, threshold=0)

        # ---- Step 6：OBS 联动（按时延短路：nas read_latency 未越界则 OBS 无关）----
        for rid in nas:
            v = self._metric(tools, region, cluster_id, rid, "SRE.EFS", "read_latency")
            ab = v is not None and v > diag_threshold
            tools.trace.mark_last(abnormal=ab, observed_value=v, threshold=diag_threshold)

        # ---- Step 7：EVS（脚本/URL 面）----
        evs_abnormal = scripts.check_evs_metric_result(10.0)
        for iid, metrics in evs_abnormal.items():
            metric, value = next(iter(metrics.items()))
            causes.append(self._c("EVS磁盘时延异常", "EVS_AWAIT", iid, metric, value, 10))

        # ---- Step 8：ECS CPU（本 case 的决定性证据）----
        if self.behavior != "skip_decisive":
            for rid in ecs:
                v = self._metric(
                    tools, region, cluster_id, rid, "SYS.ECS", "cpu_util", per_ecs=True
                )
                ab = v is not None and v > 80
                tools.trace.mark_last(abnormal=ab, observed_value=v, threshold=80)
                if ab:
                    report_id = "ecs-01" if self.behavior == "wrong_instance" else rid
                    causes.append(
                        self._c("CPU使用率异常", "ECS_CPU", report_id, "cpu_util", f"{int(v)}%", "80%")
                    )

        if self.behavior == "skip_decisive":
            # 没看证据，凭经验猜（蒙对）
            causes.append(self._c("CPU使用率异常", "ECS_CPU", "ecs-02", "cpu_util", "?%", "80%"))
        if self.behavior == "contradiction":
            causes.append(self._c("nas QOS限流", "NAS_QOS", "nas-01", "d_nas_read3QOS", 1, 0))

        return build_root_cause_output(causes)

    # ---------------- helpers ---------------- #

    @staticmethod
    def _metric(
        tools: ToolProxy,
        region: str,
        cluster_id: str,
        rid: str,
        name_space: str,
        metric: str,
        per_ecs: bool = False,
    ) -> float | None:
        inst = (
            f"{{instance_id={rid}}}"
            if per_ecs
            else f"{{cluster_id={cluster_id},instance_id={rid}}}"
        )
        data = tools.call(
            "monitor_cmc_get_tenant_metric_data",
            {
                "region_code": region,
                "name_space": name_space,
                "instance_id": inst,
                "metric": metric,
                "metric_data_type": "number",
            },
        )
        return _series_max(data)

    @staticmethod
    def _parse_observed_value(additional_info: str) -> float:
        """从 additionalInformation 里取 value>=threshold 的最大实际值。"""
        m = _ORIG.search(additional_info)
        blob = m.group(1) if m else additional_info
        best = 0.0
        for _name, thr, val in _KV.findall(blob):
            if float(val) >= float(thr):
                best = max(best, float(val))
        return best or 1.0

    @staticmethod
    def _c(
        label: str,
        category: str,
        rid: str,
        metric: str,
        value: Any,
        threshold: Any,
    ) -> dict[str, Any]:
        return {
            "label": label,
            "category": category,
            "ids": [rid],
            "metric": metric,
            "value": value,
            "threshold": threshold,
        }
