# SFS Turbo 智能故障诊断 Agent — API 与数据模型设计

## 1. 场景概述

**核心故障场景**：训练任务劣化时，SFS 服务主动定位出 OBS 服务时延导致性能劣化。

**Agent 诊断流程**：

```
收到 SFS 告警(含 ECS instanceID)
  → 查询 SFS 服务拓扑，获取服务边界
  → 拉取 SFS 服务内全部告警
  → 告警聚类归因为 N 大类
  → 对每类下发诊断任务
  → 若全部未返回根因 → 说明非 SFS 自身问题
  → 通过拓扑发现 SFS 依赖 OBS
  → 拉取 OBS 服务全部告警
  → 重复聚类 + 诊断
  → 定位根因: OBS 时延劣化
```

---

## 2. API 总览

| 序号 | API | 用途 | Agent 调用时机 |
|------|-----|------|---------------|
| T1 | GET /topology/services/{serviceId} | 获取服务拓扑及依赖关系 | 发现告警后查询服务边界 |
| T2 | GET /topology/services/{serviceId}/instances | 获取服务下全部实例 | 确定告警范围 |
| T3 | GET /topology/services/{serviceId}/dependencies | 获取上下游依赖 | 本服务无根因时向下游追溯 |
| A1 | POST /alarms/query | 按服务/实例查询告警 | 拉取某服务全量告警 |
| A2 | GET /alarms/{alarmId} | 告警详情 | 查看单条告警详细信息 |
| A3 | POST /alarms/cluster | 告警聚类 | 将 10+ 条告警归为 N 大类 |
| D1 | POST /diagnosis/tasks | 创建诊断任务 | 对每个告警聚类下发诊断 |
| D2 | GET /diagnosis/tasks/{taskId} | 查询诊断结果 | 轮询诊断任务状态和结论 |
| M1 | POST /metrics/query | 查询指标数据 | 验证诊断假设(如 OBS 时延) |
| M2 | GET /metrics/definitions | 获取可用指标列表 | 确认可观测指标 |
| L1 | POST /logs/query | 查询日志 | 辅助诊断定位 |
| L2 | GET /logs/context/{logId} | 获取日志上下文 | 查看某条日志前后内容 |

---

## 3. 拓扑 API（Topology）

### 3.1 数据模型

```json
// ServiceTopology — 服务拓扑
{
  "serviceId": "string",           // 服务唯一标识
  "serviceName": "string",         // 服务名称
  "serviceType": "string",         // 服务类型: SFS_TURBO | OBS | ECS | EVS | VPC
  "region": "string",              // 区域
  "az": "string",                  // 可用区
  "status": "string",              // NORMAL | DEGRADED | FAULT
  "instances": ["string"],         // 实例ID列表
  "dependencies": [                // 依赖的下游服务
    {
      "serviceId": "string",
      "serviceName": "string",
      "serviceType": "string",
      "dependencyType": "string",  // STRONG | WEAK
      "protocol": "string",       // NFS | HTTP | RDMA | TCP
      "description": "string"
    }
  ],
  "dependents": [                  // 依赖本服务的上游服务
    {
      "serviceId": "string",
      "serviceName": "string",
      "serviceType": "string"
    }
  ],
  "metadata": {
    "createTime": "string",        // ISO 8601
    "updateTime": "string",
    "version": "string"
  }
}

// ServiceInstance — 服务实例
{
  "instanceId": "string",          // 实例唯一标识
  "instanceName": "string",
  "serviceId": "string",           // 所属服务
  "instanceType": "string",        // SFS_NODE | OBS_GATEWAY | ECS_VM
  "status": "string",              // RUNNING | DEGRADED | FAULT | STOPPED
  "hostInfo": {
    "ecsInstanceId": "string",     // ECS 实例ID
    "privateIp": "string",
    "az": "string",
    "hostName": "string"
  },
  "role": "string",                // MASTER | SLAVE | PROXY | GATEWAY
  "connections": [                 // 实例间连接关系
    {
      "targetInstanceId": "string",
      "targetServiceId": "string",
      "connectionType": "string",  // NFS_MOUNT | OBS_API | INTERNAL_RPC
      "port": 0,
      "status": "string"
    }
  ],
  "resources": {
    "cpuCores": 0,
    "memoryGB": 0,
    "diskGB": 0,
    "networkBandwidthMbps": 0
  }
}
```

### 3.2 T1 — 获取服务拓扑

```
GET /v1/topology/services/{serviceId}
```

**请求参数**

| 参数 | 位置 | 必填 | 说明 |
|------|------|------|------|
| serviceId | path | 是 | 服务ID |
| depth | query | 否 | 拓扑展开深度，默认1，最大5 |
| includeInstances | query | 否 | 是否包含实例详情，默认false |

**Mock 响应**

```json
{
  "code": 200,
  "data": {
    "serviceId": "sfs-turbo-001",
    "serviceName": "SFS Turbo 文件存储",
    "serviceType": "SFS_TURBO",
    "region": "cn-north-4",
    "az": "cn-north-4a",
    "status": "DEGRADED",
    "instances": [
      "sfs-node-01", "sfs-node-02", "sfs-node-03",
      "sfs-proxy-01", "sfs-proxy-02",
      "sfs-meta-01", "sfs-meta-02"
    ],
    "dependencies": [
      {
        "serviceId": "obs-bucket-train-data",
        "serviceName": "OBS 训练数据桶",
        "serviceType": "OBS",
        "dependencyType": "STRONG",
        "protocol": "HTTP",
        "description": "SFS Turbo 后端数据持久化到 OBS"
      },
      {
        "serviceId": "evs-sfs-meta",
        "serviceName": "EVS 元数据盘",
        "serviceType": "EVS",
        "dependencyType": "STRONG",
        "protocol": "TCP",
        "description": "元数据节点挂载 EVS 高性能盘"
      },
      {
        "serviceId": "vpc-subnet-001",
        "serviceName": "VPC 子网",
        "serviceType": "VPC",
        "dependencyType": "STRONG",
        "protocol": "TCP",
        "description": "网络互联"
      }
    ],
    "dependents": [
      {
        "serviceId": "ecs-gpu-training-cluster",
        "serviceName": "GPU 训练集群",
        "serviceType": "ECS"
      }
    ],
    "metadata": {
      "createTime": "2025-01-15T08:00:00Z",
      "updateTime": "2025-03-05T10:30:00Z",
      "version": "v3.2"
    }
  }
}
```

### 3.3 T2 — 获取服务下全部实例

```
GET /v1/topology/services/{serviceId}/instances
```

**请求参数**

| 参数 | 位置 | 必填 | 说明 |
|------|------|------|------|
| serviceId | path | 是 | 服务ID |
| status | query | 否 | 按状态过滤: RUNNING, DEGRADED, FAULT |
| role | query | 否 | 按角色过滤: MASTER, SLAVE, PROXY |
| pageSize | query | 否 | 分页大小，默认50 |
| pageToken | query | 否 | 分页token |

**Mock 响应**

```json
{
  "code": 200,
  "data": {
    "total": 7,
    "instances": [
      {
        "instanceId": "sfs-node-01",
        "instanceName": "SFS存储节点-01",
        "serviceId": "sfs-turbo-001",
        "instanceType": "SFS_NODE",
        "status": "RUNNING",
        "hostInfo": {
          "ecsInstanceId": "i-abcdef001",
          "privateIp": "192.168.1.101",
          "az": "cn-north-4a",
          "hostName": "sfs-store-01"
        },
        "role": "MASTER",
        "connections": [
          {
            "targetInstanceId": "obs-gw-01",
            "targetServiceId": "obs-bucket-train-data",
            "connectionType": "OBS_API",
            "port": 443,
            "status": "DEGRADED"
          }
        ],
        "resources": {
          "cpuCores": 64,
          "memoryGB": 256,
          "diskGB": 20000,
          "networkBandwidthMbps": 25000
        }
      },
      {
        "instanceId": "sfs-node-02",
        "instanceName": "SFS存储节点-02",
        "serviceId": "sfs-turbo-001",
        "instanceType": "SFS_NODE",
        "status": "DEGRADED",
        "hostInfo": {
          "ecsInstanceId": "i-abcdef002",
          "privateIp": "192.168.1.102",
          "az": "cn-north-4a",
          "hostName": "sfs-store-02"
        },
        "role": "SLAVE",
        "connections": [
          {
            "targetInstanceId": "obs-gw-01",
            "targetServiceId": "obs-bucket-train-data",
            "connectionType": "OBS_API",
            "port": 443,
            "status": "DEGRADED"
          }
        ],
        "resources": {
          "cpuCores": 64,
          "memoryGB": 256,
          "diskGB": 20000,
          "networkBandwidthMbps": 25000
        }
      },
      {
        "instanceId": "sfs-node-03",
        "instanceName": "SFS存储节点-03",
        "serviceId": "sfs-turbo-001",
        "instanceType": "SFS_NODE",
        "status": "RUNNING",
        "hostInfo": {
          "ecsInstanceId": "i-abcdef003",
          "privateIp": "192.168.1.103",
          "az": "cn-north-4b",
          "hostName": "sfs-store-03"
        },
        "role": "SLAVE",
        "connections": [
          {
            "targetInstanceId": "obs-gw-02",
            "targetServiceId": "obs-bucket-train-data",
            "connectionType": "OBS_API",
            "port": 443,
            "status": "NORMAL"
          }
        ],
        "resources": {
          "cpuCores": 64,
          "memoryGB": 256,
          "diskGB": 20000,
          "networkBandwidthMbps": 25000
        }
      },
      {
        "instanceId": "sfs-proxy-01",
        "instanceName": "SFS协议代理-01",
        "serviceId": "sfs-turbo-001",
        "instanceType": "SFS_NODE",
        "status": "RUNNING",
        "hostInfo": {
          "ecsInstanceId": "i-abcdef004",
          "privateIp": "192.168.1.111",
          "az": "cn-north-4a",
          "hostName": "sfs-proxy-01"
        },
        "role": "PROXY",
        "connections": [],
        "resources": {
          "cpuCores": 32,
          "memoryGB": 64,
          "diskGB": 500,
          "networkBandwidthMbps": 25000
        }
      },
      {
        "instanceId": "sfs-proxy-02",
        "instanceName": "SFS协议代理-02",
        "serviceId": "sfs-turbo-001",
        "instanceType": "SFS_NODE",
        "status": "RUNNING",
        "hostInfo": {
          "ecsInstanceId": "i-abcdef005",
          "privateIp": "192.168.1.112",
          "az": "cn-north-4b",
          "hostName": "sfs-proxy-02"
        },
        "role": "PROXY",
        "connections": [],
        "resources": {
          "cpuCores": 32,
          "memoryGB": 64,
          "diskGB": 500,
          "networkBandwidthMbps": 25000
        }
      },
      {
        "instanceId": "sfs-meta-01",
        "instanceName": "SFS元数据节点-01",
        "serviceId": "sfs-turbo-001",
        "instanceType": "SFS_NODE",
        "status": "RUNNING",
        "hostInfo": {
          "ecsInstanceId": "i-abcdef006",
          "privateIp": "192.168.1.121",
          "az": "cn-north-4a",
          "hostName": "sfs-meta-01"
        },
        "role": "MASTER",
        "connections": [],
        "resources": {
          "cpuCores": 16,
          "memoryGB": 64,
          "diskGB": 2000,
          "networkBandwidthMbps": 10000
        }
      },
      {
        "instanceId": "sfs-meta-02",
        "instanceName": "SFS元数据节点-02",
        "serviceId": "sfs-turbo-001",
        "instanceType": "SFS_NODE",
        "status": "RUNNING",
        "hostInfo": {
          "ecsInstanceId": "i-abcdef007",
          "privateIp": "192.168.1.122",
          "az": "cn-north-4b",
          "hostName": "sfs-meta-02"
        },
        "role": "SLAVE",
        "connections": [],
        "resources": {
          "cpuCores": 16,
          "memoryGB": 64,
          "diskGB": 2000,
          "networkBandwidthMbps": 10000
        }
      }
    ]
  }
}
```

### 3.4 T3 — 获取上下游依赖

```
GET /v1/topology/services/{serviceId}/dependencies
```

**请求参数**

| 参数 | 位置 | 必填 | 说明 |
|------|------|------|------|
| serviceId | path | 是 | 服务ID |
| direction | query | 否 | UPSTREAM / DOWNSTREAM / BOTH，默认BOTH |
| depth | query | 否 | 递归深度，默认1 |

**Mock 响应（查询 SFS 的下游依赖）**

```json
{
  "code": 200,
  "data": {
    "serviceId": "sfs-turbo-001",
    "direction": "DOWNSTREAM",
    "dependencies": [
      {
        "serviceId": "obs-bucket-train-data",
        "serviceName": "OBS 训练数据桶",
        "serviceType": "OBS",
        "region": "cn-north-4",
        "status": "DEGRADED",
        "dependencyType": "STRONG",
        "protocol": "HTTP",
        "latencyP99Ms": 850,
        "latencyBaselineMs": 50,
        "errorRate": 0.12,
        "description": "SFS 数据持久化层，当前P99时延异常升高"
      },
      {
        "serviceId": "evs-sfs-meta",
        "serviceName": "EVS 元数据盘",
        "serviceType": "EVS",
        "region": "cn-north-4",
        "status": "NORMAL",
        "dependencyType": "STRONG",
        "protocol": "TCP",
        "latencyP99Ms": 2,
        "latencyBaselineMs": 1,
        "errorRate": 0.0,
        "description": "元数据存储，状态正常"
      },
      {
        "serviceId": "vpc-subnet-001",
        "serviceName": "VPC 子网",
        "serviceType": "VPC",
        "region": "cn-north-4",
        "status": "NORMAL",
        "dependencyType": "STRONG",
        "protocol": "TCP",
        "latencyP99Ms": 0.5,
        "latencyBaselineMs": 0.3,
        "errorRate": 0.0,
        "description": "网络层，状态正常"
      }
    ]
  }
}
```

---

## 4. 告警 API（Alarm）

### 4.1 数据模型

```json
// Alarm — 告警
{
  "alarmId": "string",
  "alarmName": "string",
  "alarmLevel": "string",          // CRITICAL | MAJOR | MINOR | WARNING
  "alarmSource": "string",         // 告警来源: MONITOR | LOG_ANALYSIS | THRESHOLD | ANOMALY_DETECTION
  "status": "string",              // FIRING | RESOLVED | ACKNOWLEDGED
  "serviceId": "string",
  "instanceId": "string",
  "resourceType": "string",        // ECS | SFS | OBS | EVS
  "resourceId": "string",
  "metric": "string",              // 关联指标名
  "currentValue": 0.0,             // 当前值
  "threshold": 0.0,                // 阈值
  "unit": "string",
  "firstOccurTime": "string",      // ISO 8601
  "lastOccurTime": "string",
  "occurCount": 0,
  "description": "string",
  "tags": {
    "key": "value"
  },
  "relatedAlarms": ["string"],     // 关联告警ID列表
  "rawData": {}                    // 原始告警数据
}

// AlarmCluster — 告警聚类结果
{
  "clusterId": "string",
  "clusterName": "string",         // 聚类名称（自动生成）
  "category": "string",            // IO_LATENCY | NETWORK | CPU | MEMORY | DISK | DEPENDENCY
  "severity": "string",            // 聚类中最高告警级别
  "alarmCount": 0,
  "alarms": ["string"],            // 告警ID列表
  "commonPattern": "string",       // 告警共性描述
  "affectedInstances": ["string"],
  "timeRange": {
    "start": "string",
    "end": "string"
  },
  "suggestedAction": "string"      // 建议的诊断方向
}
```

### 4.2 A1 — 按条件查询告警

```
POST /v1/alarms/query
```

**请求体**

```json
{
  "serviceId": "string",           // 按服务过滤
  "instanceIds": ["string"],       // 按实例过滤（可选）
  "alarmLevels": ["string"],       // 按级别过滤
  "status": ["string"],            // 按状态过滤
  "timeRange": {
    "start": "string",             // ISO 8601
    "end": "string"
  },
  "pageSize": 50,
  "pageToken": "string"
}
```

**Mock 请求（查询 SFS 服务全量告警）**

```json
{
  "serviceId": "sfs-turbo-001",
  "alarmLevels": ["CRITICAL", "MAJOR", "MINOR", "WARNING"],
  "status": ["FIRING"],
  "timeRange": {
    "start": "2025-03-05T09:00:00Z",
    "end": "2025-03-05T11:00:00Z"
  },
  "pageSize": 50
}
```

**Mock 响应（SFS 服务内全部告警，12条）**

```json
{
  "code": 200,
  "data": {
    "total": 12,
    "alarms": [
      {
        "alarmId": "ALM-SFS-001",
        "alarmName": "SFS NFS读时延超阈值",
        "alarmLevel": "CRITICAL",
        "alarmSource": "THRESHOLD",
        "status": "FIRING",
        "serviceId": "sfs-turbo-001",
        "instanceId": "sfs-node-01",
        "resourceType": "SFS",
        "resourceId": "sfs-turbo-001/node-01",
        "metric": "sfs_nfs_read_latency_ms",
        "currentValue": 320.5,
        "threshold": 50.0,
        "unit": "ms",
        "firstOccurTime": "2025-03-05T09:15:00Z",
        "lastOccurTime": "2025-03-05T10:45:00Z",
        "occurCount": 38,
        "description": "NFS 读操作 P99 时延 320.5ms，超过阈值 50ms，持续约 1.5 小时",
        "tags": {
          "az": "cn-north-4a",
          "operation": "read",
          "protocol": "nfs"
        },
        "relatedAlarms": ["ALM-SFS-002", "ALM-SFS-003"],
        "rawData": {}
      },
      {
        "alarmId": "ALM-SFS-002",
        "alarmName": "SFS NFS写时延超阈值",
        "alarmLevel": "CRITICAL",
        "alarmSource": "THRESHOLD",
        "status": "FIRING",
        "serviceId": "sfs-turbo-001",
        "instanceId": "sfs-node-01",
        "resourceType": "SFS",
        "resourceId": "sfs-turbo-001/node-01",
        "metric": "sfs_nfs_write_latency_ms",
        "currentValue": 580.2,
        "threshold": 100.0,
        "unit": "ms",
        "firstOccurTime": "2025-03-05T09:18:00Z",
        "lastOccurTime": "2025-03-05T10:45:00Z",
        "occurCount": 35,
        "description": "NFS 写操作 P99 时延 580.2ms，超过阈值 100ms",
        "tags": {
          "az": "cn-north-4a",
          "operation": "write",
          "protocol": "nfs"
        },
        "relatedAlarms": ["ALM-SFS-001"],
        "rawData": {}
      },
      {
        "alarmId": "ALM-SFS-003",
        "alarmName": "SFS NFS读时延超阈值",
        "alarmLevel": "MAJOR",
        "alarmSource": "THRESHOLD",
        "status": "FIRING",
        "serviceId": "sfs-turbo-001",
        "instanceId": "sfs-node-02",
        "resourceType": "SFS",
        "resourceId": "sfs-turbo-001/node-02",
        "metric": "sfs_nfs_read_latency_ms",
        "currentValue": 280.3,
        "threshold": 50.0,
        "unit": "ms",
        "firstOccurTime": "2025-03-05T09:20:00Z",
        "lastOccurTime": "2025-03-05T10:44:00Z",
        "occurCount": 30,
        "description": "NFS 读操作 P99 时延 280.3ms，超过阈值 50ms",
        "tags": {
          "az": "cn-north-4a",
          "operation": "read",
          "protocol": "nfs"
        },
        "relatedAlarms": ["ALM-SFS-001"],
        "rawData": {}
      },
      {
        "alarmId": "ALM-SFS-004",
        "alarmName": "SFS NFS写时延超阈值",
        "alarmLevel": "MAJOR",
        "alarmSource": "THRESHOLD",
        "status": "FIRING",
        "serviceId": "sfs-turbo-001",
        "instanceId": "sfs-node-02",
        "resourceType": "SFS",
        "resourceId": "sfs-turbo-001/node-02",
        "metric": "sfs_nfs_write_latency_ms",
        "currentValue": 490.7,
        "threshold": 100.0,
        "unit": "ms",
        "firstOccurTime": "2025-03-05T09:22:00Z",
        "lastOccurTime": "2025-03-05T10:44:00Z",
        "occurCount": 28,
        "description": "NFS 写操作 P99 时延 490.7ms，超过阈值 100ms",
        "tags": {
          "az": "cn-north-4a",
          "operation": "write",
          "protocol": "nfs"
        },
        "relatedAlarms": [],
        "rawData": {}
      },
      {
        "alarmId": "ALM-SFS-005",
        "alarmName": "SFS 后端OBS请求超时率升高",
        "alarmLevel": "CRITICAL",
        "alarmSource": "ANOMALY_DETECTION",
        "status": "FIRING",
        "serviceId": "sfs-turbo-001",
        "instanceId": "sfs-node-01",
        "resourceType": "SFS",
        "resourceId": "sfs-turbo-001/node-01",
        "metric": "sfs_backend_obs_timeout_rate",
        "currentValue": 0.15,
        "threshold": 0.01,
        "unit": "ratio",
        "firstOccurTime": "2025-03-05T09:12:00Z",
        "lastOccurTime": "2025-03-05T10:45:00Z",
        "occurCount": 42,
        "description": "后端 OBS 请求超时率 15%，异常检测模型检出异常",
        "tags": {
          "az": "cn-north-4a",
          "backend": "obs"
        },
        "relatedAlarms": ["ALM-SFS-006"],
        "rawData": {}
      },
      {
        "alarmId": "ALM-SFS-006",
        "alarmName": "SFS 后端OBS请求超时率升高",
        "alarmLevel": "MAJOR",
        "alarmSource": "ANOMALY_DETECTION",
        "status": "FIRING",
        "serviceId": "sfs-turbo-001",
        "instanceId": "sfs-node-02",
        "resourceType": "SFS",
        "resourceId": "sfs-turbo-001/node-02",
        "metric": "sfs_backend_obs_timeout_rate",
        "currentValue": 0.12,
        "threshold": 0.01,
        "unit": "ratio",
        "firstOccurTime": "2025-03-05T09:14:00Z",
        "lastOccurTime": "2025-03-05T10:44:00Z",
        "occurCount": 38,
        "description": "后端 OBS 请求超时率 12%",
        "tags": {
          "az": "cn-north-4a",
          "backend": "obs"
        },
        "relatedAlarms": ["ALM-SFS-005"],
        "rawData": {}
      },
      {
        "alarmId": "ALM-SFS-007",
        "alarmName": "SFS IO队列深度过高",
        "alarmLevel": "MAJOR",
        "alarmSource": "THRESHOLD",
        "status": "FIRING",
        "serviceId": "sfs-turbo-001",
        "instanceId": "sfs-node-01",
        "resourceType": "SFS",
        "resourceId": "sfs-turbo-001/node-01",
        "metric": "sfs_io_queue_depth",
        "currentValue": 512,
        "threshold": 128,
        "unit": "count",
        "firstOccurTime": "2025-03-05T09:25:00Z",
        "lastOccurTime": "2025-03-05T10:45:00Z",
        "occurCount": 25,
        "description": "IO 队列深度 512，超过阈值 128，请求积压严重",
        "tags": {
          "az": "cn-north-4a"
        },
        "relatedAlarms": [],
        "rawData": {}
      },
      {
        "alarmId": "ALM-SFS-008",
        "alarmName": "SFS IO队列深度过高",
        "alarmLevel": "MINOR",
        "alarmSource": "THRESHOLD",
        "status": "FIRING",
        "serviceId": "sfs-turbo-001",
        "instanceId": "sfs-node-02",
        "resourceType": "SFS",
        "resourceId": "sfs-turbo-001/node-02",
        "metric": "sfs_io_queue_depth",
        "currentValue": 256,
        "threshold": 128,
        "unit": "count",
        "firstOccurTime": "2025-03-05T09:30:00Z",
        "lastOccurTime": "2025-03-05T10:44:00Z",
        "occurCount": 20,
        "description": "IO 队列深度 256，请求有积压",
        "tags": {
          "az": "cn-north-4a"
        },
        "relatedAlarms": [],
        "rawData": {}
      },
      {
        "alarmId": "ALM-SFS-009",
        "alarmName": "SFS 连接数接近上限",
        "alarmLevel": "WARNING",
        "alarmSource": "THRESHOLD",
        "status": "FIRING",
        "serviceId": "sfs-turbo-001",
        "instanceId": "sfs-proxy-01",
        "resourceType": "SFS",
        "resourceId": "sfs-turbo-001/proxy-01",
        "metric": "sfs_active_connections",
        "currentValue": 9500,
        "threshold": 10000,
        "unit": "count",
        "firstOccurTime": "2025-03-05T09:40:00Z",
        "lastOccurTime": "2025-03-05T10:45:00Z",
        "occurCount": 12,
        "description": "活跃连接数 9500，接近上限 10000",
        "tags": {
          "az": "cn-north-4a"
        },
        "relatedAlarms": [],
        "rawData": {}
      },
      {
        "alarmId": "ALM-SFS-010",
        "alarmName": "SFS 吞吐量下降",
        "alarmLevel": "MAJOR",
        "alarmSource": "ANOMALY_DETECTION",
        "status": "FIRING",
        "serviceId": "sfs-turbo-001",
        "instanceId": "sfs-node-01",
        "resourceType": "SFS",
        "resourceId": "sfs-turbo-001/node-01",
        "metric": "sfs_throughput_mbps",
        "currentValue": 800,
        "threshold": 5000,
        "unit": "MBps",
        "firstOccurTime": "2025-03-05T09:20:00Z",
        "lastOccurTime": "2025-03-05T10:45:00Z",
        "occurCount": 30,
        "description": "吞吐量降至 800MBps，基线为 5000MBps，下降 84%",
        "tags": {
          "az": "cn-north-4a",
          "direction": "read"
        },
        "relatedAlarms": ["ALM-SFS-011"],
        "rawData": {}
      },
      {
        "alarmId": "ALM-SFS-011",
        "alarmName": "SFS 吞吐量下降",
        "alarmLevel": "MINOR",
        "alarmSource": "ANOMALY_DETECTION",
        "status": "FIRING",
        "serviceId": "sfs-turbo-001",
        "instanceId": "sfs-node-02",
        "resourceType": "SFS",
        "resourceId": "sfs-turbo-001/node-02",
        "metric": "sfs_throughput_mbps",
        "currentValue": 1200,
        "threshold": 5000,
        "unit": "MBps",
        "firstOccurTime": "2025-03-05T09:25:00Z",
        "lastOccurTime": "2025-03-05T10:44:00Z",
        "occurCount": 25,
        "description": "吞吐量降至 1200MBps，基线为 5000MBps，下降 76%",
        "tags": {
          "az": "cn-north-4a",
          "direction": "read"
        },
        "relatedAlarms": ["ALM-SFS-010"],
        "rawData": {}
      },
      {
        "alarmId": "ALM-SFS-012",
        "alarmName": "SFS CPU使用率升高",
        "alarmLevel": "WARNING",
        "alarmSource": "THRESHOLD",
        "status": "FIRING",
        "serviceId": "sfs-turbo-001",
        "instanceId": "sfs-node-01",
        "resourceType": "SFS",
        "resourceId": "sfs-turbo-001/node-01",
        "metric": "sfs_cpu_usage_percent",
        "currentValue": 78.5,
        "threshold": 80.0,
        "unit": "%",
        "firstOccurTime": "2025-03-05T09:35:00Z",
        "lastOccurTime": "2025-03-05T10:45:00Z",
        "occurCount": 15,
        "description": "CPU 使用率 78.5%，接近阈值 80%，IO等待占比高",
        "tags": {
          "az": "cn-north-4a"
        },
        "relatedAlarms": [],
        "rawData": {}
      }
    ]
  }
}
```

### 4.3 A2 — 告警详情

```
GET /v1/alarms/{alarmId}
```

响应同上述 Alarm 模型，此处省略。

### 4.4 A3 — 告警聚类

```
POST /v1/alarms/cluster
```

**请求体**

```json
{
  "alarmIds": ["string"],          // 待聚类的告警ID列表
  "algorithm": "string",           // AUTO | TIME_BASED | METRIC_BASED | TOPOLOGY_BASED
  "maxClusters": 10                // 最大聚类数
}
```

**Mock 请求**

```json
{
  "alarmIds": [
    "ALM-SFS-001", "ALM-SFS-002", "ALM-SFS-003", "ALM-SFS-004",
    "ALM-SFS-005", "ALM-SFS-006", "ALM-SFS-007", "ALM-SFS-008",
    "ALM-SFS-009", "ALM-SFS-010", "ALM-SFS-011", "ALM-SFS-012"
  ],
  "algorithm": "AUTO",
  "maxClusters": 10
}
```

**Mock 响应（聚类为 4 大类）**

```json
{
  "code": 200,
  "data": {
    "totalAlarms": 12,
    "clusterCount": 4,
    "clusters": [
      {
        "clusterId": "CLU-001",
        "clusterName": "NFS IO时延异常",
        "category": "IO_LATENCY",
        "severity": "CRITICAL",
        "alarmCount": 4,
        "alarms": ["ALM-SFS-001", "ALM-SFS-002", "ALM-SFS-003", "ALM-SFS-004"],
        "commonPattern": "NFS 读写操作 P99 时延大幅超阈值，涉及 node-01 和 node-02 两个存储节点",
        "affectedInstances": ["sfs-node-01", "sfs-node-02"],
        "timeRange": {
          "start": "2025-03-05T09:15:00Z",
          "end": "2025-03-05T10:45:00Z"
        },
        "suggestedAction": "检查存储后端IO路径，包括磁盘、网络及后端依赖服务的健康状态"
      },
      {
        "clusterId": "CLU-002",
        "clusterName": "OBS后端请求异常",
        "category": "DEPENDENCY",
        "severity": "CRITICAL",
        "alarmCount": 2,
        "alarms": ["ALM-SFS-005", "ALM-SFS-006"],
        "commonPattern": "后端 OBS 请求超时率异常升高，多节点同时出现",
        "affectedInstances": ["sfs-node-01", "sfs-node-02"],
        "timeRange": {
          "start": "2025-03-05T09:12:00Z",
          "end": "2025-03-05T10:45:00Z"
        },
        "suggestedAction": "检查 OBS 服务健康状态，重点排查时延和可用性"
      },
      {
        "clusterId": "CLU-003",
        "clusterName": "IO队列积压与吞吐下降",
        "category": "IO_LATENCY",
        "severity": "MAJOR",
        "alarmCount": 4,
        "alarms": ["ALM-SFS-007", "ALM-SFS-008", "ALM-SFS-010", "ALM-SFS-011"],
        "commonPattern": "IO队列深度过高，同时伴随吞吐量大幅下降，属IO时延异常的伴生现象",
        "affectedInstances": ["sfs-node-01", "sfs-node-02"],
        "timeRange": {
          "start": "2025-03-05T09:20:00Z",
          "end": "2025-03-05T10:45:00Z"
        },
        "suggestedAction": "属上游IO时延告警的连锁反应，优先处理根因"
      },
      {
        "clusterId": "CLU-004",
        "clusterName": "资源使用率告警",
        "category": "RESOURCE",
        "severity": "WARNING",
        "alarmCount": 2,
        "alarms": ["ALM-SFS-009", "ALM-SFS-012"],
        "commonPattern": "连接数和 CPU 使用率接近阈值，可能是IO积压的连锁反应",
        "affectedInstances": ["sfs-proxy-01", "sfs-node-01"],
        "timeRange": {
          "start": "2025-03-05T09:35:00Z",
          "end": "2025-03-05T10:45:00Z"
        },
        "suggestedAction": "非根因，属于伴生告警，优先处理IO时延和后端依赖问题"
      }
    ]
  }
}
```

---

## 5. 诊断 API（Diagnosis）

### 5.1 数据模型

```json
// DiagnosisTask — 诊断任务
{
  "taskId": "string",
  "taskName": "string",
  "status": "string",              // PENDING | RUNNING | COMPLETED | FAILED | TIMEOUT
  "serviceId": "string",
  "clusterId": "string",           // 关联的告警聚类
  "diagnosisType": "string",       // IO_ANALYSIS | DEPENDENCY_CHECK | RESOURCE_CHECK | NETWORK_CHECK
  "createTime": "string",
  "completeTime": "string",
  "result": {
    "rootCauseFound": false,       // 是否找到根因
    "confidence": 0.0,             // 置信度 0-1
    "rootCause": "string",         // 根因描述
    "rootCauseCategory": "string", // 根因分类
    "evidence": [                  // 证据链
      {
        "type": "string",          // METRIC | LOG | TOPOLOGY | ALARM
        "description": "string",
        "data": {}
      }
    ],
    "impact": "string",            // 影响描述
    "suggestion": "string"         // 修复建议
  },
  "steps": [                       // 诊断步骤记录
    {
      "stepId": "string",
      "stepName": "string",
      "status": "string",
      "startTime": "string",
      "endTime": "string",
      "detail": "string",
      "findings": "string"
    }
  ]
}
```

### 5.2 D1 — 创建诊断任务

```
POST /v1/diagnosis/tasks
```

**请求体**

```json
{
  "serviceId": "string",
  "clusterId": "string",
  "diagnosisType": "string",
  "alarmIds": ["string"],
  "timeRange": {
    "start": "string",
    "end": "string"
  },
  "config": {
    "timeout": 300,                // 超时时间(秒)
    "depth": "DEEP",               // QUICK | NORMAL | DEEP
    "includeMetrics": true,
    "includeLogs": true
  }
}
```

### 5.3 D2 — 查询诊断结果

```
GET /v1/diagnosis/tasks/{taskId}
```

**Mock 响应 — CLU-001 IO时延诊断（未找到SFS自身根因）**

```json
{
  "code": 200,
  "data": {
    "taskId": "DIAG-001",
    "taskName": "SFS NFS IO时延异常诊断",
    "status": "COMPLETED",
    "serviceId": "sfs-turbo-001",
    "clusterId": "CLU-001",
    "diagnosisType": "IO_ANALYSIS",
    "createTime": "2025-03-05T10:46:00Z",
    "completeTime": "2025-03-05T10:49:30Z",
    "result": {
      "rootCauseFound": false,
      "confidence": 0.0,
      "rootCause": null,
      "rootCauseCategory": null,
      "evidence": [
        {
          "type": "METRIC",
          "description": "SFS 本地磁盘 IOPS 和时延均正常，排除本地磁盘故障",
          "data": {
            "metric": "sfs_local_disk_latency_ms",
            "value": 0.8,
            "baseline": 1.0
          }
        },
        {
          "type": "METRIC",
          "description": "SFS 内部 RPC 时延正常，排除 SFS 集群间通信问题",
          "data": {
            "metric": "sfs_internal_rpc_latency_ms",
            "value": 2.1,
            "baseline": 2.0
          }
        },
        {
          "type": "METRIC",
          "description": "SFS 进程资源使用正常，排除进程级故障",
          "data": {
            "metric": "sfs_process_mem_usage_percent",
            "value": 45.2,
            "baseline": 42.0
          }
        }
      ],
      "impact": "NFS IO时延异常非 SFS 自身引起，需排查后端依赖",
      "suggestion": "建议检查 SFS 后端依赖服务（OBS、EVS、VPC），重点排查 OBS 时延"
    },
    "steps": [
      {
        "stepId": "S1",
        "stepName": "本地磁盘检查",
        "status": "COMPLETED",
        "startTime": "2025-03-05T10:46:00Z",
        "endTime": "2025-03-05T10:46:45Z",
        "detail": "检查所有存储节点的本地磁盘 IOPS、时延和错误计数",
        "findings": "本地磁盘各项指标正常，无硬件故障"
      },
      {
        "stepId": "S2",
        "stepName": "集群内部通信检查",
        "status": "COMPLETED",
        "startTime": "2025-03-05T10:46:45Z",
        "endTime": "2025-03-05T10:47:30Z",
        "detail": "检查节点间 RPC 时延和丢包率",
        "findings": "集群内部通信正常"
      },
      {
        "stepId": "S3",
        "stepName": "进程级检查",
        "status": "COMPLETED",
        "startTime": "2025-03-05T10:47:30Z",
        "endTime": "2025-03-05T10:48:15Z",
        "detail": "检查 SFS 进程 CPU/内存/GC/线程池",
        "findings": "进程运行正常，无 GC 压力或线程池满"
      },
      {
        "stepId": "S4",
        "stepName": "后端链路分析",
        "status": "COMPLETED",
        "startTime": "2025-03-05T10:48:15Z",
        "endTime": "2025-03-05T10:49:30Z",
        "detail": "分析后端 OBS/EVS 调用链路耗时分布",
        "findings": "OBS 调用链路时延 P99 = 850ms（正常 < 50ms），EVS 和 VPC 链路正常。强烈建议排查 OBS 服务。"
      }
    ]
  }
}
```

**Mock 响应 — CLU-002 OBS依赖诊断（未找到SFS自身根因，确认指向OBS）**

```json
{
  "code": 200,
  "data": {
    "taskId": "DIAG-002",
    "taskName": "SFS OBS后端依赖异常诊断",
    "status": "COMPLETED",
    "serviceId": "sfs-turbo-001",
    "clusterId": "CLU-002",
    "diagnosisType": "DEPENDENCY_CHECK",
    "createTime": "2025-03-05T10:46:00Z",
    "completeTime": "2025-03-05T10:48:00Z",
    "result": {
      "rootCauseFound": false,
      "confidence": 0.0,
      "rootCause": null,
      "rootCauseCategory": null,
      "evidence": [
        {
          "type": "METRIC",
          "description": "SFS → OBS 调用时延 P99 高达 850ms，正常基线 50ms",
          "data": {
            "metric": "sfs_obs_call_latency_p99_ms",
            "value": 850,
            "baseline": 50
          }
        },
        {
          "type": "METRIC",
          "description": "SFS → OBS 超时率达 15%",
          "data": {
            "metric": "sfs_obs_timeout_rate",
            "value": 0.15,
            "baseline": 0.001
          }
        }
      ],
      "impact": "OBS 调用异常导致 SFS 性能劣化，非 SFS 自身问题",
      "suggestion": "根因不在 SFS 侧，需跨服务排查 OBS"
    },
    "steps": []
  }
}
```

**Mock 响应 — OBS 服务诊断（找到根因!）**

此诊断任务是 Agent 在追溯到 OBS 服务后，对 OBS 告警聚类下发的诊断任务。

```json
{
  "code": 200,
  "data": {
    "taskId": "DIAG-OBS-001",
    "taskName": "OBS 时延异常诊断",
    "status": "COMPLETED",
    "serviceId": "obs-bucket-train-data",
    "clusterId": "CLU-OBS-001",
    "diagnosisType": "IO_ANALYSIS",
    "createTime": "2025-03-05T10:52:00Z",
    "completeTime": "2025-03-05T10:56:00Z",
    "result": {
      "rootCauseFound": true,
      "confidence": 0.95,
      "rootCause": "OBS 存储节点 obs-store-03 磁盘阵列出现慢盘，导致 PUT/GET 操作时延升高，影响 SFS Turbo 后端数据读写性能，最终导致训练任务吞吐劣化",
      "rootCauseCategory": "HARDWARE_DEGRADATION",
      "evidence": [
        {
          "type": "METRIC",
          "description": "OBS 存储节点 obs-store-03 磁盘时延 P99 = 120ms，正常基线 5ms",
          "data": {
            "metric": "obs_disk_latency_p99_ms",
            "instanceId": "obs-store-03",
            "value": 120,
            "baseline": 5
          }
        },
        {
          "type": "METRIC",
          "description": "该节点所在磁盘阵列的 SMART 健康评分下降至 42%",
          "data": {
            "metric": "obs_disk_smart_health_score",
            "instanceId": "obs-store-03",
            "diskId": "disk-sda",
            "value": 42,
            "baseline": 98
          }
        },
        {
          "type": "LOG",
          "description": "OBS 节点日志中出现大量慢IO警告",
          "data": {
            "logId": "LOG-OBS-78901",
            "content": "WARN slow_disk_io disk=sda latency=135ms threshold=10ms count=1247 in_last_5min",
            "timestamp": "2025-03-05T10:30:00Z"
          }
        },
        {
          "type": "LOG",
          "description": "SMART 监控日志显示 Reallocated Sector 数量增长",
          "data": {
            "logId": "LOG-OBS-78902",
            "content": "WARN disk_smart_alert disk=sda reallocated_sectors=156 grown_defects=23",
            "timestamp": "2025-03-05T09:00:00Z"
          }
        },
        {
          "type": "ALARM",
          "description": "OBS 告警: obs-store-03 GET 操作时延超阈值",
          "data": {
            "alarmId": "ALM-OBS-003",
            "metric": "obs_get_latency_p99_ms",
            "value": 380
          }
        }
      ],
      "impact": "OBS 慢盘导致 GET/PUT 时延 → SFS 后端请求积压 → NFS 时延升高 → GPU 训练任务数据读取劣化 → 训练吞吐下降",
      "suggestion": "1) 紧急：将 obs-store-03 上的数据迁移至健康节点\n2) 短期：更换故障磁盘\n3) 长期：加强磁盘 SMART 预测性监控，在慢盘影响业务前提前更换"
    },
    "steps": [
      {
        "stepId": "S1",
        "stepName": "OBS 网关检查",
        "status": "COMPLETED",
        "startTime": "2025-03-05T10:52:00Z",
        "endTime": "2025-03-05T10:52:45Z",
        "detail": "检查 OBS 网关节点健康状态和负载",
        "findings": "网关节点正常，排除网关层问题"
      },
      {
        "stepId": "S2",
        "stepName": "OBS 存储节点分析",
        "status": "COMPLETED",
        "startTime": "2025-03-05T10:52:45Z",
        "endTime": "2025-03-05T10:54:00Z",
        "detail": "分析各存储节点磁盘IO指标",
        "findings": "obs-store-03 磁盘时延异常，P99=120ms，其他节点 < 5ms"
      },
      {
        "stepId": "S3",
        "stepName": "磁盘健康检查",
        "status": "COMPLETED",
        "startTime": "2025-03-05T10:54:00Z",
        "endTime": "2025-03-05T10:55:00Z",
        "detail": "检查 SMART 数据和磁盘错误日志",
        "findings": "sda 磁盘 Reallocated Sector Count=156，健康评分42%，确认为慢盘"
      },
      {
        "stepId": "S4",
        "stepName": "影响链路确认",
        "status": "COMPLETED",
        "startTime": "2025-03-05T10:55:00Z",
        "endTime": "2025-03-05T10:56:00Z",
        "detail": "确认故障传播路径: 慢盘 → OBS 时延 → SFS 后端积压 → NFS 时延 → 训练劣化",
        "findings": "时间线吻合，故障传播路径确认: 09:00 SMART告警 → 09:12 OBS超时率上升 → 09:15 SFS NFS时延超阈值"
      }
    ]
  }
}
```

---

## 6. 指标 API（Metrics）

### 6.1 数据模型

```json
// MetricDefinition — 指标定义
{
  "metricName": "string",
  "displayName": "string",
  "unit": "string",
  "description": "string",
  "serviceType": "string",         // SFS_TURBO | OBS | ECS
  "category": "string",            // PERFORMANCE | AVAILABILITY | RESOURCE | NETWORK
  "aggregations": ["AVG", "P50", "P99", "MAX", "MIN", "SUM"],
  "defaultThreshold": {
    "warning": 0.0,
    "critical": 0.0
  }
}

// MetricDataPoint — 指标数据点
{
  "timestamp": "string",
  "value": 0.0
}

// MetricQueryResult — 指标查询结果
{
  "metricName": "string",
  "instanceId": "string",
  "aggregation": "string",
  "granularity": "string",         // 1m | 5m | 15m | 1h
  "dataPoints": [MetricDataPoint],
  "statistics": {
    "avg": 0.0,
    "max": 0.0,
    "min": 0.0,
    "p50": 0.0,
    "p99": 0.0
  }
}
```

### 6.2 M1 — 查询指标数据

```
POST /v1/metrics/query
```

**请求体**

```json
{
  "metricName": "string",
  "instanceIds": ["string"],
  "aggregation": "string",         // AVG | P50 | P99 | MAX
  "granularity": "string",         // 1m | 5m | 15m | 1h
  "timeRange": {
    "start": "string",
    "end": "string"
  }
}
```

**Mock 请求（查询 OBS 时延）**

```json
{
  "metricName": "obs_get_latency_p99_ms",
  "instanceIds": ["obs-store-01", "obs-store-02", "obs-store-03"],
  "aggregation": "P99",
  "granularity": "5m",
  "timeRange": {
    "start": "2025-03-05T08:00:00Z",
    "end": "2025-03-05T11:00:00Z"
  }
}
```

**Mock 响应（obs-store-03 时延异常清晰可见）**

```json
{
  "code": 200,
  "data": {
    "results": [
      {
        "metricName": "obs_get_latency_p99_ms",
        "instanceId": "obs-store-01",
        "aggregation": "P99",
        "granularity": "5m",
        "dataPoints": [
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
        "metricName": "obs_get_latency_p99_ms",
        "instanceId": "obs-store-02",
        "aggregation": "P99",
        "granularity": "5m",
        "dataPoints": [
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
        "metricName": "obs_get_latency_p99_ms",
        "instanceId": "obs-store-03",
        "aggregation": "P99",
        "granularity": "5m",
        "dataPoints": [
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
}
```

### 6.3 M2 — 获取可用指标列表

```
GET /v1/metrics/definitions?serviceType={serviceType}
```

**Mock 响应（SFS Turbo 可用指标）**

```json
{
  "code": 200,
  "data": {
    "metrics": [
      {
        "metricName": "sfs_nfs_read_latency_ms",
        "displayName": "NFS 读时延",
        "unit": "ms",
        "description": "NFS 读操作端到端时延",
        "serviceType": "SFS_TURBO",
        "category": "PERFORMANCE",
        "aggregations": ["AVG", "P50", "P99", "MAX"],
        "defaultThreshold": {"warning": 30.0, "critical": 50.0}
      },
      {
        "metricName": "sfs_nfs_write_latency_ms",
        "displayName": "NFS 写时延",
        "unit": "ms",
        "description": "NFS 写操作端到端时延",
        "serviceType": "SFS_TURBO",
        "category": "PERFORMANCE",
        "aggregations": ["AVG", "P50", "P99", "MAX"],
        "defaultThreshold": {"warning": 60.0, "critical": 100.0}
      },
      {
        "metricName": "sfs_throughput_mbps",
        "displayName": "吞吐量",
        "unit": "MBps",
        "description": "SFS 存储吞吐量",
        "serviceType": "SFS_TURBO",
        "category": "PERFORMANCE",
        "aggregations": ["AVG", "MAX", "SUM"],
        "defaultThreshold": {"warning": 2000, "critical": 1000}
      },
      {
        "metricName": "sfs_iops",
        "displayName": "IOPS",
        "unit": "count/s",
        "description": "每秒IO操作数",
        "serviceType": "SFS_TURBO",
        "category": "PERFORMANCE",
        "aggregations": ["AVG", "MAX"],
        "defaultThreshold": {"warning": null, "critical": null}
      },
      {
        "metricName": "sfs_backend_obs_timeout_rate",
        "displayName": "OBS后端超时率",
        "unit": "ratio",
        "description": "SFS访问后端OBS的请求超时率",
        "serviceType": "SFS_TURBO",
        "category": "AVAILABILITY",
        "aggregations": ["AVG", "MAX"],
        "defaultThreshold": {"warning": 0.005, "critical": 0.01}
      },
      {
        "metricName": "sfs_obs_call_latency_p99_ms",
        "displayName": "OBS调用时延P99",
        "unit": "ms",
        "description": "SFS调用OBS接口的P99时延",
        "serviceType": "SFS_TURBO",
        "category": "PERFORMANCE",
        "aggregations": ["AVG", "P99", "MAX"],
        "defaultThreshold": {"warning": 30.0, "critical": 100.0}
      },
      {
        "metricName": "sfs_io_queue_depth",
        "displayName": "IO队列深度",
        "unit": "count",
        "description": "等待处理的IO请求队列深度",
        "serviceType": "SFS_TURBO",
        "category": "PERFORMANCE",
        "aggregations": ["AVG", "MAX"],
        "defaultThreshold": {"warning": 64, "critical": 128}
      },
      {
        "metricName": "sfs_active_connections",
        "displayName": "活跃连接数",
        "unit": "count",
        "description": "当前NFS活跃连接数",
        "serviceType": "SFS_TURBO",
        "category": "RESOURCE",
        "aggregations": ["AVG", "MAX"],
        "defaultThreshold": {"warning": 8000, "critical": 10000}
      },
      {
        "metricName": "sfs_cpu_usage_percent",
        "displayName": "CPU使用率",
        "unit": "%",
        "description": "SFS节点CPU使用率",
        "serviceType": "SFS_TURBO",
        "category": "RESOURCE",
        "aggregations": ["AVG", "MAX"],
        "defaultThreshold": {"warning": 80.0, "critical": 95.0}
      },
      {
        "metricName": "sfs_local_disk_latency_ms",
        "displayName": "本地磁盘时延",
        "unit": "ms",
        "description": "SFS节点本地磁盘IO时延",
        "serviceType": "SFS_TURBO",
        "category": "PERFORMANCE",
        "aggregations": ["AVG", "P99", "MAX"],
        "defaultThreshold": {"warning": 5.0, "critical": 20.0}
      },
      {
        "metricName": "sfs_internal_rpc_latency_ms",
        "displayName": "内部RPC时延",
        "unit": "ms",
        "description": "SFS集群内部节点间RPC时延",
        "serviceType": "SFS_TURBO",
        "category": "NETWORK",
        "aggregations": ["AVG", "P99", "MAX"],
        "defaultThreshold": {"warning": 5.0, "critical": 10.0}
      }
    ]
  }
}
```

---

## 7. 日志 API（Log）

### 7.1 数据模型

```json
// LogEntry — 日志条目
{
  "logId": "string",
  "timestamp": "string",           // ISO 8601
  "level": "string",               // DEBUG | INFO | WARN | ERROR | FATAL
  "serviceId": "string",
  "instanceId": "string",
  "source": "string",              // 日志来源文件/模块
  "message": "string",
  "structuredData": {},             // 结构化字段
  "traceId": "string",             // 链路追踪ID（可选）
  "spanId": "string"
}

// LogQueryResult — 日志查询结果
{
  "total": 0,
  "logs": [LogEntry],
  "facets": {                      // 聚合统计
    "levels": {"ERROR": 0, "WARN": 0},
    "instances": {"id": 0}
  }
}
```

### 7.2 L1 — 查询日志

```
POST /v1/logs/query
```

**请求体**

```json
{
  "serviceId": "string",
  "instanceIds": ["string"],
  "levels": ["string"],
  "keyword": "string",             // 关键词搜索
  "timeRange": {
    "start": "string",
    "end": "string"
  },
  "pageSize": 50,
  "pageToken": "string",
  "orderBy": "DESC"                // ASC | DESC
}
```

**Mock 请求（查询 SFS 节点 ERROR/WARN 日志）**

```json
{
  "serviceId": "sfs-turbo-001",
  "instanceIds": ["sfs-node-01", "sfs-node-02"],
  "levels": ["ERROR", "WARN"],
  "timeRange": {
    "start": "2025-03-05T09:00:00Z",
    "end": "2025-03-05T11:00:00Z"
  },
  "pageSize": 20,
  "orderBy": "DESC"
}
```

**Mock 响应**

```json
{
  "code": 200,
  "data": {
    "total": 156,
    "logs": [
      {
        "logId": "LOG-SFS-10001",
        "timestamp": "2025-03-05T10:44:58Z",
        "level": "ERROR",
        "serviceId": "sfs-turbo-001",
        "instanceId": "sfs-node-01",
        "source": "obs_client.go:245",
        "message": "OBS PUT request timeout after 30s, bucket=train-data-bucket, key=checkpoint/model_step_50000.bin, retry=3/3",
        "structuredData": {
          "bucket": "train-data-bucket",
          "key": "checkpoint/model_step_50000.bin",
          "timeout_ms": 30000,
          "retry_count": 3,
          "obs_endpoint": "obs.cn-north-4.myhuaweicloud.com"
        },
        "traceId": "trace-abc-001",
        "spanId": "span-def-001"
      },
      {
        "logId": "LOG-SFS-10002",
        "timestamp": "2025-03-05T10:44:52Z",
        "level": "WARN",
        "serviceId": "sfs-turbo-001",
        "instanceId": "sfs-node-01",
        "source": "io_scheduler.go:189",
        "message": "IO queue depth exceeded threshold, current=512, threshold=128, pending_requests=384",
        "structuredData": {
          "queue_depth": 512,
          "threshold": 128,
          "pending_requests": 384,
          "oldest_request_age_ms": 15230
        },
        "traceId": null,
        "spanId": null
      },
      {
        "logId": "LOG-SFS-10003",
        "timestamp": "2025-03-05T10:44:30Z",
        "level": "WARN",
        "serviceId": "sfs-turbo-001",
        "instanceId": "sfs-node-02",
        "source": "obs_client.go:198",
        "message": "OBS GET request slow, latency=850ms, bucket=train-data-bucket, key=data/shard_00042.tfrecord",
        "structuredData": {
          "bucket": "train-data-bucket",
          "key": "data/shard_00042.tfrecord",
          "latency_ms": 850,
          "obs_endpoint": "obs.cn-north-4.myhuaweicloud.com"
        },
        "traceId": "trace-abc-002",
        "spanId": "span-def-002"
      },
      {
        "logId": "LOG-SFS-10004",
        "timestamp": "2025-03-05T10:43:15Z",
        "level": "ERROR",
        "serviceId": "sfs-turbo-001",
        "instanceId": "sfs-node-01",
        "source": "nfs_handler.go:567",
        "message": "NFS READ operation exceeded SLA, client=192.168.2.50, file=/mnt/sfs/training/data/batch_1024.bin, latency=325ms, sla=50ms",
        "structuredData": {
          "client_ip": "192.168.2.50",
          "file_path": "/mnt/sfs/training/data/batch_1024.bin",
          "latency_ms": 325,
          "sla_ms": 50,
          "operation": "READ",
          "file_size_bytes": 134217728
        },
        "traceId": "trace-abc-003",
        "spanId": "span-def-003"
      },
      {
        "logId": "LOG-SFS-10005",
        "timestamp": "2025-03-05T10:42:00Z",
        "level": "WARN",
        "serviceId": "sfs-turbo-001",
        "instanceId": "sfs-node-01",
        "source": "backend_pool.go:92",
        "message": "OBS connection pool exhausted, active=200, max=200, waiting=85, avg_wait_ms=2340",
        "structuredData": {
          "active_connections": 200,
          "max_connections": 200,
          "waiting_requests": 85,
          "avg_wait_ms": 2340
        },
        "traceId": null,
        "spanId": null
      },
      {
        "logId": "LOG-SFS-10006",
        "timestamp": "2025-03-05T10:40:22Z",
        "level": "WARN",
        "serviceId": "sfs-turbo-001",
        "instanceId": "sfs-node-02",
        "source": "obs_client.go:198",
        "message": "OBS GET request slow, latency=720ms, bucket=train-data-bucket, key=data/shard_00038.tfrecord",
        "structuredData": {
          "bucket": "train-data-bucket",
          "key": "data/shard_00038.tfrecord",
          "latency_ms": 720,
          "obs_endpoint": "obs.cn-north-4.myhuaweicloud.com"
        },
        "traceId": "trace-abc-004",
        "spanId": "span-def-004"
      }
    ],
    "facets": {
      "levels": {"ERROR": 42, "WARN": 114},
      "instances": {"sfs-node-01": 98, "sfs-node-02": 58}
    }
  }
}
```

### 7.3 L2 — 获取日志上下文

```
GET /v1/logs/context/{logId}?before=10&after=10
```

**请求参数**

| 参数 | 位置 | 必填 | 说明 |
|------|------|------|------|
| logId | path | 是 | 日志ID |
| before | query | 否 | 前N条，默认10 |
| after | query | 否 | 后N条，默认10 |

**Mock 响应**

```json
{
  "code": 200,
  "data": {
    "targetLog": {
      "logId": "LOG-SFS-10001",
      "timestamp": "2025-03-05T10:44:58Z",
      "level": "ERROR",
      "message": "OBS PUT request timeout after 30s..."
    },
    "beforeLogs": [
      {
        "logId": "LOG-SFS-09998",
        "timestamp": "2025-03-05T10:44:55Z",
        "level": "WARN",
        "instanceId": "sfs-node-01",
        "source": "obs_client.go:210",
        "message": "OBS PUT request retry, attempt=2/3, bucket=train-data-bucket, elapsed=20150ms"
      },
      {
        "logId": "LOG-SFS-09995",
        "timestamp": "2025-03-05T10:44:42Z",
        "level": "WARN",
        "instanceId": "sfs-node-01",
        "source": "obs_client.go:210",
        "message": "OBS PUT request retry, attempt=1/3, bucket=train-data-bucket, elapsed=10080ms"
      },
      {
        "logId": "LOG-SFS-09990",
        "timestamp": "2025-03-05T10:44:28Z",
        "level": "INFO",
        "instanceId": "sfs-node-01",
        "source": "obs_client.go:180",
        "message": "OBS PUT request started, bucket=train-data-bucket, key=checkpoint/model_step_50000.bin, size=2147483648"
      }
    ],
    "afterLogs": [
      {
        "logId": "LOG-SFS-10002",
        "timestamp": "2025-03-05T10:45:00Z",
        "level": "ERROR",
        "instanceId": "sfs-node-01",
        "source": "checkpoint_manager.go:134",
        "message": "Checkpoint write failed, will retry in 60s, file=model_step_50000.bin"
      },
      {
        "logId": "LOG-SFS-10003",
        "timestamp": "2025-03-05T10:45:02Z",
        "level": "WARN",
        "instanceId": "sfs-node-01",
        "source": "nfs_handler.go:580",
        "message": "Client NFS WRITE callback delayed, client=192.168.2.50, delay=325ms"
      }
    ]
  }
}
```

---

## 8. OBS 服务告警（跨服务追溯用）

Agent 在确认 SFS 自身无根因后，通过拓扑发现依赖 OBS，接下来查询 OBS 服务告警。

**Mock — OBS 服务告警查询响应**

```json
{
  "code": 200,
  "data": {
    "total": 8,
    "alarms": [
      {
        "alarmId": "ALM-OBS-001",
        "alarmName": "OBS PUT操作时延超阈值",
        "alarmLevel": "CRITICAL",
        "alarmSource": "THRESHOLD",
        "status": "FIRING",
        "serviceId": "obs-bucket-train-data",
        "instanceId": "obs-gw-01",
        "resourceType": "OBS",
        "resourceId": "obs-bucket-train-data/gw-01",
        "metric": "obs_put_latency_p99_ms",
        "currentValue": 620.0,
        "threshold": 50.0,
        "unit": "ms",
        "firstOccurTime": "2025-03-05T09:10:00Z",
        "lastOccurTime": "2025-03-05T10:50:00Z",
        "occurCount": 45,
        "description": "OBS PUT 操作 P99 时延 620ms，超过阈值 50ms",
        "tags": {"az": "cn-north-4a", "operation": "PUT"},
        "relatedAlarms": ["ALM-OBS-002"],
        "rawData": {}
      },
      {
        "alarmId": "ALM-OBS-002",
        "alarmName": "OBS GET操作时延超阈值",
        "alarmLevel": "CRITICAL",
        "alarmSource": "THRESHOLD",
        "status": "FIRING",
        "serviceId": "obs-bucket-train-data",
        "instanceId": "obs-gw-01",
        "resourceType": "OBS",
        "resourceId": "obs-bucket-train-data/gw-01",
        "metric": "obs_get_latency_p99_ms",
        "currentValue": 380.0,
        "threshold": 30.0,
        "unit": "ms",
        "firstOccurTime": "2025-03-05T09:10:00Z",
        "lastOccurTime": "2025-03-05T10:50:00Z",
        "occurCount": 42,
        "description": "OBS GET 操作 P99 时延 380ms",
        "tags": {"az": "cn-north-4a", "operation": "GET"},
        "relatedAlarms": ["ALM-OBS-001"],
        "rawData": {}
      },
      {
        "alarmId": "ALM-OBS-003",
        "alarmName": "OBS 存储节点磁盘时延异常",
        "alarmLevel": "CRITICAL",
        "alarmSource": "ANOMALY_DETECTION",
        "status": "FIRING",
        "serviceId": "obs-bucket-train-data",
        "instanceId": "obs-store-03",
        "resourceType": "OBS",
        "resourceId": "obs-bucket-train-data/store-03/disk-sda",
        "metric": "obs_disk_latency_p99_ms",
        "currentValue": 120.0,
        "threshold": 10.0,
        "unit": "ms",
        "firstOccurTime": "2025-03-05T08:55:00Z",
        "lastOccurTime": "2025-03-05T10:50:00Z",
        "occurCount": 60,
        "description": "存储节点 obs-store-03 磁盘 P99 时延 120ms，正常 < 5ms，疑似慢盘",
        "tags": {"az": "cn-north-4a", "disk": "sda", "node": "obs-store-03"},
        "relatedAlarms": ["ALM-OBS-004"],
        "rawData": {}
      },
      {
        "alarmId": "ALM-OBS-004",
        "alarmName": "OBS 磁盘 SMART 健康告警",
        "alarmLevel": "MAJOR",
        "alarmSource": "MONITOR",
        "status": "FIRING",
        "serviceId": "obs-bucket-train-data",
        "instanceId": "obs-store-03",
        "resourceType": "OBS",
        "resourceId": "obs-bucket-train-data/store-03/disk-sda",
        "metric": "obs_disk_smart_health_score",
        "currentValue": 42.0,
        "threshold": 60.0,
        "unit": "%",
        "firstOccurTime": "2025-03-05T08:30:00Z",
        "lastOccurTime": "2025-03-05T10:50:00Z",
        "occurCount": 55,
        "description": "磁盘 SMART 健康评分 42%，Reallocated Sector Count=156",
        "tags": {"az": "cn-north-4a", "disk": "sda", "smart_attribute": "Reallocated_Sector_Ct"},
        "relatedAlarms": ["ALM-OBS-003"],
        "rawData": {}
      },
      {
        "alarmId": "ALM-OBS-005",
        "alarmName": "OBS 请求队列积压",
        "alarmLevel": "MAJOR",
        "alarmSource": "THRESHOLD",
        "status": "FIRING",
        "serviceId": "obs-bucket-train-data",
        "instanceId": "obs-store-03",
        "resourceType": "OBS",
        "resourceId": "obs-bucket-train-data/store-03",
        "metric": "obs_request_queue_length",
        "currentValue": 2048,
        "threshold": 500,
        "unit": "count",
        "firstOccurTime": "2025-03-05T09:15:00Z",
        "lastOccurTime": "2025-03-05T10:50:00Z",
        "occurCount": 35,
        "description": "存储节点请求队列积压严重",
        "tags": {"az": "cn-north-4a"},
        "relatedAlarms": [],
        "rawData": {}
      },
      {
        "alarmId": "ALM-OBS-006",
        "alarmName": "OBS 错误率升高",
        "alarmLevel": "MAJOR",
        "alarmSource": "THRESHOLD",
        "status": "FIRING",
        "serviceId": "obs-bucket-train-data",
        "instanceId": "obs-gw-01",
        "resourceType": "OBS",
        "resourceId": "obs-bucket-train-data/gw-01",
        "metric": "obs_5xx_error_rate",
        "currentValue": 0.08,
        "threshold": 0.01,
        "unit": "ratio",
        "firstOccurTime": "2025-03-05T09:20:00Z",
        "lastOccurTime": "2025-03-05T10:50:00Z",
        "occurCount": 30,
        "description": "5xx 错误率 8%，主要为 503 Service Unavailable",
        "tags": {"az": "cn-north-4a"},
        "relatedAlarms": [],
        "rawData": {}
      },
      {
        "alarmId": "ALM-OBS-007",
        "alarmName": "OBS 吞吐量下降",
        "alarmLevel": "MINOR",
        "alarmSource": "ANOMALY_DETECTION",
        "status": "FIRING",
        "serviceId": "obs-bucket-train-data",
        "instanceId": "obs-store-03",
        "resourceType": "OBS",
        "resourceId": "obs-bucket-train-data/store-03",
        "metric": "obs_throughput_mbps",
        "currentValue": 200,
        "threshold": 2000,
        "unit": "MBps",
        "firstOccurTime": "2025-03-05T09:10:00Z",
        "lastOccurTime": "2025-03-05T10:50:00Z",
        "occurCount": 40,
        "description": "存储节点吞吐量下降 90%",
        "tags": {"az": "cn-north-4a"},
        "relatedAlarms": [],
        "rawData": {}
      },
      {
        "alarmId": "ALM-OBS-008",
        "alarmName": "OBS IO Wait 升高",
        "alarmLevel": "WARNING",
        "alarmSource": "THRESHOLD",
        "status": "FIRING",
        "serviceId": "obs-bucket-train-data",
        "instanceId": "obs-store-03",
        "resourceType": "OBS",
        "resourceId": "obs-bucket-train-data/store-03",
        "metric": "obs_iowait_percent",
        "currentValue": 65.0,
        "threshold": 30.0,
        "unit": "%",
        "firstOccurTime": "2025-03-05T09:05:00Z",
        "lastOccurTime": "2025-03-05T10:50:00Z",
        "occurCount": 50,
        "description": "IO Wait 占比 65%，CPU 大量时间等待磁盘IO",
        "tags": {"az": "cn-north-4a"},
        "relatedAlarms": [],
        "rawData": {}
      }
    ]
  }
}
```

---

## 9. Agent 完整调用流程（伪代码）

```python
def diagnose_from_alarm(initial_alarm):
    """
    Agent 主诊断流程
    输入：初始告警（包含 ECS instanceID）
    输出：根因分析报告
    """

    # Step 1: 从告警中提取服务信息
    service_id = initial_alarm["serviceId"]  # "sfs-turbo-001"
    visited_services = set()

    while service_id and service_id not in visited_services:
        visited_services.add(service_id)

        # Step 2: 获取服务拓扑
        topology = call_api("GET /topology/services/{}", service_id)

        # Step 3: 获取该服务下全部实例
        instances = call_api("GET /topology/services/{}/instances", service_id)

        # Step 4: 拉取该服务全量告警
        alarms = call_api("POST /alarms/query", {
            "serviceId": service_id,
            "status": ["FIRING"],
            "timeRange": get_diagnosis_time_range()
        })

        if not alarms:
            break

        # Step 5: 告警聚类
        clusters = call_api("POST /alarms/cluster", {
            "alarmIds": [a["alarmId"] for a in alarms],
            "algorithm": "AUTO"
        })

        # Step 6: 对每个聚类下发诊断任务
        root_cause_found = False
        for cluster in clusters:
            task = call_api("POST /diagnosis/tasks", {
                "serviceId": service_id,
                "clusterId": cluster["clusterId"],
                "diagnosisType": infer_diagnosis_type(cluster),
                "alarmIds": cluster["alarms"]
            })

            # 轮询诊断结果
            result = poll_until_complete(task["taskId"])

            if result["rootCauseFound"]:
                # 找到根因！
                root_cause_found = True
                # 可选：拉取指标和日志作为辅助证据
                metrics = call_api("POST /metrics/query", build_metric_query(result))
                logs = call_api("POST /logs/query", build_log_query(result))
                return build_report(result, metrics, logs)

        # Step 7: 所有聚类均未找到根因 → 向下游追溯
        if not root_cause_found:
            dependencies = call_api(
                "GET /topology/services/{}/dependencies", service_id,
                params={"direction": "DOWNSTREAM"}
            )
            # 按依赖强度和健康状态排序，优先检查异常的强依赖
            next_service = select_most_suspicious_dependency(dependencies)
            if next_service:
                service_id = next_service["serviceId"]
            else:
                break

    return "未能定位根因，建议人工介入排查"
```

---

## 10. 指标与日志关键字段索引

### SFS Turbo 关键指标

| 指标名 | 说明 | 正常基线 | 告警阈值 |
|--------|------|----------|----------|
| sfs_nfs_read_latency_ms | NFS 读时延 | < 10ms | > 50ms |
| sfs_nfs_write_latency_ms | NFS 写时延 | < 20ms | > 100ms |
| sfs_throughput_mbps | 吞吐量 | > 5000MBps | < 1000MBps |
| sfs_backend_obs_timeout_rate | OBS 超时率 | < 0.1% | > 1% |
| sfs_obs_call_latency_p99_ms | OBS调用P99时延 | < 50ms | > 100ms |
| sfs_io_queue_depth | IO队列深度 | < 32 | > 128 |
| sfs_active_connections | 活跃连接数 | < 5000 | > 10000 |
| sfs_cpu_usage_percent | CPU 使用率 | < 60% | > 80% |
| sfs_local_disk_latency_ms | 本地磁盘时延 | < 1ms | > 20ms |
| sfs_internal_rpc_latency_ms | 内部RPC时延 | < 2ms | > 10ms |

### OBS 关键指标

| 指标名 | 说明 | 正常基线 | 告警阈值 |
|--------|------|----------|----------|
| obs_get_latency_p99_ms | GET P99时延 | < 5ms | > 30ms |
| obs_put_latency_p99_ms | PUT P99时延 | < 10ms | > 50ms |
| obs_disk_latency_p99_ms | 磁盘时延 | < 5ms | > 10ms |
| obs_disk_smart_health_score | SMART 健康评分 | > 95% | < 60% |
| obs_request_queue_length | 请求队列长度 | < 100 | > 500 |
| obs_5xx_error_rate | 5xx 错误率 | < 0.01% | > 1% |
| obs_throughput_mbps | 吞吐量 | > 2000MBps | < 500MBps |
| obs_iowait_percent | IO Wait | < 10% | > 30% |

### 关键日志模式

| 模式 | 级别 | 含义 |
|------|------|------|
| `OBS PUT request timeout` | ERROR | OBS 写请求超时，通常是后端异常 |
| `OBS GET request slow` | WARN | OBS 读请求慢，关注 latency_ms 字段 |
| `IO queue depth exceeded` | WARN | IO 积压，通常是后端时延升高导致 |
| `NFS READ/WRITE exceeded SLA` | ERROR | 前端请求违 SLA，用户可感知 |
| `connection pool exhausted` | WARN | 连接池耗尽，后端处理不过来 |
| `slow_disk_io` | WARN | OBS 慢盘警告 |
| `disk_smart_alert` | WARN | 磁盘硬件劣化预警 |
