# -*- coding: utf-8 -*-
"""丹尼尔斯训练周期安排（规则层）。

这一层回答：**这些配速和训练量，按什么顺序、放在一周的哪天。**

依赖 :mod:`daniels.vdot`（配速）与 :mod:`daniels.dose`（训练量上限），
但两者都不反向依赖本模块。

设计原则
--------
1. 书中明确给出的周数分配，一字不改地放进查找表，标 ``documented=True``。
2. 书中没给的长度，**默认拒绝**（``PhaseLengthError``），
   需要显式传 ``allow_undocumented=True`` 才按均分推导，并在结果里标
   ``documented=False``。
3. 四个阶段的内容侧重直接来自第 6 章的描述，不做风格化发挥。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Tuple

__all__ = [
    "PhaseLengthError",
    "PhaseInfo",
    "PHASES",
    "PhasePlan",
    "TaperRules",
    "WeekTaper",
    "DOCUMENTED_SPLITS",
    "SPLIT_SOURCES",
    "MIN_WEEKS",
    "WEEK_DAYS",
    "plan_schedule",
    "phase_info",
    "quality_days",
    "q_intensities",
    "taper_rules",
    "week_taper",
    "weekly_volume_bounds",
]


class PhaseLengthError(ValueError):
    """请求的总周数既不在书中的记录里，又没允许推导。"""


#: 一周七天的编号。第 6 章 L2086 把周日当作每周第一天。
WEEK_DAYS: Tuple[str, ...] = ("周日", "周一", "周二", "周三", "周四", "周五", "周六")


# ---------------------------------------------------------------------------
# 四个阶段
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class PhaseInfo:
    """一个训练阶段的定义。"""

    index: int
    code: str
    name_zh: str
    primary: Tuple[str, ...]
    maintain: Tuple[str, ...]
    dropped: Tuple[str, ...]
    summary: str
    source: str

    def as_dict(self) -> Dict[str, object]:
        return {
            "index": self.index,
            "code": self.code,
            "name": self.name_zh,
            "primary": list(self.primary),
            "maintain": list(self.maintain),
            "dropped": list(self.dropped),
            "summary": self.summary,
            "source": self.source,
        }


#: 四个阶段。顺序与侧重来自第 6 章 L1978-L2040。
PHASES: Tuple[PhaseInfo, ...] = (
    PhaseInfo(
        index=1,
        code="B/FIP",
        name_zh="基础与防伤",
        primary=("E",),
        maintain=(),
        dropped=("T", "I", "R"),
        summary=(
            "以 E 跑打底，配合跨步跑与轻量阻力训练；"
            "目标是把抵御伤病的能力建起来，而不是练强度"
        ),
        source="第6章 L1980、L2012-L2016",
    ),
    PhaseInfo(
        index=2,
        code="IQ",
        name_zh="初级高质量",
        primary=("R",),
        maintain=("E", "L"),
        dropped=("I", "T"),
        summary=(
            "只引入一个新压力：速度。每周两次 R 训练，中间穿插轻松日；"
            "从 E 直接跳到 I 会同时增加两个压力，所以先练 R"
        ),
        source="第6章 L1982、L2018-L2022",
    ),
    PhaseInfo(
        index=3,
        code="TQ",
        name_zh="过渡性高质量",
        primary=("I",),
        maintain=("R",),
        dropped=(),
        summary=(
            "四个阶段里压力最大的一个，以 I 训练为主；"
            "长距离选手每周两次 I，短距离选手一次 I 并继续 R"
        ),
        source="第6章 L1984、L2026-L2028",
    ),
    PhaseInfo(
        index=4,
        code="FQ",
        name_zh="最后的高质量",
        primary=("T",),
        maintain=("R",),
        dropped=("I",),
        summary=(
            "转向 T 配速，并在 T 训练末尾加几个短 R；"
            "距离较长的选手在这一阶段停止 I 训练，让比赛承担 I 的作用"
        ),
        source="第6章 L1986、L2030-L2034",
    ),
)


def phase_info(index: int) -> PhaseInfo:
    """按序号取阶段定义。

    Raises
    ------
    ValueError
        序号不在 1~4。
    """
    if index not in (1, 2, 3, 4):
        raise ValueError(f"阶段只能是 1~4，收到 {index!r}")
    return PHASES[index - 1]


# ---------------------------------------------------------------------------
# 周数分配
# ---------------------------------------------------------------------------
#: 书中直接给出的周数分配，键为总周数，值为各阶段周数 (P1, P2, P3, P4)。
#:
#: 出处：第 6 章 L2051-L2075 与图 6—2 的编号压缩系统。
#:
#: * 3 周：全部用于阶段一（L2059-L2061）
#: * 6 周：阶段一 3 周 + 阶段四 3 周（L2073）
#: * 9 周：阶段一、阶段二、阶段四各 3 周，跳过阶段三（L2073）
#: * 20 周：4 / 6 / 6 / 4，阶段四「去掉 22 和 24」（L2075）
#: * 23 周：阶段四「去掉 1 周（24）」，故为 6 / 6 / 6 / 5（L2075）
#: * 24 周：4 个 6 周（L2051）
DOCUMENTED_SPLITS: Dict[int, Tuple[int, int, int, int]] = {
    3: (3, 0, 0, 0),
    6: (3, 0, 0, 3),
    9: (3, 3, 0, 3),
    12: (3, 3, 3, 3),
    20: (4, 6, 6, 4),
    23: (6, 6, 6, 5),
    24: (6, 6, 6, 6),
}

#: 每种长度的出处说明。区分「书中明确举例」与「由图推得」——
#: 12 周这一档是从图 6—2 的编号系统算出来的，书中并没有一句
#: 「如果你有 12 周就每阶段 3 周」的原话。
SPLIT_SOURCES: Dict[int, str] = {
    3: "第6章 L2059-L2061 明确举例",
    6: "第6章 L2073 明确举例",
    9: "第6章 L2073 明确举例",
    12: "由第6章 图6—2 的编号系统推得（1 个数字 = 1 周，共 12 个），书中未单独举例",
    20: "第6章 L2075 明确举例",
    23: "第6章 L2075 明确举例",
    24: "第6章 L2051 明确给出四个 6 周",
}

#: 少于这个周数时，任何分配都没有意义。
MIN_WEEKS = 3


@dataclass(frozen=True)
class PhasePlan:
    """一次完整的阶段划分结果。"""

    total_weeks: int
    weeks: Tuple[int, int, int, int]
    """各阶段周数，(P1, P2, P3, P4)。"""

    documented: bool
    """是否直接来自 :data:`DOCUMENTED_SPLITS`。"""

    notes: Tuple[str, ...]

    def phase_of_week(self, week_index: int) -> int:
        """第 ``week_index`` 周（从 1 开始）属于第几阶段。

        Raises
        ------
        ValueError
            周序号越界。
        """
        if not 1 <= week_index <= self.total_weeks:
            raise ValueError(
                f"周序号必须在 1~{self.total_weeks}，收到 {week_index}"
            )
        cursor = 0
        for phase_index, count in enumerate(self.weeks, start=1):
            cursor += count
            if week_index <= cursor:
                return phase_index
        raise AssertionError("周序号未落入任何阶段")  # pragma: no cover

    def active_phases(self) -> Tuple[int, ...]:
        """实际有周数的阶段序号。"""
        return tuple(
            i for i, count in enumerate(self.weeks, start=1) if count > 0
        )

    def as_dict(self) -> Dict[str, object]:
        return {
            "total_weeks": self.total_weeks,
            "weeks": {
                phase_info(i + 1).code: count
                for i, count in enumerate(self.weeks)
                if count > 0
            },
            "documented": self.documented,
            "notes": list(self.notes),
        }


def _undocumented_split(total_weeks: int) -> Tuple[int, int, int, int]:
    """书里没有记录长度时的均分方案。

    四个阶段平分，余数从阶段一往后依次各加一周。
    这是一个明确写出来的**推导规则**，不是书中的分配。
    """
    base, remainder = divmod(total_weeks, 4)
    return tuple(  # type: ignore[return-value]
        base + (1 if i < remainder else 0) for i in range(4)
    )


def plan_schedule(
    total_weeks: int,
    *,
    allow_undocumented: bool = False,
) -> PhasePlan:
    """把总周数划到四个训练阶段。

    Parameters
    ----------
    total_weeks : int
        整个训练季的周数。
    allow_undocumented : bool, optional
        当总周数不在 :data:`DOCUMENTED_SPLITS` 里时，是否允许按均分推导。
        默认 ``False``，直接抛错——因为书中只给了有限的几种长度，
        其余长度的分配属于外推，不该悄悄发生。

    Returns
    -------
    PhasePlan

    Raises
    ------
    PhaseLengthError
        周数不合法，或未记录且未允许推导。

    Notes
    -----
    总周数超过 24 时，多出来的周数全部给阶段一。依据是第 9 章 L2583
    「其他跑者能花上两个多月进行阶段一」与第 10 章 L2892
    「如果你有时间并且想跑得更快，那就在加量前先进行阶段一」。
    """
    if not isinstance(total_weeks, int) or isinstance(total_weeks, bool):
        raise PhaseLengthError(
            f"total_weeks 必须是整数，收到 {type(total_weeks).__name__}"
        )
    if total_weeks < MIN_WEEKS:
        raise PhaseLengthError(
            f"总周数至少 {MIN_WEEKS} 周，收到 {total_weeks}。"
            "少于 3 周谈不上周期安排，直接按赛前减量处理即可。"
        )

    if total_weeks in DOCUMENTED_SPLITS:
        return PhasePlan(
            total_weeks=total_weeks,
            weeks=DOCUMENTED_SPLITS[total_weeks],
            documented=True,
            notes=(SPLIT_SOURCES[total_weeks],),
        )

    if total_weeks > 24:
        extra = total_weeks - 24
        return PhasePlan(
            total_weeks=total_weeks,
            weeks=(6 + extra, 6, 6, 6),
            # documented 的意思是「这个划分出自书中」。25 周以上显然不是——
            # 书里只给了 3/6/9/12/20/23/24 这几种。早先这里写 True，
            # 和它自己下面那句「不是书中直接给出的周数表」自相矛盾。
            documented=False,
            notes=(
                f"超出 24 周的 {extra} 周全部计入阶段一："
                "书里建议有富余时间时先做基础期（第9章 L2583、第10章 L2892）",
                "注意：这是对上述原则的应用，不是书中直接给出的周数表",
            ),
        )

    if not allow_undocumented:
        raise PhaseLengthError(
            f"书中没有记录 {total_weeks} 周的阶段分配。"
            f"已记录的是 {sorted(DOCUMENTED_SPLITS)}。"
            "如需按均分推导，请显式传 allow_undocumented=True，"
            "结果会被标记为 documented=False。"
        )

    return PhasePlan(
        total_weeks=total_weeks,
        weeks=_undocumented_split(total_weeks),
        documented=False,
        notes=(
            f"{total_weeks} 周不在书中的记录里，以下按四阶段均分推导，"
            "余数从阶段一往后依次分配",
            "书中只给了 3、6、9、12、20、23、24 周这几种分配；"
            "因此相邻长度的分配形状可能差异较大（例如 20 与 21），"
            "这不是算法错误",
        ),
    )


# ---------------------------------------------------------------------------
# 一周里的 Q 日排布
# ---------------------------------------------------------------------------
def quality_days(
    q_count: int = 3,
    *,
    race_weekday: int | None = None,
    back_to_back: bool = False,
) -> Tuple[int, ...]:
    """给出本周 Q 训练放在周几。

    Parameters
    ----------
    q_count : int, optional
        正常的 Q 训练次数，2 或 3。默认 3。
    race_weekday : int, optional
        比赛在周几（1=周日 … 7=周六）。给了就按比赛周重排，
        返回值**不含比赛当天**——比赛本身就是那天的 Q。
    back_to_back : bool, optional
        是否让 Q1 与 Q2 背靠背。书中说背靠背通常好过中间插轻松日。

    Returns
    -------
    tuple of int
        周几的编号，升序。

    Raises
    ------
    ValueError
        参数越界，或比赛日太靠前以致赛前放不下 Q 训练。

    Notes
    -----
    正常周的依据是第 6 章 L2094：Q1、Q2、Q3 放在每周的第 2、4、7 天，
    书里把周日算作第一天，所以是周一、周三、周六；
    背靠背则放到第 3、4、7 天。两周一次 Q 时用周一、周四（第 10 章 L2836）。

    比赛周的重排来自第 10 章 L2842 与第 11 章 L3013：

    * 周六比赛 → Q 提前到周一和周三
    * 周五比赛 → Q 提前到周一和周二
    * 周日比赛 → Q2 挪到赛前那个周三，周四到周六全部安排轻松日
    """
    if q_count not in (2, 3):
        raise ValueError(f"q_count 只能是 2 或 3，收到 {q_count!r}")
    if race_weekday is not None and race_weekday not in range(1, 8):
        raise ValueError(f"race_weekday 必须是 1~7，收到 {race_weekday!r}")

    if race_weekday is None:
        if q_count == 3:
            return (3, 4, 7) if back_to_back else (2, 4, 7)
        return (2, 5)

    if race_weekday == 7:
        # 周六比赛 → 周一和周三（第10章 L2842），编号 1=周日 故为 (2, 4)
        return (2, 4)
    if race_weekday == 6:
        # 周五比赛 → 周一和周二（同处），故为 (2, 3)
        return (2, 3)
    if race_weekday == 1:
        # 周日比赛 → Q2 挪到赛前那个周三（第11章 L3013）
        return (4,)

    # 周一到周四的比赛：书里没有专门说，按「赛前至少留 3 个轻松日」倒推
    last_quality = race_weekday - 4
    if last_quality < 1:
        raise ValueError(
            f"比赛在{WEEK_DAYS[race_weekday - 1]}，"
            "赛前放不下任何 Q 训练；这一周应当整周当作减量周"
        )
    return (last_quality,)


def q_intensities(
    phase: int,
    *,
    long_distance: bool = True,
    q_count: int = 3,
) -> Tuple[str, ...]:
    """给出某阶段 Q 日的强度建议。

    Parameters
    ----------
    phase : int
        1~4。
    long_distance : bool, optional
        是否是距离较长的选手（5 公里以上）。影响阶段三的取舍。
    q_count : int, optional
        本周有几个 Q 日，2 或 3。默认 3。

    Returns
    -------
    tuple of str
        强度序列，长度等于 ``q_count``。

    Raises
    ------
    ValueError
        阶段或 Q 日数不合法。

    Notes
    -----
    三个 Q 日时（第 6 章 L2086、L2098）：

    * 阶段一：只做 E，Q 位其实是 L 跑与跨步跑
    * 阶段二：Q1、Q2 为 R，Q3 可以是 T
    * 阶段三：Q1 为 I，Q2 为 T（末尾加几个 R），Q3 为 I 或比赛；
      短距离选手改为一次 I 加继续 R（第 6 章 L2028）
    * 阶段四：长距离选手为 T（末尾加 4~6 个 R 200 米），Q3 可为比赛或 R；
      短距离选手把 T 和 R 结合起来（第 6 章 L2034）

    ``long_distance`` 在**阶段三和阶段四**都要起作用。早先只改了阶段三，
    阶段四无论距离长短都给 ``("T", "T", ...)``——对 5 公里这类短距离目标，
    那是错的：书里说短距离选手阶段四要 T 与 R 结合，不是把 I 换成第二个 T。

    只有两个 Q 日时，**按上面那个顺序取前两项**——这是推导，
    不是书里的原话：书中给出的周样例都假设三个 Q 日。
    因此阶段三在长距离选手手里是 ``("I", "T")``，短距离是 ``("I", "R")``。
    如果你要按比赛情况删减，删的是最后一项。
    """
    if phase not in (1, 2, 3, 4):
        raise ValueError(f"阶段只能是 1~4，收到 {phase!r}")
    if q_count not in (2, 3):
        raise ValueError(f"q_count 只能是 2 或 3，收到 {q_count!r}")

    if phase == 1:
        return ("E",) * q_count
    if phase == 2:
        full = ("R", "R", "T")
    elif phase == 3:
        full = ("I", "T", "I") if long_distance else ("I", "R", "I")
    else:
        # 第6章 L2034：长距离选手专注 T、停掉 I；短距离选手把 T 和 R 结合在一起。
        full = ("T", "T", "R") if long_distance else ("T", "R", "T")
    return full[:q_count]


# ---------------------------------------------------------------------------
# 减量与周跑量
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class TaperRules:
    """赛前减量的具体动作，全部来自第 14 章 L3496。"""

    drop_strides_from_weeks_out: int = 3
    """赛前第 3 周起去掉每周的跨步跑。"""

    drop_hills_from_weeks_out: int = 2
    """赛前第 2 周起去掉所有跑坡训练。"""

    final_long_run_minutes: float = 90.0
    """最后一周的 L 跑定为 90 分钟。"""

    last_quality_days_before_race: Tuple[int, int] = (4, 5)
    """赛前 4~5 天完成最后一次 T 训练。"""

    conflict_note: str = (
        "本条与 quality_days 的比赛周排布存在冲突："
        "第10章 L2842 把周六比赛的最后一个 Q 放在周三，即赛前 3 天；"
        "第14章 L3496 则要求赛前 4~5 天完成最后一次 T 训练。"
        "本模块不做调和——排布归 quality_days，减量归本规则，由调用方取舍。"
        "注意 L2842 的适用条件：那是 1500 m~3.2 km 选手在 24 周 4 阶段计划里、"
        "**周六**比赛的排布，不能用来给周日比赛的长距离选手背书。"
        "两处只是都出现了「周三」两个字，不是同一条规则。"
    )
    """两条规则冲突时的说明，不参与计算。"""

    prefer: Tuple[str, str] = ("L", "T")
    """减量期以 L 与 T 为主，而不是 R。"""

    flat_terrain: bool = True
    """最后三周在平坦地形上跑大部分里程。"""

    def as_dict(self) -> Dict[str, object]:
        return {
            "drop_strides_from_weeks_out": self.drop_strides_from_weeks_out,
            "drop_hills_from_weeks_out": self.drop_hills_from_weeks_out,
            "final_long_run_minutes": self.final_long_run_minutes,
            "last_quality_days_before_race": list(
                self.last_quality_days_before_race
            ),
            "conflict_note": self.conflict_note,
            "prefer": list(self.prefer),
            "flat_terrain": self.flat_terrain,
        }


def taper_rules() -> TaperRules:
    """返回赛前减量规则。"""
    return TaperRules()


def weekly_volume_bounds() -> Tuple[float, float]:
    """周跑量相对最高周跑量 P 的允许区间。

    Returns
    -------
    tuple of float
        ``(0.80, 1.00)``。第 14 章 L3398：每周跑量定在 P 的 80%~100%。

    Notes
    -----
    **不要把这条当成减量许可。** L3398 出现在第 14 章「2Q 计划」一节里，
    描述的是那张马拉松计划表第二列该怎么读——0.8P 是那张表里最低的一周。
    它没有说「任何跑者每 4 周可以降 20%」。周期性减量的算术见
    :mod:`daniels.deload`。
    """
    return (0.80, 1.00)


@dataclass(frozen=True)
class WeekTaper:
    """某一周在赛前减量里的具体动作。

    :func:`taper_rules` 给的是规则，本对象给的是**这一周该做什么**。
    两者分开是因为规则常被引用、却很少被真的落到周上——曾经出现过
    同一次回答里既引用「赛前最后 3 周去掉跨步跑」，又写「跨步跑照做」。
    """

    week_index: int
    weeks_to_race: int
    is_race_week: bool
    is_taper_week: bool
    reduced_volume: bool
    drop_strides: bool
    drop_hills: bool
    long_run_minutes_cap: float | None
    prefer: Tuple[str, ...]
    notes: Tuple[str, ...]

    def as_dict(self) -> Dict[str, object]:
        return {
            "week_index": self.week_index,
            "weeks_to_race": self.weeks_to_race,
            "is_race_week": self.is_race_week,
            "is_taper_week": self.is_taper_week,
            "reduced_volume": self.reduced_volume,
            "drop_strides": self.drop_strides,
            "drop_hills": self.drop_hills,
            "long_run_minutes_cap": self.long_run_minutes_cap,
            "prefer": list(self.prefer),
            "notes": list(self.notes),
        }


def week_taper(
    week_index: int,
    total_weeks: int,
    *,
    race_week: int | None = None,
    rules: TaperRules | None = None,
) -> WeekTaper:
    """算出第 ``week_index`` 周在赛前减量里该去掉什么。

    Parameters
    ----------
    week_index : int
        第几周，从 1 开始。
    total_weeks : int
        训练季总周数。
    race_week : int, optional
        比赛在第几周，默认 ``total_weeks``。
    rules : TaperRules, optional
        减量规则，默认 :func:`taper_rules`。

    Returns
    -------
    WeekTaper

    Raises
    ------
    ValueError
        周序号越界，或该周在比赛之后。

    Notes
    -----
    依据第 14 章 L3496：赛前最后 3 周去掉跨步跑，最后 2 周去掉跑坡并
    改为执行计划第一周，最后那周的 L 跑压到 90 分钟。

    「最后 3 周」包不包含比赛周，书中没写清。本实现**包含**比赛周
    （``weeks_to_race`` 为 0、1、2、3 的都去跨步跑），理由偏保守：
    比赛周的跨步跑如果排成一节训练，与减量的目的正相反；
    赛前热身里那几下不算训练课。若你要严格按「不含赛周」读，
    只需忽略 ``weeks_to_race == 0`` 那条。
    """
    if not isinstance(week_index, int) or isinstance(week_index, bool):
        raise ValueError(
            f"week_index 必须是整数，收到 {type(week_index).__name__}"
        )
    if not isinstance(total_weeks, int) or isinstance(total_weeks, bool):
        raise ValueError(
            f"total_weeks 必须是整数，收到 {type(total_weeks).__name__}"
        )
    if not 1 <= week_index <= total_weeks:
        raise ValueError(
            f"week_index 必须在 1~{total_weeks} 之间，收到 {week_index}"
        )
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
    if week_index > race_week:
        raise ValueError(
            f"第 {week_index} 周在比赛（第 {race_week} 周）之后，"
            "赛前减量对它没有意义；赛后恢复请用 post_race_easy_days"
        )

    rules = rules or taper_rules()
    gap = race_week - week_index
    is_race_week = gap == 0
    is_taper_week = gap <= 2
    notes: list[str] = []

    drop_strides = gap <= rules.drop_strides_from_weeks_out
    drop_hills = gap <= rules.drop_hills_from_weeks_out
    reduced_volume = is_taper_week
    long_run_minutes_cap = (
        rules.final_long_run_minutes if gap == 1 else None
    )

    where = "比赛周" if gap == 0 else f"赛前第 {gap} 周"
    if drop_strides:
        notes.append(f"{where}：去掉每周的跨步跑（第14章 L3496）")
    if drop_hills:
        notes.append(f"{where}：去掉所有跑坡训练（第14章 L3496）")
    if gap == 2:
        notes.append("赛前 2 周：改为执行计划中的第一周（第14章 L3496）")
    if long_run_minutes_cap is not None:
        notes.append(
            f"赛前 1 周：L 跑压到 {long_run_minutes_cap:.0f} 分钟"
            "（第14章 L3496）"
        )
    if is_race_week:
        notes.append(
            "比赛周本身就是减量：不要再叠加一个周期性减量周，"
            "否则会连出两个减量周（见 daniels.deload.deload_weeks）"
        )
    if not is_taper_week:
        notes.append("不在赛前 2 周窗口内，按正常周安排")

    return WeekTaper(
        week_index=week_index,
        weeks_to_race=gap,
        is_race_week=is_race_week,
        is_taper_week=is_taper_week,
        reduced_volume=reduced_volume,
        drop_strides=drop_strides,
        drop_hills=drop_hills,
        long_run_minutes_cap=long_run_minutes_cap,
        prefer=rules.prefer,
        notes=tuple(notes),
    )
