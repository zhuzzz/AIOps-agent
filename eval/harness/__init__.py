"""efs-diagnosis 评测内核（harness）。

模块划分：
- trace:        轨迹数据模型（ToolCall / Trace）
- tool_proxy:   MCP 工具录制-回放层，同时充当轨迹记录器（拦截面 1）
- script_proxy: 脚本 / metrics_url 录制-回放层（拦截面 2，tool-proxy 拦不到的那部分）
- graders:      三层评分器（grade_rules / grade_trajectory / grade_outcome）
- report:       结果×轨迹四象限分类（GREEN/YELLOW/BLUE/RED）+ 分层归因
- runner:       装载 case → 跑 agent → 评分 → 出报告
"""
