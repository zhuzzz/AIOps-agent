"""Unit tests for topology data models."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from aiops_agent.models.topology import (
    ConnectionInfo,
    ConnectionType,
    DependencyDirection,
    DependencyHealth,
    DependencyType,
    HostInfo,
    InstanceResources,
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
    TopologyResponse,
)


# ---------------------------------------------------------------------------
# MetricPointer
# ---------------------------------------------------------------------------


class TestMetricPointer:
    """Tests for the MetricPointer model."""

    def test_minimal(self) -> None:
        ptr = MetricPointer(
            namespace="SYS.SFS",
            dimension_name="instance_id",
            dimension_value="sfs-node-01",
        )
        assert ptr.namespace == "SYS.SFS"
        assert ptr.log_group_id is None
        assert ptr.suggested_metrics == []

    def test_full(self) -> None:
        ptr = MetricPointer(
            namespace="SYS.ECS",
            dimension_name="instance_id",
            dimension_value="i-abc001",
            log_group_id="lg-001",
            log_stream_id="ls-001",
            suggested_metrics=["cpu_util", "mem_util", "disk_io_await"],
        )
        assert ptr.log_group_id == "lg-001"
        assert len(ptr.suggested_metrics) == 3


# ---------------------------------------------------------------------------
# HostInfo
# ---------------------------------------------------------------------------


class TestHostInfo:
    """Tests for the HostInfo model."""

    def test_required_fields(self) -> None:
        host = HostInfo(
            ecs_instance_id="i-abc001",
            private_ip="192.168.1.101",
            az="cn-north-4a",
        )
        assert host.host_name is None

    def test_with_hostname(self) -> None:
        host = HostInfo(
            ecs_instance_id="i-abc001",
            private_ip="192.168.1.101",
            az="cn-north-4a",
            host_name="sfs-store-01",
        )
        assert host.host_name == "sfs-store-01"


# ---------------------------------------------------------------------------
# ServiceInstance
# ---------------------------------------------------------------------------


class TestServiceInstance:
    """Tests for the ServiceInstance model."""

    @pytest.fixture()
    def sample_instance(self) -> ServiceInstance:
        return ServiceInstance(
            instance_id="sfs-node-01",
            instance_name="SFS存储节点-01",
            service_id="sfs-turbo-001",
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
                suggested_metrics=[
                    "disk_read_bytes_rate",
                    "disk_write_bytes_rate",
                    "nfs_op_latency_ms",
                ],
            ),
        )

    def test_instance_has_metric_pointer(
        self, sample_instance: ServiceInstance
    ) -> None:
        assert sample_instance.metric_pointer is not None
        assert sample_instance.metric_pointer.namespace == "SYS.SFS"
        assert sample_instance.metric_pointer.log_group_id == "lg-sfs-001"

    def test_instance_host_info(
        self, sample_instance: ServiceInstance
    ) -> None:
        assert sample_instance.host_info.ecs_instance_id == "i-abcdef001"
        assert sample_instance.host_info.private_ip == "192.168.1.101"

    def test_instance_with_connections(self) -> None:
        instance = ServiceInstance(
            instance_id="sfs-node-01",
            instance_name="SFS存储节点-01",
            service_id="sfs-turbo-001",
            instance_type="SFS_STORAGE",
            status=InstanceStatus.RUNNING,
            role=InstanceRole.MASTER,
            host_info=HostInfo(
                ecs_instance_id="i-abcdef001",
                private_ip="192.168.1.101",
                az="cn-north-4a",
            ),
            connections=[
                ConnectionInfo(
                    target_instance_id="obs-gw-01",
                    target_service_id="obs-bucket-train-data",
                    connection_type=ConnectionType.OBS_API,
                    port=443,
                    status=InstanceStatus.DEGRADED,
                ),
            ],
        )
        assert len(instance.connections) == 1
        assert instance.connections[0].status == InstanceStatus.DEGRADED


# ---------------------------------------------------------------------------
# DependencyHealth
# ---------------------------------------------------------------------------


class TestDependencyHealth:
    """Tests for the DependencyHealth model."""

    def test_valid_health(self) -> None:
        health = DependencyHealth(
            latency_p99_ms=850.0,
            latency_baseline_ms=50.0,
            error_rate=0.12,
            request_rate_per_sec=1500.0,
        )
        assert health.latency_p99_ms == 850.0
        assert health.error_rate == 0.12

    def test_error_rate_bounds(self) -> None:
        with pytest.raises(ValidationError):
            DependencyHealth(
                latency_p99_ms=10.0,
                latency_baseline_ms=5.0,
                error_rate=1.5,  # > 1.0 is invalid
            )

    def test_error_rate_negative(self) -> None:
        with pytest.raises(ValidationError):
            DependencyHealth(
                latency_p99_ms=10.0,
                latency_baseline_ms=5.0,
                error_rate=-0.1,
            )


# ---------------------------------------------------------------------------
# ServiceDependency
# ---------------------------------------------------------------------------


class TestServiceDependency:
    """Tests for the ServiceDependency model."""

    def test_dependency_with_health_and_pointer(self) -> None:
        dep = ServiceDependency(
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
                log_group_id="lg-obs-001",
                log_stream_id="ls-obs-api",
                suggested_metrics=[
                    "request_count",
                    "first_byte_latency",
                    "error_4xx_rate",
                    "error_5xx_rate",
                ],
            ),
        )
        assert dep.health is not None
        assert dep.health.latency_p99_ms == 850.0
        assert dep.metric_pointer is not None
        assert dep.metric_pointer.namespace == "SYS.OBS"


# ---------------------------------------------------------------------------
# ServiceTopology
# ---------------------------------------------------------------------------


class TestServiceTopology:
    """Tests for the ServiceTopology model."""

    @pytest.fixture()
    def sample_topology(self) -> ServiceTopology:
        return ServiceTopology(
            service_id="sfs-turbo-001",
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
                    service_id="sfs-turbo-001",
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
                ),
            ],
            metric_pointer=MetricPointer(
                namespace="SYS.SFS",
                dimension_name="service_id",
                dimension_value="sfs-turbo-001",
                log_group_id="lg-sfs-001",
                log_stream_id="ls-sfs-all",
                suggested_metrics=[
                    "nfs_read_ops",
                    "nfs_write_ops",
                    "nfs_latency_p99",
                ],
            ),
        )

    def test_topology_structure(
        self, sample_topology: ServiceTopology
    ) -> None:
        assert sample_topology.service_id == "sfs-turbo-001"
        assert sample_topology.status == ServiceStatus.DEGRADED
        assert len(sample_topology.instances) == 1
        assert len(sample_topology.downstream_dependencies) == 1

    def test_topology_metric_pointer(
        self, sample_topology: ServiceTopology
    ) -> None:
        assert sample_topology.metric_pointer is not None
        assert sample_topology.metric_pointer.namespace == "SYS.SFS"
        assert "nfs_latency_p99" in (
            sample_topology.metric_pointer.suggested_metrics
        )

    def test_instance_metric_pointer_for_follow_up(
        self, sample_topology: ServiceTopology
    ) -> None:
        """Verify that instances carry enough info for metric queries."""
        inst = sample_topology.instances[0]
        assert inst.metric_pointer is not None
        # Agent can directly use these to call query_metrics
        assert inst.metric_pointer.namespace == "SYS.SFS"
        assert inst.metric_pointer.dimension_name == "instance_id"
        assert inst.metric_pointer.dimension_value == "sfs-node-01"
        # Host info for ECS-level metric correlation
        assert inst.host_info.ecs_instance_id == "i-abcdef001"

    def test_dependency_health_for_triage(
        self, sample_topology: ServiceTopology
    ) -> None:
        """Verify dependency health enables immediate triage."""
        dep = sample_topology.downstream_dependencies[0]
        assert dep.status == ServiceStatus.DEGRADED
        assert dep.dependency_type == DependencyType.STRONG
        assert dep.health is not None
        # P99 is 17x baseline — clearly anomalous
        ratio = dep.health.latency_p99_ms / dep.health.latency_baseline_ms
        assert ratio > 10

    def test_serialization_roundtrip(
        self, sample_topology: ServiceTopology
    ) -> None:
        data = sample_topology.model_dump(mode="json")
        restored = ServiceTopology.model_validate(data)
        assert restored.service_id == sample_topology.service_id
        assert len(restored.instances) == len(sample_topology.instances)


# ---------------------------------------------------------------------------
# TopologyQueryParams
# ---------------------------------------------------------------------------


class TestTopologyQueryParams:
    """Tests for the TopologyQueryParams input model."""

    def test_by_service_id(self) -> None:
        params = TopologyQueryParams(
            service_id="sfs-turbo-001",
            time_range_start="2025-03-05T09:00:00Z",
            time_range_end="2025-03-05T11:00:00Z",
        )
        assert params.service_id == "sfs-turbo-001"
        assert params.instance_id is None
        assert params.direction == DependencyDirection.BOTH
        assert params.depth == 1
        assert params.include_instances is True

    def test_by_instance_id(self) -> None:
        params = TopologyQueryParams(
            instance_id="sfs-node-02",
            time_range_start="2025-03-05T09:00:00Z",
            time_range_end="2025-03-05T11:00:00Z",
        )
        assert params.instance_id == "sfs-node-02"
        assert params.service_id is None

    def test_both_ids(self) -> None:
        params = TopologyQueryParams(
            service_id="sfs-turbo-001",
            instance_id="sfs-node-02",
            time_range_start="2025-03-05T09:00:00Z",
            time_range_end="2025-03-05T11:00:00Z",
        )
        assert params.service_id == "sfs-turbo-001"
        assert params.instance_id == "sfs-node-02"

    def test_depth_bounds(self) -> None:
        with pytest.raises(ValidationError):
            TopologyQueryParams(
                service_id="sfs-turbo-001",
                time_range_start="2025-03-05T09:00:00Z",
                time_range_end="2025-03-05T11:00:00Z",
                depth=6,  # max is 5
            )

    def test_direction_enum(self) -> None:
        params = TopologyQueryParams(
            service_id="sfs-turbo-001",
            time_range_start="2025-03-05T09:00:00Z",
            time_range_end="2025-03-05T11:00:00Z",
            direction=DependencyDirection.DOWNSTREAM,
        )
        assert params.direction == DependencyDirection.DOWNSTREAM


# ---------------------------------------------------------------------------
# TopologyResponse
# ---------------------------------------------------------------------------


class TestTopologyResponse:
    """Tests for the TopologyResponse envelope."""

    def test_response_with_queried_instance(self) -> None:
        topo = ServiceTopology(
            service_id="sfs-turbo-001",
            service_name="SFS Turbo",
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
        )
        resp = TopologyResponse(
            topology=topo,
            queried_instance_id="sfs-node-02",
        )
        assert resp.queried_instance_id == "sfs-node-02"
        assert resp.topology.service_id == "sfs-turbo-001"

    def test_response_without_queried_instance(self) -> None:
        topo = ServiceTopology(
            service_id="sfs-turbo-001",
            service_name="SFS Turbo",
            service_type=ServiceType.SFS_TURBO,
            region="cn-north-4",
            az="cn-north-4a",
            status=ServiceStatus.NORMAL,
            topology_snapshot_time=datetime(
                2025, 3, 5, 10, 30, 0, tzinfo=timezone.utc
            ),
            time_range={
                "start": "2025-03-05T09:00:00Z",
                "end": "2025-03-05T11:00:00Z",
            },
        )
        resp = TopologyResponse(topology=topo)
        assert resp.queried_instance_id is None
