# SFS Turbo 智能故障诊断 — Tool Definitions & Mock Data

## 1. 场景与流程

**故障场景**：训练任务劣化 → SFS 告警触发 → Agent 自动定位根因为 OBS 慢盘导致性能劣化

**设计原则**：所有 Tool 均携带 `time_range_start` / `time_range_end` 时间窗参数，确保 Agent 在故障诊断全流程中始终聚焦于同一故障时段，避免拿到非故障时段的脏数据。

**Agent 诊断流程**：

```
收到 SFS 告警 (含 ECS instanceID, 时间戳)
  │
  │  ← Agent 根据告警时间确定诊断时间窗: [告警首次触发前30min, 当前时间]
  │
  ├─ [get_service_topology]          获取 SFS 拓扑快照（含实例列表）+ 依赖健康度 (一次拿全)
  │
  │  ← 拿到包含时间窗的拓扑图后，并行拉取本服务的全部告警、指标异常、日志
  ├─┬─ [query_alarms]                并行: 拉取时间窗内 SFS 全量告警 (12条)
  │ ├─ [detect_metric_anomalies]     并行: 对 SFS 全部实例做指标异常检测
  │ └─ [query_logs]                  并行: 拉取时间窗内 SFS 关键日志
  │
  ├─ [cluster_alarms]                告警聚类 → 4 大类（限定时间窗）
  │
  ├─ [create_diagnosis_task] × 4     对每类下发诊断（传入时间窗）
  ├─ [get_diagnosis_result] × 4      轮询结果 → 全部未找到 SFS 自身根因
  │
  │  ← topology 已返回依赖健康度，Agent 发现 OBS status=DEGRADED, latency_p99=850ms
  │——根据已有的拓扑快照，诊断 OBS 服务
  ├─┬─ [query_alarms]                并行: 拉取时间窗内 OBS 全量告警 (8条)
  │ ├─ [detect_metric_anomalies]     并行: 对 OBS 全部实例做指标异常检测
  │ └─ [query_logs]                  并行: 拉取时间窗内 OBS 关键日志
  │
  ├─ [cluster_alarms]                OBS 告警聚类
  ├─ [create_diagnosis_task]         对 OBS 聚类下发诊断
  ├─ [get_diagnosis_result]          ✅ 找到根因: obs-store-03 慢盘
  │
  ├─ [query_metrics]                 拉取时间窗内 OBS 磁盘时延指标作为证据
  └─ [query_logs]                    拉取时间窗内 OBS 慢盘日志作为证据
```

---

## 2. 公共时间窗参数说明

所有 Tool 均包含以下两个 **required** 参数：

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `time_range_start` | string (ISO 8601) | **是** | 查询时间窗起始，如 `"2025-03-05T09:00:00Z"` |
| `time_range_end` | string (ISO 8601) | **是** | 查询时间窗结束，如 `"2025-03-05T11:00:00Z"` |

**时间窗在各 Tool 中的语义**：

| Tool | 时间窗语义 |
|------|-----------|
| get_service_topology | 返回窗口内拓扑快照（含实例列表），依赖健康指标（时延/错误率）为窗口内统计值 |
| query_alarms | 返回窗口内触发或活跃的告警 |
| get_alarm_detail | 返回该告警在窗口内的状态快照和值变化趋势 |
| cluster_alarms | 对窗口内活跃的告警进行聚类分析 |
| create_diagnosis_task | 诊断引擎在该窗口内分析指标/日志/拓扑 |
| get_diagnosis_result | 返回诊断结果（窗口已在创建时指定，此处用于校验） |
| query_metrics | 返回窗口内的时序数据点 |
| detect_metric_anomalies | 在窗口内对指定服务全部实例做异常检测，返回可能的故障点 |
| list_metric_definitions | 返回窗口内生效的指标定义和阈值配置 |
| query_logs | 返回窗口内的日志条目 |
| get_log_context | 在窗口内获取目标日志的前后上下文 |

---

## 3. Tool Definitions 总览

| # | Tool Name | 用途 |
|---|-----------|------|
| 1 | get_service_topology | 获取服务拓扑、元信息、实例列表、上下游依赖及运行时健康度 |
| 2 | query_alarms | 按条件查询告警列表 |
| 3 | get_alarm_detail | 获取单条告警详情 |
| 4 | cluster_alarms | 告警聚类分析 |
| 5 | create_diagnosis_task | 创建诊断任务 |
| 6 | get_diagnosis_result | 查询诊断任务结果 |
| 7 | query_metrics | 查询时序指标数据 |
| 8 | detect_metric_anomalies | 基于指标做异常检测，返回可能的故障点 |
| 9 | list_metric_definitions | 获取可用指标清单 |
| 10 | query_logs | 查询日志 |
| 11 | get_log_context | 获取日志上下文 |

---

## 4. Tool Definitions（OpenAI Function Calling 格式）

### Tool 1: get_service_topology

```json
{
  "type": "function",
  "function": {
    "name": "get_service_topology",
    "description": "获取指定时间窗内的服务拓扑快照，一次返回服务元信息、实例列表（含状态、角色、宿主机信息）和上下游依赖关系。依赖关系包含运行时健康指标（P99时延、错误率、基线对比），Agent 可直接判断哪个依赖异常，无需额外调用。可通过 direction 控制查询上游/下游，通过 depth 控制递归展开深度。当本服务诊断未找到根因时，Agent 应从返回的 downstream_dependencies 中选择 status=DEGRADED 且 dependency_type=STRONG 的服务继续追溯。",
    "parameters": {
      "type": "object",
      "properties": {
        "service_id": {
          "type": "string",
          "description": "服务唯一标识，如 'sfs-turbo-001'"
        },
        "time_range_start": {
          "type": "string",
          "description": "时间窗起始，ISO 8601。拓扑取窗口内最后快照，依赖健康指标为窗口内统计值"
        },
        "time_range_end": {
          "type": "string",
          "description": "时间窗结束，ISO 8601"
        },
        "direction": {
          "type": "string",
          "enum": ["UPSTREAM", "DOWNSTREAM", "BOTH"],
          "description": "依赖查询方向：UPSTREAM=谁依赖我，DOWNSTREAM=我依赖谁",
          "default": "BOTH"
        },
        "depth": {
          "type": "integer",
          "description": "拓扑展开深度，1=仅直接依赖，最大5",
          "default": 1
        },
        "include_instances": {
          "type": "boolean",
          "description": "是否包含实例ID列表",
          "default": true
        }
      },
      "required": ["service_id", "time_range_start", "time_range_end"]
    }
  }
}
```

#### Mock 调用 A — 首次查询 SFS 拓扑（direction=BOTH）

**Agent 调用参数：**
```json
{
  "service_id": "sfs-turbo-001",
  "time_range_start": "2025-03-05T09:00:00Z",
  "time_range_end": "2025-03-05T11:00:00Z",
  "direction": "BOTH",
  "depth": 1,
  "include_instances": true
}
```

**Mock 返回：**
```json
{
  "service_id": "sfs-turbo-001",
  "service_name": "SFS Turbo 文件存储",
  "service_type": "SFS_TURBO",
  "region": "cn-north-4",
  "az": "cn-north-4a",
  "status": "DEGRADED",
  "topology_snapshot_time": "2025-03-05T10:30:00Z",
  "time_range": {"start": "2025-03-05T09:00:00Z", "end": "2025-03-05T11:00:00Z"},
  "instances": [
    {"instance_id": "sfs-node-01", "instance_name": "SFS存储节点-01", "instance_type": "SFS_STORAGE", "status": "RUNNING", "role": "MASTER", "host_info": {"ecs_instance_id": "i-abcdef001", "private_ip": "192.168.1.101", "az": "cn-north-4a"}},
    {"instance_id": "sfs-node-02", "instance_name": "SFS存储节点-02", "instance_type": "SFS_STORAGE", "status": "DEGRADED", "role": "SLAVE", "host_info": {"ecs_instance_id": "i-abcdef002", "private_ip": "192.168.1.102", "az": "cn-north-4a"}},
    {"instance_id": "sfs-node-03", "instance_name": "SFS存储节点-03", "instance_type": "SFS_STORAGE", "status": "RUNNING", "role": "SLAVE", "host_info": {"ecs_instance_id": "i-abcdef003", "private_ip": "192.168.1.103", "az": "cn-north-4b"}},
    {"instance_id": "sfs-proxy-01", "instance_name": "SFS协议代理-01", "instance_type": "SFS_PROXY", "status": "RUNNING", "role": "PROXY", "host_info": {"ecs_instance_id": "i-abcdef004", "private_ip": "192.168.1.111", "az": "cn-north-4a"}},
    {"instance_id": "sfs-proxy-02", "instance_name": "SFS协议代理-02", "instance_type": "SFS_PROXY", "status": "RUNNING", "role": "PROXY", "host_info": {"ecs_instance_id": "i-abcdef005", "private_ip": "192.168.1.112", "az": "cn-north-4b"}},
    {"instance_id": "sfs-meta-01", "instance_name": "SFS元数据节点-01", "instance_type": "SFS_METADATA", "status": "RUNNING", "role": "MASTER", "host_info": {"ecs_instance_id": "i-abcdef006", "private_ip": "192.168.1.121", "az": "cn-north-4a"}},
    {"instance_id": "sfs-meta-02", "instance_name": "SFS元数据节点-02", "instance_type": "SFS_METADATA", "status": "RUNNING", "role": "SLAVE", "host_info": {"ecs_instance_id": "i-abcdef007", "private_ip": "192.168.1.122", "az": "cn-north-4b"}}
  ],
  "downstream_dependencies": [
    {
      "service_id": "obs-bucket-train-data",
      "service_name": "OBS 训练数据桶",
      "service_type": "OBS",
      "dependency_type": "STRONG",
      "protocol": "HTTP",
      "status": "DEGRADED",
      "latency_p99_ms": 850,
      "latency_baseline_ms": 50,
      "error_rate": 0.12,
      "description": "SFS 数据持久化层，窗口内 P99 时延 850ms（基线 50ms）"
    },
    {
      "service_id": "evs-sfs-meta",
      "service_name": "EVS 元数据盘",
      "service_type": "EVS",
      "dependency_type": "STRONG",
      "protocol": "TCP",
      "status": "NORMAL",
      "latency_p99_ms": 2,
      "latency_baseline_ms": 1,
      "error_rate": 0.0,
      "description": "元数据存储，窗口内状态正常"
    },
    {
      "service_id": "vpc-subnet-001",
      "service_name": "VPC 子网",
      "service_type": "VPC",
      "dependency_type": "STRONG",
      "protocol": "TCP",
      "status": "NORMAL",
      "latency_p99_ms": 0.5,
      "latency_baseline_ms": 0.3,
      "error_rate": 0.0,
      "description": "网络层，窗口内状态正常"
    }
  ],
  "upstream_dependents": [
    {
      "service_id": "ecs-gpu-training-cluster",
      "service_name": "GPU 训练集群",
      "service_type": "ECS",
      "dependency_type": "STRONG",
      "protocol": "NFS",
      "status": "DEGRADED",
      "latency_p99_ms": 325,
      "latency_baseline_ms": 10,
      "error_rate": 0.05,
      "description": "GPU 训练集群挂载 SFS，窗口内 NFS 读时延劣化"
    }
  ]
}
```

#### Mock 调用 B — 追溯到 OBS 后查询 OBS 拓扑（direction=DOWNSTREAM）

**Agent 调用参数：**
```json
{
  "service_id": "obs-bucket-train-data",
  "time_range_start": "2025-03-05T08:00:00Z",
  "time_range_end": "2025-03-05T11:00:00Z",
  "direction": "DOWNSTREAM",
  "depth": 1,
  "include_instances": true
}
```

**Mock 返回：**
```json
{
  "service_id": "obs-bucket-train-data",
  "service_name": "OBS 训练数据桶",
  "service_type": "OBS",
  "region": "cn-north-4",
  "az": "cn-north-4a",
  "status": "DEGRADED",
  "topology_snapshot_time": "2025-03-05T10:30:00Z",
  "time_range": {"start": "2025-03-05T08:00:00Z", "end": "2025-03-05T11:00:00Z"},
  "instances": [
    {"instance_id": "obs-gw-01", "instance_name": "OBS网关-01", "instance_type": "OBS_GATEWAY", "status": "RUNNING", "role": "GATEWAY", "host_info": {"ecs_instance_id": "i-obs001", "private_ip": "192.168.2.101", "az": "cn-north-4a"}},
    {"instance_id": "obs-gw-02", "instance_name": "OBS网关-02", "instance_type": "OBS_GATEWAY", "status": "RUNNING", "role": "GATEWAY", "host_info": {"ecs_instance_id": "i-obs002", "private_ip": "192.168.2.102", "az": "cn-north-4b"}},
    {"instance_id": "obs-store-01", "instance_name": "OBS存储节点-01", "instance_type": "OBS_STORAGE", "status": "RUNNING", "role": "MASTER", "host_info": {"ecs_instance_id": "i-obs003", "private_ip": "192.168.2.111", "az": "cn-north-4a"}},
    {"instance_id": "obs-store-02", "instance_name": "OBS存储节点-02", "instance_type": "OBS_STORAGE", "status": "RUNNING", "role": "SLAVE", "host_info": {"ecs_instance_id": "i-obs004", "private_ip": "192.168.2.112", "az": "cn-north-4a"}},
    {"instance_id": "obs-store-03", "instance_name": "OBS存储节点-03", "instance_type": "OBS_STORAGE", "status": "DEGRADED", "role": "SLAVE", "host_info": {"ecs_instance_id": "i-obs005", "private_ip": "192.168.2.113", "az": "cn-north-4a"}}
  ],
  "downstream_dependencies": [
    {
      "service_id": "evs-obs-data",
      "service_name": "EVS OBS数据盘",
      "service_type": "EVS",
      "dependency_type": "STRONG",
      "protocol": "TCP",
      "status": "NORMAL",
      "latency_p99_ms": 1.5,
      "latency_baseline_ms": 1.0,
      "error_rate": 0.0,
      "description": "OBS 底层块存储，窗口内正常"
    },
    {
      "service_id": "vpc-subnet-002",
      "service_name": "VPC 子网(OBS)",
      "service_type": "VPC",
      "dependency_type": "STRONG",
      "protocol": "TCP",
      "status": "NORMAL",
      "latency_p99_ms": 0.4,
      "latency_baseline_ms": 0.3,
      "error_rate": 0.0,
      "description": "网络层，窗口内正常"
    }
  ],
  "upstream_dependents": []
}
```

---

### Tool 2: query_alarms

```json
{
  "type": "function",
  "function": {
    "name": "query_alarms",
    "description": "按条件查询指定时间窗内的告警列表。返回在该时间窗内首次触发或仍处于活跃状态的告警。典型用法：先按 service_id + status=FIRING 拉取窗口内全量活跃告警，再送入 cluster_alarms。",
    "parameters": {
      "type": "object",
      "properties": {
        "service_id": {
          "type": "string",
          "description": "服务唯一标识"
        },
        "time_range_start": {
          "type": "string",
          "description": "时间窗起始，ISO 8601"
        },
        "time_range_end": {
          "type": "string",
          "description": "时间窗结束，ISO 8601"
        },
        "instance_ids": {
          "type": "array",
          "items": {"type": "string"},
          "description": "按实例ID过滤"
        },
        "alarm_levels": {
          "type": "array",
          "items": {"type": "string", "enum": ["CRITICAL", "MAJOR", "MINOR", "WARNING"]},
          "description": "按告警级别过滤"
        },
        "status": {
          "type": "array",
          "items": {"type": "string", "enum": ["FIRING", "RESOLVED", "ACKNOWLEDGED"]},
          "description": "按告警状态过滤"
        },
        "page_size": {
          "type": "integer",
          "default": 50
        },
        "page_token": {
          "type": "string"
        }
      },
      "required": ["service_id", "time_range_start", "time_range_end"]
    }
  }
}
```

#### Mock 调用 A — SFS 全量活跃告警

**Agent 调用参数：**
```json
{
  "service_id": "sfs-turbo-001",
  "time_range_start": "2025-03-05T09:00:00Z",
  "time_range_end": "2025-03-05T11:00:00Z",
  "status": ["FIRING"]
}
```

**Mock 返回（12 条）：**
```json
{
  "total": 12,
  "time_range": {"start": "2025-03-05T09:00:00Z", "end": "2025-03-05T11:00:00Z"},
  "alarms": [
    {"alarm_id": "ALM-SFS-001", "alarm_name": "SFS NFS读时延超阈值", "alarm_level": "CRITICAL", "alarm_source": "THRESHOLD", "status": "FIRING", "service_id": "sfs-turbo-001", "instance_id": "sfs-node-01", "metric": "sfs_nfs_read_latency_ms", "current_value": 320.5, "threshold": 50.0, "unit": "ms", "first_occur_time": "2025-03-05T09:15:00Z", "last_occur_time": "2025-03-05T10:45:00Z", "occur_count": 38, "description": "NFS 读操作 P99 时延 320.5ms，超过阈值 50ms", "tags": {"az": "cn-north-4a", "operation": "read", "protocol": "nfs"}},
    {"alarm_id": "ALM-SFS-002", "alarm_name": "SFS NFS写时延超阈值", "alarm_level": "CRITICAL", "alarm_source": "THRESHOLD", "status": "FIRING", "service_id": "sfs-turbo-001", "instance_id": "sfs-node-01", "metric": "sfs_nfs_write_latency_ms", "current_value": 580.2, "threshold": 100.0, "unit": "ms", "first_occur_time": "2025-03-05T09:18:00Z", "last_occur_time": "2025-03-05T10:45:00Z", "occur_count": 35, "description": "NFS 写操作 P99 时延 580.2ms", "tags": {"az": "cn-north-4a", "operation": "write", "protocol": "nfs"}},
    {"alarm_id": "ALM-SFS-003", "alarm_name": "SFS NFS读时延超阈值", "alarm_level": "MAJOR", "alarm_source": "THRESHOLD", "status": "FIRING", "service_id": "sfs-turbo-001", "instance_id": "sfs-node-02", "metric": "sfs_nfs_read_latency_ms", "current_value": 280.3, "threshold": 50.0, "unit": "ms", "first_occur_time": "2025-03-05T09:20:00Z", "last_occur_time": "2025-03-05T10:44:00Z", "occur_count": 30, "description": "NFS 读操作 P99 时延 280.3ms", "tags": {"az": "cn-north-4a", "operation": "read", "protocol": "nfs"}},
    {"alarm_id": "ALM-SFS-004", "alarm_name": "SFS NFS写时延超阈值", "alarm_level": "MAJOR", "alarm_source": "THRESHOLD", "status": "FIRING", "service_id": "sfs-turbo-001", "instance_id": "sfs-node-02", "metric": "sfs_nfs_write_latency_ms", "current_value": 490.7, "threshold": 100.0, "unit": "ms", "first_occur_time": "2025-03-05T09:22:00Z", "last_occur_time": "2025-03-05T10:44:00Z", "occur_count": 28, "description": "NFS 写操作 P99 时延 490.7ms", "tags": {"az": "cn-north-4a", "operation": "write", "protocol": "nfs"}},
    {"alarm_id": "ALM-SFS-005", "alarm_name": "SFS 后端OBS请求超时率升高", "alarm_level": "CRITICAL", "alarm_source": "ANOMALY_DETECTION", "status": "FIRING", "service_id": "sfs-turbo-001", "instance_id": "sfs-node-01", "metric": "sfs_backend_obs_timeout_rate", "current_value": 0.15, "threshold": 0.01, "unit": "ratio", "first_occur_time": "2025-03-05T09:12:00Z", "last_occur_time": "2025-03-05T10:45:00Z", "occur_count": 42, "description": "后端 OBS 请求超时率 15%", "tags": {"az": "cn-north-4a", "backend": "obs"}},
    {"alarm_id": "ALM-SFS-006", "alarm_name": "SFS 后端OBS请求超时率升高", "alarm_level": "MAJOR", "alarm_source": "ANOMALY_DETECTION", "status": "FIRING", "service_id": "sfs-turbo-001", "instance_id": "sfs-node-02", "metric": "sfs_backend_obs_timeout_rate", "current_value": 0.12, "threshold": 0.01, "unit": "ratio", "first_occur_time": "2025-03-05T09:14:00Z", "last_occur_time": "2025-03-05T10:44:00Z", "occur_count": 38, "description": "后端 OBS 请求超时率 12%", "tags": {"az": "cn-north-4a", "backend": "obs"}},
    {"alarm_id": "ALM-SFS-007", "alarm_name": "SFS IO队列深度过高", "alarm_level": "MAJOR", "alarm_source": "THRESHOLD", "status": "FIRING", "service_id": "sfs-turbo-001", "instance_id": "sfs-node-01", "metric": "sfs_io_queue_depth", "current_value": 512, "threshold": 128, "unit": "count", "first_occur_time": "2025-03-05T09:25:00Z", "last_occur_time": "2025-03-05T10:45:00Z", "occur_count": 25, "description": "IO 队列深度 512", "tags": {"az": "cn-north-4a"}},
    {"alarm_id": "ALM-SFS-008", "alarm_name": "SFS IO队列深度过高", "alarm_level": "MINOR", "alarm_source": "THRESHOLD", "status": "FIRING", "service_id": "sfs-turbo-001", "instance_id": "sfs-node-02", "metric": "sfs_io_queue_depth", "current_value": 256, "threshold": 128, "unit": "count", "first_occur_time": "2025-03-05T09:30:00Z", "last_occur_time": "2025-03-05T10:44:00Z", "occur_count": 20, "description": "IO 队列深度 256", "tags": {"az": "cn-north-4a"}},
    {"alarm_id": "ALM-SFS-009", "alarm_name": "SFS 连接数接近上限", "alarm_level": "WARNING", "alarm_source": "THRESHOLD", "status": "FIRING", "service_id": "sfs-turbo-001", "instance_id": "sfs-proxy-01", "metric": "sfs_active_connections", "current_value": 9500, "threshold": 10000, "unit": "count", "first_occur_time": "2025-03-05T09:40:00Z", "last_occur_time": "2025-03-05T10:45:00Z", "occur_count": 12, "description": "活跃连接数 9500", "tags": {"az": "cn-north-4a"}},
    {"alarm_id": "ALM-SFS-010", "alarm_name": "SFS 吞吐量下降", "alarm_level": "MAJOR", "alarm_source": "ANOMALY_DETECTION", "status": "FIRING", "service_id": "sfs-turbo-001", "instance_id": "sfs-node-01", "metric": "sfs_throughput_mbps", "current_value": 800, "threshold": 5000, "unit": "MBps", "first_occur_time": "2025-03-05T09:20:00Z", "last_occur_time": "2025-03-05T10:45:00Z", "occur_count": 30, "description": "吞吐量降至 800MBps，下降 84%", "tags": {"az": "cn-north-4a", "direction": "read"}},
    {"alarm_id": "ALM-SFS-011", "alarm_name": "SFS 吞吐量下降", "alarm_level": "MINOR", "alarm_source": "ANOMALY_DETECTION", "status": "FIRING", "service_id": "sfs-turbo-001", "instance_id": "sfs-node-02", "metric": "sfs_throughput_mbps", "current_value": 1200, "threshold": 5000, "unit": "MBps", "first_occur_time": "2025-03-05T09:25:00Z", "last_occur_time": "2025-03-05T10:44:00Z", "occur_count": 25, "description": "吞吐量降至 1200MBps，下降 76%", "tags": {"az": "cn-north-4a", "direction": "read"}},
    {"alarm_id": "ALM-SFS-012", "alarm_name": "SFS CPU使用率升高", "alarm_level": "WARNING", "alarm_source": "THRESHOLD", "status": "FIRING", "service_id": "sfs-turbo-001", "instance_id": "sfs-node-01", "metric": "sfs_cpu_usage_percent", "current_value": 78.5, "threshold": 80.0, "unit": "%", "first_occur_time": "2025-03-05T09:35:00Z", "last_occur_time": "2025-03-05T10:45:00Z", "occur_count": 15, "description": "CPU 使用率 78.5%，IO等待占比高", "tags": {"az": "cn-north-4a"}}
  ]
}
```

#### Mock 调用 B — OBS 全量活跃告警

**Agent 调用参数：**
```json
{
  "service_id": "obs-bucket-train-data",
  "time_range_start": "2025-03-05T08:00:00Z",
  "time_range_end": "2025-03-05T11:00:00Z",
  "status": ["FIRING"]
}
```

**Mock 返回（8 条）：**
```json
{
  "total": 8,
  "time_range": {"start": "2025-03-05T08:00:00Z", "end": "2025-03-05T11:00:00Z"},
  "alarms": [
    {"alarm_id": "ALM-OBS-001", "alarm_name": "OBS PUT操作时延超阈值", "alarm_level": "CRITICAL", "alarm_source": "THRESHOLD", "status": "FIRING", "service_id": "obs-bucket-train-data", "instance_id": "obs-gw-01", "metric": "obs_put_latency_p99_ms", "current_value": 620.0, "threshold": 50.0, "unit": "ms", "first_occur_time": "2025-03-05T09:10:00Z", "last_occur_time": "2025-03-05T10:50:00Z", "occur_count": 45, "description": "OBS PUT P99 时延 620ms", "tags": {"az": "cn-north-4a", "operation": "PUT"}},
    {"alarm_id": "ALM-OBS-002", "alarm_name": "OBS GET操作时延超阈值", "alarm_level": "CRITICAL", "alarm_source": "THRESHOLD", "status": "FIRING", "service_id": "obs-bucket-train-data", "instance_id": "obs-gw-01", "metric": "obs_get_latency_p99_ms", "current_value": 380.0, "threshold": 30.0, "unit": "ms", "first_occur_time": "2025-03-05T09:10:00Z", "last_occur_time": "2025-03-05T10:50:00Z", "occur_count": 42, "description": "OBS GET P99 时延 380ms", "tags": {"az": "cn-north-4a", "operation": "GET"}},
    {"alarm_id": "ALM-OBS-003", "alarm_name": "OBS 存储节点磁盘时延异常", "alarm_level": "CRITICAL", "alarm_source": "ANOMALY_DETECTION", "status": "FIRING", "service_id": "obs-bucket-train-data", "instance_id": "obs-store-03", "metric": "obs_disk_latency_p99_ms", "current_value": 120.0, "threshold": 10.0, "unit": "ms", "first_occur_time": "2025-03-05T08:55:00Z", "last_occur_time": "2025-03-05T10:50:00Z", "occur_count": 60, "description": "obs-store-03 磁盘 P99 时延 120ms，疑似慢盘", "tags": {"az": "cn-north-4a", "disk": "sda", "node": "obs-store-03"}},
    {"alarm_id": "ALM-OBS-004", "alarm_name": "OBS 磁盘SMART健康告警", "alarm_level": "MAJOR", "alarm_source": "MONITOR", "status": "FIRING", "service_id": "obs-bucket-train-data", "instance_id": "obs-store-03", "metric": "obs_disk_smart_health_score", "current_value": 42.0, "threshold": 60.0, "unit": "%", "first_occur_time": "2025-03-05T08:30:00Z", "last_occur_time": "2025-03-05T10:50:00Z", "occur_count": 55, "description": "SMART 健康评分 42%", "tags": {"az": "cn-north-4a", "disk": "sda"}},
    {"alarm_id": "ALM-OBS-005", "alarm_name": "OBS 请求队列积压", "alarm_level": "MAJOR", "alarm_source": "THRESHOLD", "status": "FIRING", "service_id": "obs-bucket-train-data", "instance_id": "obs-store-03", "metric": "obs_request_queue_length", "current_value": 2048, "threshold": 500, "unit": "count", "first_occur_time": "2025-03-05T09:15:00Z", "last_occur_time": "2025-03-05T10:50:00Z", "occur_count": 35, "description": "请求队列积压严重", "tags": {"az": "cn-north-4a"}},
    {"alarm_id": "ALM-OBS-006", "alarm_name": "OBS 5xx错误率升高", "alarm_level": "MAJOR", "alarm_source": "THRESHOLD", "status": "FIRING", "service_id": "obs-bucket-train-data", "instance_id": "obs-gw-01", "metric": "obs_5xx_error_rate", "current_value": 0.08, "threshold": 0.01, "unit": "ratio", "first_occur_time": "2025-03-05T09:20:00Z", "last_occur_time": "2025-03-05T10:50:00Z", "occur_count": 30, "description": "5xx 错误率 8%", "tags": {"az": "cn-north-4a"}},
    {"alarm_id": "ALM-OBS-007", "alarm_name": "OBS 吞吐量下降", "alarm_level": "MINOR", "alarm_source": "ANOMALY_DETECTION", "status": "FIRING", "service_id": "obs-bucket-train-data", "instance_id": "obs-store-03", "metric": "obs_throughput_mbps", "current_value": 200, "threshold": 2000, "unit": "MBps", "first_occur_time": "2025-03-05T09:10:00Z", "last_occur_time": "2025-03-05T10:50:00Z", "occur_count": 40, "description": "吞吐量下降 90%", "tags": {"az": "cn-north-4a"}},
    {"alarm_id": "ALM-OBS-008", "alarm_name": "OBS IO Wait升高", "alarm_level": "WARNING", "alarm_source": "THRESHOLD", "status": "FIRING", "service_id": "obs-bucket-train-data", "instance_id": "obs-store-03", "metric": "obs_iowait_percent", "current_value": 65.0, "threshold": 30.0, "unit": "%", "first_occur_time": "2025-03-05T09:05:00Z", "last_occur_time": "2025-03-05T10:50:00Z", "occur_count": 50, "description": "IO Wait 65%", "tags": {"az": "cn-north-4a"}}
  ]
}
```

---

### Tool 3: get_alarm_detail

```json
{
  "type": "function",
  "function": {
    "name": "get_alarm_detail",
    "description": "获取单条告警在指定时间窗内的完整详情，包括窗口内的告警值变化趋势、原始数据和关联告警。",
    "parameters": {
      "type": "object",
      "properties": {
        "alarm_id": {
          "type": "string",
          "description": "告警唯一标识"
        },
        "time_range_start": {
          "type": "string",
          "description": "时间窗起始，ISO 8601"
        },
        "time_range_end": {
          "type": "string",
          "description": "时间窗结束，ISO 8601"
        }
      },
      "required": ["alarm_id", "time_range_start", "time_range_end"]
    }
  }
}
```

#### Mock 调用

**Agent 调用参数：**
```json
{
  "alarm_id": "ALM-OBS-003",
  "time_range_start": "2025-03-05T08:00:00Z",
  "time_range_end": "2025-03-05T11:00:00Z"
}
```

**Mock 返回：**
```json
{
  "alarm_id": "ALM-OBS-003",
  "alarm_name": "OBS 存储节点磁盘时延异常",
  "alarm_level": "CRITICAL",
  "alarm_source": "ANOMALY_DETECTION",
  "status": "FIRING",
  "service_id": "obs-bucket-train-data",
  "instance_id": "obs-store-03",
  "metric": "obs_disk_latency_p99_ms",
  "current_value": 120.0,
  "threshold": 10.0,
  "unit": "ms",
  "first_occur_time": "2025-03-05T08:55:00Z",
  "last_occur_time": "2025-03-05T10:50:00Z",
  "occur_count": 60,
  "description": "obs-store-03 磁盘 P99 时延 120ms，正常 < 5ms",
  "tags": {"az": "cn-north-4a", "disk": "sda", "node": "obs-store-03"},
  "related_alarm_ids": ["ALM-OBS-004", "ALM-OBS-005"],
  "value_trend_in_window": [
    {"timestamp": "2025-03-05T08:00:00Z", "value": 4.5},
    {"timestamp": "2025-03-05T08:30:00Z", "value": 4.8},
    {"timestamp": "2025-03-05T09:00:00Z", "value": 45.2},
    {"timestamp": "2025-03-05T09:30:00Z", "value": 98.3},
    {"timestamp": "2025-03-05T10:00:00Z", "value": 115.6},
    {"timestamp": "2025-03-05T10:30:00Z", "value": 120.0}
  ],
  "raw_data": {"anomaly_score": 0.97, "detection_model": "isolation_forest", "baseline_window": "7d", "baseline_p99": 4.8},
  "time_range": {"start": "2025-03-05T08:00:00Z", "end": "2025-03-05T11:00:00Z"}
}
```

---

### Tool 4: cluster_alarms

```json
{
  "type": "function",
  "function": {
    "name": "cluster_alarms",
    "description": "对一组告警在指定时间窗内进行聚类分析。时间窗限定聚类分析的数据范围和时间相关性计算。返回每个聚类的类别、告警列表和建议诊断方向。Agent 应对每个聚类分别下发诊断任务。",
    "parameters": {
      "type": "object",
      "properties": {
        "alarm_ids": {
          "type": "array",
          "items": {"type": "string"},
          "description": "待聚类的告警ID列表"
        },
        "time_range_start": {
          "type": "string",
          "description": "时间窗起始，ISO 8601"
        },
        "time_range_end": {
          "type": "string",
          "description": "时间窗结束，ISO 8601"
        },
        "algorithm": {
          "type": "string",
          "enum": ["AUTO", "TIME_BASED", "METRIC_BASED", "TOPOLOGY_BASED"],
          "default": "AUTO"
        },
        "max_clusters": {
          "type": "integer",
          "default": 10
        }
      },
      "required": ["alarm_ids", "time_range_start", "time_range_end"]
    }
  }
}
```

#### Mock 调用 — SFS 告警聚类

**Agent 调用参数：**
```json
{
  "alarm_ids": ["ALM-SFS-001","ALM-SFS-002","ALM-SFS-003","ALM-SFS-004","ALM-SFS-005","ALM-SFS-006","ALM-SFS-007","ALM-SFS-008","ALM-SFS-009","ALM-SFS-010","ALM-SFS-011","ALM-SFS-012"],
  "time_range_start": "2025-03-05T09:00:00Z",
  "time_range_end": "2025-03-05T11:00:00Z",
  "algorithm": "AUTO"
}
```

**Mock 返回（4 大类）：**
```json
{
  "total_alarms": 12,
  "cluster_count": 4,
  "time_range": {"start": "2025-03-05T09:00:00Z", "end": "2025-03-05T11:00:00Z"},
  "clusters": [
    {"cluster_id": "CLU-SFS-001", "cluster_name": "NFS IO时延异常", "category": "IO_LATENCY", "severity": "CRITICAL", "alarm_count": 4, "alarm_ids": ["ALM-SFS-001","ALM-SFS-002","ALM-SFS-003","ALM-SFS-004"], "common_pattern": "NFS 读写 P99 时延大幅超阈值，涉及 sfs-node-01 和 sfs-node-02", "affected_instances": ["sfs-node-01","sfs-node-02"], "time_range": {"start": "2025-03-05T09:15:00Z", "end": "2025-03-05T10:45:00Z"}, "suggested_diagnosis_type": "IO_ANALYSIS"},
    {"cluster_id": "CLU-SFS-002", "cluster_name": "OBS后端请求异常", "category": "DEPENDENCY", "severity": "CRITICAL", "alarm_count": 2, "alarm_ids": ["ALM-SFS-005","ALM-SFS-006"], "common_pattern": "后端 OBS 请求超时率异常升高，多节点同时出现", "affected_instances": ["sfs-node-01","sfs-node-02"], "time_range": {"start": "2025-03-05T09:12:00Z", "end": "2025-03-05T10:45:00Z"}, "suggested_diagnosis_type": "DEPENDENCY_CHECK"},
    {"cluster_id": "CLU-SFS-003", "cluster_name": "IO队列积压与吞吐下降", "category": "IO_LATENCY", "severity": "MAJOR", "alarm_count": 4, "alarm_ids": ["ALM-SFS-007","ALM-SFS-008","ALM-SFS-010","ALM-SFS-011"], "common_pattern": "IO 队列积压 + 吞吐量大幅下降，属 IO 时延异常的伴生现象", "affected_instances": ["sfs-node-01","sfs-node-02"], "time_range": {"start": "2025-03-05T09:20:00Z", "end": "2025-03-05T10:45:00Z"}, "suggested_diagnosis_type": "IO_ANALYSIS"},
    {"cluster_id": "CLU-SFS-004", "cluster_name": "资源使用率告警", "category": "RESOURCE", "severity": "WARNING", "alarm_count": 2, "alarm_ids": ["ALM-SFS-009","ALM-SFS-012"], "common_pattern": "连接数和 CPU 接近阈值，疑似 IO 积压连锁反应", "affected_instances": ["sfs-proxy-01","sfs-node-01"], "time_range": {"start": "2025-03-05T09:35:00Z", "end": "2025-03-05T10:45:00Z"}, "suggested_diagnosis_type": "RESOURCE_CHECK"}
  ]
}
```

---

### Tool 5: create_diagnosis_task

```json
{
  "type": "function",
  "function": {
    "name": "create_diagnosis_task",
    "description": "对指定告警聚类创建诊断任务。诊断引擎在 time_range 指定的时间窗内分析指标、日志和拓扑数据。任务异步执行，需通过 get_diagnosis_result 轮询。",
    "parameters": {
      "type": "object",
      "properties": {
        "service_id": {
          "type": "string",
          "description": "目标服务ID"
        },
        "cluster_id": {
          "type": "string",
          "description": "告警聚类ID"
        },
        "diagnosis_type": {
          "type": "string",
          "enum": ["IO_ANALYSIS", "DEPENDENCY_CHECK", "RESOURCE_CHECK", "NETWORK_CHECK"]
        },
        "alarm_ids": {
          "type": "array",
          "items": {"type": "string"}
        },
        "time_range_start": {
          "type": "string",
          "description": "诊断分析的时间窗起始，ISO 8601"
        },
        "time_range_end": {
          "type": "string",
          "description": "诊断分析的时间窗结束，ISO 8601"
        },
        "depth": {
          "type": "string",
          "enum": ["QUICK", "NORMAL", "DEEP"],
          "default": "NORMAL"
        }
      },
      "required": ["service_id", "cluster_id", "diagnosis_type", "alarm_ids", "time_range_start", "time_range_end"]
    }
  }
}
```

#### Mock 调用

**Agent 调用参数：**
```json
{
  "service_id": "sfs-turbo-001",
  "cluster_id": "CLU-SFS-001",
  "diagnosis_type": "IO_ANALYSIS",
  "alarm_ids": ["ALM-SFS-001","ALM-SFS-002","ALM-SFS-003","ALM-SFS-004"],
  "time_range_start": "2025-03-05T09:00:00Z",
  "time_range_end": "2025-03-05T11:00:00Z",
  "depth": "DEEP"
}
```

**Mock 返回：**
```json
{
  "task_id": "DIAG-SFS-001",
  "status": "PENDING",
  "create_time": "2025-03-05T10:46:00Z",
  "estimated_duration_seconds": 210,
  "time_range": {"start": "2025-03-05T09:00:00Z", "end": "2025-03-05T11:00:00Z"}
}
```

---

### Tool 6: get_diagnosis_result

```json
{
  "type": "function",
  "function": {
    "name": "get_diagnosis_result",
    "description": "查询诊断任务的执行状态和结果。时间窗用于校验请求是否与创建任务时一致。当 status=COMPLETED 时，result.root_cause_found=true 表示找到根因。",
    "parameters": {
      "type": "object",
      "properties": {
        "task_id": {
          "type": "string",
          "description": "诊断任务ID"
        },
        "time_range_start": {
          "type": "string",
          "description": "时间窗起始，ISO 8601，应与创建任务时一致"
        },
        "time_range_end": {
          "type": "string",
          "description": "时间窗结束，ISO 8601"
        }
      },
      "required": ["task_id", "time_range_start", "time_range_end"]
    }
  }
}
```

#### Mock 调用 A — SFS IO时延诊断（无根因）

**Agent 调用参数：**
```json
{"task_id": "DIAG-SFS-001", "time_range_start": "2025-03-05T09:00:00Z", "time_range_end": "2025-03-05T11:00:00Z"}
```

**Mock 返回：**
```json
{
  "task_id": "DIAG-SFS-001",
  "task_name": "SFS NFS IO时延异常诊断",
  "status": "COMPLETED",
  "service_id": "sfs-turbo-001",
  "cluster_id": "CLU-SFS-001",
  "time_range": {"start": "2025-03-05T09:00:00Z", "end": "2025-03-05T11:00:00Z"},
  "create_time": "2025-03-05T10:46:00Z",
  "complete_time": "2025-03-05T10:49:30Z",
  "result": {
    "root_cause_found": false,
    "confidence": 0.0,
    "root_cause": null,
    "root_cause_category": null,
    "evidence": [
      {"type": "METRIC", "description": "本地磁盘时延正常", "data": {"metric": "sfs_local_disk_latency_ms", "value": 0.8, "baseline": 1.0}},
      {"type": "METRIC", "description": "内部 RPC 时延正常", "data": {"metric": "sfs_internal_rpc_latency_ms", "value": 2.1, "baseline": 2.0}},
      {"type": "METRIC", "description": "进程资源正常", "data": {"metric": "sfs_process_mem_usage_percent", "value": 45.2, "baseline": 42.0}}
    ],
    "impact": "NFS IO 时延异常非 SFS 自身引起",
    "suggestion": "建议检查后端依赖服务（OBS），重点排查时延"
  },
  "steps": [
    {"step_id": "S1", "step_name": "本地磁盘检查", "status": "COMPLETED", "findings": "各项指标正常"},
    {"step_id": "S2", "step_name": "集群内部通信检查", "status": "COMPLETED", "findings": "RPC 时延正常"},
    {"step_id": "S3", "step_name": "进程级检查", "status": "COMPLETED", "findings": "无 GC 压力或线程池满"},
    {"step_id": "S4", "step_name": "后端链路分析", "status": "COMPLETED", "findings": "OBS 调用链路 P99=850ms（正常<50ms）"}
  ]
}
```

#### Mock 调用 B/C/D — SFS 其他 3 个聚类（均无根因，结构同上）

- **DIAG-SFS-002**（CLU-SFS-002 OBS依赖）→ `root_cause_found: false`，evidence: SFS→OBS P99=850ms
- **DIAG-SFS-003**（CLU-SFS-003 IO队列）→ `root_cause_found: false`，evidence: 与OBS时延高度吻合
- **DIAG-SFS-004**（CLU-SFS-004 资源）→ `root_cause_found: false`，evidence: CPU iowait主导

#### Mock 调用 E — OBS 慢盘诊断（✅ 找到根因）

**Agent 调用参数：**
```json
{"task_id": "DIAG-OBS-001", "time_range_start": "2025-03-05T08:00:00Z", "time_range_end": "2025-03-05T11:00:00Z"}
```

**Mock 返回：**
```json
{
  "task_id": "DIAG-OBS-001",
  "task_name": "OBS 存储节点慢盘诊断",
  "status": "COMPLETED",
  "service_id": "obs-bucket-train-data",
  "cluster_id": "CLU-OBS-001",
  "time_range": {"start": "2025-03-05T08:00:00Z", "end": "2025-03-05T11:00:00Z"},
  "create_time": "2025-03-05T10:52:00Z",
  "complete_time": "2025-03-05T10:56:00Z",
  "result": {
    "root_cause_found": true,
    "confidence": 0.95,
    "root_cause": "OBS 存储节点 obs-store-03 磁盘 sda 硬件劣化（慢盘），Reallocated Sector Count=156，SMART 健康评分 42%，导致 PUT/GET 时延从 5ms 升至 120ms+，影响 SFS Turbo 后端读写，最终导致 GPU 训练吞吐劣化",
    "root_cause_category": "HARDWARE_DEGRADATION",
    "evidence": [
      {"type": "METRIC", "description": "obs-store-03 磁盘时延 P99=120ms（基线 5ms）", "data": {"metric": "obs_disk_latency_p99_ms", "instance_id": "obs-store-03", "value": 120, "baseline": 5}},
      {"type": "METRIC", "description": "SMART 健康评分 42%", "data": {"metric": "obs_disk_smart_health_score", "instance_id": "obs-store-03", "disk_id": "disk-sda", "value": 42, "baseline": 98}},
      {"type": "LOG", "description": "大量慢IO警告", "data": {"log_id": "LOG-OBS-78901", "content": "WARN slow_disk_io disk=sda latency=135ms threshold=10ms count=1247 in_last_5min", "timestamp": "2025-03-05T10:30:00Z"}},
      {"type": "LOG", "description": "SMART Reallocated Sector 增长", "data": {"log_id": "LOG-OBS-78902", "content": "WARN disk_smart_alert disk=sda reallocated_sectors=156 grown_defects=23", "timestamp": "2025-03-05T09:00:00Z"}}
    ],
    "fault_propagation_chain": [
      "obs-store-03 磁盘 sda 硬件劣化 (08:30)",
      "OBS 磁盘 IO 时延升至 120ms (08:55)",
      "OBS PUT/GET API 时延升高 (09:10)",
      "SFS 后端 OBS 超时率升至 15% (09:12)",
      "SFS NFS 读写时延超阈值 (09:15)",
      "SFS IO 队列积压 (09:25)",
      "GPU 训练集群数据读取劣化 (09:30)"
    ],
    "impact": "慢盘 → OBS 时延 → SFS 后端积压 → NFS 时延 → 训练吞吐下降",
    "suggestion": "1) 紧急: 迁移 obs-store-03 数据至健康节点; 2) 短期: 更换故障磁盘; 3) 长期: 加强 SMART 预测性监控"
  },
  "steps": [
    {"step_id": "S1", "step_name": "OBS网关检查", "status": "COMPLETED", "findings": "网关正常"},
    {"step_id": "S2", "step_name": "存储节点分析", "status": "COMPLETED", "findings": "obs-store-03 磁盘 P99=120ms，其他 < 5ms"},
    {"step_id": "S3", "step_name": "磁盘健康检查", "status": "COMPLETED", "findings": "sda Reallocated Sector=156，健康评分 42%"},
    {"step_id": "S4", "step_name": "影响链路确认", "status": "COMPLETED", "findings": "时间线吻合: 08:30 SMART → 09:12 OBS超时 → 09:15 SFS时延"}
  ]
}
```

---

### Tool 7: query_metrics

```json
{
  "type": "function",
  "function": {
    "name": "query_metrics",
    "description": "查询指定时间窗内的时序指标数据，支持多实例对比。返回按粒度聚合的数据点序列和窗口内统计摘要。",
    "parameters": {
      "type": "object",
      "properties": {
        "metric_name": {
          "type": "string",
          "description": "指标名称"
        },
        "instance_ids": {
          "type": "array",
          "items": {"type": "string"}
        },
        "time_range_start": {
          "type": "string",
          "description": "时间窗起始，ISO 8601"
        },
        "time_range_end": {
          "type": "string",
          "description": "时间窗结束，ISO 8601"
        },
        "aggregation": {
          "type": "string",
          "enum": ["AVG", "P50", "P99", "MAX", "MIN", "SUM"],
          "default": "AVG"
        },
        "granularity": {
          "type": "string",
          "enum": ["1m", "5m", "15m", "1h"],
          "default": "5m"
        }
      },
      "required": ["metric_name", "instance_ids", "time_range_start", "time_range_end"]
    }
  }
}
```

#### Mock 调用

**Agent 调用参数：**
```json
{
  "metric_name": "obs_disk_latency_p99_ms",
  "instance_ids": ["obs-store-01", "obs-store-02", "obs-store-03"],
  "time_range_start": "2025-03-05T08:00:00Z",
  "time_range_end": "2025-03-05T11:00:00Z",
  "aggregation": "P99",
  "granularity": "5m"
}
```

**Mock 返回：**
```json
{
  "time_range": {"start": "2025-03-05T08:00:00Z", "end": "2025-03-05T11:00:00Z"},
  "results": [
    {
      "metric_name": "obs_disk_latency_p99_ms",
      "instance_id": "obs-store-01",
      "data_points": [
        {"timestamp": "2025-03-05T08:00:00Z", "value": 4.2},
        {"timestamp": "2025-03-05T08:30:00Z", "value": 4.5},
        {"timestamp": "2025-03-05T09:00:00Z", "value": 4.8},
        {"timestamp": "2025-03-05T09:30:00Z", "value": 5.1},
        {"timestamp": "2025-03-05T10:00:00Z", "value": 4.9},
        {"timestamp": "2025-03-05T10:30:00Z", "value": 5.0}
      ],
      "statistics": {"avg": 4.75, "max": 5.1, "min": 4.2, "p50": 4.85, "p99": 5.1}
    },
    {
      "metric_name": "obs_disk_latency_p99_ms",
      "instance_id": "obs-store-02",
      "data_points": [
        {"timestamp": "2025-03-05T08:00:00Z", "value": 3.8},
        {"timestamp": "2025-03-05T08:30:00Z", "value": 4.1},
        {"timestamp": "2025-03-05T09:00:00Z", "value": 4.3},
        {"timestamp": "2025-03-05T09:30:00Z", "value": 4.0},
        {"timestamp": "2025-03-05T10:00:00Z", "value": 4.2},
        {"timestamp": "2025-03-05T10:30:00Z", "value": 4.1}
      ],
      "statistics": {"avg": 4.08, "max": 4.3, "min": 3.8, "p50": 4.1, "p99": 4.3}
    },
    {
      "metric_name": "obs_disk_latency_p99_ms",
      "instance_id": "obs-store-03",
      "data_points": [
        {"timestamp": "2025-03-05T08:00:00Z", "value": 4.5},
        {"timestamp": "2025-03-05T08:30:00Z", "value": 4.8},
        {"timestamp": "2025-03-05T09:00:00Z", "value": 45.2},
        {"timestamp": "2025-03-05T09:15:00Z", "value": 120.5},
        {"timestamp": "2025-03-05T09:30:00Z", "value": 250.8},
        {"timestamp": "2025-03-05T09:45:00Z", "value": 310.2},
        {"timestamp": "2025-03-05T10:00:00Z", "value": 355.6},
        {"timestamp": "2025-03-05T10:15:00Z", "value": 370.1},
        {"timestamp": "2025-03-05T10:30:00Z", "value": 380.4},
        {"timestamp": "2025-03-05T10:45:00Z", "value": 385.0}
      ],
      "statistics": {"avg": 222.61, "max": 385.0, "min": 4.5, "p50": 280.5, "p99": 385.0}
    }
  ]
}
```

---

### Tool 8: detect_metric_anomalies

```json
{
  "type": "function",
  "function": {
    "name": "detect_metric_anomalies",
    "description": "对指定服务在时间窗内的全部实例执行指标异常检测。自动拉取该服务类型的所有关键指标，与历史基线对比，返回检测到的异常列表及可能的故障判定。Agent 可在拿到拓扑后立即并行调用此 Tool，快速获取指标层面的异常概览，辅助后续诊断决策。",
    "parameters": {
      "type": "object",
      "properties": {
        "service_id": {
          "type": "string",
          "description": "服务唯一标识"
        },
        "instance_ids": {
          "type": "array",
          "items": {"type": "string"},
          "description": "待检测的实例ID列表，不传则检测该服务全部实例"
        },
        "time_range_start": {
          "type": "string",
          "description": "时间窗起始，ISO 8601"
        },
        "time_range_end": {
          "type": "string",
          "description": "时间窗结束，ISO 8601"
        },
        "sensitivity": {
          "type": "string",
          "enum": ["LOW", "MEDIUM", "HIGH"],
          "description": "异常检测灵敏度，HIGH 会返回更多弱异常",
          "default": "MEDIUM"
        }
      },
      "required": ["service_id", "time_range_start", "time_range_end"]
    }
  }
}
```

#### Mock 调用 A — SFS 指标异常检测

**Agent 调用参数：**
```json
{
  "service_id": "sfs-turbo-001",
  "time_range_start": "2025-03-05T09:00:00Z",
  "time_range_end": "2025-03-05T11:00:00Z",
  "sensitivity": "MEDIUM"
}
```

**Mock 返回：**
```json
{
  "service_id": "sfs-turbo-001",
  "time_range": {"start": "2025-03-05T09:00:00Z", "end": "2025-03-05T11:00:00Z"},
  "total_metrics_checked": 42,
  "anomaly_count": 8,
  "anomalies": [
    {
      "metric_name": "sfs_nfs_read_latency_ms",
      "instance_id": "sfs-node-01",
      "anomaly_type": "SPIKE",
      "severity": "CRITICAL",
      "current_value": 320.5,
      "baseline_value": 10.0,
      "threshold": 50.0,
      "deviation_factor": 32.05,
      "anomaly_start_time": "2025-03-05T09:15:00Z",
      "description": "NFS 读时延飙升至基线 32 倍"
    },
    {
      "metric_name": "sfs_backend_obs_timeout_rate",
      "instance_id": "sfs-node-01",
      "anomaly_type": "SPIKE",
      "severity": "CRITICAL",
      "current_value": 0.15,
      "baseline_value": 0.001,
      "threshold": 0.01,
      "deviation_factor": 150.0,
      "anomaly_start_time": "2025-03-05T09:12:00Z",
      "description": "OBS 后端超时率飙升至基线 150 倍"
    },
    {
      "metric_name": "sfs_throughput_mbps",
      "instance_id": "sfs-node-01",
      "anomaly_type": "DROP",
      "severity": "MAJOR",
      "current_value": 800,
      "baseline_value": 5000,
      "threshold": 1000,
      "deviation_factor": 0.16,
      "anomaly_start_time": "2025-03-05T09:20:00Z",
      "description": "吞吐量下降 84%"
    },
    {
      "metric_name": "sfs_io_queue_depth",
      "instance_id": "sfs-node-01",
      "anomaly_type": "SPIKE",
      "severity": "MAJOR",
      "current_value": 512,
      "baseline_value": 16,
      "threshold": 128,
      "deviation_factor": 32.0,
      "anomaly_start_time": "2025-03-05T09:25:00Z",
      "description": "IO 队列深度飙升"
    }
  ],
  "possible_faults": [
    {
      "fault_type": "BACKEND_DEPENDENCY_DEGRADATION",
      "confidence": 0.85,
      "description": "后端 OBS 依赖异常导致 SFS IO 链路整体劣化",
      "related_anomalies": ["sfs_backend_obs_timeout_rate", "sfs_nfs_read_latency_ms", "sfs_throughput_mbps", "sfs_io_queue_depth"],
      "affected_instances": ["sfs-node-01", "sfs-node-02"],
      "suggestion": "优先排查下游 OBS 服务状态"
    }
  ]
}
```

#### Mock 调用 B — OBS 指标异常检测

**Agent 调用参数：**
```json
{
  "service_id": "obs-bucket-train-data",
  "time_range_start": "2025-03-05T08:00:00Z",
  "time_range_end": "2025-03-05T11:00:00Z",
  "sensitivity": "MEDIUM"
}
```

**Mock 返回：**
```json
{
  "service_id": "obs-bucket-train-data",
  "time_range": {"start": "2025-03-05T08:00:00Z", "end": "2025-03-05T11:00:00Z"},
  "total_metrics_checked": 30,
  "anomaly_count": 6,
  "anomalies": [
    {
      "metric_name": "obs_disk_latency_p99_ms",
      "instance_id": "obs-store-03",
      "anomaly_type": "SPIKE",
      "severity": "CRITICAL",
      "current_value": 385.0,
      "baseline_value": 5.0,
      "threshold": 10.0,
      "deviation_factor": 77.0,
      "anomaly_start_time": "2025-03-05T08:55:00Z",
      "description": "磁盘 P99 时延飙升至基线 77 倍，疑似慢盘"
    },
    {
      "metric_name": "obs_disk_smart_health_score",
      "instance_id": "obs-store-03",
      "anomaly_type": "DROP",
      "severity": "CRITICAL",
      "current_value": 42.0,
      "baseline_value": 98.0,
      "threshold": 60.0,
      "deviation_factor": 0.43,
      "anomaly_start_time": "2025-03-05T08:30:00Z",
      "description": "SMART 健康评分骤降至 42%"
    },
    {
      "metric_name": "obs_iowait_percent",
      "instance_id": "obs-store-03",
      "anomaly_type": "SPIKE",
      "severity": "MAJOR",
      "current_value": 65.0,
      "baseline_value": 5.0,
      "threshold": 30.0,
      "deviation_factor": 13.0,
      "anomaly_start_time": "2025-03-05T09:05:00Z",
      "description": "IO Wait 飙升至 65%"
    },
    {
      "metric_name": "obs_put_latency_p99_ms",
      "instance_id": "obs-gw-01",
      "anomaly_type": "SPIKE",
      "severity": "CRITICAL",
      "current_value": 620.0,
      "baseline_value": 10.0,
      "threshold": 50.0,
      "deviation_factor": 62.0,
      "anomaly_start_time": "2025-03-05T09:10:00Z",
      "description": "PUT P99 时延飙升"
    }
  ],
  "possible_faults": [
    {
      "fault_type": "DISK_HARDWARE_DEGRADATION",
      "confidence": 0.92,
      "description": "obs-store-03 磁盘硬件劣化（慢盘），SMART 健康评分骤降 + 磁盘时延飙升 + IO Wait 升高，影响 OBS 整体读写性能",
      "related_anomalies": ["obs_disk_latency_p99_ms", "obs_disk_smart_health_score", "obs_iowait_percent", "obs_put_latency_p99_ms"],
      "affected_instances": ["obs-store-03"],
      "suggestion": "紧急迁移 obs-store-03 数据至健康节点，更换故障磁盘"
    }
  ]
}
```

---

### Tool 9: list_metric_definitions

```json
{
  "type": "function",
  "function": {
    "name": "list_metric_definitions",
    "description": "获取指定服务类型在指定时间窗内生效的指标定义和阈值配置。阈值可能随版本变更，时间窗用于确定返回哪个版本。",
    "parameters": {
      "type": "object",
      "properties": {
        "service_type": {
          "type": "string",
          "enum": ["SFS_TURBO", "OBS", "ECS", "EVS", "VPC"]
        },
        "time_range_start": {
          "type": "string",
          "description": "时间窗起始，ISO 8601"
        },
        "time_range_end": {
          "type": "string",
          "description": "时间窗结束，ISO 8601"
        },
        "category": {
          "type": "string",
          "enum": ["PERFORMANCE", "AVAILABILITY", "RESOURCE", "NETWORK"]
        }
      },
      "required": ["service_type", "time_range_start", "time_range_end"]
    }
  }
}
```

#### Mock 调用

**Agent 调用参数：**
```json
{"service_type": "SFS_TURBO", "time_range_start": "2025-03-05T09:00:00Z", "time_range_end": "2025-03-05T11:00:00Z"}
```

**Mock 返回：**
```json
{
  "service_type": "SFS_TURBO",
  "config_version": "v2.3",
  "effective_time": "2025-02-01T00:00:00Z",
  "time_range": {"start": "2025-03-05T09:00:00Z", "end": "2025-03-05T11:00:00Z"},
  "metrics": [
    {"metric_name": "sfs_nfs_read_latency_ms",     "display_name": "NFS 读时延",     "unit": "ms",    "category": "PERFORMANCE", "baseline": 10,   "threshold_warning": 30,   "threshold_critical": 50},
    {"metric_name": "sfs_nfs_write_latency_ms",    "display_name": "NFS 写时延",     "unit": "ms",    "category": "PERFORMANCE", "baseline": 20,   "threshold_warning": 60,   "threshold_critical": 100},
    {"metric_name": "sfs_throughput_mbps",          "display_name": "吞吐量",         "unit": "MBps",  "category": "PERFORMANCE", "baseline": 5000, "threshold_warning": 2000, "threshold_critical": 1000},
    {"metric_name": "sfs_backend_obs_timeout_rate", "display_name": "OBS后端超时率",  "unit": "ratio", "category": "AVAILABILITY","baseline": 0.001,"threshold_warning": 0.005,"threshold_critical": 0.01},
    {"metric_name": "sfs_obs_call_latency_p99_ms", "display_name": "OBS调用P99时延", "unit": "ms",    "category": "PERFORMANCE", "baseline": 50,   "threshold_warning": 30,   "threshold_critical": 100},
    {"metric_name": "sfs_io_queue_depth",           "display_name": "IO队列深度",     "unit": "count", "category": "PERFORMANCE", "baseline": 16,   "threshold_warning": 64,   "threshold_critical": 128},
    {"metric_name": "sfs_active_connections",       "display_name": "活跃连接数",     "unit": "count", "category": "RESOURCE",    "baseline": 3000, "threshold_warning": 8000, "threshold_critical": 10000},
    {"metric_name": "sfs_cpu_usage_percent",        "display_name": "CPU使用率",      "unit": "%",     "category": "RESOURCE",    "baseline": 40,   "threshold_warning": 80,   "threshold_critical": 95},
    {"metric_name": "sfs_local_disk_latency_ms",    "display_name": "本地磁盘时延",   "unit": "ms",    "category": "PERFORMANCE", "baseline": 1,    "threshold_warning": 5,    "threshold_critical": 20},
    {"metric_name": "sfs_internal_rpc_latency_ms",  "display_name": "内部RPC时延",    "unit": "ms",    "category": "NETWORK",     "baseline": 2,    "threshold_warning": 5,    "threshold_critical": 10}
  ]
}
```

---

### Tool 10: query_logs

```json
{
  "type": "function",
  "function": {
    "name": "query_logs",
    "description": "查询指定时间窗内的服务日志，支持关键词搜索和级别过滤。返回日志条目列表和窗口内的级别/实例分布统计。",
    "parameters": {
      "type": "object",
      "properties": {
        "service_id": {
          "type": "string"
        },
        "time_range_start": {
          "type": "string",
          "description": "时间窗起始，ISO 8601"
        },
        "time_range_end": {
          "type": "string",
          "description": "时间窗结束，ISO 8601"
        },
        "instance_ids": {
          "type": "array",
          "items": {"type": "string"}
        },
        "levels": {
          "type": "array",
          "items": {"type": "string", "enum": ["DEBUG", "INFO", "WARN", "ERROR", "FATAL"]}
        },
        "keyword": {
          "type": "string"
        },
        "page_size": {
          "type": "integer",
          "default": 20
        },
        "order_by": {
          "type": "string",
          "enum": ["ASC", "DESC"],
          "default": "DESC"
        }
      },
      "required": ["service_id", "time_range_start", "time_range_end"]
    }
  }
}
```

#### Mock 调用 — OBS 慢盘日志

**Agent 调用参数：**
```json
{
  "service_id": "obs-bucket-train-data",
  "time_range_start": "2025-03-05T08:00:00Z",
  "time_range_end": "2025-03-05T11:00:00Z",
  "instance_ids": ["obs-store-03"],
  "levels": ["ERROR", "WARN"],
  "keyword": "slow_disk_io",
  "page_size": 5
}
```

**Mock 返回：**
```json
{
  "total": 89,
  "time_range": {"start": "2025-03-05T08:00:00Z", "end": "2025-03-05T11:00:00Z"},
  "logs": [
    {"log_id": "LOG-OBS-78901", "timestamp": "2025-03-05T10:30:00Z", "level": "WARN", "service_id": "obs-bucket-train-data", "instance_id": "obs-store-03", "source": "disk_monitor.go:156", "message": "WARN slow_disk_io disk=sda latency=135ms threshold=10ms count=1247 in_last_5min", "structured_data": {"disk": "sda", "latency_ms": 135, "count": 1247}, "trace_id": null},
    {"log_id": "LOG-OBS-78902", "timestamp": "2025-03-05T09:00:00Z", "level": "WARN", "service_id": "obs-bucket-train-data", "instance_id": "obs-store-03", "source": "smart_monitor.go:89", "message": "WARN disk_smart_alert disk=sda reallocated_sectors=156 grown_defects=23", "structured_data": {"disk": "sda", "reallocated_sectors": 156, "grown_defects": 23}, "trace_id": null},
    {"log_id": "LOG-OBS-78903", "timestamp": "2025-03-05T08:55:00Z", "level": "WARN", "service_id": "obs-bucket-train-data", "instance_id": "obs-store-03", "source": "disk_monitor.go:156", "message": "WARN slow_disk_io disk=sda latency=98ms threshold=10ms count=523 in_last_5min", "structured_data": {"disk": "sda", "latency_ms": 98, "count": 523}, "trace_id": null}
  ],
  "facets": {"levels": {"WARN": 89}, "instances": {"obs-store-03": 89}}
}
```

---

### Tool 11: get_log_context

```json
{
  "type": "function",
  "function": {
    "name": "get_log_context",
    "description": "获取某条日志在指定时间窗内的前后上下文。时间窗限制上下文搜索范围，避免跨越故障时段。",
    "parameters": {
      "type": "object",
      "properties": {
        "log_id": {
          "type": "string"
        },
        "time_range_start": {
          "type": "string",
          "description": "时间窗起始，ISO 8601"
        },
        "time_range_end": {
          "type": "string",
          "description": "时间窗结束，ISO 8601"
        },
        "before_count": {
          "type": "integer",
          "default": 10
        },
        "after_count": {
          "type": "integer",
          "default": 10
        }
      },
      "required": ["log_id", "time_range_start", "time_range_end"]
    }
  }
}
```

#### Mock 调用

**Agent 调用参数：**
```json
{"log_id": "LOG-SFS-10001", "time_range_start": "2025-03-05T09:00:00Z", "time_range_end": "2025-03-05T11:00:00Z", "before_count": 3, "after_count": 2}
```

**Mock 返回：**
```json
{
  "time_range": {"start": "2025-03-05T09:00:00Z", "end": "2025-03-05T11:00:00Z"},
  "target_log": {
    "log_id": "LOG-SFS-10001",
    "timestamp": "2025-03-05T10:44:58Z",
    "level": "ERROR",
    "instance_id": "sfs-node-01",
    "message": "OBS PUT request timeout after 30s, bucket=train-data-bucket, key=checkpoint/model_step_50000.bin, retry=3/3"
  },
  "before_logs": [
    {"log_id": "LOG-SFS-09998", "timestamp": "2025-03-05T10:44:55Z", "level": "WARN",  "instance_id": "sfs-node-01", "message": "OBS PUT request retry, attempt=2/3, elapsed=20150ms"},
    {"log_id": "LOG-SFS-09995", "timestamp": "2025-03-05T10:44:42Z", "level": "WARN",  "instance_id": "sfs-node-01", "message": "OBS PUT request retry, attempt=1/3, elapsed=10080ms"},
    {"log_id": "LOG-SFS-09990", "timestamp": "2025-03-05T10:44:28Z", "level": "INFO",  "instance_id": "sfs-node-01", "message": "OBS PUT request started, bucket=train-data-bucket, key=checkpoint/model_step_50000.bin, size=2147483648"}
  ],
  "after_logs": [
    {"log_id": "LOG-SFS-10010", "timestamp": "2025-03-05T10:45:00Z", "level": "ERROR", "instance_id": "sfs-node-01", "message": "Checkpoint write failed, will retry in 60s, file=model_step_50000.bin"},
    {"log_id": "LOG-SFS-10011", "timestamp": "2025-03-05T10:45:02Z", "level": "WARN",  "instance_id": "sfs-node-01", "message": "Client NFS WRITE callback delayed, client=192.168.2.50, delay=325ms"}
  ]
}
```

---

## 5. Agent 编排伪代码

```python
import asyncio

def agent_diagnose(trigger_alarm):
    """Agent 主循环：所有 Tool 调用均传入统一时间窗"""

    # 根据告警时间确定诊断时间窗
    window_start = trigger_alarm["first_occur_time"] - timedelta(minutes=30)
    window_end   = now()
    service_id   = trigger_alarm["service_id"]
    visited      = set()

    for hop in range(5):  # 最多追溯 5 跳
        if service_id in visited:
            break
        visited.add(service_id)

        # 1. 查拓扑 → 一次拿到服务元信息 + 实例列表 + 依赖健康度
        topology = get_service_topology(
            service_id=service_id,
            time_range_start=window_start,
            time_range_end=window_end,
            direction="BOTH"
        )

        # 2. 拿到拓扑后，并行拉取告警、指标异常、日志
        instance_ids = [inst["instance_id"] for inst in topology["instances"]]
        alarms, anomalies, logs = asyncio.gather(
            query_alarms(
                service_id=service_id,
                time_range_start=window_start,
                time_range_end=window_end,
                status=["FIRING"]
            ),
            detect_metric_anomalies(
                service_id=service_id,
                time_range_start=window_start,
                time_range_end=window_end
            ),
            query_logs(
                service_id=service_id,
                time_range_start=window_start,
                time_range_end=window_end,
                levels=["ERROR", "WARN"]
            )
        )

        if alarms["total"] == 0:
            break

        # 3. 告警聚类
        clusters = cluster_alarms(
            alarm_ids=[a["alarm_id"] for a in alarms["alarms"]],
            time_range_start=window_start,
            time_range_end=window_end
        )

        # 4. 对每个聚类下发诊断
        root_cause_found = False
        for cluster in clusters["clusters"]:
            task = create_diagnosis_task(
                service_id=service_id,
                cluster_id=cluster["cluster_id"],
                diagnosis_type=cluster["suggested_diagnosis_type"],
                alarm_ids=cluster["alarm_ids"],
                time_range_start=window_start,
                time_range_end=window_end
            )
            result = poll(get_diagnosis_result,
                task_id=task["task_id"],
                time_range_start=window_start,
                time_range_end=window_end
            )

            if result["result"]["root_cause_found"]:
                root_cause_found = True
                evidence_metrics = query_metrics(...)   # 采集证据
                evidence_logs = query_logs(...)
                return build_report(result, evidence_metrics, evidence_logs, anomalies)

        # 5. 全部无根因 → 从 topology 返回的依赖中选择嫌疑最大的
        #    同时参考 anomalies.possible_faults 辅助判断
        if not root_cause_found:
            deps = topology["downstream_dependencies"]
            suspect = pick_most_suspicious(deps)  # status=DEGRADED + STRONG 优先
            if suspect:
                service_id = suspect["service_id"]
                # OBS 异常可能比 SFS 告警更早，向前扩展时间窗
                window_start = window_start - timedelta(minutes=30)
            else:
                break

    return {"root_cause": None, "message": "未能自动定位根因"}
```

---

## 6. 关键指标速查

### SFS Turbo

| 指标 | 基线 | 告警阈值 |
|------|------|----------|
| sfs_nfs_read_latency_ms | < 10ms | > 50ms |
| sfs_nfs_write_latency_ms | < 20ms | > 100ms |
| sfs_throughput_mbps | > 5000 | < 1000 |
| sfs_backend_obs_timeout_rate | < 0.1% | > 1% |
| sfs_obs_call_latency_p99_ms | < 50ms | > 100ms |
| sfs_io_queue_depth | < 32 | > 128 |
| sfs_local_disk_latency_ms | < 1ms | > 20ms |
| sfs_internal_rpc_latency_ms | < 2ms | > 10ms |

### OBS

| 指标 | 基线 | 告警阈值 |
|------|------|----------|
| obs_get_latency_p99_ms | < 5ms | > 30ms |
| obs_put_latency_p99_ms | < 10ms | > 50ms |
| obs_disk_latency_p99_ms | < 5ms | > 10ms |
| obs_disk_smart_health_score | > 95% | < 60% |
| obs_5xx_error_rate | < 0.01% | > 1% |
| obs_iowait_percent | < 10% | > 30% |
