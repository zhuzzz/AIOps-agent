# efs-ecs-cpu-001 录制响应清单

一 case 一文件夹、纯文件、零数据库。匹配键由 `harness/tool_proxy.py:build_key` 生成。
指标类工具按 `cmc__{name_space}__{metric}.json` 细分，一文件含全部实例、按 instance_id 过滤。

| 文件 | 来源 | 取值 | 角色 |
|---|---|---|---|
| `cma__current_alarms.json` | Step0 | avg_write_latency=1001.899(≥500) | 告警，定 diagnosis_threshold=500.95 |
| `smarttopo__topology.json` | Step1 | nas/mds/space/ecs×2/evs | 拓扑，给出 ecs-02 |
| `cmc__SRE.EFS__d_nas_read3QOS.json` | Step2 | nas-01=0 | 正常（QOS 不限流） |
| `cmc__SRE.EFS__d_nas_write3QOS.json` | Step2 | nas-01=0 | 正常 |
| `cmc__SRE.EFS__d_nas_read3NT.json` | Step2 | nas-01=12ms | 正常（<阈值） |
| `cmc__SRE.EFS__d_space_spRead.json` | Step3 | space-01=8ms | 正常 |
| `cmc__SRE.EFS__avg_metaread_latency.json` | Step4 | mds-01=6ms | 正常 |
| `cmc__SRE.EFS__d_mds_process_survival_time.json` | Step4 | mds-01=99999 | 正常（进程存活） |
| `cmc__SRE.EFS__read_latency.json` | Step6 | nas-01=40ms | 正常（OBS 短路） |
| **`cmc__SYS.ECS__cpu_util.json`** | Step8 | ecs-01=35, **ecs-02=92** | **决定性证据（唯一越界）** |
| `evs__disk_await.json` | Step7(脚本面) | evs-01 read=4/write=5ms | 正常（<10ms） |

> 真实落地时：**只有"决定性的那一个响应"需要手工设为越界**（此处 ecs-02=92），
> 其余 ~10 个正常响应建议直接从一次真实 run 的 `/tmp/relay_mcp_responses/` 抓取。
> 完整 skill 在 Step2/4/6 还会查更多指标，本 worked example 取每层的判别性指标即可跑通主链路。
