# -*- coding: utf-8 -*-
"""周期性减量（外推层）。

为什么单开一层，而不是塞进 periodize
------------------------------------
书中**没有**「每 N 周减一次量」这个概念。全书只有三处把周跑量写成比例，
而且全部围绕**一场具体的比赛**：

* 第 14 章 L3398：2Q 马拉松计划的第二列用「峰值 P 的 80%~100%」表示。
  0.8P 是该计划里**最低**的一周，不是一条「降 20% 安全」的普适许可；
* 第 14 章 L3496：赛前最后 3 周去跨步跑、最后 2 周去跑坡、最后一周 L 跑 90 分钟；
* 第 14 章 L3482、第 11 章 L2990：赛后按距离安排轻松日。

三者回答的都是「**比赛**前后怎么减」，没有一条是「减下来、回到原水平、
四周后再减一次」。所以周期性减量是**外推**，不是书中内容。

本模块的职责边界
----------------
它**不生成完整周表**，也不编课目。排课由调用方负责。它只提供三组
可以逐项核对的数字：

1. :func:`deload_impact` —— 把「减 X%」换算成各强度的上限，指出哪个强度
   会掉出可行区间。T 的 4.8 km 单次下限是硬约束，低跑量减量周往往直接无解。
2. :func:`deload_weeks` —— 排节奏，并且禁止排出连续两个减量周、
   禁止把减量周压进赛前减量窗口。
3. :func:`check_progression` —— 反过来校验一张**已经写好的**周跑量表
   是否违反第 11 章 L2956 的加量规则。

这样做的原因是：以前这些算术靠临场推，出过一次「减量周排在第 4、8、11 周，
却写成每 4 周一次」的错误——表本身自洽不了，读表的人也看不出来。
"""

from __future__ import annotations

from collections.abc import Sequence as _Sequence
from dataclasses import dataclass
from typing import Dict, Iterable, Sequence, Tuple

from .dose import (
    INTENSITIES,
    cap_for,
    threshold_cap,
    volume_step_km,
)

__all__ = [
    "DELOAD_PROVENANCE",
    "DeloadImpact",
    "DeloadRhythm",
    "GrowthPath",
    "CycleGain",
    "ProgressionIssue",
    "deload_impact",
    "deload_weeks",
    "growth_path",
    "t_peak_km",
    "check_progression",
]


#: 外推层必须随身携带的来源说明。任何引用周期性减量的回答都应先讲这一段。
DELOAD_PROVENANCE: Dict[str, str] = {
    "book_position": (
        "书中没有周期性减量（每 N 周减量 X%）的概念。"
        "全书的减量只有两类：赛前减量与赛后恢复"
    ),
    "what_exists": (
        "第14章 L3398 把 2Q 马拉松计划的周跑量写成峰值 P 的 80%~100%，"
        "其中 0.8P 是该计划最低的一周"
    ),
    "misuse": (
        "不要把这句（第14章 L3398）读成「降 20% 被书批准」。"
        "它描述的是某张具体计划表的第二列，"
        "不是一条适用于任何跑者、任何周数的减量许可"
    ),
    "consequence": (
        "周期性减量会让每一轮的周跑量上限同比缩小。"
        "T 的单次下限是 4.8 km（第14章 L3478），"
        "减量周的 10% 上限一旦低于它，该周就排不出合规的 T 训练"
    ),
    "source": "第14章 L3398、L3478、L3496；第11章 L2956",
}


# ---------------------------------------------------------------------------
# 减量周对各强度上限的影响
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class DeloadImpact:
    """减量周对某一个强度上限的影响。"""

    intensity: str
    base_km: float
    """训练周的周跑量。"""
    deload_km: float
    """减量周的周跑量。"""
    base_cap_km: float
    """训练周的单次上限。"""
    deload_cap_km: float
    """减量周的单次上限。"""
    min_km: float | None
    """单次下限；只有 T 有（4.8 km）。"""
    ratio: float | None
    """实际套用的周跑量百分比。"""
    feasible_before: bool
    feasible_after: bool

    @property
    def collapses(self) -> bool:
        """训练周排得出、减量周排不出。"""
        return self.feasible_before and not self.feasible_after

    @property
    def lost_km(self) -> float:
        """单次上限缩水多少公里。"""
        return max(0.0, self.base_cap_km - self.deload_cap_km)

    def as_dict(self) -> Dict[str, object]:
        out: Dict[str, object] = {
            "intensity": self.intensity,
            "base_km": round(self.base_km, 2),
            "deload_km": round(self.deload_km, 2),
            "base_cap_km": round(self.base_cap_km, 2),
            "deload_cap_km": round(self.deload_cap_km, 2),
            "lost_km": round(self.lost_km, 2),
            "feasible_before": self.feasible_before,
            "feasible_after": self.feasible_after,
            "collapses": self.collapses,
        }
        if self.min_km is not None:
            out["min_km"] = self.min_km
        if self.ratio is not None:
            out["ratio_pct"] = round(self.ratio * 100.0, 1)
        return out


def _require_fraction(drop_fraction: float) -> None:
    if not isinstance(drop_fraction, (int, float)) or isinstance(
        drop_fraction, bool
    ):
        raise ValueError(
            f"drop_fraction 必须是数字，收到 {type(drop_fraction).__name__}"
        )
    if not 0.0 < drop_fraction < 1.0:
        raise ValueError(
            f"drop_fraction 必须在 (0, 1) 之间，收到 {drop_fraction}"
        )


def deload_impact(
    base_km: float,
    drop_fraction: float = 0.20,
    *,
    surface: str = "road",
    phase: int | None = None,
    intensities: Iterable[str] = INTENSITIES,
) -> Tuple[DeloadImpact, ...]:
    """算出「减量 X%」之后，各强度的单次上限还能装下多少。

    Parameters
    ----------
    base_km : float
        训练周的周跑量，公里。
    drop_fraction : float, optional
        减量周下调的比例，``0.20`` 表示降 20%。默认 0.20。
    surface : str, optional
        ``"road"`` 或 ``"trail"``，只影响 L。
    phase : int, optional
        训练阶段，只影响越野跑的 L 分支。
    intensities : Iterable[str], optional
        要比较的强度，默认五档全比。

    Returns
    -------
    tuple of DeloadImpact
        按 :data:`daniels.dose.INTENSITIES` 的顺序。

    Raises
    ------
    ValueError
        ``base_km`` 非正，或 ``drop_fraction`` 不在 (0, 1)。

    Examples
    --------
    周跑量 35 km 的训练周，T 上限是 3.5 km，本来就低于 4.8 km 的下限；
    降到 28 km 后上限 2.8 km，仍然无解。可见「减量周没法排 T」在这里
    并不是减量造成的——训练周本身就排不了，是两件事，别混着说。

    >>> from daniels.deload import deload_impact
    >>> {i.intensity: (i.feasible_before, i.feasible_after)
    ...  for i in deload_impact(64.0)}
    {'L': (True, True), 'M': (True, True), 'T': (True, True), 'I': (True, True), 'R': (True, True)}
    """
    if not isinstance(base_km, (int, float)) or isinstance(base_km, bool):
        raise ValueError(f"base_km 必须是数字，收到 {type(base_km).__name__}")
    if not base_km > 0:
        raise ValueError(f"base_km 必须为正，收到 {base_km}")
    _require_fraction(drop_fraction)

    wanted = tuple(dict.fromkeys(i.upper() for i in intensities))
    unknown = [i for i in wanted if i not in INTENSITIES]
    if unknown:
        raise ValueError(f"未知强度 {unknown}，可选 {INTENSITIES}")

    deload_km = base_km * (1.0 - drop_fraction)
    shifts = {i: (base_km, deload_km) for i in wanted}
    results = []
    for intensity in wanted:
        # L 需要 surface/phase，其余强度不接受这两个参数。
        kwargs = (
            {"surface": surface, "phase": phase} if intensity == "L" else {}
        )
        before = cap_for(intensity, shifts[intensity][0], **kwargs)
        after = cap_for(intensity, shifts[intensity][1], **kwargs)
        if before.max_km is None or after.max_km is None:
            raise AssertionError(f"{intensity} 缺少距离上限")  # pragma: no cover
        results.append(
            DeloadImpact(
                intensity=intensity,
                base_km=base_km,
                deload_km=deload_km,
                base_cap_km=before.max_km,
                deload_cap_km=after.max_km,
                min_km=after.min_km,
                ratio=after.ratio,
                feasible_before=before.feasible,
                feasible_after=after.feasible,
            )
        )
    return tuple(results)


def t_peak_km(
    t_session_km: float,
    drop_fraction: float = 0.20,
) -> float:
    """要在减量周里保住一次指定长度的 T 训练，峰值周跑量至少要多少。

    两个约束同时存在：

    * 减量周的 T 上限必须装得下这次训练：
      ``P * (1 - f) * 10% >= t_session_km``
    * 减量周的上限本身不能低于 4.8 km 的单次下限：
      ``P * (1 - f) * 10% >= 4.8``

    取两者较大的那个。

    Parameters
    ----------
    t_session_km : float
        训练周里那次 T 训练的长度，公里。
    drop_fraction : float, optional
        减量比例，默认 0.20。

    Returns
    -------
    float
        所需的最低峰值 P，公里。

    Notes
    -----
    只有 T 需要这个计算：L/M/I/R 都没有单次下限，减量只会等比缩小上限，
    不会出现「无解」。T 是唯一会在减量周被 4.8 km 卡死的强度。

    Examples
    --------
    想在一次降 20% 的减量周里跑 6 km T，峰值要做到 6 / (0.8 × 10%) = 75 km：

    >>> from daniels.deload import t_peak_km
    >>> round(t_peak_km(6.0), 1)
    75.0
    """
    if not isinstance(t_session_km, (int, float)) or isinstance(
        t_session_km, bool
    ):
        raise ValueError(
            f"t_session_km 必须是数字，收到 {type(t_session_km).__name__}"
        )
    if not t_session_km > 0:
        raise ValueError(f"t_session_km 必须为正，收到 {t_session_km}")
    _require_fraction(drop_fraction)

    cap = threshold_cap(1.0)
    ratio = cap.ratio or 0.10
    floor_km = cap.min_km or 4.8
    effective = 1.0 - drop_fraction
    return max(t_session_km, floor_km) / (ratio * effective)


# ---------------------------------------------------------------------------
# 节奏：哪几周是减量周
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class DeloadRhythm:
    """一张训练季里减量周落在哪几周。"""

    total_weeks: int
    every_weeks: int
    drop_fraction: float
    race_week: int
    weeks: Tuple[int, ...]
    """真正设为减量周的周序号（升序）。"""
    skipped: Tuple[Tuple[int, str], ...]
    """名义上该减、但被排掉的周，以及原因。"""
    notes: Tuple[str, ...]

    def is_deload(self, week_index: int) -> bool:
        """第 ``week_index`` 周是不是减量周。"""
        return week_index in self.weeks

    @property
    def nominal_count(self) -> int:
        """按节奏算出来、不管比赛周的减量周个数。"""
        return self.total_weeks // self.every_weeks

    def as_dict(self) -> Dict[str, object]:
        return {
            "total_weeks": self.total_weeks,
            "every_weeks": self.every_weeks,
            "drop_fraction": self.drop_fraction,
            "race_week": self.race_week,
            "weeks": list(self.weeks),
            "nominal_count": self.nominal_count,
            "actual_count": len(self.weeks),
            "skipped": [
                {"week": w, "reason": r} for w, r in self.skipped
            ],
            "notes": list(self.notes),
        }


def deload_weeks(
    total_weeks: int,
    every_weeks: int = 4,
    *,
    drop_fraction: float = 0.20,
    race_week: int | None = None,
    taper_window: int = 2,
) -> DeloadRhythm:
    """按「每 ``every_weeks`` 周一次」排出减量周的周序号。

    Parameters
    ----------
    total_weeks : int
        训练季总周数。
    every_weeks : int, optional
        每隔几周减一次，默认 4。必须 ≥ 2，否则会排出连续减量。
    drop_fraction : float, optional
        减量比例，默认 0.20。
    race_week : int, optional
        比赛在第几周。默认等于 ``total_weeks``（最后一周比赛）。
    taper_window : int, optional
        赛前减量窗口的周数，默认 2，依据第 14 章 L3496
        「比赛前最后 2 周执行计划中的第一周」。

    Returns
    -------
    DeloadRhythm

    Raises
    ------
    ValueError
        周数、间隔或比赛周不合法。

    Notes
    -----
    两条硬约束，都是为了避免「连续两个减量周」：

    1. **比赛周不设减量周**。比赛周本身已经是减量，再降一次就变成两周连减，
       而且会把最后一次质量训练挤到更前面。
    2. **赛前 ``taper_window`` 周内不设减量周**。赛前减量已经覆盖这段，
       叠加的后果是最后一个训练周期只剩很少的正常训练周。

    举例：12 周、每 4 周、比赛在第 12 周时，名义上有第 4、8、12 三个减量周；
    第 12 周是比赛周，被排掉，所以实际只有 **2 个**（第 4、8 周）。
    把第三个挪到第 11 周是错的——那会造成第 11、12 周连续减量。
    """
    if not isinstance(total_weeks, int) or isinstance(total_weeks, bool):
        raise ValueError(
            f"total_weeks 必须是整数，收到 {type(total_weeks).__name__}"
        )
    if total_weeks < 2:
        raise ValueError(f"total_weeks 至少 2 周，收到 {total_weeks}")
    if not isinstance(every_weeks, int) or isinstance(every_weeks, bool):
        raise ValueError(
            f"every_weeks 必须是整数，收到 {type(every_weeks).__name__}"
        )
    if every_weeks < 2:
        raise ValueError(
            f"every_weeks 至少 2 周，收到 {every_weeks}；"
            "间隔 1 周等于每周都减量"
        )
    _require_fraction(drop_fraction)

    if race_week is None:
        race_week = total_weeks
    if not isinstance(race_week, int) or isinstance(race_week, bool):
        raise ValueError(
            f"race_week 必须是整数，收到 {type(race_week).__name__}"
        )
    if not 1 <= race_week <= total_weeks:
        raise ValueError(
            f"race_week 必须在 1~{total_weeks} 之间，收到 {race_week}"
        )
    if not isinstance(taper_window, int) or isinstance(taper_window, bool):
        raise ValueError(
            f"taper_window 必须是整数，收到 {type(taper_window).__name__}"
        )
    if taper_window < 1:
        raise ValueError(f"taper_window 至少 1 周，收到 {taper_window}")

    candidates = list(range(every_weeks, total_weeks + 1, every_weeks))
    weeks: list[int] = []
    skipped: list[Tuple[int, str]] = []
    for week in candidates:
        gap = race_week - week
        if gap == 0:
            skipped.append(
                (week, "比赛周本身已经是减量周，再降一次会连出两个减量周")
            )
            continue
        if 0 < gap < taper_window:
            skipped.append(
                (
                    week,
                    f"距比赛只有 {gap} 周，落在赛前 {taper_window} 周减量窗口内"
                    "（第14章 L3496），叠加后同样会连出两个减量周",
                )
            )
            continue
        if gap < 0:
            skipped.append((week, "比赛已经结束"))
            continue
        weeks.append(week)

    notes: list[str] = []
    notes.append(
        f"按每 {every_weeks} 周一次的节奏，{total_weeks} 周名义上有 "
        f"{len(candidates)} 个减量周"
    )
    if len(weeks) < len(candidates):
        notes.append(
            f"扣掉比赛周与赛前窗口后实际是 {len(weeks)} 个："
            f"{list(weeks)}。这不是遗漏，是排不进去"
        )
    if weeks:
        gaps = [b - a for a, b in zip(weeks, weeks[1:])]
        if gaps:
            notes.append(f"相邻减量周间隔：{gaps} 周")
        notes.append(
            "最后一个减量周之后的训练周数更少，增量要按剩余周数重新分配，"
            "不能沿用前面的「每 4 周 +1 步」"
        )
    else:
        notes.append(
            "总周数太短，放不下独立的减量周；赛前减量已经覆盖"
        )
    notes.append(
        "减量周只降量、不降配速：配速由 VDOT 与阶段决定，与周跑量无关"
    )

    return DeloadRhythm(
        total_weeks=total_weeks,
        every_weeks=every_weeks,
        drop_fraction=drop_fraction,
        race_week=race_week,
        weeks=tuple(weeks),
        skipped=tuple(skipped),
        notes=tuple(notes),
    )


# ---------------------------------------------------------------------------
# 增长路径：从当前跑量加到目标跑量要多少周
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class CycleGain:
    """一个训练周期的跑量水平。"""

    cycle: int
    build_km: float
    """训练周的周跑量。"""
    deload_km: float
    """该周期减量周的周跑量。"""
    t_cap_in_deload_km: float
    """减量周的 T 单次上限。"""
    t_feasible_in_deload: bool
    """减量周能否排出一节合规的 T。"""

    def as_dict(self) -> Dict[str, object]:
        return {
            "cycle": self.cycle,
            "build_km": round(self.build_km, 1),
            "deload_km": round(self.deload_km, 1),
            "t_cap_in_deload_km": round(self.t_cap_in_deload_km, 2),
            "t_feasible_in_deload": self.t_feasible_in_deload,
        }


@dataclass(frozen=True)
class GrowthPath:
    """从当前周跑量加到目标周跑量的完整估算。"""

    base_km: float
    target_km: float
    step_km: float
    every_weeks: int
    drop_fraction: float
    sessions_per_week: int
    cycles: Tuple[CycleGain, ...]
    total_weeks: int
    """走完这条路径需要的总周数。"""
    first_target_week: int | None
    """第一次达到目标跑量是第几周；``None`` 表示在 ``max_weeks`` 内没达到。"""
    notes: Tuple[str, ...]

    def as_dict(self) -> Dict[str, object]:
        return {
            "base_km": self.base_km,
            "target_km": self.target_km,
            "step_km": round(self.step_km, 1),
            "every_weeks": self.every_weeks,
            "drop_fraction": self.drop_fraction,
            "sessions_per_week": self.sessions_per_week,
            "total_weeks": self.total_weeks,
            "first_target_week": self.first_target_week,
            "cycles": [c.as_dict() for c in self.cycles],
            "notes": list(self.notes),
        }


def growth_path(
    base_km: float,
    target_km: float,
    sessions_per_week: int,
    *,
    every_weeks: int = 4,
    drop_fraction: float = 0.20,
    max_weeks: int = 104,
) -> GrowthPath:
    """在「每 N 周减一次量」的前提下，从当前跑量加到目标跑量要多少周。

    加量规则来自第 11 章 L2956：每 3~4 周把**每次**跑的里程加 1.6 km，
    周增量封顶 16 km。按出勤次数折算即 ``volume_step_km``。
    这里把一个周期的加量集中在周期开头，减量周不承担加量。

    Parameters
    ----------
    base_km : float
        当前周跑量，公里。
    target_km : float
        目标周跑量，公里，必须大于 ``base_km``。
    sessions_per_week : int
        每周跑步次数，用来折算每周期最多加多少公里。
    every_weeks : int, optional
        周期长度，默认 4，且最后一周为减量周。
    drop_fraction : float, optional
        减量比例，默认 0.20。
    max_weeks : int, optional
        估算上限，默认 104 周；超过则认为目标不现实。

    Returns
    -------
    GrowthPath

    Raises
    ------
    ValueError
        参数不合法，或 ``target_km <= base_km``。

    Notes
    -----
    返回值里的 ``total_weeks`` 是**走完最后一个周期**的周数，
    ``first_target_week`` 是第一次到达目标的那一周。两者通常差 ``every_weeks - 1`` 周，
    报数时要说清用的是哪个。
    """
    if not isinstance(base_km, (int, float)) or isinstance(base_km, bool):
        raise ValueError(f"base_km 必须是数字，收到 {type(base_km).__name__}")
    if not base_km > 0:
        raise ValueError(f"base_km 必须为正，收到 {base_km}")
    if not isinstance(target_km, (int, float)) or isinstance(target_km, bool):
        raise ValueError(
            f"target_km 必须是数字，收到 {type(target_km).__name__}"
        )
    if target_km <= base_km:
        raise ValueError(
            f"target_km 必须大于 base_km，收到 {base_km} -> {target_km}；"
            "想减量请用 deload_impact"
        )
    if not isinstance(every_weeks, int) or isinstance(every_weeks, bool):
        raise ValueError(
            f"every_weeks 必须是整数，收到 {type(every_weeks).__name__}"
        )
    if every_weeks < 2:
        raise ValueError(f"every_weeks 至少 2 周，收到 {every_weeks}")
    if not isinstance(max_weeks, int) or isinstance(max_weeks, bool):
        raise ValueError(
            f"max_weeks 必须是整数，收到 {type(max_weeks).__name__}"
        )
    if max_weeks < every_weeks:
        raise ValueError(
            f"max_weeks 至少 {every_weeks} 周，收到 {max_weeks}"
        )
    _require_fraction(drop_fraction)

    step = volume_step_km(sessions_per_week)
    cycles: list[CycleGain] = []
    level = float(base_km)
    week = 0
    first_target_week: int | None = None
    cycle_index = 0

    while week < max_weeks:
        cycle_index += 1
        deload_km = level * (1.0 - drop_fraction)
        t_cap = threshold_cap(deload_km)
        cycles.append(
            CycleGain(
                cycle=cycle_index,
                build_km=level,
                deload_km=deload_km,
                t_cap_in_deload_km=t_cap.max_km or 0.0,
                t_feasible_in_deload=t_cap.feasible,
            )
        )
        for position in range(1, every_weeks + 1):
            week += 1
            if week > max_weeks:
                break
            if position < every_weeks and level >= target_km - 1e-9:
                if first_target_week is None:
                    first_target_week = week
        if level >= target_km - 1e-9:
            break
        level = min(level + step, float(target_km))

    total_weeks = week
    notes = [
        f"每 {every_weeks} 周一个周期，周期内 {every_weeks - 1} 个训练周 + 1 个减量周",
        f"每次加量 {step:.1f} km（第11章 L2956：每次 +1.6 km × 每周 "
        f"{sessions_per_week} 次）",
    ]
    if first_target_week is None:
        notes.append(
            f"{max_weeks} 周内没达到目标 {target_km:g} km，"
            "这个目标在当前出勤次数下不现实"
        )
    else:
        notes.append(
            f"第 {first_target_week} 周首次到 {target_km:g} km，"
            f"走完那一周期共 {total_weeks} 周"
        )
    infeasible = [c.cycle for c in cycles if not c.t_feasible_in_deload]
    if infeasible:
        notes.append(
            f"第 {infeasible} 个周期的减量周排不出合规的 T 训练："
            "该周上限低于 4.8 km 的单次下限。"
            "这些周的减量课应放 M/L/E，把 T 留在训练周"
        )
    else:
        notes.append("每个周期的减量周都能排出一节合规的 T 训练")
    notes.append(
        "这是按加量规则做的估算，不含受伤、生病、比赛周占用的时间"
    )

    return GrowthPath(
        base_km=float(base_km),
        target_km=float(target_km),
        step_km=step,
        every_weeks=every_weeks,
        drop_fraction=drop_fraction,
        sessions_per_week=sessions_per_week,
        cycles=tuple(cycles),
        total_weeks=total_weeks,
        first_target_week=first_target_week,
        notes=tuple(notes),
    )


# ---------------------------------------------------------------------------
# 反向校验：一张已经写好的周跑量表
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class ProgressionIssue:
    """周跑量增长违反第 11 章 L2956 的一处记录。"""

    week_index: int
    from_km: float
    to_km: float
    gain_km: float
    allowed_km: float
    reason: str

    def as_dict(self) -> Dict[str, object]:
        return {
            "week_index": self.week_index,
            "from_km": round(self.from_km, 2),
            "to_km": round(self.to_km, 2),
            "gain_km": round(self.gain_km, 2),
            "allowed_km": round(self.allowed_km, 2),
            "reason": self.reason,
        }


def check_progression(
    volumes: Sequence[float],
    sessions_per_week: int,
    *,
    every_weeks: int = 4,
) -> list[ProgressionIssue]:
    """校验一张周跑量表是否违反加量规则。

    Parameters
    ----------
    volumes : Sequence[float]
        逐周周跑量，公里，按周顺序。减量周照实写低值。
    sessions_per_week : int
        每周跑步次数。
    every_weeks : int, optional
        两次加量之间至少隔几周，默认 4（第 11 章 L2956 说的是「每 3~4 周」，
        这里取保守的一侧）。

    Returns
    -------
    list of ProgressionIssue
        空列表表示合规。

    Raises
    ------
    ValueError
        表为空、含非正数，或参数不合法。

    Notes
    -----
    **只有创出新高的加量才算加量。** 从减量周回到原水平不算：
    身体已经适应过那个量，回去不构成新刺激。这条区分很重要——
    否则任何减量计划都会被误判成违规。

    判断两条：

    1. 单次加量不得超过 ``volume_step_km(sessions_per_week)``；
    2. 两次「创新高」之间至少隔 ``every_weeks`` 周。
    """
    if not isinstance(volumes, _Sequence) or isinstance(volumes, (str, bytes)):
        raise ValueError(
            f"volumes 必须是数字序列，收到 {type(volumes).__name__}"
        )
    if len(volumes) < 2:
        raise ValueError(f"volumes 至少 2 周，收到 {len(volumes)}")
    for index, value in enumerate(volumes, start=1):
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise ValueError(
                f"第 {index} 周的跑量必须是数字，收到 {type(value).__name__}"
            )
        if not value > 0:
            raise ValueError(f"第 {index} 周的跑量必须为正，收到 {value}")
    if not isinstance(every_weeks, int) or isinstance(every_weeks, bool):
        raise ValueError(
            f"every_weeks 必须是整数，收到 {type(every_weeks).__name__}"
        )
    if every_weeks < 2:
        raise ValueError(f"every_weeks 至少 2 周，收到 {every_weeks}")

    allowed = volume_step_km(sessions_per_week)
    issues: list[ProgressionIssue] = []
    high = float(volumes[0])
    gain_weeks: list[int] = []

    for offset in range(1, len(volumes)):
        week_index = offset + 1
        current = float(volumes[offset])
        if current <= high + 1e-9:
            continue
        gain = current - high
        if gain > allowed + 1e-9:
            issues.append(
                ProgressionIssue(
                    week_index=week_index,
                    from_km=high,
                    to_km=current,
                    gain_km=gain,
                    allowed_km=allowed,
                    reason=(
                        f"单次加量 {gain:.1f} km 超过 {allowed:.1f} km："
                        f"每次最多 +1.6 km，每周 {sessions_per_week} 次"
                    ),
                )
            )
        recent = [w for w in gain_weeks if week_index - w < every_weeks]
        if recent:
            issues.append(
                ProgressionIssue(
                    week_index=week_index,
                    from_km=high,
                    to_km=current,
                    gain_km=gain,
                    allowed_km=allowed,
                    reason=(
                        f"距上次加量（第 {recent[-1]} 周）只有 "
                        f"{week_index - recent[-1]} 周，要求至少 {every_weeks} 周"
                    ),
                )
            )
        gain_weeks.append(week_index)
        high = current

    return issues
