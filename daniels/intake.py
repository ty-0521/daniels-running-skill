# -*- coding: utf-8 -*-
"""接诊门禁：缺一层就不许出数。

为什么要有这一层
----------------
十轮真实测试里，一半的错误都出在同一个地方：**输入不齐也能开口**。

* 用户只说「一周三次、每次 35 分钟」，它自己按 6:00/km 折成 **17–18 km**，
  后面四个结论全建在这个估出来的数上，一句没提这是估的；
* 用户从头到尾没说过比赛日期，它先后**编了两个**：2027-02-07、2027-06-27，
  而且都是先定周数、再倒推日期——顺序正好反了；
* 用户说的是一周三次，它给出的表是**五次**，写进标题，没问过。

这三件事都不是算错。是**不许算的时候算了**。

所以这一层的职责只有一个：**把「输入不齐」变成「算不出来」**，
而不是「算出一个看起来像结果的东西」。

用法
----
::

    state = IntakeState()
    state.set("goal_distance_km", 21.0975)
    status = state.status()
    if status.code != "ready":
        print(status.questions)      # 只问下一层缺的，不一次抛二十个
    else:
        paces = paces_from_intake(state)

设计上的一条硬规矩：**问题分批给**。一次抛二十个问题，真人会直接关掉。
:meth:`IntakeState.status` 只返回**最靠前的那一层**里缺的东西。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Dict, Tuple

from .vdot import DISTANCE_MAX_M, DISTANCE_MIN_M, PaceSet, pace_set, vdot_from_race

__all__ = [
    "FIELD_SPECS",
    "FIELD_BY_KEY",
    "IntakeState",
    "Status",
    "FieldSpec",
    "paces_from_intake",
]


@dataclass(frozen=True)
class FieldSpec:
    """一项问诊字段。"""

    key: str
    layer: int
    title: str
    question: str
    """可以直接照着问用户的原话。"""
    why: str
    """为什么非问不可。缺了它，什么算不出来。"""

    def as_dict(self) -> Dict[str, object]:
        return {
            "key": self.key,
            "layer": self.layer,
            "title": self.title,
            "question": self.question,
            "why": self.why,
        }


#: 问诊字段，按层排列。层内顺序就是提问顺序。
#:
#: 层的划分依据是**依赖关系**，不是重要性：上一层的答案决定下一层该不该问、
#: 怎么问。比如没有比赛日期，"还差几周"根本算不出来，问周数就是瞎问。
FIELD_SPECS: Tuple[FieldSpec, ...] = (
    FieldSpec(
        key="goal_distance_km",
        layer=0,
        title="目标距离",
        question="你想跑的比赛是多少公里？（5 公里、10 公里、半马 21.1、全马 42.2）",
        why="目标距离决定总周数和长跑上限，没有它排不出任何周表",
    ),
    FieldSpec(
        key="race_date",
        layer=0,
        title="比赛日期",
        question=(
            "比赛是哪一天？请给具体日期。如果还没定，也说一声——"
            "那我只给训练方向，不排周表"
        ),
        why=(
            "日期是起点，周数是结果。反过来的话（先定几周、再倒推日期）"
            "会把整张表的日历建立在编出来的日子上"
        ),
    ),
    FieldSpec(
        key="red_flags",
        layer=0,
        title="红线筛查",
        question=(
            "现在有没有疼痛、伤病、刚做过手术、怀孕，或者心血管方面的问题？"
            "有的话直接说，先不排计划"
        ),
        why=(
            "带伤训练这件事不该由一张周表决定。有红线就停，"
            "不是把跑量降 20% 继续"
        ),
    ),
    FieldSpec(
        key="recent_result",
        layer=1,
        title="近期成绩",
        question=(
            "最近 3 个月有没有一次尽力跑？给我距离和时间，"
            "例如「5 公里 28:12」。10 公里以上最准"
        ),
        why=(
            "所有配速都从 VDOT 来，VDOT 只能从一次计时的尽力跑算出来。"
            "「最长跑过 8 公里」是距离，不是成绩，换不出 VDOT"
        ),
    ),
    FieldSpec(
        key="will_test",
        layer=1,
        title="是否愿意测一次",
        question="如果没有成绩，愿不愿意这周去测一次 5 公里或 10 公里计时？",
        why="没有成绩又不测，配速一律填不出来，只能给不含配速的跑量骨架",
    ),
    FieldSpec(
        key="weekly_km",
        layer=2,
        title="当前周跑量",
        question="你现在一周跑多少公里？如果只知道时间，也请说清每次跑多少公里",
        why=(
            "所有训练量上限都是周跑量的百分比。只给分钟的话，"
            "必须再用配速折算——那一步是估，不是数据"
        ),
    ),
    FieldSpec(
        key="longest_recent_km",
        layer=2,
        title="最长一次",
        question="最近一个月最长一次跑了多少公里？",
        why="长跑从当前最长距离往上走，起点定错了整条长跑阶梯都错",
    ),
    FieldSpec(
        key="days_per_week",
        layer=2,
        title="可跑步天数",
        question="一周能拿出几天跑步？",
        why=(
            "书里的半马计划按每周 5~6 天排。你现在是 3 天的话，"
            "这不叫细节，叫换一种生活安排——必须你同意"
        ),
    ),
    FieldSpec(
        key="surface",
        layer=3,
        title="场地",
        question="主要在公路、越野小径，还是跑步机上跑？",
        why="越野的 L 跑上限比公路严得多（30%/60 分钟 对 30%/150 分钟）",
    ),
    FieldSpec(
        key="altitude_m",
        layer=3,
        title="海拔",
        question="训练地海拔大概多少米？",
        why="超过 914 米才需要修正；2500 米以上书里没有数据，会直接拒绝",
    ),
)

#: 按 key 索引，便于校验。
FIELD_BY_KEY: Dict[str, FieldSpec] = {spec.key: spec for spec in FIELD_SPECS}

#: 第 0~2 层是硬门禁；第 3 层的场地与海拔有默认值，不在必填里。
#:
#: 顺序与 :data:FIELD_SPECS 一致：**红线紧跟在目标和日期后面**。
#: 它必须比任何训练数据都先问到——带伤收集跑量是白费。
REQUIRED_KEYS: Tuple[str, ...] = (
    "goal_distance_km",
    "race_date",
    "red_flags",
    "weekly_km",
    "longest_recent_km",
    "days_per_week",
)

#: 有默认值的字段。
DEFAULTS: Dict[str, Any] = {"surface": "road", "altitude_m": 0.0}


@dataclass(frozen=True)
class Status:
    """一次问诊的结论。"""

    code: str
    """``stopped`` / ``contradictory`` / ``need_info`` / ``need_result`` / ``ready``。"""
    missing: Tuple[FieldSpec, ...] = ()
    stop_reason: str = ""
    contradictions: Tuple[str, ...] = ()
    """各字段之间对不上的地方。有它就停，不是"再问一句"能解决的。"""

    @property
    def can_build_plan(self) -> bool:
        """能不能开始排周表（不含配速）。"""
        return self.code in ("need_result", "ready")

    @property
    def can_fill_paces(self) -> bool:
        """能不能填配速。只有拿到成绩才行。"""
        return self.code == "ready"

    @property
    def questions(self) -> Tuple[str, ...]:
        """下一轮该问的话。只问最靠前那一层缺的。"""
        if self.code in ("stopped", "contradictory"):
            return ()
        return tuple(spec.question for spec in self.missing)

    def as_dict(self) -> Dict[str, object]:
        return {
            "code": self.code,
            "can_build_plan": self.can_build_plan,
            "can_fill_paces": self.can_fill_paces,
            "missing": [spec.key for spec in self.missing],
            "questions": list(self.questions),
            "stop_reason": self.stop_reason,
            "contradictions": list(self.contradictions),
        }


@dataclass
class IntakeState:
    """问诊进度。

    ``answers`` 里有没有某个 key，和那个 key 的值是不是空，是两件事：
    ``red_flags`` 必须**明确问过**，没问过就算缺；问过而回答"没有"，
    存成空元组即算完成。
    """

    answers: Dict[str, Any] = field(default_factory=dict)

    def set(self, key: str, value: Any) -> "IntakeState":
        """记录一项回答，返回自身便于链式调用。

        Raises
        ------
        KeyError
            字段名不存在。
        ValueError
            值不合法（距离、时间、天数、海拔越界）。
        """
        if key not in FIELD_BY_KEY:
            raise KeyError(
                f"没有这个字段：{key!r}，可用 {sorted(FIELD_BY_KEY)}"
            )
        self.answers[key] = _validate(key, value)
        return self

    def get(self, key: str, default: Any = None) -> Any:
        if key in self.answers:
            return self.answers[key]
        return DEFAULTS.get(key, default)

    def has(self, key: str) -> bool:
        """这一项是否**已经问过并得到回答**。"""
        return key in self.answers

    @property
    def race_date(self) -> date | None:
        """比赛日期，已经是 ``datetime.date``；没设时为 ``None``。

        可以直接喂给 :func:`daniels.dates.weeks_until` / ``feasible_plans``。
        """
        value = self.answers.get("race_date")
        return value if isinstance(value, date) else None

    def missing(self) -> Tuple[FieldSpec, ...]:
        """还缺哪些必填项（按层、按声明顺序）。"""
        return tuple(
            FIELD_BY_KEY[key]
            for key in REQUIRED_KEYS
            if key not in self.answers
        )

    def red_flags(self) -> Tuple[str, ...]:
        value = self.answers.get("red_flags") or ()
        if isinstance(value, str):
            return (value,) if value.strip() else ()
        return tuple(value)

    def contradictions(self) -> Tuple[str, ...]:
        """字段之间对不上的地方。

        每一项单独看都合法，合在一起就不成立。这类输入最危险：
        校验会全部通过，然后整张表建在一个不可能的前提上。

        两条规则：

        1. 周跑量不可能小于「最长一次」——一次跑不会比一周还多；
        2. 平均每次的距离不可能超过「最长一次」——最长是上界。
        """
        out: list[str] = []
        weekly = self.answers.get("weekly_km")
        longest = self.answers.get("longest_recent_km")
        days = self.answers.get("days_per_week")
        if weekly is not None and longest is not None:
            if float(weekly) < float(longest) - 1e-9:
                out.append(
                    f"周跑量 {float(weekly):g} km 小于最长一次 "
                    f"{float(longest):g} km：一次跑不可能比一周的总量还多"
                )
            elif days:
                average = float(weekly) / days
                if average > float(longest) + 1e-9:
                    out.append(
                        f"一周跑 {days} 天共 {float(weekly):g} km，平均每次 "
                        f"{average:.1f} km，但最长只跑过 {float(longest):g} km："
                        "平均值不可能超过最长"
                    )
        return tuple(out)

    def next_layer(self) -> int | None:
        """最靠前的、还有缺项的那一层。全齐时返回 ``None``。"""
        pending = self.missing()
        if not pending:
            return None
        return min(spec.layer for spec in pending)

    def status(self) -> Status:
        """给当前进度下结论。"""
        flags = self.red_flags()
        if flags:
            return Status(
                code="stopped",
                stop_reason=(
                    "提到「" + "、".join(flags) + "」：先停，去看医生或运动康复，"
                    "在此之前不排计划、不给训练量。带伤训练不该由一张周表决定"
                ),
            )

        bad = self.contradictions()
        if bad:
            return Status(code="contradictory", contradictions=bad)

        pending = self.missing()
        if pending:
            layer = min(spec.layer for spec in pending)
            return Status(
                code="need_info",
                missing=tuple(s for s in pending if s.layer == layer),
            )

        if not self.has("recent_result"):
            return Status(
                code="need_result",
                missing=(FIELD_BY_KEY["recent_result"],),
            )

        return Status(code="ready")

    def brief(self) -> str:
        """一张可以贴给用户看的接诊单。"""
        status = self.status()
        lines = [f"接诊状态：{status.code}"]
        for spec in FIELD_SPECS:
            if spec.key in self.answers:
                value = self.answers[spec.key]
                shown = "（无）" if value in ((), "", None) else value
                lines.append(f"  ✓ 第{spec.layer}层 {spec.title}：{shown}")
            elif spec.key in REQUIRED_KEYS:
                lines.append(f"  ✗ 第{spec.layer}层 {spec.title}：缺")
        if status.code == "stopped":
            lines.append(f"  ！{status.stop_reason}")
        elif status.code == "contradictory":
            lines.append("  ！数据对不上，先别往下走：")
            for item in status.contradictions:
                lines.append(f"    · {item}")
        elif status.questions:
            lines.append("  下一轮要问：")
            for question in status.questions:
                lines.append(f"    · {question}")
        if status.code == "need_result":
            lines.append(
                "  注意：现在可以排跑量骨架，但**配速一律空着**，"
                "并且必须说明这是不含配速的骨架"
            )
        return "\n".join(lines)


def _validate(key: str, value: Any) -> Any:
    """逐字段校验。宁可在这里报错，不要让它悄悄进到计算里。"""
    if key == "race_date":
        # 这是十六轮实测里闯祸最多的一个字段：被编过两次、被改过一次。
        # 它原来接受任何字符串——「明年3月」「2027/03/21」「2027-13-45」、空串，
        # 全都返回 ready。现在只收 ISO 日期，并且存成 date。
        if isinstance(value, date) and not isinstance(value, bool):
            return value
        if not isinstance(value, str):
            raise ValueError(
                f"比赛日期要写成字符串 'YYYY-MM-DD' 或 datetime.date，"
                f"收到 {type(value).__name__}"
            )
        text = value.strip()
        if not text:
            raise ValueError("比赛日期不能为空")
        try:
            return date.fromisoformat(text)
        except ValueError:
            raise ValueError(
                f"比赛日期要写成 YYYY-MM-DD（例如 2027-03-21），收到 {value!r}。"
                "如果还没定，就不要设这一项——缺着比填个模糊的好"
            ) from None
    if key == "goal_distance_km":
        _require_number(key, value)
        if not DISTANCE_MIN_M / 1000.0 <= float(value) <= DISTANCE_MAX_M / 1000.0:
            raise ValueError(
                f"目标距离必须在 {DISTANCE_MIN_M / 1000.0:g}~"
                f"{DISTANCE_MAX_M / 1000.0:g} km 之间，收到 {value}"
            )
        return float(value)
    if key == "recent_result":
        if value is None:
            return None
        try:
            distance, seconds = value
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"recent_result 必须是 (距离米, 秒数)，收到 {value!r}"
            ) from exc
        _require_number("距离", distance)
        _require_number("时间", seconds)
        if not DISTANCE_MIN_M <= float(distance) <= DISTANCE_MAX_M:
            raise ValueError(
                f"成绩距离必须在 {DISTANCE_MIN_M:.0f}~{DISTANCE_MAX_M:.0f} m，"
                f"收到 {distance}"
            )
        if not float(seconds) > 0:
            raise ValueError(f"成绩时间必须为正，收到 {seconds}")
        return (float(distance), float(seconds))
    if key == "weekly_km":
        _require_number(key, value)
        if not float(value) > 0:
            raise ValueError(f"周跑量必须为正，收到 {value}")
        return float(value)
    if key == "longest_recent_km":
        _require_number(key, value)
        if not float(value) > 0:
            raise ValueError(f"最长距离必须为正，收到 {value}")
        return float(value)
    if key == "days_per_week":
        if not isinstance(value, int) or isinstance(value, bool):
            raise ValueError(
                f"天数必须是整数，收到 {type(value).__name__}"
            )
        if not 1 <= value <= 14:
            raise ValueError(f"天数必须在 1~14 之间，收到 {value}")
        return value
    if key == "red_flags":
        if isinstance(value, str):
            return (value,) if value.strip() else ()
        return tuple(str(item) for item in value)
    if key == "will_test":
        return bool(value)
    if key == "surface":
        if value not in ("road", "trail"):
            raise ValueError(f"surface 只能是 road 或 trail，收到 {value!r}")
        return value
    if key == "altitude_m":
        if isinstance(value, str):
            # 允许「1500」「1500m」「1500 米」三种写法。
            # 早先这里只 strip 了单位却没转成数字，于是传字符串一定崩——
            # 那段代码看起来像在支持带单位的写法，其实从来没生效过。
            text = value.strip()
            for suffix in ("米", "m", "M"):
                if text.endswith(suffix):
                    text = text[: -len(suffix)]
                    break
            text = text.strip()
            try:
                value = float(text)
            except ValueError:
                raise ValueError(
                    f"海拔要写成数字，例如 1500 或 '1500m'，收到 {value!r}"
                ) from None
        _require_number(key, value)
        if not 0 <= float(value) <= 8848:
            raise ValueError(f"海拔必须在 0~8848 m 之间，收到 {value}")
        return float(value)
    return value


def _require_number(name: str, value: Any) -> None:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ValueError(f"{name} 必须是数字，收到 {type(value).__name__}")


def paces_from_intake(state: IntakeState) -> PaceSet:
    """由问诊结果直接给出配速。

    这是唯一一条从「用户说的话」到「配速表」的合法路径：
    没有成绩就走不到这里。

    Raises
    ------
    ValueError
        还没拿到可换算的成绩。
    """
    if not state.has("recent_result"):
        raise ValueError(
            "还没有计时的成绩，填不了配速。"
            "「最长跑过多少公里」换不出 VDOT——那需要一次尽力跑的距离和时间"
        )
    distance, seconds = state.answers["recent_result"]
    vdot = vdot_from_race(distance, seconds)
    return pace_set(vdot, altitude_m=state.get("altitude_m", 0.0) or 0.0)
