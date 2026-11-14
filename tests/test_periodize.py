# -*- coding: utf-8 -*-
"""daniels.periodize 的回归测试。

周数分配的每个断言都对应第 6 章里的一句话；找不到出处的长度，
测试的是「默认拒绝」这个行为本身。

运行：
    cd D:\\daniels-running-skill
    python -m unittest discover -s tests -v
"""

from __future__ import annotations

import unittest

from daniels.periodize import (
    DOCUMENTED_SPLITS,
    MIN_WEEKS,
    PHASES,
    WEEK_DAYS,
    PhaseLengthError,
    phase_info,
    plan_schedule,
    q_intensities,
    quality_days,
    taper_rules,
    weekly_volume_bounds,
)


class TestDocumentedSplits(unittest.TestCase):
    """书中直接记录的五种长度。"""

    def test_three_weeks_all_phase_one(self) -> None:
        """3 周全部用于阶段一（第6章 L2059-L2061）。"""
        plan = plan_schedule(3)
        self.assertEqual(plan.weeks, (3, 0, 0, 0))
        self.assertTrue(plan.documented)
        self.assertEqual(plan.active_phases(), (1,))

    def test_six_weeks_phase_one_then_four(self) -> None:
        """6 周 = 阶段一 3 周 + 阶段四 3 周（第6章 L2073）。"""
        plan = plan_schedule(6)
        self.assertEqual(plan.weeks, (3, 0, 0, 3))
        self.assertEqual(plan.active_phases(), (1, 4))

    def test_nine_weeks_skips_phase_three(self) -> None:
        """9 周跳过阶段三（第6章 L2073）。"""
        plan = plan_schedule(9)
        self.assertEqual(plan.weeks, (3, 3, 0, 3))
        self.assertEqual(plan.active_phases(), (1, 2, 4))

    def test_twelve_weeks_three_each(self) -> None:
        plan = plan_schedule(12)
        self.assertEqual(plan.weeks, (3, 3, 3, 3))

    def test_twenty_weeks(self) -> None:
        """20 周 = 4 / 6 / 6 / 4（第6章 L2075）。"""
        plan = plan_schedule(20)
        self.assertEqual(plan.weeks, (4, 6, 6, 4))

    def test_twenty_three_weeks(self) -> None:
        """23 周从阶段四去掉 1 周（第6章 L2075）。"""
        plan = plan_schedule(23)
        self.assertEqual(plan.weeks, (6, 6, 6, 5))

    def test_twenty_four_weeks_four_by_six(self) -> None:
        """24 周 = 4 个 6 周（第6章 L2051）。"""
        plan = plan_schedule(24)
        self.assertEqual(plan.weeks, (6, 6, 6, 6))

    def test_all_splits_sum_correctly(self) -> None:
        for weeks, split in DOCUMENTED_SPLITS.items():
            with self.subTest(weeks=weeks):
                self.assertEqual(sum(split), weeks)
                self.assertEqual(plan_schedule(weeks).weeks, split)


class TestExtendedLengths(unittest.TestCase):
    """超过 24 周时，富余时间全部给阶段一。"""

    def test_extra_weeks_go_to_phase_one(self) -> None:
        plan = plan_schedule(28)
        self.assertEqual(plan.weeks, (10, 6, 6, 6))
        # documented 的意思是「这个划分出自书中」。28 周显然不是——
        # 书里只给了 3/6/9/12/20/23/24 这几种，下面那个测试自己也是这么说的。
        self.assertFalse(plan.documented)

    def test_note_flags_it_as_application_not_table(self) -> None:
        notes = " ".join(plan_schedule(30).notes)
        self.assertIn("不是书中直接给出的周数表", notes)


class TestUndocumentedLengths(unittest.TestCase):
    """书里没记录的长度：默认拒绝，显式允许才均分。"""

    def test_default_rejects(self) -> None:
        for weeks in (13, 16, 18, 21, 22):
            with self.subTest(weeks=weeks):
                with self.assertRaises(PhaseLengthError):
                    plan_schedule(weeks)

    def test_error_message_lists_documented_lengths(self) -> None:
        with self.assertRaises(PhaseLengthError) as ctx:
            plan_schedule(16)
        message = str(ctx.exception)
        for weeks in ("3", "6", "9", "12", "20", "23", "24"):
            self.assertIn(weeks, message)
        self.assertIn("allow_undocumented=True", message)

    def test_opt_in_even_split(self) -> None:
        plan = plan_schedule(16, allow_undocumented=True)
        self.assertEqual(plan.weeks, (4, 4, 4, 4))
        self.assertFalse(plan.documented)
        self.assertEqual(sum(plan.weeks), 16)

    def test_remainder_goes_to_early_phases(self) -> None:
        """17 周：余数给阶段一，得到 5 / 4 / 4 / 4。"""
        plan = plan_schedule(17, allow_undocumented=True)
        self.assertEqual(plan.weeks, (5, 4, 4, 4))

    def test_undocumented_notes_explain_the_shape(self) -> None:
        notes = " ".join(plan_schedule(21, allow_undocumented=True).notes)
        self.assertIn("均分", notes)


class TestInvalidLengths(unittest.TestCase):
    """非法输入。"""

    def test_too_short(self) -> None:
        for weeks in (0, 1, 2):
            with self.subTest(weeks=weeks):
                with self.assertRaises(PhaseLengthError):
                    plan_schedule(weeks)

    def test_minimum_is_documented(self) -> None:
        self.assertEqual(MIN_WEEKS, 3)

    def test_non_integer(self) -> None:
        for bad in (3.5, "6", True, None):
            with self.subTest(value=bad):
                with self.assertRaises(PhaseLengthError):
                    plan_schedule(bad)  # type: ignore[arg-type]


class TestPhaseOfWeek(unittest.TestCase):
    """周序号到阶段的映射。"""

    def test_twenty_four_week_mapping(self) -> None:
        plan = plan_schedule(24)
        for week, expected in (
            (1, 1), (6, 1),
            (7, 2), (12, 2),
            (13, 3), (18, 3),
            (19, 4), (24, 4),
        ):
            with self.subTest(week=week):
                self.assertEqual(plan.phase_of_week(week), expected)

    def test_nine_week_mapping(self) -> None:
        plan = plan_schedule(9)
        self.assertEqual(
            [plan.phase_of_week(w) for w in range(1, 10)],
            [1, 1, 1, 2, 2, 2, 4, 4, 4],
        )

    def test_out_of_range(self) -> None:
        plan = plan_schedule(24)
        for bad in (0, 25, -1):
            with self.subTest(week=bad):
                with self.assertRaises(ValueError):
                    plan.phase_of_week(bad)


class TestPhaseInfo(unittest.TestCase):
    """四个阶段的定义。"""

    def test_codes(self) -> None:
        self.assertEqual(
            [p.code for p in PHASES], ["B/FIP", "IQ", "TQ", "FQ"]
        )

    def test_primary_intensity_progression(self) -> None:
        """E → R → I → T（第6章 L2036）。"""
        self.assertEqual(
            [p.primary[0] for p in PHASES], ["E", "R", "I", "T"]
        )

    def test_phase_four_drops_intervals(self) -> None:
        """阶段四长距离选手停掉 I（第6章 L2034）。"""
        self.assertIn("I", phase_info(4).dropped)

    def test_invalid_index(self) -> None:
        for bad in (0, 5, -1):
            with self.subTest(index=bad):
                with self.assertRaises(ValueError):
                    phase_info(bad)


class TestQualityDays(unittest.TestCase):
    """Q 日排布。"""

    def test_three_sessions_default(self) -> None:
        """周一、周三、周六（第6章 L2094，周日为第一天）。"""
        self.assertEqual(quality_days(), (2, 4, 7))

    def test_back_to_back(self) -> None:
        """背靠背时放到第 3、4、7 天（同一段）。"""
        self.assertEqual(quality_days(back_to_back=True), (3, 4, 7))

    def test_two_sessions(self) -> None:
        """两周一次 Q 时用周一、周四（第10章 L2836）。"""
        self.assertEqual(quality_days(2), (2, 5))

    def test_invalid_count(self) -> None:
        for bad in (1, 4, 0):
            with self.subTest(count=bad):
                with self.assertRaises(ValueError):
                    quality_days(bad)


class TestRaceWeekReshuffle(unittest.TestCase):
    """比赛周的 Q 重排。"""

    def test_saturday_race(self) -> None:
        """周六比赛 → 周一和周三（第10章 L2842）；编号 1=周日 故为 (2, 4)。"""
        self.assertEqual(quality_days(2, race_weekday=7), (2, 4))
        self.assertEqual(
            [WEEK_DAYS[d - 1] for d in quality_days(2, race_weekday=7)],
            ["周一", "周三"],
        )

    def test_friday_race(self) -> None:
        """周五比赛 → 周一和周二（第10章 L2842），即 (2, 3)。"""
        self.assertEqual(quality_days(2, race_weekday=6), (2, 3))
        self.assertEqual(
            [WEEK_DAYS[d - 1] for d in quality_days(2, race_weekday=6)],
            ["周一", "周二"],
        )

    def test_sunday_race(self) -> None:
        """周日比赛 → Q2 挪到赛前那个周三（第11章 L3013）。"""
        self.assertEqual(quality_days(2, race_weekday=1), (4,))

    def test_gap_to_race(self) -> None:
        """最后一次 Q 距比赛的天数：周六和周五为 3 天，周日为 4 天。"""
        for race, expected in ((7, 3), (6, 3), (1, 4)):
            with self.subTest(race_weekday=race):
                gap = (race - max(quality_days(2, race_weekday=race))) % 7
                self.assertEqual(gap, expected)

    def test_conflicts_with_taper_rule(self) -> None:
        """如实记录冲突，不掩盖。

        第10章 L2842 的排布让周六比赛的最后一个 Q 落在赛前 3 天，
        而第14章 L3496 要求赛前 4~5 天完成最后一次 T 训练。
        两条规则不合，本模块各自保留、由调用方取舍。
        """
        low, _ = taper_rules().last_quality_days_before_race
        gap_sat = (7 - max(quality_days(2, race_weekday=7))) % 7
        self.assertLess(gap_sat, low)
        self.assertIn("冲突", taper_rules().conflict_note)

    def test_midweek_race_has_no_room(self) -> None:
        """周二到周四的比赛，赛前放不下 Q 训练。"""
        for race in (2, 3, 4):
            with self.subTest(race_weekday=race):
                with self.assertRaises(ValueError):
                    quality_days(2, race_weekday=race)

    def test_thursday_race(self) -> None:
        """周四比赛时，最后一个 Q 落在周日（第 1 天）。"""
        self.assertEqual(quality_days(2, race_weekday=5), (1,))

    def test_invalid_weekday(self) -> None:
        for bad in (0, 8, -1):
            with self.subTest(day=bad):
                with self.assertRaises(ValueError):
                    quality_days(2, race_weekday=bad)


class TestQIntensities(unittest.TestCase):
    """各阶段 Q 日的强度建议。"""

    def test_phase_one(self) -> None:
        self.assertEqual(q_intensities(1), ("E", "E", "E"))

    def test_phase_two(self) -> None:
        self.assertEqual(q_intensities(2), ("R", "R", "T"))

    def test_phase_three_long_distance(self) -> None:
        self.assertEqual(q_intensities(3, long_distance=True), ("I", "T", "I"))

    def test_phase_three_short_distance_keeps_repetition(self) -> None:
        self.assertEqual(q_intensities(3, long_distance=False), ("I", "R", "I"))

    def test_phase_four(self) -> None:
        self.assertEqual(q_intensities(4), ("T", "T", "R"))

    def test_phase_four_short_distance_mixes_in_repetition(self) -> None:
        """第6章 L2034：短距离选手阶段四把 T 和 R 结合，不是两个 T。

        早先 long_distance 只在阶段三起作用，阶段四被忽略——5 公里目标会拿到
        ("T", "T")，而那正是短距离选手最不该做的。
        """
        self.assertEqual(
            q_intensities(4, long_distance=False), ("T", "R", "T")
        )
        self.assertEqual(
            q_intensities(4, long_distance=False, q_count=2), ("T", "R")
        )

    def test_phase_four_long_distance_unchanged(self) -> None:
        self.assertEqual(
            q_intensities(4, long_distance=True), ("T", "T", "R")
        )
        self.assertEqual(
            q_intensities(4, long_distance=True, q_count=2), ("T", "T")
        )

    def test_long_distance_flag_covers_both_phases_three_and_four(self) -> None:
        """参数在两个阶段都得起作用，不能只在阶段三。"""
        for phase in (3, 4):
            long_set = q_intensities(phase, long_distance=True, q_count=3)
            short_set = q_intensities(phase, long_distance=False, q_count=3)
            with self.subTest(phase=phase):
                self.assertNotEqual(long_set, short_set)

    def test_two_quality_days_take_first_two(self) -> None:
        """只有两个 Q 日时取前三项的前两项（推导，书中样例都假设三个）。"""
        self.assertEqual(q_intensities(3, long_distance=True, q_count=2), ("I", "T"))
        self.assertEqual(q_intensities(3, long_distance=False, q_count=2), ("I", "R"))
        self.assertEqual(q_intensities(4, q_count=2), ("T", "T"))
        self.assertEqual(q_intensities(2, q_count=2), ("R", "R"))
        self.assertEqual(q_intensities(1, q_count=2), ("E", "E"))

    def test_length_matches_q_count(self) -> None:
        for phase in (1, 2, 3, 4):
            for count in (2, 3):
                with self.subTest(phase=phase, count=count):
                    self.assertEqual(
                        len(q_intensities(phase, q_count=count)), count
                    )

    def test_invalid_phase(self) -> None:
        with self.assertRaises(ValueError):
            q_intensities(5)

    def test_invalid_q_count(self) -> None:
        for bad in (1, 4, 0):
            with self.subTest(count=bad):
                with self.assertRaises(ValueError):
                    q_intensities(3, q_count=bad)


class TestTaperAndVolume(unittest.TestCase):
    """减量规则与周跑量区间。"""

    def test_taper_values(self) -> None:
        """第14章 L3496 的四条具体动作。"""
        rules = taper_rules()
        self.assertEqual(rules.drop_strides_from_weeks_out, 3)
        self.assertEqual(rules.drop_hills_from_weeks_out, 2)
        self.assertEqual(rules.final_long_run_minutes, 90.0)
        self.assertEqual(rules.last_quality_days_before_race, (4, 5))
        self.assertEqual(rules.prefer, ("L", "T"))

    def test_volume_bounds(self) -> None:
        """第14章 L3398：周跑量定在 P 的 80%~100%。"""
        self.assertEqual(weekly_volume_bounds(), (0.80, 1.00))

    def test_as_dict_is_serializable(self) -> None:
        data = taper_rules().as_dict()
        self.assertEqual(data["final_long_run_minutes"], 90.0)
        self.assertIsInstance(data["prefer"], list)


class TestPlanSerialization(unittest.TestCase):
    """plan.as_dict 供上层 API 使用。"""

    def test_shape(self) -> None:
        data = plan_schedule(24).as_dict()
        self.assertEqual(data["total_weeks"], 24)
        self.assertEqual(
            data["weeks"], {"B/FIP": 6, "IQ": 6, "TQ": 6, "FQ": 6}
        )
        self.assertTrue(data["documented"])

    def test_zero_phases_are_omitted(self) -> None:
        data = plan_schedule(6).as_dict()
        self.assertEqual(data["weeks"], {"B/FIP": 3, "FQ": 3})


if __name__ == "__main__":
    unittest.main(verbosity=2)
