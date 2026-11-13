# -*- coding: utf-8 -*-
"""整张周表的统一裁决。

为什么要有这一层
----------------
十轮真实测试里，有两次它宣称「0 违规」而实际上并不成立：

* 一张 12 周的减量表，第 7、10 周各加 8 km，上限只有 6.4 km；
* 一张 18 周的表，第 13 周的加量距上一次只有 2 周，规则要求至少 4 周。

两次都不是算错。两次都是**只跑了其中一项校验，然后把那一项的结论说成了整张表的结论**。
"加量节奏过了" 被说成 "这张表合规"，中间那一跳没人管。

所以本模块只暴露一个入口：:func:`audit_plan`。它把六类检查全跑一遍，
**只返回一个** ``passed``。想让 "0 违规" 三个字成立，没有别的路。

刻意做成「不完整即不通过」
--------------------------
每一周都必须把长跑（``L``）写进 ``sessions``，否则长跑占比根本没被检查。
少写一次训练就能换来一个"通过"，那这个通过一文不值。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterable, Sequence, Tuple

from .deload import check_progression
from .dose import Session, check_week

__all__ = [
    "BASE_SOURCES",
    "Finding",
    "PlanAudit",
    "WeekEntry",
    "audit_plan",
    "plan_from_dict",
]


#: 起点周跑量的来源。只有前两种允许出「通过」。
BASE_SOURCES: Tuple[str, ...] = ("user", "derived", "assumed")


@dataclass(frozen=True)
class WeekEntry:
    """一周的完整记录。

    Parameters
    ----------
    week : int
        第几周，从 1 开始。
    weekly_km : float
        本周总跑量，公里。
    sessions : tuple of Session
        本周的高质量训练，**必须包含长跑**（``Session("L", ...)``），
        比赛周可以只有比赛。
    race_km : float, optional
        非空表示这一周是比赛周，值为比赛距离。
        比赛周不参与加量节奏的判断，也不参与长跑占比的判断。
    part_km : tuple of float, optional
        逐次跑的距离。给了就核对合计是否等于 ``weekly_km``——
        这一条专治「表里列出来 29.1，却写 38 含赛」。
    """

    week: int
    weekly_km: float
    sessions: Tuple[Session, ...] = ()
    race_km: float | None = None
    part_km: Tuple[float, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.week, int) or isinstance(self.week, bool):
            raise ValueError(
                f"week 必须是整数，收到 {type(self.week).__name__}"
            )
        if self.week < 1:
            raise ValueError(f"week 必须 ≥ 1，收到 {self.week}")
        if not isinstance(self.weekly_km, (int, float)) or isinstance(
            self.weekly_km, bool
        ):
            raise ValueError(
                f"weekly_km 必须是数字，收到 {type(self.weekly_km).__name__}"
            )
        if not self.weekly_km > 0:
            raise ValueError(
                f"第 {self.week} 周的周跑量必须为正，收到 {self.weekly_km}"
            )
        if self.race_km is not None and not self.race_km > 0:
            raise ValueError(
                f"第 {self.week} 周的比赛距离必须为正，收到 {self.race_km}"
            )
        for item in self.part_km:
            if not isinstance(item, (int, float)) or isinstance(item, bool):
                raise ValueError(
                    f"第 {self.week} 周的 part_km 必须是数字，收到 {item!r}"
                )
            if item < 0:
                raise ValueError(
                    f"第 {self.week} 周的 part_km 里有负数 {item}；"
                    "逐次距离不能为负，否则合计能凑对但内容是错的"
                )

    @property
    def is_race_week(self) -> bool:
        return self.race_km is not None

    def has_long_run(self) -> bool:
        return any(s.intensity == "L" for s in self.sessions)


@dataclass(frozen=True)
class Finding:
    """一条问题记录。"""

    check: str
    """``cap`` / ``progression`` / ``race_volume`` / ``sum`` / ``incomplete`` / ``base``。"""
    severity: str
    """``error`` 或 ``warn``。两者都会让整表不通过。"""
    week: int | None
    message: str

    def as_dict(self) -> Dict[str, object]:
        return {
            "check": self.check,
            "severity": self.severity,
            "week": self.week,
            "message": self.message,
        }


@dataclass(frozen=True)
class PlanAudit:
    """一次整表审计的结果。

    ``passed`` 只在 ``findings`` 为空时为 ``True``。
    这不留余地是故意的：**任何一条没过的检查，都不许说成"这张表合规"**。
    """

    weeks: int
    checks: Tuple[str, ...]
    findings: Tuple[Finding, ...]
    volumes: Tuple[float, ...] = ()
    notes: Tuple[str, ...] = field(default_factory=tuple)

    @property
    def passed(self) -> bool:
        return not self.findings

    @property
    def errors(self) -> Tuple[Finding, ...]:
        return tuple(f for f in self.findings if f.severity == "error")

    @property
    def warnings(self) -> Tuple[Finding, ...]:
        return tuple(f for f in self.findings if f.severity == "warn")

    def summary(self) -> str:
        """一句话结论。可以直接贴进回答。"""
        if self.passed:
            return (
                f"通过：{self.weeks} 周，{len(self.checks)} 类检查全过"
                f"（{'、'.join(self.checks)}）"
            )
        errors = len(self.errors)
        warns = len(self.warnings)
        parts = []
        if errors:
            parts.append(f"{errors} 项错误")
        if warns:
            parts.append(f"{warns} 项提示")
        head = "、".join(parts)
        return (
            f"不通过：{self.weeks} 周里有 {head}；"
            "在修掉之前不可以说「合规」「0 违规」"
        )

    def report(self) -> str:
        """多行报告。"""
        lines = [self.summary()]
        for item in self.findings:
            where = "全局" if item.week is None else f"第 {item.week} 周"
            lines.append(f"  [{item.check}/{item.severity}] {where}：{item.message}")
        for note in self.notes:
            lines.append(f"  · {note}")
        return "\n".join(lines)

    def as_dict(self) -> Dict[str, object]:
        return {
            "weeks": self.weeks,
            "passed": self.passed,
            "checks": list(self.checks),
            "summary": self.summary(),
            "findings": [item.as_dict() for item in self.findings],
            "volumes": [round(v, 1) for v in self.volumes],
            "notes": list(self.notes),
        }


def _require_weeks(weeks: Iterable[WeekEntry]) -> Tuple[WeekEntry, ...]:
    items = tuple(weeks)
    if len(items) < 2:
        raise ValueError(
            f"至少需要 2 周才能判断加量节奏，收到 {len(items)} 周"
        )
    numbers = [w.week for w in items]
    if numbers != sorted(numbers):
        raise ValueError(f"周序号必须升序排列，收到 {numbers}")
    if len(set(numbers)) != len(numbers):
        raise ValueError(f"周序号有重复：{numbers}")
    return items


def plan_from_dict(payload: Dict[str, object]) -> Tuple[Tuple[WeekEntry, ...], Dict[str, object]]:
    """把一份 JSON 结构解析成 :func:`audit_plan` 的参数。

    这个格式是对外契约，agent 直接生成它即可，不必拼命令行。

    Parameters
    ----------
    payload : dict
        形如::

            {
              "sessions_per_week": 5,
              "base_source": "user",
              "every_weeks": 4,
              "weeks": [
                {"week": 1, "weekly_km": 24, "sessions": [["L", 8]]},
                {"week": 18, "weekly_km": 28.1, "race_km": 21.1}
              ]
            }

        ``sessions`` 里每一项是 ``[强度, 公里]`` 或 ``[强度, 公里, 备注]``。

    Returns
    -------
    (weeks, kwargs)
        可直接 ``audit_plan(weeks, **kwargs)``。

    Raises
    ------
    ValueError
        结构不对、缺字段、类型错误。
    """
    if not isinstance(payload, dict):
        raise ValueError(f"计划必须是 JSON 对象，收到 {type(payload).__name__}")
    raw_weeks = payload.get("weeks")
    if not isinstance(raw_weeks, list) or not raw_weeks:
        raise ValueError("weeks 必须是非空数组")

    weeks: list[WeekEntry] = []
    for index, item in enumerate(raw_weeks, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"weeks 第 {index} 项必须是对象")
        try:
            week = int(item["week"])
            weekly_km = float(item["weekly_km"])
        except KeyError as exc:
            raise ValueError(
                f"weeks 第 {index} 项缺少 {exc.args[0]!r}"
            ) from exc
        sessions = []
        for raw in item.get("sessions") or []:
            if not isinstance(raw, (list, tuple)) or len(raw) < 2:
                raise ValueError(
                    f"第 {week} 周的 sessions 项应为 [强度, 公里]，收到 {raw!r}"
                )
            sessions.append(Session(str(raw[0]), float(raw[1])))
        race_km = item.get("race_km")
        part_km = item.get("part_km") or ()
        weeks.append(
            WeekEntry(
                week=week,
                weekly_km=weekly_km,
                sessions=tuple(sessions),
                race_km=None if race_km is None else float(race_km),
                part_km=tuple(float(x) for x in part_km),
            )
        )

    try:
        spw = int(payload["sessions_per_week"])
    except KeyError as exc:
        raise ValueError("缺少 sessions_per_week（每周跑步次数）") from exc
    kwargs: Dict[str, object] = {
        "sessions_per_week": spw,
        "base_source": str(payload.get("base_source", "user")),
        "surface": str(payload.get("surface", "road")),
        "every_weeks": int(payload.get("every_weeks", 4)),
    }
    phase = payload.get("phase")
    if phase is not None:
        kwargs["phase"] = int(phase)
    return tuple(weeks), kwargs


def audit_plan(
    weeks: Sequence[WeekEntry],
    sessions_per_week: int,
    *,
    base_source: str = "user",
    paces: object | None = None,
    surface: str = "road",
    every_weeks: int = 4,
    phase: int | None = None,
) -> PlanAudit:
    """把整张周表跑一遍全部检查，只给一个结论。

    Parameters
    ----------
    weeks : Sequence[WeekEntry]
        逐周记录，至少 2 周，周序号升序。
    sessions_per_week : int
        每周跑步次数，用来折算每次最多能加多少公里（第 11 章 L2956）。
    base_source : str, optional
        起点周跑量从哪来：``"user"``（用户给的）、``"derived"``（由用户给的
        数据算出）、``"assumed"``（估的）。**``"assumed"`` 一定不通过**——
        估出来的起点不许拿来算"合规"。
    paces : PaceSet, optional
        给了就把分钟上限也纳入判断（见 :func:`daniels.dose.check_week`）。
    surface : str, optional
        ``"road"`` 或 ``"trail"``。
    every_weeks : int, optional
        两次加量至少隔几周，默认 4。
    phase : int, optional
        训练阶段，用于越野跑的 L 跑分支。

    Returns
    -------
    PlanAudit

    Raises
    ------
    ValueError
        周表为空、少于 2 周、序号乱序或重复，或 ``base_source`` 不在
        :data:`BASE_SOURCES` 里。

    Notes
    -----
    检查项一共六类：

    1. ``cap`` —— 每周逐次跑 :func:`daniels.dose.check_week`；
    2. ``incomplete`` —— 训练周缺长跑，长跑占比就没被检查，直接判不完整；
    3. ``race_volume`` —— 比赛周的周跑量必须 ≥ 比赛距离；
    4. ``sum`` —— 给了逐次距离就核对合计；
    5. ``progression`` —— 非比赛周的周跑量序列跑 :func:`daniels.deload.check_progression`；
    6. ``base`` —— 起点来源为 ``"assumed"`` 时给一条 warn。

    比赛周不参与第 5 项：比赛距离会把那一周的跑量顶上去，
    那不是一次"加量"。
    """
    items = _require_weeks(weeks)
    if base_source not in BASE_SOURCES:
        raise ValueError(
            f"base_source 只能是 {BASE_SOURCES}，收到 {base_source!r}"
        )
    if not isinstance(sessions_per_week, int) or isinstance(
        sessions_per_week, bool
    ):
        raise ValueError(
            f"sessions_per_week 必须是整数，"
            f"收到 {type(sessions_per_week).__name__}"
        )
    if sessions_per_week <= 0:
        raise ValueError(
            f"sessions_per_week 必须为正，收到 {sessions_per_week}"
        )

    findings: list[Finding] = []
    notes_race: list[str] = []
    #: 实际跑过的检查。**必须动态填**——写死成六项的话，某项没跑也会被算进去，
    #: 那就是拿部分校验冒充整表结论，正是这个模块要防的事。
    checks: list[str] = ["cap", "incomplete", "race_volume", "sum"]

    for entry in items:
        # 1. 逐次上限。比赛周要把「比赛本身」排除掉——
        #    比赛不是长跑，不该受长跑上限约束。用距离相等识别。
        checked = list(entry.sessions)
        excluded: list[Session] = []
        if entry.race_km is not None:
            checked, excluded = (
                [s for s in checked if s.km < entry.race_km - 1e-9],
                [s for s in checked if s.km >= entry.race_km - 1e-9],
            )
        if checked:
            for violation in check_week(
                checked,
                entry.weekly_km,
                paces=paces,  # type: ignore[arg-type]
                surface=surface,
                phase=phase,
            ):
                findings.append(
                    Finding(
                        check="cap",
                        severity="error",
                        week=entry.week,
                        message=violation.message,
                    )
                )
        if excluded:
            notes_race.append(
                f"第 {entry.week} 周：比赛本身（{entry.race_km:.1f} km）"
                "不参与上限判断"
            )

        # 2. 完整性：训练周必须给出长跑
        if not entry.is_race_week and not entry.has_long_run():
            findings.append(
                Finding(
                    check="incomplete",
                    severity="error",
                    week=entry.week,
                    message=(
                        "训练周没有长跑（L）。长跑占比是这张表最容易被突破的一条，"
                        "少写一次就跑不了，所以判为不完整"
                    ),
                )
            )
        elif entry.is_race_week and not entry.has_long_run():
            pass  # 比赛周本来就没有长跑

        # 3. 比赛周的周跑量
        if entry.race_km is not None:
            if entry.weekly_km < entry.race_km - 1e-9:
                findings.append(
                    Finding(
                        check="race_volume",
                        severity="error",
                        week=entry.week,
                        message=(
                            f"周跑量 {entry.weekly_km:.1f} km 小于比赛距离 "
                            f"{entry.race_km:.1f} km，这张表算不平"
                        ),
                    )
                )

        # 4. 逐次合计
        if entry.part_km:
            total = sum(entry.part_km)
            if abs(total - entry.weekly_km) > 0.05:
                findings.append(
                    Finding(
                        check="sum",
                        severity="error",
                        week=entry.week,
                        message=(
                            f"逐次距离合计 {total:.1f} km，"
                            f"与周跑量 {entry.weekly_km:.1f} km 不符"
                        ),
                    )
                )

    # 5. 加量节奏：比赛周不参与
    training = [w for w in items if not w.is_race_week]
    if len(training) >= 2:
        checks.append("progression")
        issues = check_progression(
            [w.weekly_km for w in training],
            sessions_per_week,
            every_weeks=every_weeks,
        )
        for issue in issues:
            week = training[issue.week_index - 1].week
            findings.append(
                Finding(
                    check="progression",
                    severity="error",
                    week=week,
                    message=issue.reason,
                )
            )
    else:
        # 只有 1 个训练周时，加量节奏无从判断。这一项没跑就**不能算出结论**：
        # 以前这里会静默跳过，然后照样在报告里写「六类检查全过」。
        findings.append(
            Finding(
                check="incomplete",
                severity="error",
                week=None,
                message=(
                    f"非比赛周只有 {len(training)} 个，加量节奏无法判断。"
                    "这一项没跑，整表就不成立——至少要有 2 个训练周"
                ),
            )
        )

    # 6. 起点来源
    checks.append("base")
    if base_source == "assumed":
        findings.append(
            Finding(
                check="base",
                severity="warn",
                week=None,
                message=(
                    "起点周跑量是估的，不是用户给的。整张表可以算，"
                    "但不能说它合规——起点一动，全表平移"
                ),
            )
        )

    notes = [
        f"加量节奏只取非比赛周的 {len(training)} 周；"
        f"单次加量的上限是 {sessions_per_week * 1.6:.1f} km"
        f"（每次 +1.6 km × {sessions_per_week} 次出勤），"
        f"两次加量至少隔 {every_weeks} 周。"
        "这是上限不是步长：表里实际每步小一点不算违规",
    ]
    notes.extend(notes_race)
    if base_source != "assumed":
        notes.append(f"起点来源：{base_source}")

    return PlanAudit(
        weeks=len(items),
        checks=tuple(checks),
        findings=tuple(findings),
        volumes=tuple(w.weekly_km for w in items),
        notes=tuple(notes),
    )
