# -*- coding: utf-8 -*-
"""公开表面的补测：那些「写了但没人跑过」的分支。

这一组不是按模块切的，是按**测覆盖率时发现的空洞**切的：用 stdlib `trace`
跑完 544 条测试，有 112 条语句一次都没执行。绝大多数是烂输入的报错分支
（低危），但有十几处是**公开 API 和 CLI 接线**：

* ``Pace`` 的派生属性（kph / mph / 各种 format）
* ``DoseCap.binding()`` 的 "minutes" 与 "equal" 两个分支
* 越野 L 跑的两个分支（阶段一 60 分钟、阶段二 25%）
* ``IntakeState.next_layer()``
* ``week_taper`` 省略 ``race_week`` 时的默认值
* CLI 的 ``intake`` 参数映射、``cite --search/--list``、``audit -``（读标准输入）

这些都是别人会直接调的东西。没人跑过就等于没验过。
"""

from __future__ import annotations

import argparse
import io
import json
import unittest
from contextlib import redirect_stderr, redirect_stdout

import daniels as d
from daniels.__main__ import main


def run(*argv: str, stdin: str | None = None) -> tuple:
    out, err = io.StringIO(), io.StringIO()
    old_stdin = None
    if stdin is not None:
        import sys

        old_stdin = sys.stdin
        sys.stdin = io.StringIO(stdin)
    try:
        with redirect_stdout(out), redirect_stderr(err):
            code = main(list(argv))
    finally:
        if old_stdin is not None:
            import sys

            sys.stdin = old_stdin
    return code, out.getvalue(), err.getvalue()


class TestPaceSurface(unittest.TestCase):
    """``Pace`` 的派生属性与格式化方法。"""

    def setUp(self) -> None:
        self.t = d.pace_set(50.0).t

    def test_kph_and_mph(self) -> None:
        self.assertAlmostEqual(self.t.kph, 3600 / self.t.seconds_per_km, places=6)
        self.assertAlmostEqual(self.t.mph, self.t.kph / 1.609344, places=6)
        self.assertGreater(self.t.kph, self.t.mph)

    def test_distance_in_and_time_for_are_inverse(self) -> None:
        seconds = 600.0
        meters = self.t.distance_in(seconds)
        self.assertAlmostEqual(self.t.time_for(meters), seconds, places=6)

    def test_format_methods_return_strings(self) -> None:
        for name in ("format_km", "format_400m", "format_mile"):
            with self.subTest(name=name):
                text = getattr(self.t, name)()
                self.assertIsInstance(text, str)
                self.assertIn(":", text)

    def test_format_400m_ceil_is_not_smaller(self) -> None:
        """取整方向上界：向上取整的结果不会比四舍五入短。"""
        floor_sec = self.t.format_400m()
        ceil_sec = self.t.format_400m_ceil()
        self.assertGreaterEqual(len(ceil_sec), len(floor_sec))

    def test_plus_seconds_per_400m(self) -> None:
        slower = self.t.plus_seconds_per_400m(5.0)
        self.assertAlmostEqual(
            slower.seconds_per_400m - self.t.seconds_per_400m, 5.0, places=6
        )
        self.assertGreater(slower.seconds_per_km, self.t.seconds_per_km)


class TestCapBinding(unittest.TestCase):
    """``DoseCap.binding()`` 的三个分支。"""

    def setUp(self) -> None:
        # 64 km 周：L 上限 16.0 km 或 150 分钟
        self.cap = d.long_run_cap(64.0)

    def test_binding_is_km_for_fast_pace(self) -> None:
        self.assertEqual(self.cap.binding(d.Pace(300.0)), "km")

    def test_binding_is_minutes_for_slow_pace(self) -> None:
        self.assertEqual(self.cap.binding(d.Pace(700.0)), "minutes")

    def test_binding_is_equal_at_the_crossover(self) -> None:
        """150 分钟正好等于 16 km 的那个配速。"""
        pace = d.Pace(150 * 60 / 16.0)  # 562.5 s/km
        self.assertEqual(self.cap.binding(pace), "equal")
        self.assertAlmostEqual(self.cap.limit_km(pace), 16.0, places=6)

    def test_limit_km_never_exceeds_distance_cap(self) -> None:
        for seconds in (200.0, 400.0, 700.0):
            with self.subTest(seconds=seconds):
                self.assertLessEqual(
                    self.cap.limit_km(d.Pace(seconds)), self.cap.max_km + 1e-9
                )

    def test_binding_is_none_without_any_cap(self) -> None:
        cap = d.threshold_cap(64.0)
        cap = d.DoseCap(
            intensity="T", max_km=None, max_minutes=None, rules=()
        )
        self.assertEqual(cap.binding(d.Pace(300.0)), "none")


class TestTrailLongRun(unittest.TestCase):
    """越野的 L 跑两个分支——分支 D 的实测就靠这两条。"""

    def test_phase_one_uses_sixty_minutes(self) -> None:
        cap = d.cap_for("L", 35.0, surface="trail", phase=1)
        self.assertEqual(cap.max_minutes, 60.0)
        self.assertAlmostEqual(cap.max_km, 10.5, places=6)
        ids = [r.rule_id for r in cap.rules]
        self.assertIn("D-L-05", ids)
        self.assertIn("D-L-04", ids)

    def test_phase_two_uses_twenty_five_percent(self) -> None:
        cap = d.cap_for("L", 35.0, surface="trail", phase=2)
        self.assertEqual(cap.ratio, 0.25)
        self.assertAlmostEqual(cap.max_km, 8.75, places=6)
        ids = [r.rule_id for r in cap.rules]
        self.assertIn("D-L-06", ids)

    def test_trail_is_stricter_than_road_below_64km(self) -> None:
        """64 km 以下公路走 30%，越野阶段二走 25%——越野更严。

        64 km 以上两者都是 25%，数值相同，差别只在规则编号与说明。
        """
        trail = d.cap_for("L", 35.0, surface="trail", phase=2).max_km
        road = d.long_run_cap(35.0).max_km
        self.assertLess(trail, road)

    def test_trail_equals_road_above_64km(self) -> None:
        trail = d.cap_for("L", 100.0, surface="trail", phase=2).max_km
        road = d.long_run_cap(100.0).max_km
        self.assertAlmostEqual(trail, road, places=6)


class TestIntakeSurface(unittest.TestCase):
    """``next_layer()`` 与几条被冷落的输入分支。"""

    def test_next_layer_zero_when_only_goal(self) -> None:
        self.assertEqual(d.IntakeState().set("goal_distance_km", 21.1).next_layer(), 0)

    def test_next_layer_none_when_complete(self) -> None:
        state = (
            d.IntakeState()
            .set("goal_distance_km", 21.1)
            .set("race_date", "2027-04-18")
            .set("red_flags", ())
            .set("weekly_km", 19.0)
            .set("longest_recent_km", 8.0)
            .set("days_per_week", 3)
        )
        self.assertIsNone(state.next_layer())

    def test_red_flags_accepts_a_bare_string(self) -> None:
        state = d.IntakeState().set("red_flags", "膝盖疼")
        self.assertEqual(state.red_flags(), ("膝盖疼",))

    def test_will_test_is_coerced_to_bool(self) -> None:
        self.assertTrue(d.IntakeState().set("will_test", 1).answers["will_test"])
        self.assertFalse(d.IntakeState().set("will_test", 0).answers["will_test"])

    def test_altitude_accepts_units(self) -> None:
        for text in ("1500", "1500m", "1500 米"):
            with self.subTest(text=text):
                self.assertEqual(
                    d.IntakeState().set("altitude_m", text).get("altitude_m"),
                    1500.0,
                )

    def test_altitude_out_of_range(self) -> None:
        with self.assertRaises(ValueError):
            d.IntakeState().set("altitude_m", 9000)

    def test_brief_shows_stopped_reason(self) -> None:
        text = d.IntakeState().set("red_flags", ("膝盖疼",)).brief()
        self.assertIn("先停", text)


class TestWeekTaperDefault(unittest.TestCase):
    """``week_taper`` 省略 ``race_week`` 时，默认比赛在最后一周。"""

    def test_default_race_week_is_last(self) -> None:
        taper = d.week_taper(12, 12)
        self.assertTrue(taper.is_race_week)
        self.assertEqual(taper.weeks_to_race, 0)

    def test_bad_race_week(self) -> None:
        with self.assertRaises(ValueError):
            d.week_taper(5, 12, race_week=13)


class TestAuditKwargs(unittest.TestCase):
    """``audit_plan`` 里那两条没被跑过的分支。"""

    def test_race_session_is_excluded_with_a_note(self) -> None:
        weeks = (
            d.WeekEntry(week=1, weekly_km=30.0, sessions=(d.Session("L", 9.0),)),
            d.WeekEntry(
                week=2,
                weekly_km=21.1,
                sessions=(d.Session("L", 21.1),),
                race_km=21.1,
            ),
        )
        result = d.audit_plan(weeks, 4)
        joined = " ".join(result.notes)
        self.assertIn("不参与上限判断", joined)

    def test_phase_kwarg_is_threaded_through(self) -> None:
        weeks = (
            d.WeekEntry(week=1, weekly_km=35.0, sessions=(d.Session("L", 10.5),)),
            d.WeekEntry(week=2, weekly_km=35.0, sessions=(d.Session("L", 10.5),)),
        )
        trail = d.audit_plan(
            weeks, 4, surface="trail", phase=2
        )
        self.assertFalse(trail.passed)  # 25% = 8.75，10.5 超了

    def test_as_dict_of_a_week_entry_bad_input(self) -> None:
        with self.assertRaises(ValueError):
            d.WeekEntry(week=0, weekly_km=30.0)


class TestSafetyGuards(unittest.TestCase):
    """那些「守着别人别出错」的分支——它们自己也得被跑过一次。"""

    def test_manifest_self_check_detects_a_dead_name(self) -> None:
        """`_self_check` 是清单的守卫：名字写错了要能报出来。

        这个分支只有在清单写错时才执行，正常跑测试永远碰不到。
        用打桩把它逼出来，确认守卫真的是守卫。
        """
        import importlib
        from unittest import mock

        mm = importlib.import_module("daniels.manifest")
        fake = {"layers": {"vdot": ["vdot_from_race", "根本没有这个函数"]}}
        with mock.patch.object(mm, "manifest", return_value=fake):
            problems = mm._self_check()
        self.assertEqual(len(problems), 1)
        self.assertIn("根本没有这个函数", problems[0])

    def test_self_check_passes_on_the_real_manifest(self) -> None:
        import importlib

        mm = importlib.import_module("daniels.manifest")
        self.assertEqual(mm._self_check(), [])

    def test_citation_label_falls_back_when_empty(self) -> None:
        item = d.Citation(key="x", chapter="", lines="", summary="占位")
        self.assertEqual(item.label, "（无出处）")

    def test_citation_str(self) -> None:
        self.assertIn("第14章 L3478", str(d.cite("D-T-02")))


class TestCliRedFlag(unittest.TestCase):
    """`intake` 命中红线时的 CLI 出口，以及几条约不到的路。"""

    def test_red_flag_exits_with_findings(self) -> None:
        code, out, _ = run(
            "intake", "--goal", "21.1", "--date", "2027-04-18",
            "--weekly", "19", "--longest", "8", "--days", "3",
            "--red-flag", "膝盖疼", "--result", "5k 28:12",
        )
        self.assertEqual(code, 2)
        self.assertIn("先停", out)

    def test_will_test_path(self) -> None:
        code, _, _ = run(
            "intake", "--goal", "21.1", "--date", "2027-04-18",
            "--weekly", "19", "--longest", "8", "--days", "3",
            "--no-red-flag", "--will-test",
        )
        self.assertEqual(code, 1)  # 没有成绩 -> need_result

    def test_cite_search_without_hits(self) -> None:
        code, out, _ = run("cite", "--search", "量子力学与红烧肉")
        self.assertEqual(code, 0)
        self.assertIn("没有匹配", out)

    def test_trail_phase_three_note(self) -> None:
        """阶段三、四走 trail 时会附一条「沿用 25%」的说明。"""
        cap = d.cap_for("L", 35.0, surface="trail", phase=3)
        self.assertTrue(any("25%" in note for note in cap.notes))


class TestCliPlumbing(unittest.TestCase):
    """CLI 的参数映射与几条少走的路径。"""

    def test_intake_full_mapping(self) -> None:
        code, _, err = run(
            "intake", "--goal", "21.1", "--date", "2027-04-18",
            "--weekly", "19", "--longest", "8", "--days", "3",
            "--no-red-flag", "--result", "5k 28:12",
        )
        self.assertEqual(code, 0, err)

    def test_intake_json(self) -> None:
        code, out, _ = run("intake", "--goal", "21.1", "--json")
        self.assertEqual(code, 1)  # need_info
        payload = json.loads(out)
        self.assertEqual(payload["code"], "need_info")
        self.assertIn("red_flags", payload["missing"])

    def test_intake_surface_and_altitude(self) -> None:
        code, _, err = run(
            "intake", "--goal", "21.1", "--date", "2027-04-18",
            "--weekly", "19", "--longest", "8", "--days", "3",
            "--no-red-flag", "--surface", "trail", "--altitude", "1500",
            "--result", "5k 28:12",
        )
        self.assertEqual(code, 0, err)

    def test_cite_search(self) -> None:
        code, out, _ = run("cite", "--search", "长跑", "--limit", "2")
        self.assertEqual(code, 0)
        self.assertIn("D-L-", out)

    def test_cite_list(self) -> None:
        code, out, _ = run("cite", "--list")
        self.assertEqual(code, 0)
        self.assertIn("altitude", out)

    def test_cite_without_arguments(self) -> None:
        code, _, err = run("cite")
        self.assertEqual(code, 1)
        self.assertIn("规则号", err)

    def test_audit_from_stdin(self) -> None:
        payload = json.dumps(
            {
                "sessions_per_week": 4,
                "base_source": "user",
                "weeks": [
                    {"week": 1, "weekly_km": 30, "sessions": [["L", 9]]},
                    {"week": 2, "weekly_km": 30, "sessions": [["L", 9]]},
                ],
            }
        )
        code, out, _ = run("audit", "-", stdin=payload)
        self.assertEqual(code, 0)
        self.assertIn("通过", out)

    def test_audit_bad_json_is_a_clean_error(self) -> None:
        code, _, err = run("audit", "-", stdin="{not json")
        self.assertEqual(code, 1)

    def test_calendar_without_any_option(self) -> None:
        """两天后就比赛，任何计划长度都放不下。"""
        code, out, _ = run(
            "calendar", "--race", "2026-11-15", "--today", "2026-11-13"
        )
        self.assertEqual(code, 1)
        self.assertIn("没有还来得及", out)

    def test_json_subcommands_emit_valid_json(self) -> None:
        for argv in (
            ("deload", "--base", "35", "--weeks", "12", "--json"),
            ("calendar", "--race", "2027-04-18", "--today", "2026-11-13",
             "--json"),
            ("taper", "--weeks", "12", "--json"),
            ("progression", "30", "30", "--sessions", "4", "--json"),
            ("cite", "D-T-02", "--json"),
        ):
            with self.subTest(command=argv[0]):
                code, out, err = run(*argv)
                self.assertIn(code, (0, 2), err)
                json.loads(out)


if __name__ == "__main__":
    unittest.main()
