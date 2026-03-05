"""Unit tests for the get_service_topology tool."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from aiops_agent.models.topology import (
    DependencyDirection,
    DependencyHealth,
    DependencyType,
    HostInfo,
    InstanceRole,
    InstanceStatus,
    MetricPointer,
    Protocol,
    ServiceDependency,
    ServiceInstance,
    ServiceStatus,
    ServiceTopology,
    ServiceType,
    TopologyQueryParams,
)
from aiops_agent.tools.topology import get_service_topology


def _make_sample_topology(service_id: str = "sfs-turbo-001") -> ServiceTopology:
    """Build a sample ServiceTopology for testing."""
    return ServiceTopology(
        service_id=service_id,
        service_name="SFS Turbo 文件存储",
        service_type=ServiceType.SFS_TURBO,
        region="cn-north-4",
        az="cn-north-4a",
        status=ServiceStatus.DEGRADED,
        topology_snapshot_time=datetime(
            2025, 3, 5, 10, 30, 0, tzinfo=timezone.utc
        ),
        time_range={
            "start": "2025-03-05T09:00:00Z",
            "end": "2025-03-05T11:00:00Z",
        },
        instances=[
            ServiceInstance(
                instance_id="sfs-node-01",
                instance_name="SFS存储节点-01",
                service_id=service_id,
                instance_type="SFS_STORAGE",
                status=InstanceStatus.RUNNING,
                role=InstanceRole.MASTER,
                host_info=HostInfo(
                    ecs_instance_id="i-abcdef001",
                    private_ip="192.168.1.101",
                    az="cn-north-4a",
                ),
                metric_pointer=MetricPointer(
                    namespace="SYS.SFS",
                    dimension_name="instance_id",
                    dimension_value="sfs-node-01",
                    log_group_id="lg-sfs-001",
                    log_stream_id="ls-sfs-node-01",
                    suggested_metrics=["disk_read_bytes_rate"],
                ),
            ),
            ServiceInstance(
                instance_id="sfs-node-02",
                instance_name="SFS存储节点-02",
                service_id=service_id,
                instance_type="SFS_STORAGE",
                status=InstanceStatus.DEGRADED,
                role=InstanceRole.SLAVE,
                host_info=HostInfo(
                    ecs_instance_id="i-abcdef002",
                    private_ip="192.168.1.102",
                    az="cn-north-4a",
                ),
                metric_pointer=MetricPointer(
                    namespace="SYS.SFS",
                    dimension_name="instance_id",
                    dimension_value="sfs-node-02",
                    log_group_id="lg-sfs-001",
                    log_stream_id="ls-sfs-node-02",
                    suggested_metrics=["disk_read_bytes_rate"],
                ),
            ),
        ],
        downstream_dependencies=[
            ServiceDependency(
                service_id="obs-bucket-train-data",
                service_name="OBS 训练数据桶",
                service_type=ServiceType.OBS,
                dependency_type=DependencyType.STRONG,
                protocol=Protocol.HTTP,
                status=ServiceStatus.DEGRADED,
                health=DependencyHealth(
                    latency_p99_ms=850.0,
                    latency_baseline_ms=50.0,
                    error_rate=0.12,
                ),
                metric_pointer=MetricPointer(
                    namespace="SYS.OBS",
                    dimension_name="bucket_name",
                    dimension_value="obs-bucket-train-data",
                ),
            ),
        ],
        metric_pointer=MetricPointer(
            namespace="SYS.SFS",
            dimension_name="service_id",
            dimension_value=service_id,
            log_group_id="lg-sfs-001",
            log_stream_id="ls-sfs-all",
        ),
    )


@pytest.mark.asyncio
class TestGetServiceTopologyByServiceId:
    """Test get_service_topology when called with service_id."""

    async def test_returns_topology(self) -> None:
        params = TopologyQueryParams(
            service_id="sfs-turbo-001",
            time_range_start="2025-03-05T09:00:00Z",
            time_range_end="2025-03-05T11:00:00Z",
        )
        mock_topo = _make_sample_topology()

        with patch(
            "aiops_agent.tools.topology._fetch_topology",
            new_callable=AsyncMock,
            return_value=mock_topo,
        ):
            response = await get_service_topology(params)

        assert response.topology.service_id == "sfs-turbo-001"
        assert response.queried_instance_id is None

    async def test_with_direction_and_depth(self) -> None:
        params = TopologyQueryParams(
            service_id="sfs-turbo-001",
            time_range_start="2025-03-05T09:00:00Z",
            time_range_end="2025-03-05T11:00:00Z",
            direction=DependencyDirection.DOWNSTREAM,
            depth=2,
        )
        mock_topo = _make_sample_topology()

        with patch(
            "aiops_agent.tools.topology._fetch_topology",
            new_callable=AsyncMock,
            return_value=mock_topo,
        ) as mock_fetch:
            response = await get_service_topology(params)
            mock_fetch.assert_called_once_with(
                service_id="sfs-turbo-001",
                time_range_start="2025-03-05T09:00:00Z",
                time_range_end="2025-03-05T11:00:00Z",
                direction=DependencyDirection.DOWNSTREAM,
                depth=2,
                include_instances=True,
            )

        assert response.topology.service_id == "sfs-turbo-001"


@pytest.mark.asyncio
class TestGetServiceTopologyByInstanceId:
    """Test get_service_topology when called with instance_id."""

    async def test_resolves_instance_to_service(self) -> None:
        params = TopologyQueryParams(
            instance_id="sfs-node-02",
            time_range_start="2025-03-05T09:00:00Z",
            time_range_end="2025-03-05T11:00:00Z",
        )
        mock_topo = _make_sample_topology()

        with (
            patch(
                "aiops_agent.tools.topology._resolve_service_from_instance",
                new_callable=AsyncMock,
                return_value="sfs-turbo-001",
            ),
            patch(
                "aiops_agent.tools.topology._fetch_topology",
                new_callable=AsyncMock,
                return_value=mock_topo,
            ),
        ):
            response = await get_service_topology(params)

        assert response.topology.service_id == "sfs-turbo-001"
        assert response.queried_instance_id == "sfs-node-02"

    async def test_both_ids_provided(self) -> None:
        """When both service_id and instance_id are given, use service_id
        directly and set queried_instance_id."""
        params = TopologyQueryParams(
            service_id="sfs-turbo-001",
            instance_id="sfs-node-02",
            time_range_start="2025-03-05T09:00:00Z",
            time_range_end="2025-03-05T11:00:00Z",
        )
        mock_topo = _make_sample_topology()

        with patch(
            "aiops_agent.tools.topology._fetch_topology",
            new_callable=AsyncMock,
            return_value=mock_topo,
        ):
            response = await get_service_topology(params)

        assert response.topology.service_id == "sfs-turbo-001"
        assert response.queried_instance_id == "sfs-node-02"


@pytest.mark.asyncio
class TestGetServiceTopologyValidation:
    """Test input validation."""

    async def test_no_id_raises_error(self) -> None:
        params = TopologyQueryParams(
            time_range_start="2025-03-05T09:00:00Z",
            time_range_end="2025-03-05T11:00:00Z",
        )
        with pytest.raises(ValueError, match="At least one of"):
            await get_service_topology(params)
