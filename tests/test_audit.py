# -*- coding: utf-8 -*-
"""整表审计的测试。

这一组守的是十轮里最顽固的那条毛病：**只跑一项校验，然后把那一项的结论
说成整张表的结论**。两次假"0 违规"都出在这里，所以这里断言的不是
"能查出问题"，而是"查不出问题的时候不许说合规"。

运行：
    cd D:\\training
    python -m unittest discover -s tests -v
"""

from __future__ import annotations

import json
import unittest

import daniels as d
from daniels.__main__ import main
import io
from contextlib import redirect_stderr, redirect_stdout


def run(*argv: str) -> tuple:
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = main(list(argv))
    return code, out.getvalue(), err.getvalue()


#: 实测出现过的那张 18 周表，原样保留。第 13 周加量只隔了 2 周。
INCORRECT_WEEKS = (
    [24] * 5 + [32] * 5 + [40] * 2 + [48] * 3 + [42, 34, 28.1]
)
INCORRECT_LONG = [8] * 5 + [10] * 5 + [12] * 2 + [14] * 3 + [11, 10]

#: 把加量点从 6/11/13 挪到 5/9/13、并把长跑压到 30% 以内的版本。
COMPLIANT_WEEKS = (
    [24] * 4 + [32] * 4 + [40] * 4 + [48] * 3 + [42, 34, 28.1]
)
COMPLIANT_LONG = (
    [7] * 4 + [9] * 4 + [12] * 4 + [14] * 3 + [11, 10]
)


def build(volumes, longs, race_week=18, race_km=21.1):
    """按周搭一张表。比赛周只有比赛，不占 ``longs`` 的位置。"""
    weeks = []
    long_iter = iter(longs)
    for index, volume in enumerate(volumes, start=1):
        if index == race_week:
            weeks.append(
                d.WeekEntry(
                    week=index,
                    weekly_km=volume,
                    sessions=(),
                    race_km=race_km,
                )
            )
            continue
        weeks.append(
            d.WeekEntry(
                week=index,
                weekly_km=volume,
                sessions=(d.Session("L", next(long_iter)),),
            )
        )
    return tuple(weeks)


class TestIncidentTable(unittest.TestCase):
    """实测那张 18 周表必须不通过。"""

    def test_fails(self) -> None:
        result = d.audit_plan(build(INCORRECT_WEEKS, INCORRECT_LONG), 5)
        self.assertFalse(result.passed)
        self.assertIn("不通过", result.summary())

    def test_progression_error_is_reported_at_week_13(self) -> None:
        result = d.audit_plan(build(INCORRECT_WEEKS, INCORRECT_LONG), 5)
        flagged = [
            f.week for f in result.errors if f.check == "progression"
        ]
        self.assertEqual(flagged, [13])

    def test_long_run_ratio_errors_present(self) -> None:
        """前 10 周 24/32 km 配 8/10 km 长跑，都超 30%。"""
        result = d.audit_plan(build(INCORRECT_WEEKS, INCORRECT_LONG), 5)
        flagged = {f.week for f in result.errors if f.check == "cap"}
        self.assertTrue({1, 5, 6, 10}.issubset(flagged))

    def test_race_volume_is_not_judged_as_long_run(self) -> None:
        """比赛周只有比赛，不该报长跑超限，也不该报缺少长跑。"""
        result = d.audit_plan(build(INCORRECT_WEEKS, INCORRECT_LONG), 5)
        week_18 = [f for f in result.errors if f.week == 18]
        self.assertEqual(week_18, [])

    def test_cannot_say_compliant(self) -> None:
        result = d.audit_plan(
            build(INCORRECT_WEEKS, INCORRECT_LONG), 5, base_source="assumed"
        )
        self.assertFalse(result.passed)
        text = result.report()
        self.assertIn("不可以说", text)
        self.assertTrue(result.summary().startswith("不通过"))


class TestCompliantTable(unittest.TestCase):
    """把加量点和长跑都摆正之后，必须通过。"""

    def test_passes(self) -> None:
        result = d.audit_plan(build(COMPLIANT_WEEKS, COMPLIANT_LONG), 5)
        self.assertTrue(result.passed, result.report())
        self.assertIn("通过", result.summary())

    def test_passes_only_when_base_is_not_assumed(self) -> None:
        """起点是估的，表可以算，但不许说合规。"""
        result = d.audit_plan(
            build(COMPLIANT_WEEKS, COMPLIANT_LONG), 5, base_source="assumed"
        )
        self.assertFalse(result.passed)
        self.assertEqual([f.check for f in result.warnings], ["base"])

    def test_volume_sequence_recorded(self) -> None:
        result = d.audit_plan(build(COMPLIANT_WEEKS, COMPLIANT_LONG), 5)
        self.assertEqual(len(result.volumes), 18)


class TestEachCheckFires(unittest.TestCase):
    """六类检查逐条能触发。"""

    def test_single_training_week_cannot_pass(self) -> None:
        """只有 1 个训练周时，加量节奏根本没法判断——不许出结论。

        以前这里会静默跳过，然后照样在报告里写「N 类检查全过」。
        """
        weeks = (
            d.WeekEntry(week=1, weekly_km=30.0, sessions=(d.Session("L", 9.0),)),
            d.WeekEntry(week=2, weekly_km=30.0, sessions=(), race_km=21.1),
        )
        result = d.audit_plan(weeks, 4)
        self.assertFalse(result.passed)
        self.assertIn("无法判断", " ".join(f.message for f in result.errors))

    def test_checks_lists_only_what_actually_ran(self) -> None:
        """报告里的检查项必须等于真跑过的项，不能写死。"""
        two = (
            d.WeekEntry(week=1, weekly_km=30.0, sessions=(d.Session("L", 9.0),)),
            d.WeekEntry(week=2, weekly_km=30.0, sessions=(), race_km=21.1),
        )
        result = d.audit_plan(two, 4)
        self.assertNotIn("progression", result.checks)
        # 不通过时不该出现任何"检查全过"的说法
        self.assertNotIn("类检查全过", result.summary())
        self.assertNotIn("6 类", result.summary())

    def test_checks_has_all_when_everything_runs(self) -> None:
        result = d.audit_plan(build(COMPLIANT_WEEKS, COMPLIANT_LONG), 5)
        self.assertEqual(len(result.checks), 6)
        self.assertIn("6 类", result.summary())

    def test_negative_part_rejected(self) -> None:
        """逐次距离为负时，合计能凑对但内容是错的。"""
        with self.assertRaises(ValueError):
            d.WeekEntry(
                week=1,
                weekly_km=30.0,
                sessions=(d.Session("L", 9.0),),
                part_km=(-5.0, 35.0),
            )

    def test_weekly_volume_soft_max_is_a_note_not_a_blocker(self) -> None:
        """129 km 是建议不是天花板——书里说「已习惯或备战全马」可以超过。

        所以它记成 note、不阻断通过；否则合法的马拉松计划会被判死。
        """
        weeks = (
            d.WeekEntry(week=1, weekly_km=130.0, sessions=(d.Session("L", 32.5),)),
            d.WeekEntry(week=2, weekly_km=130.0, sessions=(d.Session("L", 32.5),)),
        )
        result = d.audit_plan(weeks, 6)
        self.assertTrue(result.passed, result.report())
        joined = " ".join(result.notes)
        self.assertIn("129", joined)
        self.assertIn("L3278", joined)

    def test_no_soft_max_note_below_threshold(self) -> None:
        weeks = (
            d.WeekEntry(week=1, weekly_km=100.0, sessions=(d.Session("L", 30.0),)),
            d.WeekEntry(week=2, weekly_km=100.0, sessions=(d.Session("L", 30.0),)),
        )
        result = d.audit_plan(weeks, 6)
        self.assertNotIn("软上限", " ".join(result.notes))

    def test_incomplete_when_long_run_missing(self) -> None:
        weeks = (
            d.WeekEntry(week=1, weekly_km=30.0, sessions=(d.Session("L", 9.0),)),
            d.WeekEntry(week=2, weekly_km=30.0),
        )
        result = d.audit_plan(weeks, 4)
        self.assertEqual([f.check for f in result.errors], ["incomplete"])

    def test_race_volume_smaller_than_race(self) -> None:
        weeks = (
            d.WeekEntry(week=1, weekly_km=30.0, sessions=(d.Session("L", 9.0),)),
            d.WeekEntry(week=2, weekly_km=20.0, sessions=(), race_km=21.1),
        )
        result = d.audit_plan(weeks, 4)
        self.assertIn("race_volume", [f.check for f in result.errors])

    def test_sum_mismatch(self) -> None:
        """专治「表里列出来 29.1，却写 38 含赛」。"""
        weeks = (
            d.WeekEntry(week=1, weekly_km=30.0, sessions=(d.Session("L", 9.0),)),
            d.WeekEntry(
                week=2,
                weekly_km=38.0,
                sessions=(d.Session("L", 9.0),),
                part_km=(5, 5, 8, 11.1),
            ),
        )
        result = d.audit_plan(weeks, 4)
        self.assertIn("sum", [f.check for f in result.errors])

    def test_sum_ok_when_matching(self) -> None:
        weeks = (
            d.WeekEntry(week=1, weekly_km=30.0, sessions=(d.Session("L", 9.0),),
                        part_km=(6, 6, 9, 9)),
            d.WeekEntry(week=2, weekly_km=30.0, sessions=(d.Session("L", 9.0),),
                        part_km=(6, 6, 9, 9)),
        )
        result = d.audit_plan(weeks, 4)
        self.assertNotIn("sum", [f.check for f in result.errors])

    def test_cap_violation(self) -> None:
        weeks = (
            d.WeekEntry(week=1, weekly_km=24.0, sessions=(d.Session("L", 8.0),)),
            d.WeekEntry(week=2, weekly_km=24.0, sessions=(d.Session("L", 8.0),)),
        )
        result = d.audit_plan(weeks, 4)
        self.assertTrue(any(f.check == "cap" for f in result.errors))

    def test_t_infeasible_below_48(self) -> None:
        weeks = (
            d.WeekEntry(
                week=1,
                weekly_km=30.0,
                sessions=(d.Session("L", 9.0), d.Session("T", 3.0)),
            ),
            d.WeekEntry(week=2, weekly_km=30.0, sessions=(d.Session("L", 9.0),)),
        )
        result = d.audit_plan(weeks, 4)
        messages = " ".join(f.message for f in result.errors)
        self.assertIn("T", messages)


class TestContract(unittest.TestCase):
    """入参与 JSON 契约。"""

    def test_empty_weeks_rejected(self) -> None:
        with self.assertRaises(ValueError):
            d.audit_plan((), 4)

    def test_single_week_rejected(self) -> None:
        with self.assertRaises(ValueError):
            d.audit_plan(
                (d.WeekEntry(week=1, weekly_km=30.0,
                             sessions=(d.Session("L", 9.0),)),),
                4,
            )

    def test_out_of_order_rejected(self) -> None:
        weeks = (
            d.WeekEntry(week=2, weekly_km=30.0, sessions=(d.Session("L", 9.0),)),
            d.WeekEntry(week=1, weekly_km=30.0, sessions=(d.Session("L", 9.0),)),
        )
        with self.assertRaises(ValueError):
            d.audit_plan(weeks, 4)

    def test_duplicate_week_rejected(self) -> None:
        weeks = (
            d.WeekEntry(week=1, weekly_km=30.0, sessions=(d.Session("L", 9.0),)),
            d.WeekEntry(week=1, weekly_km=30.0, sessions=(d.Session("L", 9.0),)),
        )
        with self.assertRaises(ValueError):
            d.audit_plan(weeks, 4)

    def test_bad_base_source(self) -> None:
        weeks = (
            d.WeekEntry(week=1, weekly_km=30.0, sessions=(d.Session("L", 9.0),)),
            d.WeekEntry(week=2, weekly_km=30.0, sessions=(d.Session("L", 9.0),)),
        )
        with self.assertRaises(ValueError):
            d.audit_plan(weeks, 4, base_source="guessed")

    def test_bad_sessions_per_week(self) -> None:
        weeks = (
            d.WeekEntry(week=1, weekly_km=30.0, sessions=(d.Session("L", 9.0),)),
            d.WeekEntry(week=2, weekly_km=30.0, sessions=(d.Session("L", 9.0),)),
        )
        for bad in (0, -1, 4.5):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    d.audit_plan(weeks, bad)  # type: ignore[arg-type]

    def test_plan_from_dict_round_trip(self) -> None:
        payload = {
            "sessions_per_week": 4,
            "base_source": "user",
            "weeks": [
                {"week": 1, "weekly_km": 30, "sessions": [["L", 9]]},
                {"week": 2, "weekly_km": 30, "sessions": [["L", 9]]},
            ],
        }
        weeks, kwargs = d.plan_from_dict(payload)
        self.assertEqual(len(weeks), 2)
        self.assertEqual(kwargs["sessions_per_week"], 4)
        result = d.audit_plan(weeks, **kwargs)  # type: ignore[arg-type]
        self.assertTrue(result.passed, result.report())

    def test_plan_from_dict_rejects_bad_input(self) -> None:
        with self.assertRaises(ValueError):
            d.plan_from_dict([])  # type: ignore[arg-type]
        with self.assertRaises(ValueError):
            d.plan_from_dict({})
        with self.assertRaises(ValueError):
            d.plan_from_dict({"weeks": []})
        with self.assertRaises(ValueError):
            d.plan_from_dict({"weeks": [{"week": 1}]})
        with self.assertRaises(ValueError):
            d.plan_from_dict(
                {"sessions_per_week": 4,
                 "weeks": [{"week": 1, "weekly_km": 30, "sessions": ["L9"]}]}
            )
        with self.assertRaises(ValueError):
            d.plan_from_dict({"weeks": [{"week": 1, "weekly_km": 30}]})

    def test_as_dict_is_json_safe(self) -> None:
        result = d.audit_plan(build(INCORRECT_WEEKS, INCORRECT_LONG), 5)
        json.dumps(result.as_dict(), ensure_ascii=False)


class TestAuditCli(unittest.TestCase):
    """命令行出口：不合规必须退出码 2。"""

    def setUp(self) -> None:
        self.path = "_test_plan.json"
        weeks = build(COMPLIANT_WEEKS, COMPLIANT_LONG)
        payload = {
            "sessions_per_week": 5,
            "base_source": "user",
            "weeks": [
                {
                    "week": entry.week,
                    "weekly_km": entry.weekly_km,
                    "sessions": [
                        [s.intensity, s.km] for s in entry.sessions
                    ],
                    **(
                        {"race_km": entry.race_km}
                        if entry.race_km is not None
                        else {}
                    ),
                }
                for entry in weeks
            ],
        }
        with open(self.path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False)

    def tearDown(self) -> None:
        import os

        if os.path.exists(self.path):
            os.remove(self.path)

    def test_compliant_exits_zero(self) -> None:
        code, out, _ = run("audit", self.path)
        self.assertEqual(code, 0)
        self.assertIn("通过", out)

    def test_json_mode(self) -> None:
        code, out, _ = run("audit", self.path, "--json")
        self.assertEqual(code, 0)
        payload = json.loads(out)
        self.assertTrue(payload["passed"])
        self.assertEqual(payload["weeks"], 18)


if __name__ == "__main__":
    unittest.main()
