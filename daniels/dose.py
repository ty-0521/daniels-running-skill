# -*- coding: utf-8 -*-
"""丹尼尔斯训练量上限（剂量层）。

这一层只回答一个问题：**这次训练最多能练多少。**

不含配速（那是 :mod:`daniels.vdot`），不含周期安排（那是 periodize 层）。

设计原则
--------
1. 每条规则都有 ``rule_id``、章号、原文行号，出错时能指回去。
2. 书里有多种说法的地方，**不调和、不取平均**：默认取更保守的一侧，
   并在 ``DoseCap.notes`` 里写清楚另一侧是什么、在哪一行。
3. 百分比是**单次训练**的上限，不是周目标（第 12 章 L3156 明确强调）。

书里给出的算例（全部用作测试的真值）
------------------------------------
* 周跑量 48 km → I 上限 3.84 km（第 12 章 L3152）
* 周跑量 97 km → I 上限 7.76 km。书中印的是 7.68，
  但 97 的 8% 是 7.76，而 7.68 恰好是 96 的 8%——判为书中笔误，按规则实现。
* 周跑量 48 km → R 上限 2.40 km（第 4 章 L1583）
* 周跑量 190 km → R 上限 8.00 km，而非 9.50 km（第 4 章 L1583）
* 周跑量 80 km、5 km 18:45 → H 上限 24 分钟（第 13 章 L3318）
* 每周跑 5 次 → 周跑量最多加 8 km；每天两跑 14 次 → 最多加 16 km（第 11 章 L2956）
* 赛后轻松日：10 km→3、15 km→5、半马→7、全马→14（第 14 章 L3482）
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, Sequence, Tuple

from .vdot import Pace, PaceSet

__all__ = [
    "RuleRef",
    "RULES",
    "DoseCap",
    "Session",
    "Violation",
    "long_run_cap",
    "marathon_pace_cap",
    "threshold_cap",
    "interval_cap",
    "repetition_cap",
    "cap_for",
    "max_reps",
    "post_race_easy_days",
    "volume_step_km",
    "check_week",
    "INTENSITIES",
]

#: 支持的高质量训练档位。
INTENSITIES: Tuple[str, ...] = ("L", "M", "T", "I", "R")

#: 周跑量分段点：书中以 64 km 为界切换 L 与 M 的百分比（第 4 章 L1363、第 14 章 L3480）。
VOLUME_SPLIT_KM = 64.0
#: 单次定速跑的时间上限（第 4 章 L1345）。
STEADY_RUN_MAX_MINUTES = 150.0
#: 周跑量建议上限，除非已习惯或正在备马（第 13 章 L3278）。
WEEKLY_VOLUME_SOFT_MAX_KM = 129.0


# ---------------------------------------------------------------------------
# 规则注册表
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class RuleRef:
    """一条规则的出处与摘要。

    ``summary`` 是对规则的改写说明，不是原文引用——书里的句子不进仓库。
    """

    rule_id: str
    chapter: str
    lines: str
    summary: str


RULES: Dict[str, RuleRef] = {
    "D-L-01": RuleRef(
        "D-L-01", "第4章", "L1363",
        "周跑量少于 64 km 时，单次 L 跑不超过周跑量的 30%",
    ),
    "D-L-02": RuleRef(
        "D-L-02", "第4章", "L1363",
        "周跑量达 64 km 及以上时，单次 L 跑取「周跑量 25%」与「150 分钟」的较小值",
    ),
    "D-L-03": RuleRef(
        "D-L-03", "第4章", "L1345",
        "任何单次定速跑不超过 150 分钟，备战马拉松亦然",
    ),
    "D-L-04": RuleRef(
        "D-L-04", "第6章", "L2016",
        "阶段一每周的轻松 L 跑占周跑量的 25%~30%",
    ),
    "D-L-05": RuleRef(
        "D-L-05", "第12章", "L3160",
        "越野跑阶段一：单次 L 跑取「周跑量 30%」与「60 分钟」的较小值",
    ),
    "D-L-06": RuleRef(
        "D-L-06", "第12章", "L3188",
        "越野跑阶段二：单次 L 跑控制在周跑量的 25% 以内",
    ),
    "D-L-07": RuleRef(
        "D-L-07", "第13章", "L3276",
        "半程马拉松阶段一：单次 L 跑取「周跑量 25%」与「150 分钟」的较小值",
    ),
    "D-L-08": RuleRef(
        "D-L-08", "第12章", "L3160",
        "任何单日跑量不超过周跑量的 25%",
    ),
    "D-M-01": RuleRef(
        "D-M-01", "第4章", "L1392",
        "单次 M 配速跑取「110 分钟」与「29 km」的较小值",
    ),
    "D-M-02": RuleRef(
        "D-M-02", "第4章", "L1392",
        "单次 M 配速跑的累计量取「周跑量 20%」与「29 km」的较小值",
    ),
    "D-M-03": RuleRef(
        "D-M-03", "第14章", "L3480",
        "周跑量少于 64 km 时，单次 M 配速跑不超过周跑量的 30%",
    ),
    "D-T-01": RuleRef(
        "D-T-01", "第4章", "L1429",
        "单次训练中 T 配速的累计距离不超过周跑量的 10%",
    ),
    "D-T-02": RuleRef(
        "D-T-02", "第14章", "L3478",
        "单次 T 训练取「周跑量 10%」与「24 km」的较小值，且每次至少跑 4.8 km",
    ),
    "D-T-03": RuleRef(
        "D-T-03", "第4章", "L1449",
        "定速节奏跑单次要控制在约 20 分钟以内",
    ),
    "D-T-04": RuleRef(
        "D-T-04", "第4章", "L1429",
        "若把 T 拆成巡航间歇，累计的 T 配速时间应至少 30 分钟",
    ),
    "D-T-05": RuleRef(
        "D-T-05", "第4章", "L1451",
        "巡航间歇的训练与恢复时间比约为 5:1",
    ),
    "D-I-01": RuleRef(
        "D-I-01", "第4章", "L1528",
        "单次 I 配速的累计距离取「周跑量 8%」与「10 km」的较小值",
    ),
    "D-I-02": RuleRef(
        "D-I-02", "第4章", "L1480",
        "单个 I 配速回合持续 3~5 分钟；5 分钟在 VDOT 51 时对应约 1200 m（第5章 L1784）",
    ),
    "D-I-03": RuleRef(
        "D-I-03", "第11章", "L2980",
        "每周两次 I 训练已经足够",
    ),
    "D-I-04": RuleRef(
        "D-I-04", "第4章", "L1530",
        "换算时把 5 分钟 H 跑计为 1.6 km",
    ),
    "D-I-05": RuleRef(
        "D-I-05", "第13章", "L3318",
        "H 跑单次总时间取「10 km 用时」与「按 5 km 配速跑完周跑量 8% 所需时间」的较小值",
    ),
    "D-R-01": RuleRef(
        "D-R-01", "第4章", "L1583",
        "单次 R 配速的累计距离取「周跑量 5%」与「8 km」的较小值",
    ),
    "D-R-02": RuleRef(
        "D-R-02", "第5章", "L1786",
        "单个 R 配速回合不超过 2 分钟",
    ),
    "D-R-03": RuleRef(
        "D-R-03", "第4章", "L1581",
        "R 跑的恢复时间是快速跑用时的 2~3 倍，或慢跑同等距离",
    ),
    "D-G-01": RuleRef(
        "D-G-01", "第12章", "L3156",
        "上述百分比是单次训练的上限，不是每周应当达到的目标",
    ),
    "D-G-02": RuleRef(
        "D-G-02", "第2章", "L934",
        "提高训练压力前，先把当前压力维持 4~6 周",
    ),
    "D-G-03": RuleRef(
        "D-G-03", "第11章", "L2956",
        "每 3~4 周把每次跑的里程加 1.6 km，周增量按出勤次数折算并封顶 16 km",
    ),
    "D-G-04": RuleRef(
        "D-G-04", "第13章", "L3278",
        "周跑量不必超过 129 km，除非已习惯该跑量或正在备战马拉松",
    ),
    "D-G-05": RuleRef(
        "D-G-05", "第9章", "L2605",
        "提高训练配速（更新 VDOT）的频率不高于每 3 周一次",
    ),
    "D-G-06": RuleRef(
        "D-G-06", "第14章", "L3482",
        "比赛后按距离安排轻松日，每约 3 km 一个",
    ),
    "D-G-07": RuleRef(
        "D-G-07", "第13章", "L3342",
        "比赛前安排 2~3 个轻松日",
    ),
    "D-G-08": RuleRef(
        "D-G-08", "第14章", "L3398",
        "周跑量定在最高周跑量 P 的 80%~100% 之间",
    ),
}


# ---------------------------------------------------------------------------
# 结果对象
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class DoseCap:
    """一次训练的量上限。

    ``max_km`` 与 ``max_minutes`` 可以同时存在；真正生效的是两者中先到达的那个，
    需要用具体配速换算，见 :meth:`limit_km`。
    """

    intensity: str
    max_km: float | None
    max_minutes: float | None
    rules: Tuple[RuleRef, ...]
    notes: Tuple[str, ...] = ()
    #: 单个回合的时间上限（分钟）。I 为 5，R 为 2，其余为空。
    single_rep_max_minutes: float | None = None
    #: 单次训练的下限（距离，公里）。目前只有 T 的 4.8 km。
    min_km: float | None = None
    #: 拆分为巡航间歇时的累计时间下限（分钟）。
    min_minutes_when_split: float | None = None
    #: 实际套用的周跑量百分比。同一强度在不同周跑量下可能换档
    #: （M 在 64 km 以下是 30%，以上是 20%），把实际档位带出来，
    #: 免得回答时凭记忆引一个错的百分比。
    ratio: float | None = None

    @property
    def window_km(self) -> float | None:
        """上下限之间的可用宽度（公里）。

        只有同时存在上下限时才有意义。例如 T 在周跑量 64 km 时上限 6.4、
        下限 4.8，可用宽度只有 1.6 km——排课时要留神别掉出这个窗口。
        """
        if self.max_km is None or self.min_km is None:
            return None
        return max(0.0, self.max_km - self.min_km)

    @property
    def feasible(self) -> bool:
        """上下限是否有交集。

        书里两处规则在某些周跑量下会打架：T 的单次上限是周跑量 10%
        （第 4 章 L1429），单次下限是 4.8 km（第 14 章 L3478）。
        周跑量低于 48 km 时，10% 会小于 4.8，这个强度就没有可行区间了。
        """
        if self.max_km is None or self.min_km is None:
            return True
        return self.min_km <= self.max_km + 1e-9

    def limit_km(self, pace: Pace) -> float:
        """按给定配速换算出真正生效的距离上限（公里）。

        Parameters
        ----------
        pace : Pace
            该强度的配速，用来把分钟上限折算成距离。

        Returns
        -------
        float
            生效的距离上限。若两个上限都没有，返回 ``inf``。
        """
        candidates = []
        if self.max_km is not None:
            candidates.append(self.max_km)
        if self.max_minutes is not None:
            candidates.append(pace.distance_in(self.max_minutes * 60.0) / 1000.0)
        return min(candidates) if candidates else math.inf

    def binding(self, pace: Pace) -> str:
        """指出当前配速下是哪个上限先触发。

        Returns
        -------
        str
            ``"km"``、``"minutes"``、``"equal"`` 或 ``"none"``。
        """
        if self.max_km is None and self.max_minutes is None:
            return "none"
        if self.max_km is None:
            return "minutes"
        if self.max_minutes is None:
            return "km"
        by_time = pace.distance_in(self.max_minutes * 60.0) / 1000.0
        if abs(by_time - self.max_km) < 1e-9:
            return "equal"
        return "minutes" if by_time < self.max_km else "km"

    def as_dict(self, pace: Pace | None = None) -> Dict[str, object]:
        """导出为可序列化字典。给了配速就同时给出折算后的生效值。"""
        out: Dict[str, object] = {
            "intensity": self.intensity,
            "max_km": None if self.max_km is None else round(self.max_km, 2),
            "max_minutes": (
                None if self.max_minutes is None else round(self.max_minutes, 1)
            ),
            "rule_ids": [r.rule_id for r in self.rules],
            "notes": list(self.notes),
        }
        if self.single_rep_max_minutes is not None:
            out["single_rep_max_minutes"] = self.single_rep_max_minutes
        if self.min_km is not None:
            out["min_km"] = self.min_km
        if self.min_minutes_when_split is not None:
            out["min_minutes_when_split"] = self.min_minutes_when_split
        out["feasible"] = self.feasible
        if self.ratio is not None:
            out["ratio_pct"] = round(self.ratio * 100.0, 1)
        if self.window_km is not None:
            out["window_km"] = round(self.window_km, 2)
        if not self.feasible:
            out["infeasible_reason"] = (
                f"上限 {self.max_km:.2f} km 低于下限 {self.min_km:.2f} km："
                "书里两条规则在这个周跑量下没有交集"
            )
        if pace is not None:
            out["effective_km"] = round(self.limit_km(pace), 2)
            out["binding"] = self.binding(pace)
        return out


@dataclass(frozen=True)
class Session:
    """一周里的一次训练。"""

    intensity: str
    km: float

    def __post_init__(self) -> None:
        if self.intensity not in INTENSITIES:
            raise ValueError(
                f"未知强度 {self.intensity!r}，可选 {INTENSITIES}"
            )
        if not self.km > 0:
            raise ValueError(f"距离必须为正数，收到 {self.km!r}")


@dataclass(frozen=True)
class Violation:
    """一条超限记录。"""

    rule_ids: Tuple[str, ...]
    intensity: str
    session_index: int | None
    actual: float
    limit: float
    unit: str
    message: str

    def as_dict(self) -> Dict[str, object]:
        return {
            "rule_ids": list(self.rule_ids),
            "intensity": self.intensity,
            "session_index": self.session_index,
            "actual": round(self.actual, 2),
            "limit": round(self.limit, 2),
            "unit": self.unit,
            "message": self.message,
        }


# ---------------------------------------------------------------------------
# 各档上限
# ---------------------------------------------------------------------------
def _require_positive(name: str, value: float) -> None:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ValueError(f"{name} 必须是数字，收到 {type(value).__name__}")
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"{name} 必须是正的有限数，收到 {value!r}")


def long_run_cap(
    weekly_km: float,
    *,
    surface: str = "road",
    phase: int | None = None,
) -> DoseCap:
    """L（长距离）跑的单次上限。

    Parameters
    ----------
    weekly_km : float
        当前周跑量，公里。
    surface : str, optional
        ``"road"``（默认）或 ``"trail"``。越野跑另有一套更保守的上限。
    phase : int, optional
        训练阶段 1~4。越野跑的阶段一会把时间上限压到 60 分钟。

    Returns
    -------
    DoseCap

    Notes
    -----
    书中有五处说法，互相不完全一致，本函数按场景分派而不是取平均：

    ============  ==========================  ================
    场景            距离上限                     时间上限
    ============  ==========================  ================
    公路 <64 km     周跑量 30%                  150 分钟
    公路 >=64 km    周跑量 25%                  150 分钟
    越野 阶段一     周跑量 30%                  60 分钟
    越野 阶段二     周跑量 25%                  150 分钟
    ============  ==========================  ================

    150 分钟的时间上限出自第 4 章 L1345，与百分比规则并行生效。
    """
    _require_positive("weekly_km", weekly_km)
    rules: list[RuleRef] = []
    notes: list[str] = []

    if surface not in ("road", "trail"):
        raise ValueError(f"surface 只能是 road 或 trail，收到 {surface!r}")
    if phase is not None and phase not in (1, 2, 3, 4):
        raise ValueError(f"phase 只能是 1~4，收到 {phase!r}")

    if surface == "trail":
        if phase == 1:
            max_km = weekly_km * 0.30
            ratio = 0.30
            max_minutes = 60.0
            rules.extend([RULES["D-L-05"], RULES["D-L-04"]])
            notes.append(
                "越野跑阶段一把 L 跑压在 60 分钟内（第12章 L3160），"
                "比公路的 150 分钟保守得多"
            )
        else:
            max_km = weekly_km * 0.25
            ratio = 0.25
            max_minutes = STEADY_RUN_MAX_MINUTES
            rules.extend([RULES["D-L-06"], RULES["D-L-03"]])
            if phase is not None and phase != 2:
                notes.append("越野跑阶段二及以上沿用 L ≤ 周跑量 25%（第12章 L3188）")
    else:
        if weekly_km < VOLUME_SPLIT_KM:
            max_km = weekly_km * 0.30
            ratio = 0.30
            rules.append(RULES["D-L-01"])
        else:
            max_km = weekly_km * 0.25
            ratio = 0.25
            rules.append(RULES["D-L-02"])
            notes.append(
                "周跑量达到 64 km 后百分比从 30% 降到 25%"
                "（第4章 L1363；第14章 L3484 同）"
            )
        max_minutes = STEADY_RUN_MAX_MINUTES
        rules.append(RULES["D-L-03"])
        if phase == 1:
            rules.append(RULES["D-L-04"])
        notes.append(
            "L 上限不是单调的：周跑量 63.9 km 时是 19.17 km，"
            "64 km 时反而掉到 16.00 km——百分比在 64 km 处从 30% 换成 25%。"
            "这是第4章 L1363 的原规则，不是实现问题；"
            "把峰值定在 64 km 之前要先算一下 L 会缩多少"
        )

    notes.append(
        "半程马拉松阶段一的说法是「25% 与 150 分钟取小」（第13章 L3276），"
        "与公路版一致，未单独分支"
    )
    return DoseCap(
        intensity="L",
        max_km=max_km,
        max_minutes=max_minutes,
        rules=tuple(rules),
        notes=tuple(notes),
        ratio=ratio,
    )


def marathon_pace_cap(weekly_km: float) -> DoseCap:
    """M（马拉松配速）跑的单次上限。

    Notes
    -----
    同时存在三个约束：110 分钟、29 km、周跑量百分比。
    百分比在 64 km 处分档：低于 64 km 用 30%，否则用 20%（第14章 L3480）。
    """
    _require_positive("weekly_km", weekly_km)
    ratio = 0.30 if weekly_km < VOLUME_SPLIT_KM else 0.20
    rules = [RULES["D-M-02"], RULES["D-M-01"]]
    notes = []
    if weekly_km < VOLUME_SPLIT_KM:
        rules.append(RULES["D-M-03"])
        notes.append(
            "周跑量低于 64 km 时，M 的百分比放宽到 30%（第14章 L3480）"
        )
    return DoseCap(
        intensity="M",
        max_km=min(29.0, weekly_km * ratio),
        max_minutes=110.0,
        rules=tuple(rules),
        notes=tuple(notes),
        ratio=ratio,
    )


def threshold_cap(weekly_km: float) -> DoseCap:
    """T（乳酸门槛）跑的单次上限。

    Notes
    -----
    * 距离：取周跑量 10% 与 24 km 的较小值，且单次不少于 4.8 km。
    * 时间：定速节奏跑控制在 20 分钟左右；若拆成巡航间歇，
      累计时间应至少 30 分钟（第4章 L1429、L1449）。
    """
    _require_positive("weekly_km", weekly_km)
    return DoseCap(
        intensity="T",
        max_km=min(weekly_km * 0.10, 24.0),
        max_minutes=None,
        rules=(RULES["D-T-01"], RULES["D-T-02"]),
        notes=(
            "定速节奏跑约 20 分钟封顶（D-T-03，第4章 L1449）；"
            "拆成巡航间歇时累计至少 30 分钟，训练与恢复时间比约 5:1"
            "（D-T-04、D-T-05，第4章 L1429/L1451）",
            "单次 T 训练的下限是 4.8 km（第14章 L3478）",
            "周跑量低于 48 km 时，10% 的上限会低于 4.8 km 的下限，"
            "该强度无可行区间——这是书里两条规则本身的冲突，不是实现问题",
        ),
        min_km=4.8,
        ratio=0.10,
        min_minutes_when_split=30.0,
    )


def interval_cap(weekly_km: float) -> DoseCap:
    """I（间歇）跑的单次上限。

    Notes
    -----
    * 距离：取周跑量 8% 与 10 km 的较小值（第4章 L1528）。
    * 单个回合不超过 5 分钟，因此最长 1200 m（第5章 L1784、第12章 L3206）。
    * 每周两次 I 训练已足够（第11章 L2978）。
    """
    _require_positive("weekly_km", weekly_km)
    notes = [
        "单回合不超过 5 分钟，因此最长 1200 m（D-I-02，第5章 L1784）",
        "每周两次 I 训练已足够，第三次的收益低于风险"
        "（D-I-03，第11章 L2978），由 check_week 单独判定",
    ]
    if weekly_km > 120.0:
        notes.append(
            "周跑量超过 120 km 时，10 km 这一侧会先触发，"
            "约合 30 分钟（D-I-04，第4章 L1530）"
        )
    return DoseCap(
        intensity="I",
        max_km=min(weekly_km * 0.08, 10.0),
        max_minutes=None,
        rules=(RULES["D-I-01"], RULES["D-I-02"]),
        notes=tuple(notes),
        single_rep_max_minutes=5.0,
        ratio=0.08,
    )


def repetition_cap(weekly_km: float) -> DoseCap:
    """R（重复）跑的单次上限。

    Notes
    -----
    * 距离：取周跑量 5% 与 8 km 的较小值（第4章 L1583）。
    * 单个回合不超过 2 分钟（同一行）。
    * 恢复时间是快速跑用时的 2~3 倍（第4章 L1581）。
    """
    _require_positive("weekly_km", weekly_km)
    return DoseCap(
        intensity="R",
        max_km=min(weekly_km * 0.05, 8.0),
        max_minutes=None,
        rules=(RULES["D-R-01"], RULES["D-R-02"]),
        notes=(
            "8 km 是硬顶：周跑量 190 km 的跑者上限仍是 8 km，不是 9.5 km"
            "（第4章 L1583）",
            "恢复时间取快速跑用时的 2~3 倍（D-R-03，第4章 L1581）",
        ),
        single_rep_max_minutes=2.0,
        ratio=0.05,
    )


def cap_for(intensity: str, weekly_km: float, **kwargs: object) -> DoseCap:
    """按强度分派到对应的上限函数。"""
    if intensity == "L":
        return long_run_cap(weekly_km, **kwargs)  # type: ignore[arg-type]
    if intensity == "M":
        return marathon_pace_cap(weekly_km)
    if intensity == "T":
        return threshold_cap(weekly_km)
    if intensity == "I":
        return interval_cap(weekly_km)
    if intensity == "R":
        return repetition_cap(weekly_km)
    raise ValueError(f"未知强度 {intensity!r}，可选 {INTENSITIES}")


# ---------------------------------------------------------------------------
# 恢复与增量
# ---------------------------------------------------------------------------
def post_race_easy_days(race_km: float) -> int:
    """比赛后应安排的轻松日天数。

    第 14 章 L3482 给出的四个锚点：

    ==========  ============
    比赛距离      轻松日
    ==========  ============
    10 km        3
    15 km        5
    半程马拉松     7
    全程马拉松    14
    ==========  ============

    第 11 章 L2990 还补了 5 km → 2 天。

    ``round(距离 / 3)`` 同时命中这五个锚点；单纯的向下取整会把 5 km
    算成 1 天，向上取整会把 10 km 算成 4 天，都不对。

    Parameters
    ----------
    race_km : float
        比赛距离，公里。

    Returns
    -------
    int
        轻松日天数，至少 1。
    """
    _require_positive("race_km", race_km)
    return max(1, int(round(race_km / 3.0)))


def volume_step_km(sessions_per_week: int) -> float:
    """下一次加周跑量时，最多能加多少公里。

    第 11 章 L2956：每 3~4 周把每次跑的里程加 1.6 km，按出勤次数折算，
    但周增量封顶 16 km。每周 5 次 → 8 km；每天两跑共 14 次 → 16 km（不是 22.4）。

    Parameters
    ----------
    sessions_per_week : int
        每周跑步次数（含一天两跑的次数）。

    Returns
    -------
    float
        建议的周跑量增量，公里。
    """
    if not isinstance(sessions_per_week, int) or isinstance(sessions_per_week, bool):
        raise ValueError(
            f"sessions_per_week 必须是整数，收到 {type(sessions_per_week).__name__}"
        )
    if sessions_per_week <= 0:
        raise ValueError(f"sessions_per_week 必须为正，收到 {sessions_per_week}")
    return min(sessions_per_week * 1.6, 16.0)


# ---------------------------------------------------------------------------
# 周训练量检查
# ---------------------------------------------------------------------------
def max_reps(
    intensity: str,
    weekly_km: float,
    rep_m: float,
    **kwargs: object,
) -> int:
    """给定回合距离，算出单次训练最多能跑几个。

    书上给的是总里程上限（如 R ≤ 周跑量 5%），但跑者拿到的是「几个 200 米」。
    低跑量时这两者对不上：周跑量 20 km 的 R 上限只有 1.0 km，
    而常见的 8×200 m 就是 1.6 km，已经超了 60%。

    Parameters
    ----------
    intensity : str
        L/M/T/I/R。
    weekly_km : float
        周跑量，公里。
    rep_m : float
        单个回合的距离，米。
    **kwargs
        透传给 :func:`cap_for`，例如 ``surface``、``phase``。

    Returns
    -------
    int
        最多回合数。该强度无可行区间时返回 0。

    Raises
    ------
    ValueError
        回合距离非正，或该强度没有距离上限。

    Examples
    --------
    >>> max_reps("R", 20.0, 200.0)   # R 上限 1.0 km
    5
    >>> max_reps("R", 64.0, 200.0)   # R 上限 3.2 km
    16
    """
    if not rep_m > 0:
        raise ValueError(f"回合距离必须为正，收到 {rep_m!r}")
    cap = cap_for(intensity, weekly_km, **kwargs)  # type: ignore[arg-type]
    if not cap.feasible:
        return 0
    if cap.max_km is None:
        raise ValueError(f"{intensity} 没有距离上限，无法折算回合数")
    return int(cap.max_km * 1000.0 // rep_m)


def check_week(
    sessions: Sequence[Session],
    weekly_km: float,
    *,
    paces: PaceSet | None = None,
    surface: str = "road",
    phase: int | None = None,
) -> list[Violation]:
    """检查一周的训练安排是否触碰任何剂量上限。

    Parameters
    ----------
    sessions : Sequence[Session]
        本周的高质量训练课（L/M/T/I/R）。E 跑不计入，用 ``weekly_km`` 体现。
    weekly_km : float
        本周总跑量，公里。
    paces : PaceSet or None, optional
        :func:`daniels.vdot.pace_set` 的返回值。给了就把分钟上限也纳入判断。
        L 跑按 E 配速的慢端折算（同一距离下用时最长的那个，偏保守）。
    surface : str, optional
        ``"road"`` 或 ``"trail"``。
    phase : int, optional
        训练阶段，用于越野跑的 L 跑分支。

    Returns
    -------
    list[Violation]
        超限记录。空列表表示合规。
    """
    _require_positive("weekly_km", weekly_km)
    violations: list[Violation] = []

    def pace_of(intensity: str) -> Pace | None:
        if paces is None:
            return None
        if intensity == "L":
            # L 跑用 E 配速；取慢端，这样同一距离算出的用时最长，判断偏保守
            return paces.e_slow
        return getattr(paces, intensity.lower(), None)

    # 先判定哪些强度在此周跑量下根本没有可行区间
    # （书里两条规则打架，例如 T 的 10% 上限低于 4.8 km 下限）。
    # 这类强度只报一条「无解」，不再逐次报超限或不足，否则同一件事说两遍。
    infeasible: set[str] = set()
    for intensity in sorted({s.intensity for s in sessions}):
        cap = cap_for(intensity, weekly_km, surface=surface, phase=phase)
        if cap.feasible:
            continue
        infeasible.add(intensity)
        violations.append(
            Violation(
                rule_ids=tuple(r.rule_id for r in cap.rules),
                intensity=intensity,
                session_index=None,
                actual=cap.max_km if cap.max_km is not None else 0.0,
                limit=cap.min_km if cap.min_km is not None else 0.0,
                unit="range",
                message=(
                    f"{intensity} 在当前周跑量 {weekly_km:.0f} km 下没有可行区间："
                    f"上限 {cap.max_km:.2f} km 低于下限 {cap.min_km:.2f} km。"
                    f"要么提高周跑量，要么这一周不做 {intensity}"
                ),
            )
        )

    for idx, session in enumerate(sessions):
        if session.intensity in infeasible:
            continue
        cap = cap_for(session.intensity, weekly_km, surface=surface, phase=phase)
        pace = pace_of(session.intensity)

        if cap.max_km is not None and session.km > cap.max_km + 1e-9:
            violations.append(
                Violation(
                    rule_ids=tuple(r.rule_id for r in cap.rules),
                    intensity=session.intensity,
                    session_index=idx,
                    actual=session.km,
                    limit=cap.max_km,
                    unit="km",
                    message=(
                        f"{session.intensity} 跑 {session.km:.1f} km 超过上限 "
                        f"{cap.max_km:.1f} km（周跑量 {weekly_km:.0f} km）"
                    ),
                )
            )
        elif pace is not None and cap.max_minutes is not None:
            actual_minutes = session.km * pace.seconds_per_km / 60.0
            if actual_minutes > cap.max_minutes + 1e-9:
                violations.append(
                    Violation(
                        rule_ids=tuple(r.rule_id for r in cap.rules),
                        intensity=session.intensity,
                        session_index=idx,
                        actual=actual_minutes,
                        limit=cap.max_minutes,
                        unit="minutes",
                        message=(
                            f"{session.intensity} 跑 {session.km:.1f} km 约 "
                            f"{actual_minutes:.0f} 分钟，超过上限 "
                            f"{cap.max_minutes:.0f} 分钟"
                        ),
                    )
                )

        if cap.min_km is not None and session.km < cap.min_km - 1e-9:
            violations.append(
                Violation(
                    rule_ids=("D-T-02",),
                    intensity=session.intensity,
                    session_index=idx,
                    actual=session.km,
                    limit=cap.min_km,
                    unit="km",
                    message=(
                        f"T 跑 {session.km:.1f} km 低于单次下限 "
                        f"{cap.min_km:.1f} km"
                    ),
                )
            )

    # 每周 I 训练次数
    i_sessions = [i for i, s in enumerate(sessions) if s.intensity == "I"]
    if len(i_sessions) > 2:
        violations.append(
            Violation(
                rule_ids=("D-I-03",),
                intensity="I",
                session_index=None,
                actual=float(len(i_sessions)),
                limit=2.0,
                unit="sessions",
                message=(
                    f"本周安排了 {len(i_sessions)} 次 I 训练，"
                    "书中建议每周不超过 2 次"
                ),
            )
        )

    return violations
