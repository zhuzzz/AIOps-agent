"""路由层评测：评"告警是否被路由到正确的 skill"。

诊断对不对是一回事，选没选对 skill 是另一回事。路由层 ground truth 比诊断根因好标
（可从 skill 的 keywords / resource_types / hypotheses 半自动反查，SRE 仅在边界盖章），
且不依赖诊断回放，适合先行起步。
"""
