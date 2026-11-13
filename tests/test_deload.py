# -*- coding: utf-8 -*-
"""周期性减量（外推层）的测试。

这一组用例来自一次真实事故：有人要求「每 4 周安排一个减量周，跑量降 20%」，
得到了一张外表整齐、内部自相矛盾的表——

* 减量周排在第 4、8、11 周，间隔 4 和 3，不是每 4 周；
* 第 11、12 周连续减量，最后一个周期只剩 1 个训练周；
* 表头写「赛前最后 3 周去跨步跑」，表里写「跨步跑照做」；
* 表里赛周合计 29.1 km，却写成 38 km；
* 加量跳 +8 km，而规则只允许 +6.4 km，却宣称「全部通过校验」。

所以这里的断言不是「函数能跑」，而是**这些具体的错不能再出现**。

运行：
    cd D:\\training
    python -m unittest discover -s tests -v
"""

from __future__ import annotations

import io
import json
import unittest
from contextlib import redirect_stderr, redirect_stdout

import daniels as d
from daniels.__main__ import main


def run(*argv: str) -> tuple:
    """执行一次 CLI，返回 (退出码, 标准输出, 标准错误)。"""
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = main(list(argv))
    return code, out.getvalue(), err.getvalue()


#: 事故里的那张周跑量表，原样保留。
INCIDENT_VOLUMES = (35, 35, 35, 28, 35, 35, 43, 34, 43, 51, 41, 38)


class TestDeloadImpact(unittest.TestCase):
    """减量周对各强度上限的影响。"""

    def test_order_follows_intensities(self) -> None:
        impacts = d.deload_impact(50.0)
        self.assertEqual(
            tuple(item.intensity for item in impacts), d.INTENSITIES
        )

    def test_caps_shrink_by_drop_fraction(self) -> None:
        for item in d.deload_impact(80.0, 0.20):
            with self.subTest(intensity=item.intensity):
                self.assertAlmostEqual(
                    item.deload_cap_km, item.base_cap_km * 0.8, places=6
                )

    def test_t_is_the_only_intensity_that_can_collapse(self) -> None:
        """只有 T 有单次下限，其余强度只等比缩小，不会无解。"""
        for base in (20.0, 35.0, 50.0, 70.0, 120.0):
            collapsing = {
                item.intensity
                for item in d.deload_impact(base)
                if item.collapses
            }
            with self.subTest(base=base):
                self.assertTrue(collapsing <= {"T"})

    def test_t_collapses_just_below_60km(self) -> None:
        """峰值 59 km 的减量周是 47.2 km，T 上限 4.72 < 4.8，排不出。"""
        impact = {i.intensity: i for i in d.deload_impact(59.0)}
        self.assertTrue(impact["T"].feasible_before)
        self.assertFalse(impact["T"].feasible_after)
        self.assertTrue(impact["T"].collapses)
        self.assertAlmostEqual(impact["T"].deload_cap_km, 4.72, places=6)

    def test_t_survives_at_exactly_60km(self) -> None:
        """峰值 60 km 的减量周是 48 km，T 上限正好 4.8 km，可行。"""
        impact = {i.intensity: i for i in d.deload_impact(60.0)}
        self.assertTrue(impact["T"].feasible_after)
        self.assertFalse(impact["T"].collapses)
        self.assertAlmostEqual(impact["T"].deload_cap_km, 4.8, places=6)

    def test_t_already_infeasible_at_35km_before_deload(self) -> None:
        """35 km 的训练周 T 上限只有 3.5 km——本来就没有合规的 T。

        这条是防「张冠李戴」的：不能把「训练周就排不了 T」说成
        「减量周让 T 排不了」。前者是周跑量不够，后者才是减量造成的。
        """
        impact = {i.intensity: i for i in d.deload_impact(35.0)}
        self.assertFalse(impact["T"].feasible_before)
        self.assertFalse(impact["T"].feasible_after)
        self.assertFalse(impact["T"].collapses)
        self.assertAlmostEqual(impact["T"].base_cap_km, 3.5, places=6)

    def test_l_uses_deload_volume_for_ratio_branch(self) -> None:
        """L 的百分比在 64 km 处分档，减量后可能换档，必须按减量后算。"""
        impact = {i.intensity: i for i in d.deload_impact(70.0)}
        # 70 km 用 25%，减量后 56 km 掉回 30% 档
        self.assertAlmostEqual(impact["L"].base_cap_km, 17.5, places=6)
        self.assertAlmostEqual(impact["L"].deload_cap_km, 56.0 * 0.30, places=6)
        self.assertEqual(impact["L"].ratio, 0.30)

    def test_lost_km_is_never_negative(self) -> None:
        for item in d.deload_impact(64.0):
            self.assertGreaterEqual(item.lost_km, 0.0)

    def test_as_dict_has_all_keys(self) -> None:
        payload = d.deload_impact(64.0)[0].as_dict()
        for key in (
            "intensity",
            "base_km",
            "deload_km",
            "base_cap_km",
            "deload_cap_km",
            "lost_km",
            "feasible_before",
            "feasible_after",
            "collapses",
        ):
            self.assertIn(key, payload)

    def test_rejects_bad_arguments(self) -> None:
        with self.assertRaises(ValueError):
            d.deload_impact(0.0)
        with self.assertRaises(ValueError):
            d.deload_impact(-10.0)
        with self.assertRaises(ValueError):
            d.deload_impact("35")  # type: ignore[arg-type]
        with self.assertRaises(ValueError):
            d.deload_impact(35.0, 0.0)
        with self.assertRaises(ValueError):
            d.deload_impact(35.0, 1.0)
        with self.assertRaises(ValueError):
            d.deload_impact(35.0, 0.2, intensities=("X",))


class TestTPeak(unittest.TestCase):
    """反推：要在减量周里保住一节 T，峰值得做到多少。"""

    def test_six_km_t_needs_75km_peak(self) -> None:
        self.assertAlmostEqual(d.t_peak_km(6.0), 75.0, places=9)

    def test_floor_alone_needs_60km_peak(self) -> None:
        self.assertAlmostEqual(d.t_peak_km(4.8), 60.0, places=9)

    def test_short_session_still_bounded_by_floor(self) -> None:
        """想跑 3 km T 也做不到——下限 4.8 km 才是约束。"""
        self.assertAlmostEqual(d.t_peak_km(3.0), 60.0, places=9)

    def test_no_deload_needs_48km(self) -> None:
        """降 0% 时退化为「周跑量 ≥ 48 km」，与 dose 层一致。"""
        self.assertAlmostEqual(d.t_peak_km(4.8, 0.0001), 48.0, places=2)

    def test_monotone_in_drop_fraction(self) -> None:
        values = [d.t_peak_km(6.0, f) for f in (0.05, 0.10, 0.20, 0.30)]
        self.assertEqual(values, sorted(values))

    def test_rejects_bad_arguments(self) -> None:
        with self.assertRaises(ValueError):
            d.t_peak_km(0.0)
        with self.assertRaises(ValueError):
            d.t_peak_km(6.0, 0.0)
        with self.assertRaises(ValueError):
            d.t_peak_km(6.0, 1.5)


class TestDeloadWeeks(unittest.TestCase):
    """减量周落在哪几周。"""

    def test_twelve_weeks_gives_two_deloads_not_three(self) -> None:
        """事故的核心：12 周每 4 周只在第 4、8 周减量。

        名义上的第三个（第 12 周）是比赛周，不能叠加。
        把它挪到第 11 周是错的——那会连出 11、12 两个减量周。
        """
        rhythm = d.deload_weeks(12, 4, race_week=12)
        self.assertEqual(rhythm.weeks, (4, 8))
        self.assertEqual(rhythm.nominal_count, 3)
        self.assertNotIn(11, rhythm.weeks)
        self.assertNotIn(12, rhythm.weeks)

    def test_race_week_is_reported_as_skipped(self) -> None:
        rhythm = d.deload_weeks(12, 4, race_week=12)
        skipped = dict(rhythm.skipped)
        self.assertIn(12, skipped)
        self.assertIn("比赛周", skipped[12])

    def test_taper_window_is_reported_as_skipped(self) -> None:
        # 13 周、比赛在第 13 周：名义上的第 12 周落在赛前 2 周窗口内
        rhythm = d.deload_weeks(13, 4, race_week=13)
        self.assertNotIn(12, rhythm.weeks)
        self.assertIn(12, dict(rhythm.skipped))
        self.assertIn("赛前", dict(rhythm.skipped)[12])

    def test_twenty_weeks_keeps_four(self) -> None:
        rhythm = d.deload_weeks(20, 4, race_week=20)
        self.assertEqual(rhythm.weeks, (4, 8, 12, 16))

    def test_no_two_deloads_are_adjacent(self) -> None:
        """扫全参数空间：任何组合都不许排出连续的减量周。"""
        for total in range(3, 61):
            for every in range(2, 9):
                for race in {total, max(1, total - 1), total // 2 + 1}:
                    rhythm = d.deload_weeks(total, every, race_week=race)
                    gaps = [
                        b - a
                        for a, b in zip(rhythm.weeks, rhythm.weeks[1:])
                    ]
                    with self.subTest(total=total, every=every, race=race):
                        self.assertTrue(
                            all(gap >= 2 for gap in gaps),
                            f"出现连续减量周：{rhythm.weeks}",
                        )

    def test_deload_weeks_never_contain_race_week(self) -> None:
        for total in range(3, 41):
            for every in (2, 3, 4, 5):
                rhythm = d.deload_weeks(total, every)
                with self.subTest(total=total, every=every):
                    self.assertNotIn(rhythm.race_week, rhythm.weeks)

    def test_weeks_are_ascending_and_after_first_cycle(self) -> None:
        rhythm = d.deload_weeks(40, 5, race_week=40)
        self.assertEqual(list(rhythm.weeks), sorted(rhythm.weeks))
        self.assertTrue(all(w >= 5 for w in rhythm.weeks))

    def test_is_deload_matches_weeks(self) -> None:
        rhythm = d.deload_weeks(12, 4, race_week=12)
        for week in range(1, 13):
            with self.subTest(week=week):
                self.assertEqual(rhythm.is_deload(week), week in (4, 8))

    def test_short_plan_has_no_deload(self) -> None:
        rhythm = d.deload_weeks(4, 4, race_week=4)
        self.assertEqual(rhythm.weeks, ())
        self.assertTrue(any("放不下" in note for note in rhythm.notes))

    def test_notes_never_claim_more_than_actual(self) -> None:
        """笔记里写的「实际 N 个」必须等于真实个数。"""
        for total in range(4, 41):
            rhythm = d.deload_weeks(total, 4)
            for note in rhythm.notes:
                if "实际是" in note:
                    with self.subTest(total=total):
                        self.assertIn(str(len(rhythm.weeks)), note)

    def test_as_dict_is_serialisable(self) -> None:
        payload = d.deload_weeks(12, 4, race_week=12).as_dict()
        json.dumps(payload, ensure_ascii=False)
        self.assertEqual(payload["weeks"], [4, 8])
        self.assertEqual(payload["actual_count"], 2)
        self.assertEqual(payload["nominal_count"], 3)

    def test_rejects_bad_arguments(self) -> None:
        with self.assertRaises(ValueError):
            d.deload_weeks(12, 1)  # 间隔 1 周 = 每周减量
        with self.assertRaises(ValueError):
            d.deload_weeks(12, 4, race_week=0)
        with self.assertRaises(ValueError):
            d.deload_weeks(12, 4, race_week=13)
        with self.assertRaises(ValueError):
            d.deload_weeks(1, 4)
        with self.assertRaises(ValueError):
            d.deload_weeks(12.0, 4)  # type: ignore[arg-type]
        with self.assertRaises(ValueError):
            d.deload_weeks(12, 4, taper_window=0)
        with self.assertRaises(ValueError):
            d.deload_weeks(12, 4, drop_fraction=1.2)


class TestGrowthPath(unittest.TestCase):
    """从当前跑量加到目标跑量要多少周。"""

    def test_35_to_60_takes_20_weeks(self) -> None:
        path = d.growth_path(35.0, 60.0, 4)
        self.assertEqual(path.total_weeks, 20)
        self.assertEqual(path.first_target_week, 17)
        self.assertAlmostEqual(path.step_km, 6.4, places=6)

    def test_levels_match_the_incident_narrative(self) -> None:
        """事故里写的「35→43→…→60」路径不成立，真实台阶是 +6.4。"""
        path = d.growth_path(35.0, 60.0, 4)
        self.assertEqual(
            [round(cycle.build_km, 1) for cycle in path.cycles],
            [35.0, 41.4, 47.8, 54.2, 60.0],
        )

    def test_t_only_becomes_feasible_in_the_last_deload_week(self) -> None:
        path = d.growth_path(35.0, 60.0, 4)
        feasible = [c.cycle for c in path.cycles if c.t_feasible_in_deload]
        self.assertEqual(feasible, [5])

    def test_notes_flag_infeasible_deload_weeks(self) -> None:
        path = d.growth_path(35.0, 60.0, 4)
        joined = " ".join(path.notes)
        self.assertIn("[1, 2, 3, 4]", joined)
        self.assertIn("M/L/E", joined)

    def test_deload_volume_is_dropped_by_fraction(self) -> None:
        for cycle in d.growth_path(40.0, 70.0, 5).cycles:
            with self.subTest(cycle=cycle.cycle):
                self.assertAlmostEqual(
                    cycle.deload_km, cycle.build_km * 0.8, places=6
                )

    def test_more_sessions_means_faster_growth(self) -> None:
        slow = d.growth_path(40.0, 80.0, 3)
        fast = d.growth_path(40.0, 80.0, 5)
        self.assertGreater(fast.step_km, slow.step_km)
        self.assertLess(fast.total_weeks, slow.total_weeks)

    def test_as_dict_is_serialisable(self) -> None:
        json.dumps(d.growth_path(35.0, 60.0, 4).as_dict(), ensure_ascii=False)

    def test_rejects_bad_arguments(self) -> None:
        with self.assertRaises(ValueError):
            d.growth_path(60.0, 35.0, 4)
        with self.assertRaises(ValueError):
            d.growth_path(35.0, 35.0, 4)
        with self.assertRaises(ValueError):
            d.growth_path(35.0, 60.0, 0)
        with self.assertRaises(ValueError):
            d.growth_path(35.0, 60.0, 4, every_weeks=1)
        with self.assertRaises(ValueError):
            d.growth_path(35.0, 60.0, 4, max_weeks=2)


class TestCheckProgression(unittest.TestCase):
    """反向校验一张已经写好的周跑量表。"""

    def test_incident_table_is_rejected(self) -> None:
        """「12 周全部通过校验」是假的：至少 3 处违规。"""
        issues = d.check_progression(INCIDENT_VOLUMES, 4)
        self.assertGreaterEqual(len(issues), 3)
        weeks = {issue.week_index for issue in issues}
        self.assertIn(7, weeks)
        self.assertIn(10, weeks)

    def test_incident_single_week_jump_is_eight_km(self) -> None:
        issues = d.check_progression(INCIDENT_VOLUMES, 4)
        jumps = [
            issue
            for issue in issues
            if issue.week_index == 7 and "单次加量" in issue.reason
        ]
        self.assertEqual(len(jumps), 1)
        self.assertAlmostEqual(jumps[0].gain_km, 8.0, places=6)
        self.assertAlmostEqual(jumps[0].allowed_km, 6.4, places=6)

    def test_clean_cycle_plan_passes(self) -> None:
        """每周期 +6.4 km、每 4 周一次的干净表应当通过。"""
        volumes = (35, 35, 35, 28, 41, 41, 41, 33, 47, 47, 47, 38)
        self.assertEqual(d.check_progression(volumes, 4), [])

    def test_return_from_deload_is_not_a_gain(self) -> None:
        """从减量周回到原水平不算加量，否则任何减量计划都会被误判。"""
        self.assertEqual(
            d.check_progression((35, 35, 35, 28, 35, 35), 4), []
        )

    def test_single_large_jump_is_caught(self) -> None:
        issues = d.check_progression((30, 30, 45), 4)
        self.assertEqual(len(issues), 1)
        self.assertAlmostEqual(issues[0].gain_km, 15.0, places=6)

    def test_two_gains_within_four_weeks_is_caught(self) -> None:
        issues = d.check_progression((40, 40, 46, 40, 50), 4)
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0].week_index, 5)
        self.assertIn("只有 2 周", issues[0].reason)

    def test_gains_are_allowed_after_the_window(self) -> None:
        self.assertEqual(
            d.check_progression((40, 40, 46, 46, 46, 46, 52), 4), []
        )

    def test_more_sessions_allows_bigger_steps(self) -> None:
        volumes = (40, 40, 44)
        self.assertEqual(d.check_progression(volumes, 3), [])
        self.assertNotEqual(d.check_progression(volumes, 2), [])

    def test_issues_are_json_safe(self) -> None:
        for issue in d.check_progression(INCIDENT_VOLUMES, 4):
            json.dumps(issue.as_dict(), ensure_ascii=False)

    def test_rejects_bad_arguments(self) -> None:
        with self.assertRaises(ValueError):
            d.check_progression((35,), 4)
        with self.assertRaises(ValueError):
            d.check_progression((), 4)
        with self.assertRaises(ValueError):
            d.check_progression((35, 0), 4)
        with self.assertRaises(ValueError):
            d.check_progression((35, "40"), 4)  # type: ignore[arg-type]
        with self.assertRaises(ValueError):
            d.check_progression((35, 40), 4, every_weeks=1)
        with self.assertRaises(ValueError):
            d.check_progression("35,40", 4)  # type: ignore[arg-type]


class TestWeekTaper(unittest.TestCase):
    """赛前减量落到具体某一周。"""

    def test_three_weeks_out_drops_strides(self) -> None:
        taper = d.week_taper(9, 12, race_week=12)
        self.assertTrue(taper.drop_strides)
        self.assertFalse(taper.drop_hills)

    def test_four_weeks_out_drops_nothing(self) -> None:
        taper = d.week_taper(8, 12, race_week=12)
        self.assertFalse(taper.drop_strides)
        self.assertFalse(taper.drop_hills)
        self.assertFalse(taper.is_taper_week)

    def test_two_weeks_out_also_drops_hills(self) -> None:
        taper = d.week_taper(10, 12, race_week=12)
        self.assertTrue(taper.drop_strides)
        self.assertTrue(taper.drop_hills)
        self.assertTrue(taper.is_taper_week)
        self.assertTrue(taper.reduced_volume)

    def test_week_before_race_caps_long_run(self) -> None:
        taper = d.week_taper(11, 12, race_week=12)
        self.assertEqual(taper.long_run_minutes_cap, 90.0)

    def test_other_weeks_have_no_long_run_cap(self) -> None:
        for week in (1, 5, 8, 9, 10, 12):
            with self.subTest(week=week):
                self.assertIsNone(
                    d.week_taper(week, 12, race_week=12).long_run_minutes_cap
                )

    def test_race_week_is_flagged(self) -> None:
        taper = d.week_taper(12, 12, race_week=12)
        self.assertTrue(taper.is_race_week)
        self.assertEqual(taper.weeks_to_race, 0)

    def test_hills_imply_strides(self) -> None:
        """跑的窗口比跨步窄，去跑坡的周必然也去跨步。"""
        for week in range(1, 13):
            taper = d.week_taper(week, 12, race_week=12)
            with self.subTest(week=week):
                if taper.drop_hills:
                    self.assertTrue(taper.drop_strides)

    def test_incident_plan_violated_this(self) -> None:
        """事故计划写「每周两次 8×100 m 跨步照做」，赛前三周全部违规。"""
        offending = [
            week
            for week in range(1, 13)
            if d.week_taper(week, 12, race_week=12).drop_strides
        ]
        self.assertIn(10, offending)
        self.assertIn(11, offending)
        self.assertIn(12, offending)
        self.assertEqual(offending, [9, 10, 11, 12])

    def test_prefer_is_long_and_threshold(self) -> None:
        self.assertEqual(d.week_taper(11, 12, race_week=12).prefer, ("L", "T"))

    def test_as_dict_is_serialisable(self) -> None:
        json.dumps(
            d.week_taper(11, 12, race_week=12).as_dict(), ensure_ascii=False
        )

    def test_rejects_bad_arguments(self) -> None:
        with self.assertRaises(ValueError):
            d.week_taper(0, 12)
        with self.assertRaises(ValueError):
            d.week_taper(13, 12)
        with self.assertRaises(ValueError):
            d.week_taper(5, 12, race_week=13)
        with self.assertRaises(ValueError):
            d.week_taper(5, 12, race_week=0)


class TestProvenance(unittest.TestCase):
    """外推层必须随身带的来源说明。"""

    def test_keys_are_present(self) -> None:
        for key in (
            "book_position",
            "what_exists",
            "misuse",
            "consequence",
            "source",
        ):
            self.assertIn(key, d.DELOAD_PROVENANCE)

    def test_states_that_the_book_has_no_such_concept(self) -> None:
        self.assertIn("没有", d.DELOAD_PROVENANCE["book_position"])
        self.assertIn("周期性减量", d.DELOAD_PROVENANCE["book_position"])

    def test_warns_against_reading_80pct_as_permission(self) -> None:
        self.assertIn("L3398", d.DELOAD_PROVENANCE["what_exists"])
        self.assertIn("L3398", d.DELOAD_PROVENANCE["misuse"])

    def test_manifest_declares_it_unsupported(self) -> None:
        areas = " ".join(
            item["area"] for item in d.manifest()["unsupported"]
        )
        self.assertIn("周期性减量", areas)

    def test_manifest_lists_the_deload_layer(self) -> None:
        layers = d.manifest()["layers"]
        self.assertIn("deload", layers)
        for name in ("deload_impact", "deload_weeks", "growth_path"):
            self.assertIn(name, layers["deload"])

    def test_weekly_volume_bounds_unchanged(self) -> None:
        self.assertEqual(d.weekly_volume_bounds(), (0.80, 1.00))


class TestDeloadCli(unittest.TestCase):
    """命令行出口。"""

    def test_deload_reports_two_weeks(self) -> None:
        code, out, _ = run(
            "deload", "--base", "35", "--weeks", "12", "--race-week", "12"
        )
        self.assertEqual(code, 0)
        self.assertIn("第 [4, 8] 周", out)
        self.assertIn("比赛周", out)

    def test_deload_json_payload(self) -> None:
        code, out, _ = run(
            "deload",
            "--base",
            "60",
            "--weeks",
            "12",
            "--race-week",
            "12",
            "--json",
        )
        self.assertEqual(code, 0)
        payload = json.loads(out)
        self.assertEqual(payload["rhythm"]["weeks"], [4, 8])
        self.assertIn("provenance", payload)
        self.assertEqual(len(payload["impact"]), 5)

    def test_deload_rejects_negative_volume(self) -> None:
        code, _, err = run(
            "deload", "--base", "-5", "--weeks", "12", "--race-week", "12"
        )
        self.assertEqual(code, 1)
        self.assertIn("错误", err)

    def test_progression_exits_2_on_incident_table(self) -> None:
        code, out, _ = run(
            "progression", *[str(v) for v in INCIDENT_VOLUMES], "--sessions", "4"
        )
        self.assertEqual(code, 2)
        self.assertIn("第 7 周", out)

    def test_progression_exits_0_on_clean_table(self) -> None:
        code, out, _ = run(
            "progression", "35", "35", "35", "28", "41", "41", "41", "33",
            "--sessions", "4",
        )
        self.assertEqual(code, 0)
        self.assertIn("合规", out)

    def test_taper_prints_the_series(self) -> None:
        code, out, _ = run("taper", "--weeks", "12", "--race-week", "12")
        self.assertEqual(code, 0)
        self.assertIn("去跨步", out)
        self.assertIn("L≤90min", out)

    def test_taper_surfaces_the_documented_conflict(self) -> None:
        """不能再把 L2842 与 L3496 说成一回事。"""
        _, out, _ = run("taper", "--weeks", "12", "--race-week", "12")
        self.assertIn("冲突", out)
        self.assertIn("不能用来给周日比赛的长距离选手背书", out)

    def test_taper_single_week_json(self) -> None:
        code, out, _ = run(
            "taper", "--weeks", "12", "--race-week", "12", "--week", "11", "--json"
        )
        self.assertEqual(code, 0)
        payload = json.loads(out)
        self.assertEqual(payload["long_run_minutes_cap"], 90.0)
        self.assertTrue(payload["drop_strides"])


class TestIncidentRegression(unittest.TestCase):
    """把事故里的每一个主张逐条对照，确认现在都有据可查。"""

    def test_12_weeks_cannot_hold_deload_at_35km(self) -> None:
        """35 km 基数下，12 周里放不进 3 个减量周。"""
        self.assertEqual(d.deload_weeks(12, 4, race_week=12).weeks, (4, 8))

    def test_t_session_impossible_at_35km_any_week(self) -> None:
        """35 km 时训练周和减量周都排不出 T，这是周跑量问题不是减量问题。"""
        impact = {i.intensity: i for i in d.deload_impact(35.0)}
        self.assertFalse(impact["T"].feasible_before)
        self.assertLess(impact["T"].base_cap_km, 4.8)

    def test_6km_t_needs_75km_peak(self) -> None:
        self.assertAlmostEqual(d.t_peak_km(6.0), 75.0, places=9)

    def test_35_to_60_needs_20_weeks_not_12(self) -> None:
        self.assertEqual(d.growth_path(35.0, 60.0, 4).total_weeks, 20)

    def test_strides_must_stop_three_weeks_out(self) -> None:
        self.assertTrue(d.week_taper(9, 12, race_week=12).drop_strides)

    def test_incident_table_fails_progression(self) -> None:
        self.assertTrue(d.check_progression(INCIDENT_VOLUMES, 4))


if __name__ == "__main__":
    unittest.main()
