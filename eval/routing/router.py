"""一个最小但真实的关键词/资源类型路由器。

打分逻辑：把告警文本（含 resource_type）与各 skill profile 的 keywords/resource_types
做大小写不敏感子串匹配计分，取 top-1；若最高分低于阈值则**拒识**（返回 None），
用来暴露"过度自信误路由"。生产可换成向量召回 + LLM 仲裁，评分器与 case 不变。
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class SkillProfile:
    name: str
    keywords: list[str] = field(default_factory=list)
    resource_types: list[str] = field(default_factory=list)


# efs-diagnosis 的 profile 直接取自 skill frontmatter（keywords / resource_types）
EFS_DIAGNOSIS = SkillProfile(
    name="efs-diagnosis",
    keywords=[
        "EFS", "SFS Turbo", "IO异常", "读写时延", "IO告警",
        "QOS", "mds", "space", "OBS联动", "efs_io_latency",
    ],
    resource_types=["efs::sfs-turbo"],
)

# 一个诱饵 skill，用于检验"竞争"与"误路由"
DB_DIAGNOSIS = SkillProfile(
    name="db-diagnosis",
    keywords=["RDS", "MySQL", "慢查询", "SQL", "数据库", "连接数"],
    resource_types=["rds::mysql"],
)

DEFAULT_REGISTRY = [EFS_DIAGNOSIS, DB_DIAGNOSIS]


@dataclass
class RouteDecision:
    skill: str | None
    score: float
    ranking: list[tuple[str, float]]


def _score(text: str, resource_type: str, profile: SkillProfile) -> float:
    t = text.lower()
    hits = sum(1 for kw in profile.keywords if kw.lower() in t)
    if resource_type and any(
        rt.lower() in resource_type.lower() for rt in profile.resource_types
    ):
        hits += 2  # 资源类型命中权重更高
    return float(hits)


def route(
    alarm_text: str,
    resource_type: str = "",
    registry: list[SkillProfile] | None = None,
    threshold: float = 1.0,
) -> RouteDecision:
    """返回路由决策；低于阈值则拒识（skill=None）。"""
    reg = registry or DEFAULT_REGISTRY
    ranking = sorted(
        ((p.name, _score(alarm_text, resource_type, p)) for p in reg),
        key=lambda x: x[1],
        reverse=True,
    )
    top_skill, top_score = ranking[0]
    if top_score < threshold:
        return RouteDecision(skill=None, score=top_score, ranking=ranking)
    return RouteDecision(skill=top_skill, score=top_score, ranking=ranking)
