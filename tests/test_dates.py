# -*- coding: utf-8 -*-
"""日历模块的测试。

这组守的是一次真实错误：把 20 周的起点手算成 2026-11-29，那天是周日，
从它到 2027-04-18 是 141 天，装不满 20 周。正确起点是 11-30（周一），正好 140 天。

日期这类东西，只要允许手算就会错。所以断言写得比较死：起点星期、总天数、
终点是否等于比赛日，全部逐条钉住。
"""

from __future__ import annotations

import io
import json
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import date, timedelta

import daniels as d
from daniels.__main__ import main

TODAY = date(2026, 11, 13)
RACE = date(2027, 4, 18)


def run(*argv: str) -> tuple:
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = main(list(argv))
    return code, out.getvalue(), err.getvalue()


class TestWeeksUntil(unittest.TestCase):
    """整周数与余数。"""

    def test_incident_value(self) -> None:
        self.assertEqual(d.weeks_until(TODAY, RACE), (22, 2))

    def test_exact_weeks(self) -> None:
        self.assertEqual(
            d.weeks_until(date(2026, 11, 16), date(2026, 11, 30)), (2, 0)
        )

    def test_race_in_past_rejected(self) -> None:
        with self.assertRaises(ValueError):
            d.weeks_until(RACE, TODAY)

    def test_same_day_rejected(self) -> None:
        with self.assertRaises(ValueError):
            d.weeks_until(TODAY, TODAY)

    def test_type_checked(self) -> None:
        with self.assertRaises(TypeError):
            d.weeks_until("2026-11-13", RACE)  # type: ignore[arg-type]
        with self.assertRaises(TypeError):
            d.weeks_until(TODAY, 20270418)  # type: ignore[arg-type]


class TestPlanWindow(unittest.TestCase):
    """给定周数求起点与终点。"""

    def test_twenty_weeks_starts_on_monday_not_sunday(self) -> None:
        """事故点：起点必须是 11-30（周一），不是 11-29（周日）。"""
        start, end = d.plan_window(20, RACE)
        self.assertEqual(start, date(2026, 11, 30))
        self.assertEqual(end, RACE)
        self.assertEqual(start.weekday(), 0)  # 周一

    def test_sunday_start_is_not_a_valid_window(self) -> None:
        """从 11-29 到比赛日装不满 20 周——多出一天。"""
        wrong = date(2026, 11, 29)
        self.assertNotEqual(wrong, d.plan_window(20, RACE)[0])
        self.assertEqual((RACE - wrong).days + 1, 141)
        self.assertNotEqual(141 % 7, 0)

    def test_end_always_equals_race_date(self) -> None:
        for weeks in range(3, 30):
            with self.subTest(weeks=weeks):
                start, end = d.plan_window(weeks, RACE)
                self.assertEqual(end, RACE)
                # 起点到终点含头含尾正好 7 × weeks 天
                self.assertEqual((end - start).days + 1, 7 * weeks)

    def test_start_weekday_is_day_after_race(self) -> None:
        """周日比赛 → 周一开练。这条不用配置，是算出来的。"""
        start, _ = d.plan_window(20, RACE)
        self.assertEqual(
            (RACE.weekday() + 1) % 7, start.weekday()
        )

    def test_saturday_race_starts_sunday(self) -> None:
        saturday = date(2027, 4, 17)
        start, end = d.plan_window(12, saturday)
        self.assertEqual(start.weekday(), 6)  # 周日
        self.assertEqual(end, saturday)

    def test_bad_weeks(self) -> None:
        for bad in (0, -1, 12.0, True, "12"):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    d.plan_window(bad, RACE)  # type: ignore[arg-type]


class TestMaxPlanWeeks(unittest.TestCase):
    """「我还有几周」在排计划语境下的答案。

    ``weeks_until`` 给的是已过去的天数换算，``max_plan_weeks`` 给的是能排多长。
    两个数都对，但说的是不同的事——真实测试里一份回答把它们并排写出来，
    先「6 周零 6 天」再「7 个完整周可用」，读者会以为它算错了。
    """

    def test_year_end_is_exactly_seven_weeks(self) -> None:
        """11-13 到 12-31 含头含尾 49 天，正好 7 周。"""
        end = date(2026, 12, 31)
        self.assertEqual((end - TODAY).days + 1, 49)
        self.assertEqual(d.max_plan_weeks(TODAY, end), 7)

    def test_weeks_until_disagrees_on_purpose(self) -> None:
        end = date(2026, 12, 31)
        self.assertEqual(d.weeks_until(TODAY, end), (6, 6))
        self.assertNotEqual(d.weeks_until(TODAY, end)[0], d.max_plan_weeks(TODAY, end))

    def test_half_marathon_case(self) -> None:
        self.assertEqual(d.max_plan_weeks(TODAY, RACE), 22)

    def test_matches_feasible_plans(self) -> None:
        """两个函数必须永远说同一件事（都受 max_weeks 40 的上限约束）。"""
        for end in (
            date(2026, 12, 31),
            date(2027, 2, 14),
            date(2027, 4, 18),
            date(2027, 9, 5),
        ):
            options = d.feasible_plans(TODAY, end)
            with self.subTest(end=end):
                self.assertTrue(options, "这些日期都应该排得下")
                # max_plan_weeks 是纯日期算术；feasible_plans 还受 max_weeks=40 约束
                self.assertEqual(
                    min(d.max_plan_weeks(TODAY, end), 40),
                    max(p.weeks for p in options),
                )

    def test_start_of_that_window_is_not_before_today(self) -> None:
        for end in (date(2026, 12, 31), date(2027, 4, 18)):
            weeks = d.max_plan_weeks(TODAY, end)
            start, _ = d.plan_window(weeks, end)
            with self.subTest(end=end):
                self.assertGreaterEqual(start, TODAY)

    def test_short_runway(self) -> None:
        """比赛只剩一周时，能排 1 周；只剩 3 天时排 0 周。"""
        self.assertEqual(d.max_plan_weeks(TODAY, date(2026, 11, 19)), 1)
        self.assertEqual(d.max_plan_weeks(TODAY, date(2026, 11, 16)), 0)
        with self.assertRaises(ValueError):
            d.max_plan_weeks(TODAY, TODAY)


class TestFeasiblePlans(unittest.TestCase):
    """哪些长度现在还能用。"""

    def test_documented_options(self) -> None:
        weeks = [
            p.weeks
            for p in d.feasible_plans(TODAY, RACE, documented_only=True)
        ]
        self.assertEqual(weeks, [3, 6, 9, 12, 20])

    def test_twenty_weeks_is_the_long_one(self) -> None:
        options = {
            p.weeks: p
            for p in d.feasible_plans(TODAY, RACE, documented_only=True)
        }
        self.assertEqual(options[20].start_date, date(2026, 11, 30))
        self.assertTrue(options[20].documented)
        self.assertFalse(options[20].starts_in_past)

    def test_23_weeks_started_in_the_past(self) -> None:
        """23 周本来也行，但 11-09 已经过去了——这条以前靠心算。"""
        weeks = [p.weeks for p in d.feasible_plans(TODAY, RACE)]
        self.assertNotIn(23, weeks)
        with_past = d.feasible_plans(
            TODAY, RACE, documented_only=True, include_past=True
        )
        past = {p.weeks: p for p in with_past if p.starts_in_past}
        self.assertIn(23, past)
        self.assertEqual(past[23].start_date, date(2026, 11, 9))

    def test_22_weeks_available_but_undocumented(self) -> None:
        options = {p.weeks: p for p in d.feasible_plans(TODAY, RACE)}
        self.assertIn(22, options)
        self.assertFalse(options[22].documented)
        self.assertEqual(options[22].start_date, date(2026, 11, 16))

    def test_every_option_ends_on_race_day(self) -> None:
        for item in d.feasible_plans(TODAY, RACE, include_past=True):
            with self.subTest(weeks=item.weeks):
                self.assertEqual(item.end_date, RACE)

    def test_no_option_starts_before_today_unless_asked(self) -> None:
        for item in d.feasible_plans(TODAY, RACE):
            self.assertGreaterEqual(item.start_date, TODAY)
            self.assertFalse(item.starts_in_past)

    def test_ascending(self) -> None:
        weeks = [p.weeks for p in d.feasible_plans(TODAY, RACE)]
        self.assertEqual(weeks, sorted(weeks))

    def test_short_runway(self) -> None:
        """两周后就比赛：只剩 3 周以下的长度，全都不够。"""
        options = d.feasible_plans(TODAY, date(2026, 11, 29))
        self.assertEqual(options, ())

    def test_race_in_past_rejected(self) -> None:
        with self.assertRaises(ValueError):
            d.feasible_plans(RACE, TODAY)

    def test_bad_ranges(self) -> None:
        with self.assertRaises(ValueError):
            d.feasible_plans(TODAY, RACE, min_weeks=0)
        with self.assertRaises(ValueError):
            d.feasible_plans(TODAY, RACE, min_weeks=10, max_weeks=5)
        with self.assertRaises(ValueError):
            d.feasible_plans(TODAY, RACE, max_weeks=5.5)  # type: ignore[arg-type]

    def test_split_only_for_documented(self) -> None:
        for item in d.feasible_plans(TODAY, RACE):
            with self.subTest(weeks=item.weeks):
                if item.documented:
                    self.assertIsNotNone(item.split)
                    self.assertEqual(sum(item.split), item.weeks)
                else:
                    self.assertIsNone(item.split)

    def test_as_dict_is_json_safe(self) -> None:
        for item in d.feasible_plans(TODAY, RACE, include_past=True):
            json.dumps(item.as_dict(), ensure_ascii=False)


class TestCalendarCli(unittest.TestCase):
    """命令行出口。"""

    def test_lists_documented_lengths(self) -> None:
        code, out, _ = run(
            "calendar", "--race", "2027-04-18", "--today", "2026-11-13",
            "--documented-only",
        )
        self.assertEqual(code, 0)
        self.assertIn("2026-11-30", out)
        self.assertIn("22 周 2 天", out)
        self.assertNotIn("2026-11-29", out)

    def test_json_payload(self) -> None:
        code, out, _ = run(
            "calendar", "--race", "2027-04-18", "--today", "2026-11-13",
            "--json",
        )
        self.assertEqual(code, 0)
        payload = json.loads(out)
        self.assertEqual(payload["weeks_until"], 22)
        self.assertEqual(payload["leftover_days"], 2)
        self.assertEqual(payload["race_date"], "2027-04-18")

    def test_bad_date(self) -> None:
        code, _, err = run(
            "calendar", "--race", "4/18/2027", "--today", "2026-11-13"
        )
        self.assertEqual(code, 1)
        self.assertIn("YYYY-MM-DD", err)


class TestConsistencyWithPeriodize(unittest.TestCase):
    """dates 与 periodize 对同一件事要一致。"""

    def test_documented_flag_matches_plan_schedule(self) -> None:
        for item in d.feasible_plans(
            TODAY, RACE, include_past=True
        ):
            with self.subTest(weeks=item.weeks):
                plan = d.plan_schedule(item.weeks, allow_undocumented=True)
                self.assertEqual(plan.documented, item.documented)

    def test_split_matches_plan_schedule(self) -> None:
        for item in d.feasible_plans(TODAY, RACE, documented_only=True):
            with self.subTest(weeks=item.weeks):
                plan = d.plan_schedule(item.weeks)
                self.assertEqual(plan.weeks, item.split)

    def test_min_weeks_default_matches(self) -> None:
        options = d.feasible_plans(TODAY, RACE)
        self.assertEqual(options[0].weeks, d.MIN_WEEKS)
        self.assertEqual(timedelta(days=7 * 3 - 1), RACE - options[0].start_date)


if __name__ == "__main__":
    unittest.main()
