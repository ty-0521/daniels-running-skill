# -*- coding: utf-8 -*-
"""daniels.dose 的回归测试。

真值优先用书中自己给出的算例；没有算例的，用正文里的明确数值。

运行：
    cd D:\\daniels-running-skill
    python -m unittest discover -s tests -v
"""

from __future__ import annotations

import unittest

from daniels import Pace
from daniels.dose import (
    RULES,
    DoseCap,
    Session,
    cap_for,
    check_week,
    interval_cap,
    long_run_cap,
    marathon_pace_cap,
    post_race_easy_days,
    repetition_cap,
    threshold_cap,
    volume_step_km,
)


class TestIntervalCap(unittest.TestCase):
    """I 跑上限。第 12 章 L3152 直接给了两个算例。"""

    def test_book_example_48km(self) -> None:
        """周跑量 48 km → I 上限 3.84 km（48 的 8%）。"""
        self.assertAlmostEqual(interval_cap(48.0).max_km, 3.84, places=6)

    def test_book_example_97km(self) -> None:
        """周跑量 97 km → 规则给出 7.76 km。

        注意：书中第 12 章 L3152 印的是 7.68 km，但 97 的 8% 是 7.76。
        7.68 恰好等于 96 的 8%，判断为书中算例的笔误（96 写成 97）。
        本模块按规则实现，不复刻笔误；见下面一条测试。
        """
        self.assertAlmostEqual(interval_cap(97.0).max_km, 7.76, places=6)

    def test_book_printed_value_matches_96km(self) -> None:
        """锁定上面那个判断：书中的 7.68 对应的是 96 km。"""
        self.assertAlmostEqual(interval_cap(96.0).max_km, 7.68, places=6)

    def test_ten_km_ceiling(self) -> None:
        """周跑量再大，10 km 这一侧也会先触发。"""
        self.assertAlmostEqual(interval_cap(200.0).max_km, 10.0, places=6)

    def test_single_rep_limit(self) -> None:
        """单回合 5 分钟，因此最长 1200 m。"""
        cap = interval_cap(64.0)
        self.assertEqual(cap.single_rep_max_minutes, 5.0)


class TestRepetitionCap(unittest.TestCase):
    """R 跑上限。第 4 章 L1583 给了两个算例。"""

    def test_book_example_48km(self) -> None:
        """周跑量 48 km → R 上限 2.4 km（48 的 5%）。"""
        self.assertAlmostEqual(repetition_cap(48.0).max_km, 2.4, places=6)

    def test_book_example_190km(self) -> None:
        """周跑量 190 km → 上限 8 km，不是 9.5 km。"""
        self.assertAlmostEqual(repetition_cap(190.0).max_km, 8.0, places=6)

    def test_single_rep_limit(self) -> None:
        """单回合不超过 2 分钟。"""
        self.assertEqual(repetition_cap(64.0).single_rep_max_minutes, 2.0)


class TestLongRunCap(unittest.TestCase):
    """L 跑上限。公路与越野两套，64 km 是分界。"""

    def test_under_64_km_uses_30_percent(self) -> None:
        cap = long_run_cap(48.0)
        self.assertAlmostEqual(cap.max_km, 14.4, places=6)
        self.assertEqual(cap.max_minutes, 150.0)
        self.assertIn("D-L-01", [r.rule_id for r in cap.rules])

    def test_at_64_km_switches_to_25_percent(self) -> None:
        """64 km 及以上改用 25%（第4章 L1363）。"""
        cap = long_run_cap(64.0)
        self.assertAlmostEqual(cap.max_km, 16.0, places=6)
        self.assertIn("D-L-02", [r.rule_id for r in cap.rules])

    def test_just_below_64_km_still_30_percent(self) -> None:
        self.assertAlmostEqual(long_run_cap(63.9).max_km, 19.17, places=2)

    def test_trail_phase_one_caps_at_60_minutes(self) -> None:
        """越野阶段一：60 分钟，比公路的 150 分钟保守（第12章 L3160）。"""
        cap = long_run_cap(64.0, surface="trail", phase=1)
        self.assertAlmostEqual(cap.max_km, 19.2, places=6)
        self.assertEqual(cap.max_minutes, 60.0)

    def test_trail_phase_two_uses_25_percent(self) -> None:
        cap = long_run_cap(80.0, surface="trail", phase=2)
        self.assertAlmostEqual(cap.max_km, 20.0, places=6)
        self.assertEqual(cap.max_minutes, 150.0)

    def test_invalid_inputs(self) -> None:
        with self.assertRaises(ValueError):
            long_run_cap(0.0)
        with self.assertRaises(ValueError):
            long_run_cap(48.0, surface="treadmill")
        with self.assertRaises(ValueError):
            long_run_cap(48.0, phase=5)


class TestMarathonPaceCap(unittest.TestCase):
    """M 跑上限：110 分钟、29 km、周跑量百分比三者取小。"""

    def test_under_64_km_uses_30_percent(self) -> None:
        cap = marathon_pace_cap(48.0)
        self.assertAlmostEqual(cap.max_km, 14.4, places=6)
        self.assertEqual(cap.max_minutes, 110.0)

    def test_at_64_km_uses_20_percent(self) -> None:
        cap = marathon_pace_cap(96.0)
        self.assertAlmostEqual(cap.max_km, 19.2, places=6)

    def test_29km_ceiling(self) -> None:
        self.assertAlmostEqual(marathon_pace_cap(200.0).max_km, 29.0, places=6)

    def test_minutes_can_bind(self) -> None:
        """慢跑者的 M 配速下，110 分钟会比 29 km 先到。"""
        cap = marathon_pace_cap(200.0)
        slow = Pace(600.0)  # 10:00/km
        self.assertEqual(cap.binding(slow), "minutes")
        self.assertAlmostEqual(cap.limit_km(slow), 11.0, places=6)


class TestThresholdCap(unittest.TestCase):
    """T 跑上限：10%、24 km、以及单次 4.8 km 下限。"""

    def test_ten_percent(self) -> None:
        self.assertAlmostEqual(threshold_cap(64.0).max_km, 6.4, places=6)

    def test_24km_ceiling(self) -> None:
        self.assertAlmostEqual(threshold_cap(400.0).max_km, 24.0, places=6)

    def test_minimum_per_session(self) -> None:
        self.assertEqual(threshold_cap(64.0).min_km, 4.8)

    def test_split_minimum(self) -> None:
        """拆成巡航间歇时累计至少 30 分钟（第4章 L1429）。"""
        self.assertEqual(threshold_cap(64.0).min_minutes_when_split, 30.0)


class TestLimitKmAndBinding(unittest.TestCase):
    """距离上限与时间上限谁先触发。"""

    def test_long_run_distance_binds_at_fast_pace(self) -> None:
        cap = long_run_cap(80.0)  # 20 km 或 150 分钟
        fast = Pace(300.0)  # 5:00/km，150 分钟可跑 30 km
        self.assertEqual(cap.binding(fast), "km")
        self.assertAlmostEqual(cap.limit_km(fast), 20.0, places=6)

    def test_long_run_time_binds_at_slow_pace(self) -> None:
        cap = long_run_cap(80.0)
        slow = Pace(480.0)  # 8:00/km，150 分钟只能跑 18.75 km
        self.assertEqual(cap.binding(slow), "minutes")
        self.assertAlmostEqual(cap.limit_km(slow), 18.75, places=6)

    def test_no_limit_returns_inf(self) -> None:
        cap = DoseCap("X", None, None, ())
        self.assertEqual(cap.limit_km(Pace(300.0)), float("inf"))
        self.assertEqual(cap.binding(Pace(300.0)), "none")


class TestPostRaceEasyDays(unittest.TestCase):
    """赛后轻松日。五个锚点全部命中。"""

    def test_book_anchors(self) -> None:
        """第14章 L3482 的四个锚点 + 第11章 L2990 的 5 km。"""
        cases = [
            (5.0, 2),
            (10.0, 3),
            (15.0, 5),
            (21.0975, 7),
            (42.195, 14),
        ]
        for km, expected in cases:
            with self.subTest(km=km):
                self.assertEqual(post_race_easy_days(km), expected)

    def test_minimum_one_day(self) -> None:
        self.assertEqual(post_race_easy_days(1.0), 1)

    def test_invalid(self) -> None:
        with self.assertRaises(ValueError):
            post_race_easy_days(0.0)


class TestVolumeStep(unittest.TestCase):
    """周跑量增量。第 11 章 L2956 给了两个算例。"""

    def test_book_example_five_sessions(self) -> None:
        """每周 5 次 → 8 km。"""
        self.assertAlmostEqual(volume_step_km(5), 8.0, places=6)

    def test_book_example_fourteen_sessions(self) -> None:
        """每天两跑共 14 次 → 封顶 16 km，不是 22.4 km。"""
        self.assertAlmostEqual(volume_step_km(14), 16.0, places=6)

    def test_no_cap_region(self) -> None:
        self.assertAlmostEqual(volume_step_km(3), 4.8, places=6)

    def test_invalid(self) -> None:
        for bad in (0, -1):
            with self.subTest(value=bad):
                with self.assertRaises(ValueError):
                    volume_step_km(bad)
        with self.assertRaises(ValueError):
            volume_step_km(3.5)  # type: ignore[arg-type]


class TestCapFor(unittest.TestCase):
    """分派函数。"""

    def test_dispatch(self) -> None:
        for intensity in ("L", "M", "T", "I", "R"):
            with self.subTest(intensity=intensity):
                self.assertEqual(cap_for(intensity, 64.0).intensity, intensity)

    def test_unknown(self) -> None:
        with self.assertRaises(ValueError):
            cap_for("E", 64.0)


class TestCheckWeek(unittest.TestCase):
    """整周检查。"""

    def test_clean_week(self) -> None:
        sessions = [
            Session("L", 16.0),
            Session("T", 6.0),
            Session("I", 3.0),
        ]
        self.assertEqual(check_week(sessions, 64.0), [])

    def test_interval_over_cap(self) -> None:
        """周跑量 48 km 时 I 上限 3.84 km，跑 4.5 km 应报错。"""
        violations = check_week([Session("I", 4.5)], 48.0)
        self.assertEqual(len(violations), 1)
        v = violations[0]
        self.assertEqual(v.intensity, "I")
        self.assertAlmostEqual(v.limit, 3.84, places=6)
        self.assertEqual(v.unit, "km")
        self.assertIn("D-I-01", v.rule_ids)

    def test_too_many_interval_sessions(self) -> None:
        """每周三次 I 训练应被标记（第11章 L2978）。"""
        sessions = [Session("I", 1.0), Session("I", 1.0), Session("I", 1.0)]
        violations = check_week(sessions, 64.0)
        self.assertEqual(len(violations), 1)
        self.assertEqual(violations[0].unit, "sessions")
        self.assertEqual(violations[0].rule_ids, ("D-I-03",))

    def test_threshold_below_minimum(self) -> None:
        """T 跑低于 4.8 km 应被标记（第14章 L3478）。"""
        violations = check_week([Session("T", 3.0)], 64.0)
        self.assertEqual(len(violations), 1)
        self.assertEqual(violations[0].rule_ids, ("D-T-02",))

    def test_long_run_time_cap_with_pace(self) -> None:
        """L 跑按 E 配速慢端折算；慢到一定程度时 150 分钟会先触发。

        PaceSet 里没有 ``l`` 属性，L 必须走 e_slow，否则时间上限会被静默跳过。
        """
        from daniels import pace_set

        ps = pace_set(20.0)  # E 慢端约 7:56/km
        cap = long_run_cap(80.0)  # 20 km 或 150 分钟
        self.assertEqual(cap.binding(ps.e_slow), "minutes")
        self.assertLess(cap.limit_km(ps.e_slow), 20.0)

        violations = check_week([Session("L", 19.0)], 80.0, paces=ps)
        self.assertEqual(len(violations), 1)
        self.assertEqual(violations[0].unit, "minutes")
        self.assertAlmostEqual(violations[0].limit, 150.0, places=6)

    def test_long_run_ok_under_both_caps(self) -> None:
        """同一套配速下，12 km 的两条上限都不触发。

        注意 VDOT 20 的 E 慢端约 9:55/km，16 km 就要 159 分钟，
        对这类跑者 150 分钟的时间上限确实会先到——这不是误报。
        """
        from daniels import pace_set

        self.assertEqual(
            check_week([Session("L", 12.0)], 80.0, paces=pace_set(20.0)), []
        )

    def test_invalid_week(self) -> None:
        with self.assertRaises(ValueError):
            check_week([], 0.0)


class TestFeasibility(unittest.TestCase):
    """上下限打架的情况：T 的 10% 上限与 4.8 km 下限。"""

    def test_threshold_feasible_from_48km(self) -> None:
        """周跑量 48 km 恰好是临界点（4.8 / 10%）。"""
        self.assertFalse(threshold_cap(40.0).feasible)
        self.assertFalse(threshold_cap(47.9).feasible)
        self.assertTrue(threshold_cap(48.0).feasible)

    def test_other_intensities_always_feasible(self) -> None:
        """只有 T 有下限，其余强度没有这个问题。"""
        for name in ("L", "M", "I", "R"):
            with self.subTest(intensity=name):
                self.assertTrue(cap_for(name, 20.0).feasible)

    def test_infeasible_is_reported_in_dict(self) -> None:
        data = threshold_cap(40.0).as_dict()
        self.assertFalse(data["feasible"])
        self.assertIn("infeasible_reason", data)

    def test_check_week_flags_impossible_threshold(self) -> None:
        """周跑量 40 km 时，任何 T 训练都无解，必须单独报一条。"""
        violations = check_week([Session("T", 4.0)], 40.0)
        ranges = [v for v in violations if v.unit == "range"]
        self.assertEqual(len(ranges), 1)
        self.assertEqual(ranges[0].intensity, "T")
        self.assertIn("没有可行区间", ranges[0].message)

    def test_check_week_does_not_flag_feasible_week(self) -> None:
        violations = check_week([Session("T", 5.0)], 56.0)
        self.assertEqual([v for v in violations if v.unit == "range"], [])


class TestLongRunNonMonotonic(unittest.TestCase):
    """L 上限在 64 km 处会突然下降——这是书里的规则，不是 bug。"""

    def test_drops_at_the_boundary(self) -> None:
        just_below = long_run_cap(63.9).max_km
        at_boundary = long_run_cap(64.0).max_km
        self.assertGreater(just_below, at_boundary)
        self.assertAlmostEqual(just_below, 19.17, places=2)
        self.assertAlmostEqual(at_boundary, 16.0, places=6)

    def test_recovers_above_boundary(self) -> None:
        """过了 64 km 后按 25% 重新增长，所以会再涨回去。"""
        self.assertGreater(long_run_cap(70.0).max_km, long_run_cap(64.0).max_km)

    def test_note_explains_it(self) -> None:
        notes = " ".join(long_run_cap(64.0).notes)
        self.assertIn("不是单调", notes)
        self.assertIn("不是实现问题", notes)


class TestWindowWidth(unittest.TestCase):
    """上下限之间的可用宽度。"""

    def test_threshold_window_at_64km(self) -> None:
        """T 窗口只有 6.4 - 4.8 = 1.6 km 宽。"""
        cap = threshold_cap(64.0)
        self.assertAlmostEqual(cap.window_km, 1.6, places=6)

    def test_no_lower_bound_returns_none(self) -> None:
        self.assertIsNone(interval_cap(64.0).window_km)
        self.assertIsNone(long_run_cap(64.0).window_km)

    def test_window_shrinks_as_volume_drops(self) -> None:
        self.assertGreater(threshold_cap(64.0).window_km, threshold_cap(52.0).window_km)

    def test_in_dict(self) -> None:
        data = threshold_cap(64.0).as_dict()
        self.assertAlmostEqual(data["window_km"], 1.6, places=6)


class TestAppliedRatio(unittest.TestCase):
    """实际套用的百分比档位——同一强度会在不同周跑量下换档。"""

    def test_marathon_switches_at_64km(self) -> None:
        """M 少于 64 km 时是 30%，64 km 及以上是 20%（第4章 L1392、第14章 L3480）。"""
        self.assertAlmostEqual(marathon_pace_cap(35.0).ratio, 0.30)
        self.assertAlmostEqual(marathon_pace_cap(63.9).ratio, 0.30)
        self.assertAlmostEqual(marathon_pace_cap(64.0).ratio, 0.20)
        self.assertAlmostEqual(marathon_pace_cap(96.0).ratio, 0.20)

    def test_long_run_switches_at_64km(self) -> None:
        self.assertAlmostEqual(long_run_cap(48.0).ratio, 0.30)
        self.assertAlmostEqual(long_run_cap(64.0).ratio, 0.25)

    def test_long_run_trail_branches(self) -> None:
        self.assertAlmostEqual(
            long_run_cap(64.0, surface="trail", phase=1).ratio, 0.30
        )
        self.assertAlmostEqual(
            long_run_cap(64.0, surface="trail", phase=2).ratio, 0.25
        )

    def test_fixed_intensities(self) -> None:
        self.assertAlmostEqual(threshold_cap(64.0).ratio, 0.10)
        self.assertAlmostEqual(interval_cap(64.0).ratio, 0.08)
        self.assertAlmostEqual(repetition_cap(64.0).ratio, 0.05)

    def test_ratio_is_in_dict(self) -> None:
        data = marathon_pace_cap(35.0).as_dict()
        self.assertAlmostEqual(data["ratio_pct"], 30.0)
        data = marathon_pace_cap(96.0).as_dict()
        self.assertAlmostEqual(data["ratio_pct"], 20.0)

    def test_ratio_matches_max_km(self) -> None:
        """ratio × 周跑量应当等于距离上限（29 km 与 24 km 封顶除外）。"""
        for weekly in (35.0, 48.0, 60.0):
            with self.subTest(weekly=weekly):
                cap = marathon_pace_cap(weekly)
                self.assertAlmostEqual(
                    cap.ratio * weekly, cap.max_km, places=6
                )


class TestRuleRegistry(unittest.TestCase):
    """规则注册表自身的完整性。"""

    def test_ids_are_unique_and_consistent(self) -> None:
        seen = set()
        for key, rule in RULES.items():
            self.assertEqual(key, rule.rule_id)
            self.assertNotIn(key, seen)
            seen.add(key)

    def test_every_rule_has_provenance(self) -> None:
        for rule in RULES.values():
            with self.subTest(rule=rule.rule_id):
                self.assertTrue(rule.chapter.startswith("第"))
                self.assertTrue(rule.lines.startswith("L"))
                self.assertTrue(rule.summary)

    def test_caps_cite_existing_rules(self) -> None:
        """所有上限引用的 rule_id 都必须在注册表里。"""
        caps = [
            long_run_cap(48.0),
            long_run_cap(80.0),
            long_run_cap(64.0, surface="trail", phase=1),
            long_run_cap(80.0, surface="trail", phase=2),
            marathon_pace_cap(48.0),
            marathon_pace_cap(96.0),
            threshold_cap(64.0),
            interval_cap(64.0),
            repetition_cap(64.0),
        ]
        for cap in caps:
            for rule in cap.rules:
                with self.subTest(rule=rule.rule_id):
                    self.assertIn(rule.rule_id, RULES)


if __name__ == "__main__":
    unittest.main(verbosity=2)
