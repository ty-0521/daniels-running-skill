# -*- coding: utf-8 -*-
"""全人群扫描测试。

前面几个测试文件验的是「某个数对不对」，这个文件验的是
**换一种跑者会不会塌**：从 VDOT 20 的初跑者到 VDOT 85 的精英，
从每周 20 公里到 160 公里，任何一格都不应该出现逻辑倒挂、
异常崩溃或荒谬的数值。

运行：
    cd D:\\training
    python -m unittest discover -s tests -v
"""

from __future__ import annotations

import unittest

import daniels as d
from daniels.vdot import VDOT_MAX, VDOT_MIN

#: 扫描用的 VDOT 网格（步长 0.5，覆盖书里 20~85 的全部整数档）。
VDOT_GRID = [VDOT_MIN + 0.5 * i for i in range(int((VDOT_MAX - VDOT_MIN) / 0.5) + 1)]

#: 扫描用的周跑量网格。
WEEKLY_GRID = [20.0, 30.0, 40.0, 48.0, 56.0, 64.0, 80.0, 100.0, 130.0, 160.0]


class TestPaceOrdering(unittest.TestCase):
    """配速必须严格由慢到快：E慢 > E快 > M > T > I > R。

    低 VDOT 时「1 英里配速 + 75 秒」这条 E 换算式会算出比 M 还快的 E，
    曾经导致 VDOT 20 的轻松跑比马拉松配速还快。这里锁死不许再出现。
    """

    def test_order_holds_across_all_vdot(self) -> None:
        for vdot in VDOT_GRID:
            with self.subTest(vdot=vdot):
                p = d.pace_set(vdot)
                order = [
                    p.e_slow.seconds_per_km,
                    p.e_fast.seconds_per_km,
                    p.m.seconds_per_km,
                    p.t.seconds_per_km,
                    p.i.seconds_per_km,
                    p.r.seconds_per_km,
                ]
                self.assertEqual(order, sorted(order, reverse=True))

    def test_easy_is_slower_than_marathon_pace(self) -> None:
        """E 比 M 慢是最基本的常识，任何 VDOT 都不能反。"""
        for vdot in VDOT_GRID:
            with self.subTest(vdot=vdot):
                p = d.pace_set(vdot)
                self.assertGreater(p.e_fast.seconds_per_km, p.m.seconds_per_km)

    def test_e_range_never_collapses(self) -> None:
        for vdot in VDOT_GRID:
            with self.subTest(vdot=vdot):
                p = d.pace_set(vdot)
                width = p.e_slow.seconds_per_km - p.e_fast.seconds_per_km
                self.assertGreaterEqual(width, 14.9)


class TestCapsAcrossVolume(unittest.TestCase):
    """各档上限随周跑量的走向。"""

    def test_caps_grow_with_volume(self) -> None:
        """T/I/R 的绝对上限随周跑量单调不减（封顶后持平）。"""
        for name, func in (
            ("T", d.threshold_cap),
            ("I", d.interval_cap),
            ("R", d.repetition_cap),
        ):
            with self.subTest(intensity=name):
                values = [func(weekly).max_km for weekly in WEEKLY_GRID]
                self.assertEqual(values, sorted(values))

    def test_long_run_is_not_monotonic(self) -> None:
        """L 在 64 km 处会掉下来，这是书里的规则，不是 bug。"""
        self.assertGreater(d.long_run_cap(63.9).max_km, d.long_run_cap(64.0).max_km)

    def test_threshold_infeasible_below_48(self) -> None:
        for weekly in (20.0, 30.0, 40.0, 47.0):
            with self.subTest(weekly=weekly):
                self.assertFalse(d.threshold_cap(weekly).feasible)
        for weekly in (48.0, 56.0, 64.0):
            with self.subTest(weekly=weekly):
                self.assertTrue(d.threshold_cap(weekly).feasible)

    def test_every_cap_reports_a_ratio(self) -> None:
        for weekly in (20.0, 64.0, 160.0):
            for name in d.INTENSITIES:
                with self.subTest(intensity=name, weekly=weekly):
                    cap = d.cap_for(name, weekly)
                    self.assertIsNotNone(cap.ratio)
                    self.assertGreater(cap.ratio, 0.0)
                    self.assertLessEqual(cap.ratio, 0.5)


class TestMaxReps(unittest.TestCase):
    """回合数折算：这是跑者真正拿去执行的东西。"""

    def test_beginner_cannot_do_eight_by_200(self) -> None:
        """周跑量 20 km 的跑者，R 上限 1.0 km，只能跑 5 个 200 米。"""
        self.assertEqual(d.max_reps("R", 20.0, 200.0), 5)

    def test_book_volume_example(self) -> None:
        """周跑量 64 km 时 R 上限 3.2 km，可跑 16 个 200 米。"""
        self.assertEqual(d.max_reps("R", 64.0, 200.0), 16)

    def test_infeasible_returns_zero(self) -> None:
        """T 在 35 km 周跑量下无解，回合数当然是 0。"""
        self.assertEqual(d.max_reps("T", 35.0, 1000.0), 0)

    def test_never_exceeds_cap(self) -> None:
        """任何组合下，回合数 × 回合距离都不能超过上限。"""
        for name in d.INTENSITIES:
            for weekly in WEEKLY_GRID:
                for rep in (200.0, 400.0, 1000.0):
                    cap = d.cap_for(name, weekly)
                    if not cap.feasible or cap.max_km is None:
                        continue
                    reps = d.max_reps(name, weekly, rep)
                    with self.subTest(intensity=name, weekly=weekly, rep=rep):
                        self.assertLessEqual(reps * rep, cap.max_km * 1000.0 + 1e-6)

    def test_at_least_one_rep_when_feasible(self) -> None:
        """只要强度可行、回合又不超过上限，至少应该有 1 个。"""
        for weekly in (48.0, 64.0, 100.0):
            with self.subTest(weekly=weekly):
                self.assertGreaterEqual(d.max_reps("T", weekly, 1000.0), 4)

    def test_invalid_arguments(self) -> None:
        for bad in (0.0, -200.0):
            with self.subTest(rep=bad):
                with self.assertRaises(ValueError):
                    d.max_reps("R", 64.0, bad)


class TestNoCrashesAcrossGrid(unittest.TestCase):
    """整张网格都不能抛异常（除非是明确的边界错误）。"""

    def test_pace_set_survives_grid(self) -> None:
        for vdot in VDOT_GRID:
            with self.subTest(vdot=vdot):
                d.pace_set(vdot).as_dict()

    def test_caps_survive_grid(self) -> None:
        for name in d.INTENSITIES:
            for weekly in WEEKLY_GRID:
                with self.subTest(intensity=name, weekly=weekly):
                    d.cap_for(name, weekly).as_dict()

    def test_altitude_grid(self) -> None:
        for altitude in (0.0, 500.0, 914.0, 1200.0, 1524.0, 2130.0, 2500.0):
            with self.subTest(altitude=altitude):
                p = d.pace_set(51.0, altitude_m=altitude)
                # 海拔越高，I/T/M 只会更慢，不会更快
                self.assertGreaterEqual(
                    p.i.seconds_per_km, d.pace_set(51.0).i.seconds_per_km
                )


class TestPlanConsistency(unittest.TestCase):
    """周期层与其他层是否自洽。"""

    def test_every_documented_length_covers_all_weeks(self) -> None:
        for weeks in d.DOCUMENTED_SPLITS:
            with self.subTest(weeks=weeks):
                plan = d.plan_schedule(weeks)
                self.assertEqual(sum(plan.weeks), weeks)
                phases = {plan.phase_of_week(w) for w in range(1, weeks + 1)}
                self.assertEqual(phases, set(plan.active_phases()))

    def test_q_intensities_are_valid_codes(self) -> None:
        allowed = {"E", "R", "T", "I", "L"}
        for phase in (1, 2, 3, 4):
            for count in (2, 3):
                with self.subTest(phase=phase, count=count):
                    codes = d.q_intensities(phase, q_count=count)
                    self.assertEqual(len(codes), count)
                    self.assertTrue(set(codes) <= allowed)

    def test_q_days_are_distinct_and_in_range(self) -> None:
        for count in (2, 3):
            for race in (None, 1, 5, 6, 7):
                try:
                    days = d.quality_days(count, race_weekday=race)
                except ValueError:
                    continue
                with self.subTest(count=count, race=race):
                    self.assertEqual(len(days), len(set(days)))
                    for day in days:
                        self.assertIn(day, range(1, 8))


if __name__ == "__main__":
    unittest.main(verbosity=2)
