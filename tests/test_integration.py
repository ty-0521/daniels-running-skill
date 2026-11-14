# -*- coding: utf-8 -*-
"""端到端集成测试：按 SKILL.md 写的工作流走完整条链路。

单元测试验的是每个函数本身，这里验的是「把函数按文档串起来能不能真的
给出一份可用的训练建议」，以及越界时会不会乖乖报错。

运行：
    cd D:\\daniels-running-skill
    python -m unittest discover -s tests -v
"""

from __future__ import annotations

import unittest

import daniels as d


class TestMainstreamRunner(unittest.TestCase):
    """5 km 20:00、周跑量 64 km 的跑者，24 周计划。"""

    @classmethod
    def setUpClass(cls) -> None:
        cls.vdot = d.vdot_from_race(5000.0, 20 * 60)
        cls.paces = d.pace_set(cls.vdot)
        cls.weekly = 64.0
        cls.plan = d.plan_schedule(24)

    # -- 第 1 步 ----------------------------------------------------------
    def test_step1_vdot(self) -> None:
        self.assertAlmostEqual(self.vdot, 49.81, delta=0.02)

    # -- 第 2 步 ----------------------------------------------------------
    def test_step2_paces_are_ordered(self) -> None:
        """五档必须严格由慢到快：E > M > T > I > R。"""
        order = [
            self.paces.e_slow.seconds_per_km,
            self.paces.m.seconds_per_km,
            self.paces.t.seconds_per_km,
            self.paces.i.seconds_per_km,
            self.paces.r.seconds_per_km,
        ]
        self.assertEqual(order, sorted(order, reverse=True))

    def test_step2_m_pace_reproduces_vdot(self) -> None:
        """拿 M 配速跑完马拉松，反算应当回到同一个 VDOT。"""
        marathon = self.paces.m.time_for(42195.0)
        self.assertAlmostEqual(
            d.vdot_from_race(42195.0, marathon), self.vdot, delta=0.15
        )

    def test_step2_e_is_a_range_not_a_point(self) -> None:
        gap = self.paces.e_slow.seconds_per_km - self.paces.e_fast.seconds_per_km
        self.assertGreater(gap, 20.0)

    # -- 第 3 步 ----------------------------------------------------------
    def test_step3_caps_shrink_with_volume(self) -> None:
        """周跑量越大，同一强度的单次上限越大——但受封顶限制。"""
        for name, func in (
            ("T", d.threshold_cap),
            ("I", d.interval_cap),
            ("R", d.repetition_cap),
        ):
            with self.subTest(intensity=name):
                low = func(40.0).max_km
                high = func(120.0).max_km
                self.assertGreater(high, low)
                self.assertLessEqual(high, {"T": 24.0, "I": 10.0, "R": 8.0}[name])

    # -- 第 4 步 ----------------------------------------------------------
    def test_step4_compliant_week(self) -> None:
        week = [
            d.Session("L", 16.0),
            d.Session("T", 6.0),
            d.Session("I", 3.0),
        ]
        self.assertEqual(
            d.check_week(week, self.weekly, paces=self.paces), []
        )

    def test_step4_violating_week_is_caught(self) -> None:
        week = [
            d.Session("L", 22.0),
            d.Session("T", 10.0),
            d.Session("I", 8.0),
        ]
        violations = d.check_week(week, self.weekly, paces=self.paces)
        self.assertEqual(len(violations), 3)
        for item in violations:
            self.assertTrue(item.rule_ids)
            self.assertTrue(item.message)

    # -- 第 5 步 ----------------------------------------------------------
    def test_step5_plan_phases_cover_every_week(self) -> None:
        seen = {self.plan.phase_of_week(w) for w in range(1, 25)}
        self.assertEqual(seen, {1, 2, 3, 4})

    def test_step5_q_days_match_phase_intensities(self) -> None:
        for phase in (1, 2, 3, 4):
            with self.subTest(phase=phase):
                days = d.quality_days(3)
                intensities = d.q_intensities(phase)
                self.assertEqual(len(days), len(intensities))
                for day in days:
                    self.assertTrue(1 <= day <= 7)

    # -- 第 6 步 ----------------------------------------------------------
    def test_step6_explain_links_back_to_a_function(self) -> None:
        topic = d.explain_topic("why-easy-is-slow")
        self.assertIsNotNone(topic.computed_by)
        self.assertTrue(hasattr(d, topic.computed_by))

    def test_step6_search_finds_the_intensity_question(self) -> None:
        hits = d.search("T 配速是什么感觉")
        self.assertTrue(hits)
        self.assertEqual(hits[0].topic_id, "t-comfortably-hard")

    # -- 整体 --------------------------------------------------------------
    def test_manifest_reflects_the_whole_package(self) -> None:
        data = d.manifest()
        self.assertEqual(data["version"], d.__version__)
        for layer in data["layers"].values():
            for name in layer:
                self.assertTrue(hasattr(d, name))


class TestBeginnerRunner(unittest.TestCase):
    """VDOT 28 的初跑者：必须拿到书中更保守的那一套值。"""

    def test_novice_row_is_available(self) -> None:
        paces = d.pace_set(28.0)
        self.assertTrue(paces.novice)
        self.assertIsNotNone(paces.novice_row)

    def test_novice_values_follow_the_book(self) -> None:
        """第 5 章 L1812：VDOT 28 → M 7:27/km，马拉松 5:15。"""
        row = d.pace_set(28.0).novice_row
        self.assertIsNotNone(row)
        self.assertEqual(d.format_time(row.m.seconds_per_km), "7:27")
        self.assertAlmostEqual(row.m.time_for(42195.0), 5 * 3600 + 15 * 60, delta=120)

    def test_beginner_caps_are_tighter_in_absolute_terms(self) -> None:
        """周跑量相同时，初跑者的单次 I 上限与高手一样是 8%，但绝对量更小。"""
        self.assertAlmostEqual(d.interval_cap(40.0).max_km, 3.2, places=6)
        self.assertAlmostEqual(d.interval_cap(120.0).max_km, 9.6, places=6)

    def test_short_plan_skips_phase_three(self) -> None:
        """9 周计划跳过阶段三（第6章 L2073）。"""
        self.assertEqual(d.plan_schedule(9).weeks, (3, 3, 0, 3))


class TestBoundariesAreEnforced(unittest.TestCase):
    """越界必须抛错，不能悄悄外推。"""

    def test_vdot_below_range(self) -> None:
        with self.assertRaises(d.VdotRangeError):
            d.pace_set(19.9)

    def test_vdot_above_range(self) -> None:
        with self.assertRaises(d.VdotRangeError):
            d.pace_set(85.1)

    def test_altitude_above_range(self) -> None:
        with self.assertRaises(d.AltitudeRangeError):
            d.altitude_correction(2501.0)

    def test_undocumented_plan_length(self) -> None:
        with self.assertRaises(d.PhaseLengthError):
            d.plan_schedule(16)

    def test_plan_too_short(self) -> None:
        with self.assertRaises(d.PhaseLengthError):
            d.plan_schedule(2)

    def test_distance_out_of_range(self) -> None:
        with self.assertRaises(d.DanielsError):
            d.vdot_from_race(400.0, 60.0)

    def test_error_messages_are_actionable(self) -> None:
        """报错要说清楚能做什么，而不只是「出错了」。"""
        with self.assertRaises(d.VdotRangeError) as ctx:
            d.pace_set(90)
        self.assertIn("20", str(ctx.exception))
        self.assertIn("85", str(ctx.exception))


if __name__ == "__main__":
    unittest.main(verbosity=2)
