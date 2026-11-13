# -*- coding: utf-8 -*-
"""对外清单：把三层的内容、误差上界与支持边界导成一份可序列化数据。

这份清单的用途是让接入方（agent、CLI、Web API）不必读源码就知道：

* 有哪些规则、哪些词条；
* 每个数值的可信度到什么程度；
* 哪些区域明确不支持，遇到时应当拒绝而不是外推。
"""

from __future__ import annotations

from typing import Dict, List, Tuple

from . import __version__
from .citations import audit_record
from .deload import DELOAD_PROVENANCE
from .dose import (
    RULES,
    VOLUME_SPLIT_KM,
    WEEKLY_VOLUME_SOFT_MAX_KM,
)
from .explain import TOPICS
from .periodize import DOCUMENTED_SPLITS, PHASES
from .vdot import (
    ALT_MAX_M,
    ALT_NEGLIGIBLE_M,
    ALT_REFERENCE_M,
    VDOT_MAX,
    VDOT_MIN,
    VDOT_NOVICE_UPPER,
)

__all__ = [
    "ERROR_BOUNDS",
    "UNSUPPORTED",
    "manifest",
]

#: 每个可验证数值的实测误差上界。数字来自 ``pace_audit.py`` 与测试套件。
ERROR_BOUNDS: Tuple[Dict[str, object], ...] = (
    {
        "metric": "VDOT 正反算",
        "max_error": "0.21 个 VDOT",
        "basis": "附录 D 四个分界值（1600 m 4:40 / 5:20 / 5:21 / 6:12）",
    },
    {
        "metric": "M 配速",
        "max_error": "0.14%",
        "basis": "表 5—2，VDOT 51 一行",
    },
    {
        "metric": "T 配速",
        "max_error": "0.72%",
        "basis": "表 5—2 与表 5—3 共 13 个点",
    },
    {
        "metric": "I 配速（VDOT ≥ 30）",
        "max_error": "0.45%",
        "basis": "表 5—2 的 VDOT 51 与 60",
    },
    {
        "metric": "I 配速（VDOT < 30）",
        "max_error": "3.5%",
        "basis": "表 5—3 的 11 行",
        "note": (
            "不是公式误差：表 5—3 的 I 列按 R 加 7~8 秒/400 m 排，"
            "与 98% vVO2max 的定义本身不一致。"
            "需要照书执行时用 PaceSet.novice_row"
        ),
    },
    {
        "metric": "R 配速",
        "max_error": "1.43%",
        "basis": "表 5—2 与表 5—3",
        "note": "书中表格按整秒印刷，1 秒的量化误差已占去大半",
    },
    {
        "metric": "E 配速区间",
        "max_error": "1.23%",
        "basis": "表 5—2，VDOT 51 一行的快慢两端",
    },
    {
        "metric": "训练量上限",
        "max_error": "0（按公式精确）",
        "basis": "书中的百分比与封顶值",
        "note": "误差只可能来自书中算例本身（已发现一例笔误）",
    },
)

#: 明确不支持的输入区域。遇到这些必须拒绝或标注，不得外推。
UNSUPPORTED: Tuple[Dict[str, str], ...] = (
    {
        "area": f"VDOT 低于 {VDOT_MIN:.0f} 或高于 {VDOT_MAX:.0f}",
        "reason": "书中表 5—3 收 20~30，表 5—1/5—2 收 30~85，之外无数据",
        "behavior": "抛 VdotRangeError",
    },
    {
        "area": "年龄与性别调整",
        "reason": "表 5—7 与表 5—8 是图片，无可用真值可校",
        "behavior": "不实现；需要时由使用者自行处理",
    },
    {
        "area": "跑步机坡度—速度换算表",
        "reason": "表 4—5/4—6 只有 1 个可读锚点，不足以还原",
        "behavior": "只保留「跑步机坡度加 2% 补风阻」这一条定性规则",
    },
    {
        "area": "训练计划表的逐字课目",
        "reason": "表 7—1 至 14—9 全部是位图，OCR 只能取到骨架",
        "behavior": "按规则生成课目，并说明与书本印刷表不是逐字一致",
    },
    {
        "area": f"海拔高于 {ALT_MAX_M:.0f} m",
        "reason": "书中讨论范围是 1200~2500 m",
        "behavior": "抛 AltitudeRangeError",
    },
    {
        "area": "书中未记录的训练季长度",
        "reason": f"只记录了 {sorted(DOCUMENTED_SPLITS)} 这几种周数",
        "behavior": "抛 PhaseLengthError；需显式开启推导才会返回",
    },
    {
        "area": "周期性减量（每 N 周减量 X%）",
        "reason": "书中没有这个概念；全书的减量只有赛前减量与赛后恢复两类",
        "behavior": (
            "daniels.deload 只给算术（哪几周减、各强度上限变多少、"
            "加到目标跑量要多少周、周表有没有违规），不生成周表；"
            "回答里引用之前必须先说明这是外推，不是书中规则"
        ),
    },
    {
        "area": "带伤、术后、孕期或心血管问题下的训练安排",
        "reason": "这不是训练量问题，是医疗问题",
        "behavior": (
            "intake 一旦收到红线就返回 stopped，退出码 2，"
            "不给任何跑量、配速或替代训练建议"
        ),
    },
    {
        "area": "手写行号",
        "reason": (
            "十轮实测里行号引错 3 次，且每次结论都对、只有出处错，"
            "读者核不到"
        ),
        "behavior": (
            "行号一律走 daniels.citations.cite() / search_citations()；"
            "32 条规则已逐条回原文核过，核对记录见 citation_audit"
        ),
    },
)


def manifest() -> Dict[str, object]:
    """导出完整清单。

    Returns
    -------
    dict
        可直接 ``json.dumps`` 的结构。
    """
    return {
        "name": "daniels-running-skill",
        "version": __version__,
        "description": (
            "《丹尼尔斯经典跑步训练法（第3版）》的可验证知识库："
            "数值层给配速与上限，规则层给周期与合规检查，"
            "叙述层给不带原文的解释"
        ),
        "layers": {
            "vdot": [
                "vdot_from_race",
                "race_time",
                "pace_set",
                "h_time_cap",
                "altitude_correction",
            ],
            "dose": [
                "long_run_cap",
                "marathon_pace_cap",
                "threshold_cap",
                "interval_cap",
                "repetition_cap",
                "check_week",
                "post_race_easy_days",
                "volume_step_km",
            ],
            "periodize": [
                "plan_schedule",
                "phase_info",
                "quality_days",
                "q_intensities",
                "taper_rules",
                "week_taper",
                "weekly_volume_bounds",
            ],
            "dates": [
                "weeks_until",
                "max_plan_weeks",
                "plan_window",
                "feasible_plans",
            ],
            "deload": [
                "deload_impact",
                "deload_weeks",
                "growth_path",
                "t_peak_km",
                "check_progression",
            ],
            "audit": ["audit_plan", "plan_from_dict"],
            "intake": ["IntakeState", "paces_from_intake"],
            "citations": ["cite", "search_citations", "citations"],
            "explain": ["explain_topic", "search", "topic_ids"],
        },
        "constants": {
            "vdot_range": [VDOT_MIN, VDOT_MAX],
            "vdot_novice_upper": VDOT_NOVICE_UPPER,
            "volume_split_km": VOLUME_SPLIT_KM,
            "weekly_volume_soft_max_km": WEEKLY_VOLUME_SOFT_MAX_KM,
            "altitude": {
                "negligible_below": ALT_NEGLIGIBLE_M,
                "reference": ALT_REFERENCE_M,
                "max": ALT_MAX_M,
            },
            "documented_plan_lengths": sorted(DOCUMENTED_SPLITS),
        },
        "error_bounds": [dict(item) for item in ERROR_BOUNDS],
        "unsupported": [dict(item) for item in UNSUPPORTED],
        "deload_provenance": dict(DELOAD_PROVENANCE),
        "citation_audit": audit_record(),
        "rules": [
            {
                "rule_id": rule.rule_id,
                "chapter": rule.chapter,
                "lines": rule.lines,
                "summary": rule.summary,
            }
            for rule in sorted(RULES.values(), key=lambda r: r.rule_id)
        ],
        "topics": [
            {
                "topic_id": topic.topic_id,
                "question": topic.question,
                "sources": list(topic.sources),
            }
            for topic in sorted(TOPICS.values(), key=lambda t: t.topic_id)
        ],
        "phases": [phase.as_dict() for phase in PHASES],
    }


def _self_check() -> List[str]:
    """确保清单里的每个引用都真实存在。返回问题列表，空表示正常。"""
    problems: List[str] = []
    import daniels

    for layer, names in manifest()["layers"].items():  # type: ignore[union-attr]
        for name in names:
            if not hasattr(daniels, name):
                problems.append(f"层 {layer} 引用了不存在的函数 {name}")
    return problems
