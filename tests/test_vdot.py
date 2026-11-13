# -*- coding: utf-8 -*-
"""daniels.vdot 的回归测试。

真值来源全部是书中正文或表格里可以直接读到的数字，不引用第三方转录。
每条测试的注释标出出处，便于复查。

运行：
    cd D:\\training
    python -m unittest discover -s tests -v
"""

from __future__ import annotations

import math
import unittest

from daniels import (
    TABLE5_3,
    DanielsError,
    VdotRangeError,
    altitude_correction,
    format_time,
    h_time_cap,
    pace_set,
    parse_time,
    pct_max,
    race_time,
    vdot_from_race,
)
from daniels.vdot import AltitudeRangeError, METER_PER_MILE


def rel_err(actual: float, expected: float) -> float:
    """相对误差（绝对值，百分比）。"""
    return abs(actual - expected) / expected * 100.0


class TestVdotFromRace(unittest.TestCase):
    """VDOT 正算：附录 D 的分界值 + 第 3 章的两个 5 km 对应点。"""

    def test_appendix_d_boundaries(self) -> None:
        """附录 D L4049-L4055：1600 m 成绩对应的 VDOT 分界值。"""
        cases = [
            (280.0, 63.8),  # 4:40 或更快
            (320.0, 54.8),  # 5:20
            (321.0, 54.7),  # 5:21
            (372.0, 46.3),  # 6:12
        ]
        for seconds, expected in cases:
            with self.subTest(time=format_time(seconds)):
                got = vdot_from_race(1600.0, seconds)
                self.assertAlmostEqual(got, expected, delta=0.10)

    def test_ch3_five_k_mapping(self) -> None:
        """第 3 章 L1234：相对 O2max 50 → 5 km 19:56；60 → 17:02。"""
        self.assertAlmostEqual(
            vdot_from_race(5000.0, 19 * 60 + 56), 50.0, delta=0.15
        )
        self.assertAlmostEqual(
            vdot_from_race(5000.0, 17 * 60 + 2), 60.0, delta=0.15
        )

    def test_pct_max_at_thirty_minutes(self) -> None:
        """第 3 章 L1082/L1143：30 分钟左右的比赛可达到约 93% 的 VO2max。"""
        self.assertAlmostEqual(pct_max(30.0), 0.93, delta=0.004)

    def test_distance_out_of_range(self) -> None:
        with self.assertRaises(DanielsError):
            vdot_from_race(400.0, 60.0)

    def test_negative_time(self) -> None:
        with self.assertRaises(DanielsError):
            vdot_from_race(5000.0, -1.0)


class TestRaceTime(unittest.TestCase):
    """VDOT 反算：表 5—1 的「1.6 公里」列实际是 1 英里。"""

    def test_table5_1_mile_times(self) -> None:
        """第 5 章 L1780：VDOT 51 ↔ 1.6 公里 5:44；L1802：VDOT 60 ↔ 4:57。

        这两句只有在按 1 英里（1609.344 m）计算时才成立；
        若按 1600 m 算会分别得到 50.6 和 59.7，相差约 0.4 个 VDOT。
        """
        self.assertAlmostEqual(race_time(METER_PER_MILE, 51.0), 344.0, delta=2.0)
        self.assertAlmostEqual(race_time(METER_PER_MILE, 60.0), 297.0, delta=2.0)

    def test_roundtrip(self) -> None:
        for vdot in (25.0, 40.0, 51.0, 63.8, 80.0):
            with self.subTest(vdot=vdot):
                seconds = race_time(10000.0, vdot)
                self.assertAlmostEqual(
                    vdot_from_race(10000.0, seconds), vdot, delta=0.01
                )

    def test_argument_order_matches_forward_function(self) -> None:
        """``race_time`` 与 ``vdot_from_race`` 都是距离在前。

        早先 ``race_time`` 是 ``(vdot, distance)``，和正向函数相反——
        两个参数都是数字，写反了只报一句"VDOT 5000 超出范围"，看不出是写反了。
        """
        import inspect

        forward = list(inspect.signature(vdot_from_race).parameters)
        backward = list(inspect.signature(race_time).parameters)
        self.assertEqual(forward[0], "distance_m")
        self.assertEqual(backward[0], "distance_m")

    def test_swapped_arguments_hint_at_the_mistake(self) -> None:
        """参数写反时，报错要说清是写反了，不能只说"距离超范围"。"""
        with self.assertRaises(DanielsError) as ctx:
            race_time(35.0, 5000.0)  # 本意是 (5000, 35)
        self.assertIn("写反", str(ctx.exception))


class TestInputValidation(unittest.TestCase):
    """烂输入要报清楚的错，不能把 Python 的裸 TypeError 抛给用户。"""

    def test_time_none(self) -> None:
        with self.assertRaises(DanielsError) as ctx:
            vdot_from_race(5000, None)  # type: ignore[arg-type]
        self.assertIn("成绩必须是秒数", str(ctx.exception))

    def test_time_string(self) -> None:
        with self.assertRaises(DanielsError):
            vdot_from_race(5000, "20:00")  # type: ignore[arg-type]

    def test_time_zero_and_negative(self) -> None:
        for bad in (0, -1, -1200.0):
            with self.subTest(bad=bad):
                with self.assertRaises(DanielsError):
                    vdot_from_race(5000, bad)

    def test_distance_wrong_type(self) -> None:
        for bad in (None, "5000", [5000]):
            with self.subTest(bad=bad):
                with self.assertRaises(DanielsError):
                    vdot_from_race(bad, 1200)  # type: ignore[arg-type]

    def test_distance_out_of_range(self) -> None:
        for bad in (0, 799, 42196):
            with self.subTest(bad=bad):
                with self.assertRaises(DanielsError):
                    vdot_from_race(bad, 1200)

    def test_vdot_out_of_range(self) -> None:
        for bad in (19.9, 85.1, float("nan"), float("inf")):
            with self.subTest(vdot=bad):
                with self.assertRaises((VdotRangeError, DanielsError)):
                    race_time(5000.0, bad)


class TestPaceSetVdot51(unittest.TestCase):
    """第 5 章 L1780-L1786 给出的 VDOT 51 全部配速，逐项核对。"""

    @classmethod
    def setUpClass(cls) -> None:
        cls.ps = pace_set(51.0)

    def test_e_range(self) -> None:
        """E 4:52 ~ 5:29 每公里（1.6 公里 7:49 ~ 8:49）。"""
        self.assertAlmostEqual(self.ps.e_fast.seconds_per_km, 292.0, delta=5.0)
        self.assertAlmostEqual(self.ps.e_slow.seconds_per_km, 329.0, delta=5.0)

    def test_m_pace(self) -> None:
        """M 4:27 每公里（7:09 每 1.6 公里）。"""
        self.assertAlmostEqual(self.ps.m.seconds_per_km, 267.0, delta=2.0)

    def test_t_pace(self) -> None:
        """T 1:40/400 m、4:11/km、6:44/1.6 km。"""
        self.assertAlmostEqual(self.ps.t.seconds_per_km, 251.0, delta=3.0)
        self.assertAlmostEqual(self.ps.t.seconds_per_400m, 100.0, delta=1.2)

    def test_i_pace(self) -> None:
        """I 92 s/400 m、3:04/800 m、3:51/km、4:36/1200 m。"""
        self.assertAlmostEqual(self.ps.i.seconds_per_km, 231.0, delta=3.0)
        self.assertAlmostEqual(self.ps.i.seconds_per_400m, 92.0, delta=1.2)

    def test_r_pace(self) -> None:
        """R 43 s/200 m、64 s/300 m、86 s/400 m。"""
        self.assertAlmostEqual(self.ps.r.seconds_per_400m, 86.0, delta=1.6)

    def test_m_is_marathon_equivalent(self) -> None:
        """M 配速反算马拉松成绩，VDOT 应回到 51。"""
        marathon = self.ps.m.time_for(42195.0)
        self.assertAlmostEqual(
            vdot_from_race(42195.0, marathon), 51.0, delta=0.15
        )


class TestPaceSetVdot60(unittest.TestCase):
    """第 5 章 L1802-L1804 给出的 VDOT 60 配速。"""

    @classmethod
    def setUpClass(cls) -> None:
        cls.ps = pace_set(60.0)

    def test_t_pace(self) -> None:
        """T 88 s/400 m。"""
        self.assertAlmostEqual(self.ps.t.seconds_per_400m, 88.0, delta=1.2)

    def test_i_pace(self) -> None:
        """I 81 s/400 m（比 R 慢 6 秒）。"""
        self.assertAlmostEqual(self.ps.i.seconds_per_400m, 81.0, delta=1.2)

    def test_r_pace(self) -> None:
        """R 75 s/400 m。"""
        self.assertAlmostEqual(self.ps.r.seconds_per_400m, 75.0, delta=1.6)


class TestDoseThresholds(unittest.TestCase):
    """书中的「能不能跑这个距离」临界 VDOT，用于验证模型不是拟合出来的。"""

    def test_i_1600m_at_vdot_66(self) -> None:
        """第 5 章 L1784：能以 I 配速跑 1.6 km 的最低 VDOT 为 66。

        对应剂量上限「单回合 I 不超过 5 分钟」。
        """
        seconds = pace_set(66.0).i.time_for(1600.0)
        self.assertAlmostEqual(seconds, 300.0, delta=3.0)

    def test_i_1600m_at_vdot_51_exceeds(self) -> None:
        """同一句：VDOT 51 跑 1.6 km I 会超过 5 分钟。"""
        self.assertGreater(pace_set(51.0).i.time_for(1600.0), 300.0)

    def test_r_800m_at_vdot_77(self) -> None:
        """第 5 章 L1786：能跑 800 m R 的 VDOT 约为 77（回合不超过 2 分钟）。"""
        self.assertLessEqual(pace_set(77.0).r.time_for(800.0), 120.0)

    def test_r_600m_at_vdot_56(self) -> None:
        """同一段：VDOT 56 可以跑 600 m R。"""
        self.assertLessEqual(pace_set(56.0).r.time_for(600.0), 120.0)

    def test_r_600m_at_vdot_51_cannot(self) -> None:
        """同一段：VDOT 51 跑 600 m R 已略微勉强（超过 2 分钟）。"""
        self.assertGreater(pace_set(51.0).r.time_for(600.0), 120.0)


class TestTable53(unittest.TestCase):
    """表 5—3（初跑者表）恢复后的校验。"""

    def test_novice_row_matches_table(self) -> None:
        """整数 VDOT 上，novice_row 的四档都必须等于表中原值。"""
        for row in TABLE5_3:
            vdot, m_s, t_s, i_400, r_200 = row
            with self.subTest(vdot=vdot):
                ps = pace_set(vdot)
                self.assertTrue(ps.novice)
                self.assertIsNotNone(ps.novice_row)
                nr = ps.novice_row
                self.assertAlmostEqual(nr.m.seconds_per_km, m_s, delta=0.01)
                self.assertAlmostEqual(nr.t.seconds_per_km, t_s, delta=0.01)
                self.assertAlmostEqual(nr.i.seconds_per_400m, i_400, delta=0.01)
                self.assertAlmostEqual(nr.r.seconds_per_400m / 2.0, r_200, delta=0.01)

    def test_novice_flag_boundary(self) -> None:
        """表 5—3 覆盖 VDOT 20~30（含两端），故上界取闭区间。"""
        self.assertTrue(pace_set(20.0).novice)
        self.assertTrue(pace_set(30.0).novice)
        self.assertIsNotNone(pace_set(30.0).novice_row)
        self.assertFalse(pace_set(30.1).novice)
        self.assertIsNone(pace_set(30.1).novice_row)

    def test_novice_interpolation_is_smooth(self) -> None:
        """非整数 VDOT 上按线性内插，且落在相邻两行之间。"""
        nr = pace_set(28.5).novice_row
        self.assertIsNotNone(nr)
        self.assertAlmostEqual(
            nr.m.seconds_per_km, (447.0 + 435.0) / 2.0, delta=0.01
        )
        self.assertAlmostEqual(
            nr.i.seconds_per_400m, (154.0 + 148.0) / 2.0, delta=0.01
        )

    def test_t_replicates_table(self) -> None:
        """T 档：表 5—3 的 11 行，最大误差 0.72%。"""
        for row in TABLE5_3:
            vdot, t_seconds = row[0], row[2]
            with self.subTest(vdot=vdot):
                got = pace_set(vdot).t.seconds_per_km
                self.assertLess(rel_err(got, t_seconds), 0.9)

    def test_r_replicates_table(self) -> None:
        """R 档：表 5—3 的 11 行，最大误差 1.43%。"""
        for row in TABLE5_3:
            vdot, r_200m = row[0], row[4]
            with self.subTest(vdot=vdot):
                got = pace_set(vdot).r.seconds_per_400m / 2.0
                self.assertLess(rel_err(got, r_200m), 1.8)

    def test_i_documented_deviation(self) -> None:
        """I 档：与表 5—3 印刷值最大差 3.5%。

        这不是公式错：表 5—3 的 I 列是按 R 加 7~8 秒/400 m 排的，
        而本模块按 98% vVO2max 算。此测试锁定已知偏差，防止无声漂移。
        """
        for row in TABLE5_3:
            vdot, i_400m = row[0], row[3]
            with self.subTest(vdot=vdot):
                got = pace_set(vdot).i.seconds_per_400m
                self.assertLess(rel_err(got, i_400m), 3.8)

    def test_m_documented_divergence(self) -> None:
        """M 档：表 5—3 用固定的 77.37% VDOT，本模块用马拉松等时，差约 3%。

        第 5 章 L1810 说表 5—3 是「为找不到自己配速的跑者增加的」，
        与表 5—2 的构造不同。此测试把差异锁定在 2%~5%。
        """
        for row in TABLE5_3:
            vdot, m_seconds = row[0], row[1]
            with self.subTest(vdot=vdot):
                gap = rel_err(pace_set(vdot).m.seconds_per_km, m_seconds)
                self.assertGreater(gap, 1.5)
                self.assertLess(gap, 5.0)


class TestFrAndH(unittest.TestCase):
    """FR 与 H 两个档位。"""

    def test_fr_relation(self) -> None:
        """第 9 章 L2659：FR 比 R 每 200 m 快 3 秒。"""
        for vdot in (30.0, 51.0, 70.0):
            with self.subTest(vdot=vdot):
                ps = pace_set(vdot)
                self.assertAlmostEqual(
                    ps.r.seconds_per_400m - ps.fr.seconds_per_400m, 6.0, delta=1e-6
                )

    def test_h_equals_i(self) -> None:
        """第 13 章 L3318：H 与 I 同配速，只是不规定距离。"""
        ps = pace_set(51.0)
        self.assertAlmostEqual(
            ps.h.seconds_per_km, ps.i.seconds_per_km, delta=1e-9
        )

    def test_h_time_cap_book_example(self) -> None:
        """第 13 章 L3318 的算例：周跑量 80 km、5 km 18:45 → 上限 24 分钟。"""
        cap = h_time_cap(80.0, 18 * 60 + 45, 39 * 60)
        self.assertAlmostEqual(cap, 24 * 60, delta=1.0)


class TestAltitude(unittest.TestCase):
    """海拔修正。"""

    def test_below_threshold_no_change(self) -> None:
        """第 8 章 L2341：914 m 以下无影响。"""
        self.assertEqual(altitude_correction(0.0).penalty_s_per_400m, 0.0)
        self.assertEqual(altitude_correction(914.0).penalty_s_per_400m, 0.0)

    def test_reference_2130(self) -> None:
        """第 14 章 L3582：2130 m 时 I/T/M 每 400 m 慢 4 秒。"""
        corr = altitude_correction(2130.0)
        self.assertAlmostEqual(corr.penalty_s_per_400m, 4.0, delta=1e-9)
        self.assertFalse(corr.extrapolated)

    def test_half_at_1524(self) -> None:
        """第 8 章 L2341：2130 m 的压力几乎是 1524 m 的两倍。"""
        corr = altitude_correction(1524.0)
        self.assertAlmostEqual(corr.penalty_s_per_400m, 2.0, delta=0.05)

    def test_extrapolation_flag(self) -> None:
        corr = altitude_correction(2400.0)
        self.assertTrue(corr.extrapolated)

    def test_above_max_raises(self) -> None:
        with self.assertRaises(AltitudeRangeError):
            altitude_correction(2501.0)

    def test_negative_raises(self) -> None:
        with self.assertRaises(AltitudeRangeError):
            altitude_correction(-1.0)

    def test_paces_at_altitude(self) -> None:
        """2130 m：I/T/M 各慢 10 秒/公里；R 与 E 不变。"""
        sea = pace_set(51.0)
        high = pace_set(51.0, altitude_m=2130.0)
        for name in ("i", "t", "m"):
            with self.subTest(intensity=name):
                delta = getattr(high, name).seconds_per_km - getattr(
                    sea, name
                ).seconds_per_km
                self.assertAlmostEqual(delta, 10.0, delta=1e-6)
        self.assertAlmostEqual(
            high.r.seconds_per_km, sea.r.seconds_per_km, delta=1e-9
        )
        self.assertAlmostEqual(
            high.e_fast.seconds_per_km, sea.e_fast.seconds_per_km, delta=1e-9
        )


class TestPaceObject(unittest.TestCase):
    """Pace 值对象的行为。"""

    def test_unit_conversions(self) -> None:
        p = pace_set(51.0).m
        self.assertAlmostEqual(p.meters_per_minute, 60000.0 / p.seconds_per_km)
        self.assertAlmostEqual(p.kph * p.seconds_per_km, 3600.0)
        self.assertAlmostEqual(
            p.seconds_per_mile, p.seconds_per_km * METER_PER_MILE / 1000.0
        )

    def test_time_and_distance(self) -> None:
        p = pace_set(51.0).t
        self.assertAlmostEqual(p.time_for(5000.0), p.seconds_per_km * 5.0)
        self.assertAlmostEqual(p.distance_in(1800.0), 1800.0 / p.seconds_per_km * 1000.0)

    def test_ceil_rounds_up_to_whole_seconds(self) -> None:
        """``format_400m_ceil`` 按整秒向上取整。

        注意：书中表 5—2 的 R 列比 1 英里比赛配速慢约 1%（VDOT 60 时
        模型 73.9 s 而书中印 75 s），所以取整本身复现不了书里的印刷值。
        这一差异已由 ``TestPaceSetVdot60.test_r_pace`` 的 1.6 秒容差覆盖。
        """
        from daniels import Pace

        self.assertEqual(Pace(185.0).format_400m_ceil(), "1:14")
        self.assertEqual(Pace(185.5).format_400m_ceil(), "1:15")
        self.assertEqual(Pace(184.0).format_400m_ceil(), "1:14")

    def test_invalid_pace(self) -> None:
        from daniels import Pace

        with self.assertRaises(DanielsError):
            Pace(0.0)


class TestFormatting(unittest.TestCase):
    """时间格式化的往返一致性。"""

    def test_format(self) -> None:
        self.assertEqual(format_time(267.0), "4:27")
        self.assertEqual(format_time(3725.0), "1:02:05")
        self.assertEqual(format_time(0.0), "0:00")

    def test_parse(self) -> None:
        self.assertAlmostEqual(parse_time("5:44"), 344.0)
        self.assertAlmostEqual(parse_time("1:02:05"), 3725.0)
        self.assertAlmostEqual(parse_time("4：27"), 267.0)  # 全角冒号

    def test_roundtrip(self) -> None:
        for text, seconds in (("4:27", 267.0), ("1:02:05", 3725.0)):
            with self.subTest(text=text):
                self.assertEqual(format_time(parse_time(text)), text)

    def test_parse_invalid(self) -> None:
        for bad in ("", "abc", "1:2:3:4"):
            with self.subTest(text=bad):
                with self.assertRaises(DanielsError):
                    parse_time(bad)


class TestPaceSetSerialization(unittest.TestCase):
    """as_dict 的输出结构，供上层规则与 API 使用。"""

    def test_keys(self) -> None:
        d = pace_set(51.0).as_dict()
        for key in (
            "vdot", "E_per_km", "M_per_km", "T_per_km", "T_per_400m",
            "I_per_km", "I_per_400m", "R_per_400m", "R_per_200m",
            "FR_per_200m", "H_per_km", "novice", "novice_M_per_km",
        ):
            self.assertIn(key, d)
        self.assertEqual(len(d["E_per_km"]), 2)
        self.assertFalse(d["novice"])
        self.assertIsNone(d["novice_M_per_km"])

    def test_formatted_values_match_book_at_vdot51(self) -> None:
        """四舍五入到整秒后，7 个数里有 6 个与书中逐字相同。

        唯一对不上的是 R：模型 85.4 秒 → 1:25，书中印 1:26。
        这是书内表 5—1（5:44）与表 5—2（R 折合 5:46）自身相差 2 秒/英里
        造成的，已在模块文档里记录。
        """
        d = pace_set(51.0).as_dict()
        self.assertEqual(d["M_per_km"], "4:27")
        self.assertEqual(d["T_per_km"], "4:11")
        self.assertEqual(d["T_per_400m"], "1:40")
        self.assertEqual(d["I_per_km"], "3:51")
        self.assertEqual(d["I_per_400m"], "1:32")
        self.assertEqual(d["R_per_200m"], "0:43")
        # R 每 400 米：1:25 vs 书中 1:26，差 1 秒
        self.assertEqual(d["R_per_400m"], "1:25")
        self.assertLessEqual(
            abs(pace_set(51.0).r.seconds_per_400m - 86.0), 1.6
        )

    def test_steps_are_positive(self) -> None:
        """I 慢于 R、T 慢于 I，且步长随 VDOT 下降而增大（第 5 章 L1804）。"""
        ps40 = pace_set(40.0)
        ps70 = pace_set(70.0)
        self.assertGreater(ps40.step_t_minus_i_s_per_400m, 0)
        self.assertGreater(ps40.step_t_minus_i_s_per_400m,
                           ps70.step_t_minus_i_s_per_400m)


if __name__ == "__main__":
    unittest.main(verbosity=2)
