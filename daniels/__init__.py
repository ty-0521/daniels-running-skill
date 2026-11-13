# -*- coding: utf-8 -*-
"""daniels —— 丹尼尔斯跑步训练法知识库。

公开接口按层组织：

* :mod:`daniels.vdot` —— VDOT 正反算、五档配速、FR/H、海拔修正
* :mod:`daniels.dose` —— 训练量上限与整周合规检查
* :mod:`daniels.periodize` —— 阶段划分、Q 日排布、赛前减量
* :mod:`daniels.dates` —— 比赛日 ↔ 周数 ↔ 起点（日期一律查，不许手算）
* :mod:`daniels.deload` —— 周期性减量（外推层，书中无此概念）
* :mod:`daniels.audit` —— 整张周表的统一裁决
* :mod:`daniels.intake` —— 接诊门禁：缺一层就不许出数
* :mod:`daniels.citations` —— 行号查询（禁止手写行号）
* :mod:`daniels.explain` —— 不带原文的解释词条
* :mod:`daniels.manifest` —— 对外清单：规则、词条、误差上界、不支持区域
"""

# 版本号必须在其他导入之前定义：manifest 会从这里取。
__version__ = "1.0.0"

from .dose import (  # noqa: F401
    INTENSITIES,
    RULES,
    VOLUME_SPLIT_KM,
    WEEKLY_VOLUME_SOFT_MAX_KM,
    DoseCap,
    RuleRef,
    Session,
    Violation,
    cap_for,
    check_week,
    interval_cap,
    long_run_cap,
    marathon_pace_cap,
    max_reps,
    post_race_easy_days,
    repetition_cap,
    threshold_cap,
    volume_step_km,
)
from .audit import (  # noqa: F401
    BASE_SOURCES,
    Finding,
    PlanAudit,
    WeekEntry,
    audit_plan,
    plan_from_dict,
)
from .citations import (  # noqa: F401
    RULE_AUDIT_LOG,
    Citation,
    audit_record,
    cite,
    citations,
    did_you_mean as citations_did_you_mean,
    search_citations,
)
from .dates import (  # noqa: F401
    PlanOption,
    feasible_plans,
    max_plan_weeks,
    plan_window,
    weeks_until,
)
from .deload import (  # noqa: F401
    DELOAD_PROVENANCE,
    CycleGain,
    DeloadImpact,
    DeloadRhythm,
    GrowthPath,
    ProgressionIssue,
    check_progression,
    deload_impact,
    deload_weeks,
    growth_path,
    t_peak_km,
)
from .explain import (  # noqa: F401
    TOPICS,
    Topic,
    did_you_mean as explain_did_you_mean,
    explain as explain_topic,
    search,
    topic_ids,
)
from .intake import (  # noqa: F401
    FIELD_BY_KEY,
    FIELD_SPECS,
    REQUIRED_KEYS,
    FieldSpec,
    IntakeState,
    Status,
    paces_from_intake,
)
from .periodize import (  # noqa: F401
    DOCUMENTED_SPLITS,
    MIN_WEEKS,
    PHASES,
    WEEK_DAYS,
    PhaseInfo,
    PhaseLengthError,
    PhasePlan,
    TaperRules,
    WeekTaper,
    phase_info,
    plan_schedule,
    q_intensities,
    quality_days,
    taper_rules,
    week_taper,
    weekly_volume_bounds,
)
from .vdot import (  # noqa: F401
    ALT_MAX_M,
    ALT_NEGLIGIBLE_M,
    ALT_REFERENCE_M,
    DISTANCE_MAX_M,
    DISTANCE_MIN_M,
    METER_PER_MILE,
    PROVENANCE,
    TABLE5_3,
    VDOT_MAX,
    VDOT_MIN,
    VDOT_NOVICE_UPPER,
    AltitudeCorrection,
    AltitudeRangeError,
    DanielsError,
    NoviceRow,
    Pace,
    PaceSet,
    VdotRangeError,
    altitude_correction,
    format_time,
    h_time_cap,
    pace_set,
    parse_time,
    pct_max,
    race_time,
    speed_of_vo2,
    vdot_from_race,
    vo2_of_speed,
)

from .manifest import (  # noqa: F401
    ERROR_BOUNDS,
    UNSUPPORTED,
    manifest,
)

__all__ = [
    # vdot 层
    "ALT_MAX_M",
    "ALT_NEGLIGIBLE_M",
    "ALT_REFERENCE_M",
    "DISTANCE_MAX_M",
    "DISTANCE_MIN_M",
    "METER_PER_MILE",
    "PROVENANCE",
    "TABLE5_3",
    "VDOT_MAX",
    "VDOT_MIN",
    "VDOT_NOVICE_UPPER",
    "AltitudeCorrection",
    "AltitudeRangeError",
    "DanielsError",
    "NoviceRow",
    "Pace",
    "PaceSet",
    "VdotRangeError",
    "altitude_correction",
    "format_time",
    "h_time_cap",
    "pace_set",
    "parse_time",
    "pct_max",
    "race_time",
    "speed_of_vo2",
    "vdot_from_race",
    "vo2_of_speed",
    # dose 层
    "INTENSITIES",
    "RULES",
    "VOLUME_SPLIT_KM",
    "WEEKLY_VOLUME_SOFT_MAX_KM",
    "DoseCap",
    "RuleRef",
    "Session",
    "Violation",
    "cap_for",
    "check_week",
    "interval_cap",
    "long_run_cap",
    "marathon_pace_cap",
    "max_reps",
    "post_race_easy_days",
    "repetition_cap",
    "threshold_cap",
    "volume_step_km",
    # periodize 层
    "DOCUMENTED_SPLITS",
    "MIN_WEEKS",
    "PHASES",
    "WEEK_DAYS",
    "PhaseInfo",
    "PhaseLengthError",
    "PhasePlan",
    "TaperRules",
    "WeekTaper",
    "phase_info",
    "plan_schedule",
    "q_intensities",
    "quality_days",
    "taper_rules",
    "week_taper",
    "weekly_volume_bounds",
    # dates 层
    "PlanOption",
    "feasible_plans",
    "max_plan_weeks",
    "plan_window",
    "weeks_until",
    # deload 层
    "DELOAD_PROVENANCE",
    "CycleGain",
    "DeloadImpact",
    "DeloadRhythm",
    "GrowthPath",
    "ProgressionIssue",
    "check_progression",
    "deload_impact",
    "deload_weeks",
    "growth_path",
    "t_peak_km",
    # audit 层
    "BASE_SOURCES",
    "Finding",
    "PlanAudit",
    "WeekEntry",
    "audit_plan",
    "plan_from_dict",
    # citations 层
    "RULE_AUDIT_LOG",
    "Citation",
    "audit_record",
    "cite",
    "citations",
    "citations_did_you_mean",
    "search_citations",
    # intake 层
    "FIELD_BY_KEY",
    "FIELD_SPECS",
    "REQUIRED_KEYS",
    "FieldSpec",
    "IntakeState",
    "Status",
    "paces_from_intake",
    # explain 层
    "TOPICS",
    "Topic",
    "explain_did_you_mean",
    "explain_topic",
    "search",
    "topic_ids",
    # manifest 层
    "ERROR_BOUNDS",
    "UNSUPPORTED",
    "manifest",
    # 包级
    "__version__",
]
