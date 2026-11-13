# -*- coding: utf-8 -*-
"""日历：比赛日 ↔ 周数 ↔ 起点。

为什么单开一块
--------------
十轮测试里日期错了两次：一次是**编**了两个比赛日（先定「12 周」再倒推日期）；
一次是**手算**起点，写成了 2026-11-29——那天是周日，从它到 2027-04-18 是 141 天，
装不满 20 周。正确起点是 11-30（周一），正好 140 天。

两次都不是不会算，是**用手算代替了查**。所以这块只做一件事：
把「给定今天和比赛日，有哪些能用的周数、各自从哪天开始」变成一次函数调用。

一条约定
--------
**周历以比赛周为最后一周，向前倒推。** 起点日 = 比赛日 − (7 × 周数 − 1) 天。
这样不管比赛在周几，起点自动落在它的次日那种星期上：

* 周日比赛（最常见）→ 起点是周一，最后一周正好收在周日；
* 周六比赛 → 起点是周日。

不需要额外配置「一周从周几开始」，因为它由比赛日决定，不是由偏好决定。

模块名为什么叫 ``dates`` 而不是 ``calendar``
-------------------------------------------
``calendar`` 是标准库的名字。包内用 ``from .calendar import ...`` 不会有问题
（Python 3 是绝对导入），但只要有人 ``cd daniels/`` 再 ``import calendar``，
拿到的就是本模块而不是标准库。开源项目里这种坑不值得留，所以改名。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Dict, Tuple

from .periodize import DOCUMENTED_SPLITS, MIN_WEEKS

__all__ = [
    "PlanOption",
    "feasible_plans",
    "max_plan_weeks",
    "plan_window",
    "weeks_until",
]


@dataclass(frozen=True)
class PlanOption:
    """一种可行的训练季长度。"""

    weeks: int
    start_date: date
    """第 1 周的第 1 天。"""
    end_date: date
    """最后一周的最后一天，应该等于比赛日。"""
    documented: bool
    """这个长度在书里有记录的阶段分配。"""
    starts_in_past: bool
    """起点已经过去了，现在开不了。"""

    @property
    def split(self) -> Tuple[int, int, int, int] | None:
        """书里的阶段分配；不在记录里时为 ``None``。"""
        return DOCUMENTED_SPLITS.get(self.weeks)

    def as_dict(self) -> Dict[str, object]:
        out: Dict[str, object] = {
            "weeks": self.weeks,
            "start_date": self.start_date.isoformat(),
            "end_date": self.end_date.isoformat(),
            "weekday_of_start": "一二三四五六日"[self.start_date.weekday()],
            "documented": self.documented,
            "starts_in_past": self.starts_in_past,
        }
        if self.split is not None:
            out["split"] = list(self.split)
        return out


def _require_date(name: str, value: object) -> date:
    if not isinstance(value, date):
        raise TypeError(
            f"{name} 必须是 datetime.date，收到 {type(value).__name__}"
        )
    return value


def weeks_until(today: date, race_date: date) -> Tuple[int, int]:
    """从今天到比赛日的整周数与余数天数。

    Parameters
    ----------
    today, race_date : datetime.date

    Returns
    -------
    (weeks, days)
        ``days`` 是除不尽的余数，0~6。

    Raises
    ------
    TypeError
        参数不是 ``date``。
    ValueError
        比赛日不在今天之后。

    Examples
    --------
    >>> from datetime import date
    >>> from daniels.dates import weeks_until
    >>> weeks_until(date(2026, 11, 13), date(2027, 4, 18))
    (22, 2)

    Notes
    -----
    这是**已经过去的天数**换算，不是「你能排多长的计划」。

    因为比赛日算最后一周的最后一天，49 天（含头含尾）正好排 7 周，而这里会返回
    ``(6, 6)``（48 天 = 6 周 6 天）。两个数都对，说的是不同的东西。
    要「能排多长」请用 :func:`max_plan_weeks` 或直接看 :func:`feasible_plans`。

    这个区别在真实测试里把人绕进去过：一份回答先写「6 周零 6 天」，
    紧接着写「只有 7 个完整周可用」——两句都对，但没说明是两个口径。
    """
    today = _require_date("today", today)
    race_date = _require_date("race_date", race_date)
    if race_date <= today:
        raise ValueError(
            f"比赛日 {race_date} 必须晚于今天 {today}；"
            "已经过去的比赛不需要排训练季了"
        )
    return divmod((race_date - today).days, 7)


def max_plan_weeks(today: date, race_date: date) -> int:
    """从今天开练、以比赛日为最后一天，最多能排多少周。

    这才是「我还有几周」在排计划语境下的答案。

    Parameters
    ----------
    today, race_date : datetime.date

    Returns
    -------
    int
        能排的最长周数。比赛日太近时会小于 :data:`daniels.periodize.MIN_WEEKS`。

    Examples
    --------
    11-13 到 12-31 是 49 天（含头含尾），正好 7 周——不是
    :func:`weeks_until` 返回的那个 ``(6, 6)``：

    >>> from datetime import date
    >>> from daniels.dates import max_plan_weeks
    >>> max_plan_weeks(date(2026, 11, 13), date(2026, 12, 31))
    7
    >>> max_plan_weeks(date(2026, 11, 13), date(2027, 4, 18))
    22
    """
    today = _require_date("today", today)
    race_date = _require_date("race_date", race_date)
    if race_date <= today:
        raise ValueError(f"比赛日 {race_date} 必须晚于今天 {today}")
    # 起点 = 比赛日 − (7w − 1)，要求起点 ≥ 今天 → w ≤ (天数 + 1) / 7
    return ((race_date - today).days + 1) // 7


def plan_window(weeks: int, race_date: date) -> Tuple[date, date]:
    """给定周数与比赛日，返回 (起点, 终点)。

    Notes
    -----
    终点一定等于 ``race_date``：最后一周的周日就是比赛日。
    起点落在比赛日的「次日那种星期」上（周日比赛 → 周一开练）。

    Raises
    ------
    ValueError
        周数不是正整数。

    Examples
    --------
    >>> from datetime import date
    >>> from daniels.dates import plan_window
    >>> start, end = plan_window(20, date(2027, 4, 18))
    >>> start.isoformat(), end.isoformat()
    ('2026-11-30', '2027-04-18')
    """
    if not isinstance(weeks, int) or isinstance(weeks, bool):
        raise ValueError(f"weeks 必须是整数，收到 {type(weeks).__name__}")
    if weeks < 1:
        raise ValueError(f"weeks 必须 ≥ 1，收到 {weeks}")
    race_date = _require_date("race_date", race_date)
    return race_date - timedelta(days=7 * weeks - 1), race_date


def feasible_plans(
    today: date,
    race_date: date,
    *,
    min_weeks: int = MIN_WEEKS,
    max_weeks: int = 40,
    documented_only: bool = False,
    include_past: bool = False,
    past_window_weeks: int = 4,
) -> Tuple[PlanOption, ...]:
    """列出这场比赛能套的所有周数，以及各自的起点。

    Parameters
    ----------
    today : date
        用来判断「起点是不是已经过去了」。
    race_date : date
        比赛日。
    min_weeks : int, optional
        最短周数，默认 3（与 :data:`daniels.periodize.MIN_WEEKS` 一致）。
    max_weeks : int, optional
        最长周数，默认 40。
    documented_only : bool, optional
        只要书里记录过的长度（3/6/9/12/20/23/24）。
    include_past : bool, optional
        默认 ``False``，只返回现在还能开始的。设为 ``True`` 时把「起点已过去」
        的也返回并标 ``starts_in_past=True``——这样才能说清楚
        「23 周本来也行，但 11-09 已经过去了」，而不是干脆不提。
    past_window_weeks : int, optional
        ``include_past=True`` 时往后多看几周，默认 4。
        不设上限的话，一场近在眼前的比赛会把几十个「早该开始」的长度全倒出来。
        4 周足够覆盖「就差一两周」的那几个，又不至于淹掉结果。

    Returns
    -------
    tuple of PlanOption
        按周数升序。

    Raises
    ------
    ValueError
        比赛日不在今天之后，或周数区间不合法。

    Examples
    --------
    书里记录过的长度里，2027-04-18 这场半马唯一还来得及的是 20 周：

    >>> from datetime import date
    >>> from daniels.dates import feasible_plans
    >>> [p.weeks for p in feasible_plans(
    ...     date(2026, 11, 13), date(2027, 4, 18), documented_only=True)]
    [3, 6, 9, 12, 20]

    23 周要 11-09 就得开始，那天已经过去了：

    >>> [p.weeks for p in feasible_plans(
    ...     date(2026, 11, 13), date(2027, 4, 18),
    ...     documented_only=True, include_past=True)]
    [3, 6, 9, 12, 20, 23]
    """
    today = _require_date("today", today)
    race_date = _require_date("race_date", race_date)
    if race_date <= today:
        raise ValueError(f"比赛日 {race_date} 必须晚于今天 {today}")
    for name, value in (("min_weeks", min_weeks), ("max_weeks", max_weeks)):
        if not isinstance(value, int) or isinstance(value, bool):
            raise ValueError(
                f"{name} 必须是整数，收到 {type(value).__name__}"
            )
    if min_weeks < 1 or max_weeks < min_weeks:
        raise ValueError(f"周数区间不合法：{min_weeks}~{max_weeks}")

    # 不要起点已过去的周数时，上限就是「能排多长」；
    # 要看「本来也行、但已经过去的」时，往后多看 past_window_weeks 周。
    # 放到 max_weeks 是不行的：一场近在眼前的比赛会倒出几十个无效选项。
    longest = min(max_weeks, max_plan_weeks(today, race_date))
    if include_past:
        limit = min(max_weeks, longest + past_window_weeks)
    else:
        limit = longest
    options = []
    for weeks in range(min_weeks, limit + 1):
        if documented_only and weeks not in DOCUMENTED_SPLITS:
            continue
        start, end = plan_window(weeks, race_date)
        in_past = start < today
        if in_past and not include_past:
            continue
        options.append(
            PlanOption(
                weeks=weeks,
                start_date=start,
                end_date=end,
                documented=weeks in DOCUMENTED_SPLITS,
                starts_in_past=in_past,
            )
        )
    return tuple(options)
