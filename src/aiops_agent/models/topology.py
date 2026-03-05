"""Service topology data models.

These models define the structure of service topology data returned by
get_service_topology. The design ensures every entity carries enough
identifiers (service_id, instance_id, host IP, ECS ID) so that downstream
tools (query_metrics, query_logs, query_alarms) can directly use them
without additional lookups.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class ServiceType(str, Enum):
    """Cloud service types."""

    SFS_TURBO = "SFS_TURBO"
    OBS = "OBS"
    ECS = "ECS"
    EVS = "EVS"
    VPC = "VPC"


class ServiceStatus(str, Enum):
    """Aggregated health status."""

    NORMAL = "NORMAL"
    DEGRADED = "DEGRADED"
    FAULT = "FAULT"


class InstanceStatus(str, Enum):
    """Runtime status of a single instance."""

    RUNNING = "RUNNING"
    DEGRADED = "DEGRADED"
    FAULT = "FAULT"
    STOPPED = "STOPPED"


class InstanceRole(str, Enum):
    """Logical role of an instance within a service."""

    MASTER = "MASTER"
    SLAVE = "SLAVE"
    PROXY = "PROXY"
    GATEWAY = "GATEWAY"


class DependencyType(str, Enum):
    """Strength of the dependency relationship."""

    STRONG = "STRONG"
    WEAK = "WEAK"


class DependencyDirection(str, Enum):
    """Direction for topology expansion."""

    UPSTREAM = "UPSTREAM"
    DOWNSTREAM = "DOWNSTREAM"
    BOTH = "BOTH"


class ConnectionType(str, Enum):
    """Inter-instance connection protocol."""

    NFS_MOUNT = "NFS_MOUNT"
    OBS_API = "OBS_API"
    INTERNAL_RPC = "INTERNAL_RPC"


class Protocol(str, Enum):
    """Inter-service communication protocol."""

    NFS = "NFS"
    HTTP = "HTTP"
    RDMA = "RDMA"
    TCP = "TCP"


# ---------------------------------------------------------------------------
# Metric / Log pointers — the key addition for diagnostic follow-up
# ---------------------------------------------------------------------------


class MetricPointer(BaseModel):
    """Pre-computed pointers that tell downstream query_metrics / query_logs
    exactly which namespace, dimension, and resource to query.

    Including these in the topology response eliminates the need for the
    agent to guess or hardcode metric namespaces when transitioning from
    topology exploration to metric/log diagnosis.
    """

    namespace: str = Field(
        ...,
        description=(
            "Metric namespace for the monitoring system, "
            "e.g. 'SYS.SFS', 'SYS.OBS', 'SYS.ECS'"
        ),
    )
    dimension_name: str = Field(
        ...,
        description=(
            "Dimension key used for querying metrics, "
            "e.g. 'instance_id', 'disk_name', 'mount_point'"
        ),
    )
    dimension_value: str = Field(
        ...,
        description="Dimension value, typically the instance_id or resource_id",
    )
    log_group_id: Optional[str] = Field(
        default=None,
        description="Log group ID in the log service (LTS) for this entity",
    )
    log_stream_id: Optional[str] = Field(
        default=None,
        description="Log stream ID in the log service (LTS) for this entity",
    )
    suggested_metrics: list[str] = Field(
        default_factory=list,
        description=(
            "Recommended metric names to check during diagnosis, "
            "e.g. ['cpu_util', 'mem_util', 'disk_io_await']"
        ),
    )


# ---------------------------------------------------------------------------
# Host & resource models
# ---------------------------------------------------------------------------


class HostInfo(BaseModel):
    """Physical/virtual host information for an instance."""

    ecs_instance_id: str = Field(
        ..., description="ECS instance ID of the host VM"
    )
    private_ip: str = Field(..., description="Private IP address")
    az: str = Field(..., description="Availability zone")
    host_name: Optional[str] = Field(
        default=None, description="Hostname (DNS or OS level)"
    )


class InstanceResources(BaseModel):
    """Allocated compute resources."""

    cpu_cores: int = Field(..., description="Number of vCPU cores")
    memory_gb: int = Field(..., description="Memory in GiB")
    disk_gb: int = Field(..., description="Local/attached disk in GiB")
    network_bandwidth_mbps: int = Field(
        ..., description="Network bandwidth in Mbps"
    )


class ConnectionInfo(BaseModel):
    """A connection from this instance to another instance."""

    target_instance_id: str = Field(
        ..., description="Target instance identifier"
    )
    target_service_id: str = Field(
        ..., description="Service that owns the target instance"
    )
    connection_type: ConnectionType = Field(
        ..., description="Connection protocol type"
    )
    port: int = Field(..., description="Target port")
    status: InstanceStatus = Field(
        ..., description="Connection health status"
    )


# ---------------------------------------------------------------------------
# Service instance
# ---------------------------------------------------------------------------


class ServiceInstance(BaseModel):
    """A single running instance within a service.

    Carries full host info + metric pointers so that the agent can
    directly query metrics/logs for this instance without further lookups.
    """

    instance_id: str = Field(..., description="Instance unique identifier")
    instance_name: str = Field(..., description="Human-readable instance name")
    service_id: str = Field(..., description="Parent service identifier")
    instance_type: str = Field(
        ...,
        description=(
            "Instance type within the service, "
            "e.g. 'SFS_STORAGE', 'SFS_PROXY', 'OBS_GATEWAY'"
        ),
    )
    status: InstanceStatus = Field(..., description="Current runtime status")
    role: InstanceRole = Field(
        ..., description="Logical role (MASTER/SLAVE/PROXY/GATEWAY)"
    )
    host_info: HostInfo = Field(..., description="Underlying host information")
    connections: list[ConnectionInfo] = Field(
        default_factory=list,
        description="Outbound connections to other instances",
    )
    resources: Optional[InstanceResources] = Field(
        default=None, description="Allocated compute resources"
    )
    metric_pointer: Optional[MetricPointer] = Field(
        default=None,
        description=(
            "Pre-computed pointer for querying this instance's metrics/logs"
        ),
    )


# ---------------------------------------------------------------------------
# Dependency health (runtime metrics within time window)
# ---------------------------------------------------------------------------


class DependencyHealth(BaseModel):
    """Runtime health metrics for a dependency edge, aggregated over the
    query time window.
    """

    latency_p99_ms: float = Field(
        ..., description="P99 latency in milliseconds within the time window"
    )
    latency_baseline_ms: float = Field(
        ..., description="Baseline P99 latency for comparison"
    )
    error_rate: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Error rate as a fraction (0.0 – 1.0)",
    )
    request_rate_per_sec: Optional[float] = Field(
        default=None,
        description="Average request rate (QPS) within the time window",
    )


class ServiceDependency(BaseModel):
    """A dependency relationship to another service, with runtime health."""

    service_id: str = Field(..., description="Dependent service identifier")
    service_name: str = Field(..., description="Dependent service name")
    service_type: ServiceType = Field(..., description="Service type")
    dependency_type: DependencyType = Field(
        ..., description="STRONG or WEAK dependency"
    )
    protocol: Protocol = Field(
        ..., description="Communication protocol (NFS/HTTP/RDMA/TCP)"
    )
    status: ServiceStatus = Field(
        ..., description="Aggregated health status of this dependency"
    )
    health: Optional[DependencyHealth] = Field(
        default=None,
        description="Runtime health metrics aggregated over the time window",
    )
    description: str = Field(
        default="", description="Human-readable description of the dependency"
    )
    metric_pointer: Optional[MetricPointer] = Field(
        default=None,
        description="Pointer for querying metrics/logs of this dependency",
    )


# ---------------------------------------------------------------------------
# Top-level topology
# ---------------------------------------------------------------------------


class ServiceTopology(BaseModel):
    """Complete topology snapshot for a service within a time window.

    This is the core return type of get_service_topology. It bundles:
    1. Service metadata (id, name, type, region, status)
    2. Instance list with host_info + metric_pointers
    3. Upstream/downstream dependencies with runtime health
    4. Metric pointers at the service level

    Design rationale:
    - Every entity (service, instance, dependency) includes enough
      identifiers so that subsequent query_metrics / query_logs calls
      can be constructed without additional API calls.
    - MetricPointer on instances tells the agent exactly which namespace,
      dimension, log_group to query.
    - DependencyHealth on edges lets the agent immediately identify which
      dependency is degraded and decide whether to drill deeper.
    """

    service_id: str = Field(..., description="Service unique identifier")
    service_name: str = Field(..., description="Human-readable service name")
    service_type: ServiceType = Field(..., description="Cloud service type")
    region: str = Field(..., description="Region code, e.g. 'cn-north-4'")
    az: str = Field(..., description="Availability zone")
    status: ServiceStatus = Field(
        ..., description="Aggregated service health status"
    )
    topology_snapshot_time: datetime = Field(
        ..., description="Timestamp of the topology snapshot"
    )
    time_range: dict[str, str] = Field(
        ..., description="Queried time window {'start': ..., 'end': ...}"
    )

    instances: list[ServiceInstance] = Field(
        default_factory=list,
        description="All instances belonging to this service",
    )

    downstream_dependencies: list[ServiceDependency] = Field(
        default_factory=list,
        description="Services this service depends on (I depend on them)",
    )
    upstream_dependents: list[ServiceDependency] = Field(
        default_factory=list,
        description="Services that depend on this service (they depend on me)",
    )

    metric_pointer: Optional[MetricPointer] = Field(
        default=None,
        description=(
            "Service-level metric pointer for querying aggregate "
            "metrics/logs of this service"
        ),
    )


# ---------------------------------------------------------------------------
# Query parameters — input model for get_service_topology
# ---------------------------------------------------------------------------


class TopologyQueryParams(BaseModel):
    """Input parameters for get_service_topology.

    Supports two entry points:
    - By service_id: returns the full service topology.
    - By instance_id: resolves the owning service first, then returns
      the full topology with the queried instance highlighted.

    At least one of service_id or instance_id must be provided.
    If both are provided, instance_id is used to filter/highlight
    within the service topology.
    """

    service_id: Optional[str] = Field(
        default=None,
        description="Service identifier, e.g. 'sfs-turbo-001'",
    )
    instance_id: Optional[str] = Field(
        default=None,
        description=(
            "Instance identifier, e.g. 'sfs-node-02'. When provided, "
            "the tool resolves the parent service and returns the full "
            "topology with this instance highlighted."
        ),
    )
    time_range_start: str = Field(
        ...,
        description=(
            "Time window start, ISO 8601. Topology uses the last snapshot "
            "within this window; dependency health is aggregated over it."
        ),
    )
    time_range_end: str = Field(
        ..., description="Time window end, ISO 8601"
    )
    direction: DependencyDirection = Field(
        default=DependencyDirection.BOTH,
        description="Dependency query direction: UPSTREAM / DOWNSTREAM / BOTH",
    )
    depth: int = Field(
        default=1,
        ge=1,
        le=5,
        description="Topology expansion depth; 1 = direct dependencies only",
    )
    include_instances: bool = Field(
        default=True,
        description="Whether to include the full instance list",
    )


# ---------------------------------------------------------------------------
# Response wrapper
# ---------------------------------------------------------------------------


class TopologyResponse(BaseModel):
    """Response envelope for get_service_topology.

    When the query is initiated by instance_id, queried_instance_id is set
    so the caller knows which instance triggered the lookup.
    """

    topology: ServiceTopology = Field(
        ..., description="The resolved service topology snapshot"
    )
    queried_instance_id: Optional[str] = Field(
        default=None,
        description=(
            "If the query was initiated by instance_id, this field echoes "
            "the instance_id back so the caller can locate it in the "
            "instances list."
        ),
    )
