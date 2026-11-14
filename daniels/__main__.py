# -*- coding: utf-8 -*-
"""命令行入口。

    python -m daniels paces 49.8
    python -m daniels vdot 5k 20:00
    python -m daniels cap --weekly 64 T --vdot 49.8
    python -m daniels check --weekly 64 --vdot 49.8 L18 T9 I5
    python -m daniels plan 24
    python -m daniels deload --base 35 --weeks 12 --every 4 --race-week 12
    python -m daniels taper --weeks 12 --race-week 12
    python -m daniels progression 35 35 35 28 35 35 43 --sessions 4
    python -m daniels audit plan.json
    python -m daniels calendar --race 2027-04-18
    python -m daniels intake --goal 21.1 --date 2027-03-21 --weekly 19
    python -m daniels cite D-T-02
    python -m daniels explain "I 训练为什么只跑 3 到 5 分钟"
    python -m daniels manifest -o skill.json

退出码：三个值互斥，脚本可以据此分流。

* ``0`` 跑通了
* ``1`` 参数、格式或计算错误；``intake`` 还没就绪
* ``2`` 检查跑完了但**发现了问题**：超限、不合规、命中红线

``argparse`` 默认用 2 报「命令写错了」，会和「发现了问题」撞车——
一个 agent 分不清是它自己打错命令，还是这张表不合规。所以这里把用法错误改成了 1。
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import List, Optional, Sequence

import daniels as d

#: 常用距离的别名。键为小写输入。
DISTANCE_ALIASES = {
    "800": 800.0,
    "800m": 800.0,
    "1500": 1500.0,
    "1500m": 1500.0,
    "1600": 1600.0,
    "1600m": 1600.0,
    "mile": 1609.344,
    "1mile": 1609.344,
    "3k": 3000.0,
    "5k": 5000.0,
    "5km": 5000.0,
    "10k": 10000.0,
    "10km": 10000.0,
    "hm": 21097.5,
    "half": 21097.5,
    "fm": 42195.0,
    "marathon": 42195.0,
}


class CliError(Exception):
    """命令行层的可预期错误。"""


#: 退出码。三个值含义互斥，脚本可以据此分流。
EXIT_OK = 0
"""跑通了。"""
EXIT_ERROR = 1
"""参数、格式或计算错误；也可能表示接诊还没就绪。"""
EXIT_FINDINGS = 2
"""检查跑完了，**发现了问题**：超限、不合规、命中红线。

注意 ``argparse`` 默认也用 2 报「命令写错了」。那会和这个值撞车——
一个 agent 无法区分「我命令打错了」和「这张表不合规」。
所以下面把 ``argparse`` 的错误码改成了 1。
"""


class _Parser(argparse.ArgumentParser):
    """把用法错误的退出码从 2 改成 1，避免与"发现问题"撞车。"""

    def error(self, message: str) -> None:  # type: ignore[override]
        self.print_usage(sys.stderr)
        print(f"错误：{message}", file=sys.stderr)
        raise SystemExit(EXIT_ERROR)


def parse_distance(text: str) -> float:
    """把 ``5k`` / ``1600m`` / ``21097`` 解析成米。

    Raises
    ------
    CliError
        无法识别。
    """
    key = text.strip().lower()
    if key in DISTANCE_ALIASES:
        return DISTANCE_ALIASES[key]
    try:
        meters = float(key.rstrip("m"))
    except ValueError as exc:
        raise CliError(
            f"无法识别的距离：{text!r}。可用 {sorted(DISTANCE_ALIASES)} 或直接写米数"
        ) from exc
    if meters <= 0:
        raise CliError(f"距离必须为正，收到 {text!r}")
    return meters


def parse_session(text: str) -> d.Session:
    """把 ``L18`` / ``T:6.4`` 解析成一次训练。

    Raises
    ------
    CliError
        格式不对。
    """
    cleaned = text.strip().upper().replace(":", "")
    if len(cleaned) < 2 or cleaned[0] not in d.INTENSITIES:
        raise CliError(
            f"训练写法应为「强度+公里数」，例如 L18、T6.4；收到 {text!r}"
        )
    try:
        km = float(cleaned[1:])
    except ValueError as exc:
        raise CliError(f"无法解析公里数：{text!r}") from exc
    if km <= 0:
        raise CliError(f"公里数必须为正，收到 {text!r}")
    return d.Session(cleaned[0], km)


# ---------------------------------------------------------------------------
# 各子命令
# ---------------------------------------------------------------------------
def cmd_vdot(args: argparse.Namespace) -> int:
    distance = parse_distance(args.distance)
    seconds = d.parse_time(args.time)
    vdot = d.vdot_from_race(distance, seconds)
    print(f"距离 {distance:.0f} m，成绩 {d.format_time(seconds)}")
    print(f"VDOT = {vdot:.2f}")
    return EXIT_OK


def cmd_paces(args: argparse.Namespace) -> int:
    paces = d.pace_set(args.vdot, altitude_m=args.altitude)
    info = paces.as_dict()
    print(f"VDOT {info['vdot']}")
    print(f"  E   {info['E_per_km'][0]} ~ {info['E_per_km'][1]} /km")
    print(f"  M   {info['M_per_km']} /km")
    print(f"  T   {info['T_per_km']} /km（{info['T_per_400m']} /400m）")
    print(f"  I   {info['I_per_km']} /km（{info['I_per_400m']} /400m）")
    print(f"  R   {info['R_per_400m']} /400m（{info['R_per_200m']} /200m）")
    print(f"  FR  {info['FR_per_200m']} /200m")
    print(f"  H   {info['H_per_km']} /km")
    print(
        f"  秒差  I−R {info['step_I_minus_R_s_per_400m']}s /400m，"
        f"T−I {info['step_T_minus_I_s_per_400m']}s /400m"
    )
    if info["altitude_m"]:
        print(
            f"  海拔 {info['altitude_m']:.0f} m：I/T/M 每 400 m 加 "
            f"{info['altitude_penalty_s_per_400m']} 秒"
        )
    if info["novice"]:
        print(f"  书中新手表：M {info['novice_M_per_km']} /km（更保守）")
    return EXIT_OK


def cmd_cap(args: argparse.Namespace) -> int:
    cap = d.cap_for(
        args.intensity,
        args.weekly,
        surface=args.surface,
        phase=args.phase,
    )
    paces = d.pace_set(args.vdot) if args.vdot else None
    pace = None
    if paces is not None:
        pace = paces.e_slow if args.intensity == "L" else getattr(
            paces, args.intensity.lower()
        )
    print(json.dumps(cap.as_dict(pace), ensure_ascii=False, indent=2))
    return EXIT_OK


def cmd_check(args: argparse.Namespace) -> int:
    sessions = [parse_session(text) for text in args.sessions]
    paces = d.pace_set(args.vdot) if args.vdot else None
    violations = d.check_week(
        sessions, args.weekly, paces=paces, surface=args.surface, phase=args.phase
    )
    if not violations:
        print(f"合规：{len(sessions)} 次训练，周跑量 {args.weekly:g} km")
        return EXIT_OK
    print(f"发现 {len(violations)} 处超限：")
    for item in violations:
        print(f"  [{','.join(item.rule_ids)}] {item.message}")
    return EXIT_FINDINGS


def cmd_plan(args: argparse.Namespace) -> int:
    plan = d.plan_schedule(
        args.weeks, allow_undocumented=args.allow_undocumented
    )
    print(json.dumps(plan.as_dict(), ensure_ascii=False, indent=2))
    print()
    print(f"默认 Q 日：{d.quality_days(3)} -> "
          f"{[d.WEEK_DAYS[x - 1] for x in d.quality_days(3)]}")
    return EXIT_OK


def cmd_deload(args: argparse.Namespace) -> int:
    drop = args.drop / 100.0
    impact = d.deload_impact(args.base, drop, surface=args.surface, phase=args.phase)
    rhythm = d.deload_weeks(
        args.weeks,
        args.every,
        drop_fraction=drop,
        race_week=args.race_week,
        taper_window=args.taper_window,
    )
    if args.json:
        print(
            json.dumps(
                {
                    "provenance": d.DELOAD_PROVENANCE,
                    "impact": [item.as_dict() for item in impact],
                    "rhythm": rhythm.as_dict(),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return EXIT_OK

    print("来源（必须先说明）：")
    print(f"  {d.DELOAD_PROVENANCE['book_position']}")
    print(f"  {d.DELOAD_PROVENANCE['misuse']}")
    print()
    print(
        f"训练周 {args.base:g} km -> 减量周 {args.base * (1 - drop):.1f} km"
        f"（降 {args.drop:g}%）"
    )
    for item in impact:
        mark = ""
        if item.collapses:
            mark = f"  × 低于 {item.min_km:.1f} km 单次下限，这一周排不了"
        elif not item.feasible_after and not item.feasible_before:
            mark = f"  × 训练周本身就已经低于 {item.min_km:.1f} km 下限"
        print(
            f"  {item.intensity}  单次上限 {item.base_cap_km:5.2f} -> "
            f"{item.deload_cap_km:5.2f} km{mark}"
        )
    survivors = [
        item.intensity for item in impact if item.feasible_after
    ]
    print(f"  减量周仍可练的强度：{'/'.join(survivors) if survivors else '无'}")
    t_cap = d.threshold_cap(1.0)
    floor_km = t_cap.min_km or 4.8
    ratio = t_cap.ratio or 0.10
    print(
        f"  T 的单次下限是 {floor_km:.1f} km，因此 T 需要训练周 ≥ "
        f"{floor_km / ratio:.0f} km、减量周 ≥ "
        f"{d.t_peak_km(floor_km, drop):.0f} km（按峰值计）"
    )
    print()
    print(f"减量周：第 {list(rhythm.weeks)} 周（名义 {rhythm.nominal_count} 个）")
    for week, reason in rhythm.skipped:
        print(f"  第 {week} 周不设减量：{reason}")
    for note in rhythm.notes:
        print(f"  · {note}")
    return EXIT_OK


def cmd_taper(args: argparse.Namespace) -> int:
    # --race-week 是可选的，缺省就是最后一周。不补这个默认值的话，
    # `taper --weeks 12` 会在 range(1, None + 1) 上直接崩。
    race_week = args.race_week if args.race_week is not None else args.weeks
    if not 1 <= race_week <= args.weeks:
        raise CliError(
            f"--race-week 必须在 1~{args.weeks} 之间，收到 {race_week}"
        )
    if args.week is not None:
        weeks = [args.week]
    else:
        weeks = list(range(1, race_week + 1))
    items = [
        d.week_taper(w, args.weeks, race_week=race_week) for w in weeks
    ]
    if args.json:
        payload = (
            items[0].as_dict() if args.week is not None
            else [item.as_dict() for item in items]
        )
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return EXIT_OK
    for item in items:
        flags = []
        if item.is_race_week:
            flags.append("比赛周")
        if item.drop_strides:
            flags.append("去跨步")
        if item.drop_hills:
            flags.append("去跑坡")
        if item.long_run_minutes_cap is not None:
            flags.append(f"L≤{item.long_run_minutes_cap:.0f}min")
        print(
            f"第 {item.week_index:>2} 周  距赛 {item.weeks_to_race:>2} 周  "
            f"{'（无）' if not flags else '、'.join(flags)}"
        )
    print()
    for note in items[-1].notes:
        print(f"  · {note}")
    print(f"  · {d.taper_rules().conflict_note}")
    return EXIT_OK


def cmd_progression(args: argparse.Namespace) -> int:
    issues = d.check_progression(
        args.volumes, args.sessions, every_weeks=args.every
    )
    if args.json:
        print(
            json.dumps(
                [item.as_dict() for item in issues],
                ensure_ascii=False,
                indent=2,
            )
        )
        return 2 if issues else 0
    if not issues:
        print(
            f"合规：{len(args.volumes)} 周的表没有违反加量规则"
            f"（每次最多 +1.6 km × {args.sessions} 次 = "
            f"{d.volume_step_km(args.sessions):.1f} km，"
            f"两次加量至少隔 {args.every} 周）"
        )
        return EXIT_OK
    print(f"发现 {len(issues)} 处违规：")
    for item in issues:
        print(
            f"  第 {item.week_index} 周 {item.from_km:g} -> {item.to_km:g} km："
            f"{item.reason}"
        )
    return EXIT_FINDINGS


def cmd_audit(args: argparse.Namespace) -> int:
    """读一份周表并裁决。

    JSON 报错要说人话。原来直接把 ``json`` 模块的原文喷给用户——
    「Expecting property name enclosed in double quotes: line 1 column 2」，
    对写表的人没有任何指向性。
    """
    where = "标准输入" if args.plan == "-" else args.plan
    try:
        if args.plan == "-":
            payload = json.load(sys.stdin)
        else:
            with open(args.plan, encoding="utf-8") as handle:
                payload = json.load(handle)
    except json.JSONDecodeError as exc:
        raise CliError(
            f"{where}不是合法 JSON：第 {exc.lineno} 行第 {exc.colno} 列，"
            f"{exc.msg}。\n"
            "  常见原因：\n"
            "  · 在 cmd / PowerShell 里手打 JSON，引号被 shell 吃掉了"
            "——请写进文件再传路径\n"
            "  · 用了单引号（JSON 只认双引号）\n"
            "  · 文件里有中文逗号、中文引号\n"
            "  格式见 docs/test-runs/plan.json"
        ) from None
    except FileNotFoundError:
        raise CliError(f"找不到文件：{where}") from None
    except OSError as exc:
        raise CliError(f"读不了 {where}：{exc.strerror or exc}") from None
    weeks, kwargs = d.plan_from_dict(payload)
    result = d.audit_plan(weeks, **kwargs)  # type: ignore[arg-type]
    if args.json:
        print(json.dumps(result.as_dict(), ensure_ascii=False, indent=2))
    else:
        print(result.report())
    return EXIT_OK if result.passed else EXIT_FINDINGS


def cmd_intake(args: argparse.Namespace) -> int:
    state = d.IntakeState()
    if args.goal is not None:
        state.set("goal_distance_km", args.goal)
    if args.date:
        state.set("race_date", args.date)
    if args.result:
        distance = parse_distance(args.result.split()[0])
        seconds = d.parse_time(args.result.split()[1])
        state.set("recent_result", (distance, seconds))
    if args.will_test:
        state.set("will_test", True)
    if args.weekly is not None:
        state.set("weekly_km", args.weekly)
    if args.longest is not None:
        state.set("longest_recent_km", args.longest)
    if args.days is not None:
        state.set("days_per_week", args.days)
    if args.red_flag:
        state.set("red_flags", args.red_flag)
    elif args.no_red_flag:
        state.set("red_flags", ())
    if args.surface:
        state.set("surface", args.surface)
    if args.altitude is not None:
        state.set("altitude_m", args.altitude)

    status = state.status()
    if args.json:
        print(json.dumps(status.as_dict(), ensure_ascii=False, indent=2))
    else:
        print(state.brief())
    if status.code == "stopped":
        return EXIT_FINDINGS
    return EXIT_OK if status.code == "ready" else EXIT_ERROR


def cmd_cite(args: argparse.Namespace) -> int:
    if args.search:
        hits = d.search_citations(args.search, limit=args.limit)
        if not hits:
            print(f"没有匹配的出处：{args.search!r}")
            guesses = d.citations_did_you_mean(args.search)
            if guesses:
                print("  你是不是想问：")
                for item in guesses:
                    print(f"    {item.key:<10} {item.label:<28} {item.summary}")
            print("  用 `python -m daniels cite --list` 看全部。")
            return EXIT_OK
        for item in hits:
            print(f"{item.key:<10} {item.label:<30} {item.summary}")
        return EXIT_OK
    if args.list:
        for item in d.citations():
            print(f"{item.key:<10} {item.label:<30} {item.summary}")
        return EXIT_OK
    if not args.rule:
        raise CliError("要给规则号（如 D-T-02），或用 --search / --list")
    item = d.cite(args.rule)
    if args.json:
        print(json.dumps(item.as_dict(), ensure_ascii=False, indent=2))
    else:
        print(f"{item.key}  {item.label}")
        print(f"  {item.summary}")
    return EXIT_OK


def cmd_calendar(args: argparse.Namespace) -> int:
    from datetime import date

    today = _parse_date("today", args.today) if args.today else date.today()
    race = _parse_date("race", args.race)
    weeks, days = d.weeks_until(today, race)
    options = d.feasible_plans(
        today,
        race,
        documented_only=args.documented_only,
        include_past=args.include_past,
    )
    if args.json:
        print(
            json.dumps(
                {
                    "today": today.isoformat(),
                    "race_date": race.isoformat(),
                    "total_days": (race - today).days,
                    "weeks_until": weeks,
                    "leftover_days": days,
                    "options": [item.as_dict() for item in options],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return EXIT_OK
    print(f"今天 {today}，比赛 {race}（周{'一二三四五六日'[race.weekday()]}）")
    print(f"相距 {(race - today).days} 天 = {weeks} 周 {days} 天")
    longest = d.max_plan_weeks(today, race)
    print(
        f"能排的最长计划 = {longest} 周"
        f"（起点 {d.plan_window(longest, race)[0] if longest >= 1 else '—'}）"
        "；注意这和上面的「几周几天」是两个口径"
    )
    print()
    if not options:
        print("这本书里没有还来得及的长度。要么换比赛，要么接受均分推导。")
        return EXIT_ERROR
    for item in options:
        info = item.as_dict()
        split = ""
        if item.split:
            split = f"  阶段 {item.split}"
        flag = "  ← 起点已过去" if item.starts_in_past else ""
        print(
            f"  {item.weeks:>2} 周  起点 {item.start_date}"
            f"（周{info['weekday_of_start']}）"
            f"{'' if item.documented else '  书中无记录'}{split}{flag}"
        )
    print()
    print("书中记录的长度：3/6/9/12/20/23/24 周；其余长度要显式允许均分推导。")
    return EXIT_OK


def _parse_date(name: str, text: str):
    """解析 ``YYYY-MM-DD``。"""
    from datetime import date

    try:
        return date.fromisoformat(text.strip())
    except ValueError as exc:
        raise CliError(
            f"{name} 日期格式应为 YYYY-MM-DD，收到 {text!r}"
        ) from exc


def cmd_explain(args: argparse.Namespace) -> int:
    # 先过边界闸门：落在书里没有数据的区域，答「没有」比答「最像的那条」正确。
    gate = d.boundary(args.query)
    hits = d.search(args.query, limit=args.limit)
    if gate is not None:
        print(f"■ {gate.question}")
        print(f"  {gate.answer}")
        print(f"  依据：{gate.basis}")
        if hits:
            print()
            print("  相关但不是这个问题的答案：")
            for topic in hits:
                print(f"    · {topic.question}")
        print()
        return EXIT_OK
    if not hits:
        print(f"没有匹配的词条：{args.query!r}")
        guesses = d.explain_did_you_mean(args.query)
        if guesses:
            print("  你是不是想问：")
            for topic in guesses:
                print(f"    {topic.question}")
        print("  用 `python -m daniels topics` 查看全部。")
        return EXIT_OK
    for topic in hits:
        print(f"■ {topic.question}")
        print(f"  {topic.answer}")
        print(f"  出处：{'、'.join(topic.sources)}")
        if topic.computed_by:
            print(f"  可算：daniels.{topic.computed_by}")
        print()
    return EXIT_OK


def cmd_topics(args: argparse.Namespace) -> int:
    for topic_id in d.topic_ids():
        print(f"{topic_id:<32}{d.TOPICS[topic_id].question}")
    print()
    print("边界（书里没有数据，正确回答是「不做」）：")
    for item in d.BOUNDARIES:
        print(f"{item.boundary_id:<32}{item.question}")
    return EXIT_OK


def cmd_manifest(args: argparse.Namespace) -> int:
    text = json.dumps(d.manifest(), ensure_ascii=False, indent=2)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as handle:
            handle.write(text + "\n")
        print(f"已写入 {args.output}")
    else:
        print(text)
    return EXIT_OK


# ---------------------------------------------------------------------------
# 解析器
# ---------------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    parser = _Parser(
        prog="python -m daniels",
        description="丹尼尔斯跑步训练法知识库：配速、训练量上限、周期安排",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("vdot", help="由比赛成绩求 VDOT")
    p.add_argument("distance", help="距离，如 5k / 1600m / mile / 21097")
    p.add_argument("time", help="成绩，如 20:00 / 1:02:05")
    p.set_defaults(func=cmd_vdot)

    p = sub.add_parser("paces", help="按 VDOT 给出五档配速")
    p.add_argument("vdot", type=float)
    p.add_argument("--altitude", type=float, default=0.0, help="海拔（米）")
    p.set_defaults(func=cmd_paces)

    p = sub.add_parser("cap", help="单次训练的量上限")
    p.add_argument("weekly", type=float, help="周跑量（公里）")
    p.add_argument("intensity", choices=list(d.INTENSITIES))
    p.add_argument("--vdot", type=float, help="给了就同时折算时间上限")
    p.add_argument("--surface", choices=["road", "trail"], default="road")
    p.add_argument("--phase", type=int, choices=[1, 2, 3, 4])
    p.set_defaults(func=cmd_cap)

    p = sub.add_parser("check", help="整周合规检查")
    p.add_argument("sessions", nargs="+", help="如 L18 T9 I5")
    p.add_argument("--weekly", type=float, required=True)
    p.add_argument("--vdot", type=float)
    p.add_argument("--surface", choices=["road", "trail"], default="road")
    p.add_argument("--phase", type=int, choices=[1, 2, 3, 4])
    p.set_defaults(func=cmd_check)

    p = sub.add_parser("plan", help="阶段划分")
    p.add_argument("weeks", type=int)
    p.add_argument("--allow-undocumented", action="store_true")
    p.set_defaults(func=cmd_plan)

    p = sub.add_parser(
        "deload",
        help="周期性减量的算术（书中无此概念，属外推）",
    )
    p.add_argument("--base", type=float, required=True, help="训练周跑量 km")
    p.add_argument("--weeks", type=int, required=True, help="训练季总周数")
    p.add_argument("--every", type=int, default=4, help="每隔几周减一次")
    p.add_argument("--drop", type=float, default=20.0, help="减量百分比")
    p.add_argument("--race-week", type=int, help="比赛在第几周，默认最后一周")
    p.add_argument(
        "--taper-window", type=int, default=2, help="赛前减量窗口周数"
    )
    p.add_argument("--surface", choices=["road", "trail"], default="road")
    p.add_argument("--phase", type=int, choices=[1, 2, 3, 4])
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_deload)

    p = sub.add_parser("taper", help="赛前减量逐周动作")
    p.add_argument("--weeks", type=int, required=True, help="训练季总周数")
    p.add_argument("--race-week", type=int, help="比赛在第几周，默认最后一周")
    p.add_argument("--week", type=int, help="只看某一周")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_taper)

    p = sub.add_parser("progression", help="校验周跑量表是否违反加量规则")
    p.add_argument("volumes", nargs="+", type=float, help="逐周周跑量，km")
    p.add_argument("--sessions", type=int, required=True, help="每周跑步次数")
    p.add_argument("--every", type=int, default=4, help="两次加量至少隔几周")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_progression)

    p = sub.add_parser("audit", help="整张周表的统一裁决（不合规退出码 2）")
    p.add_argument("plan", help="计划 JSON 文件，- 表示从标准输入读")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_audit)

    p = sub.add_parser(
        "calendar", help="比赛日 ↔ 周数 ↔ 起点（日期一律查，不许手算）"
    )
    p.add_argument("--race", required=True, help="比赛日 YYYY-MM-DD")
    p.add_argument("--today", help="今天 YYYY-MM-DD，默认取系统日期")
    p.add_argument(
        "--documented-only", action="store_true", help="只要书中记录过的长度"
    )
    p.add_argument(
        "--include-past", action="store_true", help="连起点已过去的也列出"
    )
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_calendar)

    p = sub.add_parser("intake", help="接诊：还缺哪些数据（未就绪退出码 1，红线退出码 2）")
    p.add_argument("--goal", type=float, help="目标距离 km，如 21.1")
    p.add_argument("--date", help="比赛日期，如 2027-03-21")
    p.add_argument("--result", help="近期成绩，如 '5k 28:12'")
    p.add_argument("--will-test", action="store_true", help="愿意去测一次计时")
    p.add_argument("--weekly", type=float, help="当前周跑量 km")
    p.add_argument("--longest", type=float, help="最近最长一次 km")
    p.add_argument("--days", type=int, help="每周可跑步天数")
    p.add_argument("--red-flag", action="append", help="伤病/手术/怀孕/心血管，可多次给")
    p.add_argument("--no-red-flag", action="store_true", help="明确表示没有上述问题")
    p.add_argument("--surface", choices=["road", "trail"])
    p.add_argument("--altitude", type=float, help="海拔 m")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_intake)

    p = sub.add_parser("cite", help="查规则出处（行号只许查，不许手写）")
    p.add_argument("rule", nargs="?", help="规则号，如 D-T-02")
    p.add_argument("--search", help="按关键词找规则")
    p.add_argument("--list", action="store_true", help="列出全部出处")
    p.add_argument("--limit", type=int, default=5)
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_cite)

    p = sub.add_parser("explain", help="检索解释词条")
    p.add_argument("query")
    p.add_argument("--limit", type=int, default=2)
    p.set_defaults(func=cmd_explain)

    p = sub.add_parser("topics", help="列出全部词条 id")
    p.set_defaults(func=cmd_topics)

    p = sub.add_parser("manifest", help="导出清单 JSON")
    p.add_argument("-o", "--output", help="写入文件，默认打印到标准输出")
    p.set_defaults(func=cmd_manifest)

    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    """入口。返回退出码。"""
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    try:
        return int(args.func(args))
    except (CliError, d.DanielsError, ValueError, KeyError) as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return EXIT_ERROR


if __name__ == "__main__":
    sys.exit(main())
