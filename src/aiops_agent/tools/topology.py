"""Service topology tool.

Provides get_service_topology — the primary entry point for the AIOps agent
to discover service structure, instances, and dependencies before drilling
into metrics and logs for root-cause analysis.

Supports querying by either service_id or instance_id (or both).
"""

from __future__ import annotations

import logging
from typing import Any

from aiops_agent.models.topology import (
    DependencyDirection,
    TopologyQueryParams,
    TopologyResponse,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Tool function schema (OpenAI Function Calling format)
# ---------------------------------------------------------------------------

GET_SERVICE_TOPOLOGY_SCHEMA: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "get_service_topology",
        "description": (
            "获取指定时间窗内的服务拓扑快照。支持两种入口：\n"
            "1. 通过 service_id 查询：返回完整服务拓扑。\n"
            "2. 通过 instance_id 查询：自动反查所属服务，返回完整拓扑"
            "并标记目标实例。\n"
            "两个参数至少提供一个。返回内容包含服务元信息、实例列表"
            "（含状态/角色/宿主机/metric_pointer）、上下游依赖（含运行时"
            "健康指标）。每个实体携带 metric_pointer，可直接用于后续 "
            "query_metrics / query_logs 调用，无需额外查询。\n"
            "当本服务诊断未找到根因时，Agent 应从 downstream_dependencies "
            "中选择 status=DEGRADED 且 dependency_type=STRONG 的服务继续追溯。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "service_id": {
                    "type": "string",
                    "description": (
                        "服务唯一标识，如 'sfs-turbo-001'。"
                        "与 instance_id 至少提供一个。"
                    ),
                },
                "instance_id": {
                    "type": "string",
                    "description": (
                        "实例唯一标识，如 'sfs-node-02'。提供时自动反查"
                        "所属服务并返回完整拓扑，response 中会标记 "
                        "queried_instance_id。与 service_id 至少提供一个。"
                    ),
                },
                "time_range_start": {
                    "type": "string",
                    "description": (
                        "时间窗起始，ISO 8601。拓扑取窗口内最后快照，"
                        "依赖健康指标为窗口内统计值"
                    ),
                },
                "time_range_end": {
                    "type": "string",
                    "description": "时间窗结束，ISO 8601",
                },
                "direction": {
                    "type": "string",
                    "enum": ["UPSTREAM", "DOWNSTREAM", "BOTH"],
                    "description": (
                        "依赖查询方向：UPSTREAM=谁依赖我，"
                        "DOWNSTREAM=我依赖谁"
                    ),
                    "default": "BOTH",
                },
                "depth": {
                    "type": "integer",
                    "description": "拓扑展开深度，1=仅直接依赖，最大5",
                    "default": 1,
                },
                "include_instances": {
                    "type": "boolean",
                    "description": "是否包含实例详情列表",
                    "default": True,
                },
            },
            "required": ["time_range_start", "time_range_end"],
        },
    },
}


# ---------------------------------------------------------------------------
# Core implementation
# ---------------------------------------------------------------------------


async def get_service_topology(
    params: TopologyQueryParams,
) -> TopologyResponse:
    """Retrieve the service topology snapshot for a given time window.

    This is the primary topology tool exposed to the AIOps agent. It supports
    two entry modes:

    1. **By service_id** — directly fetch the topology for a known service.
    2. **By instance_id** — resolve the parent service via the instance
       registry, then return the full service topology with the queried
       instance indicated in the response.

    The returned topology contains:
    - Service metadata (id, name, type, region, AZ, status)
    - Instance list with host_info and metric_pointers
    - Upstream/downstream dependencies with runtime health metrics
    - Service-level metric_pointer

    Every entity carries a ``MetricPointer`` so downstream tools
    (``query_metrics``, ``query_logs``) can be invoked without additional
    lookup calls.

    Args:
        params: Validated query parameters. At least one of ``service_id``
            or ``instance_id`` must be set.

    Returns:
        TopologyResponse containing the full topology and, if the query
        was initiated by instance_id, the ``queried_instance_id`` field.

    Raises:
        ValueError: If neither service_id nor instance_id is provided.
        LookupError: If the service or instance cannot be found.
    """
    if not params.service_id and not params.instance_id:
        raise ValueError(
            "At least one of service_id or instance_id must be provided."
        )

    queried_instance_id: str | None = None
    resolved_service_id: str

    if params.instance_id and not params.service_id:
        # Resolve instance -> service mapping
        resolved_service_id = await _resolve_service_from_instance(
            params.instance_id
        )
        queried_instance_id = params.instance_id
        logger.info(
            "Resolved instance_id=%s to service_id=%s",
            params.instance_id,
            resolved_service_id,
        )
    elif params.service_id:
        resolved_service_id = params.service_id
        if params.instance_id:
            queried_instance_id = params.instance_id
    else:
        raise ValueError(
            "At least one of service_id or instance_id must be provided."
        )

    # Fetch the topology from the backend API
    topology = await _fetch_topology(
        service_id=resolved_service_id,
        time_range_start=params.time_range_start,
        time_range_end=params.time_range_end,
        direction=params.direction,
        depth=params.depth,
        include_instances=params.include_instances,
    )

    return TopologyResponse(
        topology=topology,
        queried_instance_id=queried_instance_id,
    )


# ---------------------------------------------------------------------------
# Internal helpers (to be replaced with real API clients)
# ---------------------------------------------------------------------------


async def _resolve_service_from_instance(instance_id: str) -> str:
    """Look up the parent service_id for a given instance_id.

    This calls the topology backend:
        GET /v1/topology/instances/{instanceId}/service

    Args:
        instance_id: The instance identifier to resolve.

    Returns:
        The service_id that owns this instance.

    Raises:
        LookupError: If the instance is not found in the registry.
    """
    # TODO: Replace with real API call
    # response = await http_client.get(
    #     f"/v1/topology/instances/{instance_id}/service"
    # )
    raise NotImplementedError(
        f"Instance resolution not yet implemented for {instance_id}. "
        "Awaiting topology API integration."
    )


async def _fetch_topology(
    *,
    service_id: str,
    time_range_start: str,
    time_range_end: str,
    direction: DependencyDirection,
    depth: int,
    include_instances: bool,
) -> Any:
    """Fetch topology data from the backend API.

    Calls:
        GET /v1/topology/services/{serviceId}
            ?depth={depth}
            &includeInstances={include_instances}
            &direction={direction}
            &timeRangeStart={time_range_start}
            &timeRangeEnd={time_range_end}

    Args:
        service_id: Target service identifier.
        time_range_start: ISO 8601 start of time window.
        time_range_end: ISO 8601 end of time window.
        direction: UPSTREAM / DOWNSTREAM / BOTH.
        depth: Recursive expansion depth (1-5).
        include_instances: Whether to include instance details.

    Returns:
        ServiceTopology model instance.

    Raises:
        LookupError: If the service is not found.
    """
    # TODO: Replace with real API call
    # response = await http_client.get(
    #     f"/v1/topology/services/{service_id}",
    #     params={
    #         "depth": depth,
    #         "includeInstances": include_instances,
    #         "direction": direction.value,
    #         "timeRangeStart": time_range_start,
    #         "timeRangeEnd": time_range_end,
    #     },
    # )
    # return ServiceTopology.model_validate(response.json()["data"])
    raise NotImplementedError(
        f"Topology fetch not yet implemented for {service_id}. "
        "Awaiting topology API integration."
    )
