# -*- coding: utf-8 -*-
"""接诊门禁的测试。

十个真实回合里，一半的错误来自同一个地方：**输入不齐也能开口**。
这一组用例就是把那些"开口"钉死。

运行：
    cd D:\\daniels-running-skill
    python -m unittest discover -s tests -v
"""

from __future__ import annotations

import datetime as dt
import unittest

import daniels as d


def complete_state() -> d.IntakeState:
    """一份填齐了、且明确说过没有红线的问诊。"""
    return (
        d.IntakeState()
        .set("goal_distance_km", 21.0975)
        .set("race_date", "2027-03-21")
        .set("weekly_km", 19.0)
        .set("longest_recent_km", 8.0)
        .set("days_per_week", 3)
        .set("red_flags", ())
    )


class TestLayers(unittest.TestCase):
    """分层提问：一次只问最靠前那一层缺的。"""

    def test_empty_state_asks_layer_zero_only(self) -> None:
        """什么都还没给时，只问第 0 层那三项：目标、日期、红线。"""
        status = d.IntakeState().status()
        self.assertEqual(status.code, "need_info")
        self.assertEqual(
            [s.key for s in status.missing],
            ["goal_distance_km", "race_date", "red_flags"],
        )
        self.assertEqual(len(status.questions), 3)
        self.assertIn("公里", status.questions[0])

    def test_does_not_ask_layer_two_before_layer_zero(self) -> None:
        state = d.IntakeState().set("goal_distance_km", 21.1)
        status = state.status()
        # 全量缺项按层看是 0,0,2,2,2
        self.assertEqual([spec.layer for spec in state.missing()], [0, 0, 2, 2, 2])
        # 但这一轮只问第 0 层：比赛日期 + 红线
        self.assertEqual([spec.layer for spec in status.missing], [0, 0])
        self.assertEqual(len(status.questions), 2)

    def test_red_flags_are_asked_in_the_first_round(self) -> None:
        """红线必须在收集任何训练数据之前问出来。

        四个分支实测里，没有一个真的问了伤病：A 说「下一轮我会问」，
        D 列了「还缺三个数」却没有它。所以把它挪到第 0 层，
        目标一确定就得答。
        """
        state = d.IntakeState().set("goal_distance_km", 21.1)
        keys = [spec.key for spec in state.status().missing]
        self.assertIn("red_flags", keys)

    def test_red_flags_still_pending_after_goal_and_date(self) -> None:
        """给了目标和日期但没答红线时，下一轮只问红线，不进第 2 层。"""
        state = (
            d.IntakeState()
            .set("goal_distance_km", 21.1)
            .set("race_date", "2027-03-21")
        )
        status = state.status()
        self.assertEqual(status.code, "need_info")
        self.assertEqual([spec.key for spec in status.missing], ["red_flags"])

    def test_after_layer_zero_asks_layer_two(self) -> None:
        state = (
            d.IntakeState()
            .set("goal_distance_km", 21.1)
            .set("race_date", "2027-03-21")
            .set("red_flags", ())
        )
        status = state.status()
        self.assertEqual(status.code, "need_info")
        self.assertTrue(all(spec.layer == 2 for spec in status.missing))
        self.assertEqual(len(status.questions), 3)

    def test_every_field_has_question_and_reason(self) -> None:
        for spec in d.FIELD_SPECS:
            with self.subTest(key=spec.key):
                self.assertTrue(spec.question.strip())
                self.assertTrue(spec.why.strip())
                self.assertGreaterEqual(spec.layer, 0)

    def test_brief_marks_missing_fields(self) -> None:
        text = d.IntakeState().set("goal_distance_km", 21.1).brief()
        self.assertIn("need_info", text)
        self.assertIn("缺", text)


class TestMinutesAreNotDistance(unittest.TestCase):
    """十轮里最贵的那个错：把「每次 35 分钟」折成 17–18 km。"""

    def test_minutes_alone_cannot_set_weekly_km(self) -> None:
        """只给分钟时 weekly_km 就是缺的，不许自己折。"""
        state = (
            d.IntakeState()
            .set("goal_distance_km", 21.1)
            .set("race_date", "2027-03-21")
        )
        self.assertNotIn("weekly_km", state.answers)
        self.assertIn("weekly_km", [s.key for s in state.missing()])

    def test_longest_distance_is_not_a_result(self) -> None:
        """「最长跑过 8 公里」是距离，换不出 VDOT。"""
        state = complete_state()
        self.assertFalse(state.status().can_fill_paces)
        with self.assertRaises(ValueError) as ctx:
            d.paces_from_intake(state)
        self.assertIn("尽力跑", str(ctx.exception))

    def test_need_result_still_allows_a_volume_skeleton(self) -> None:
        """没成绩可以排跑量骨架，但不能填配速。"""
        status = complete_state().status()
        self.assertEqual(status.code, "need_result")
        self.assertTrue(status.can_build_plan)
        self.assertFalse(status.can_fill_paces)


class TestRedFlags(unittest.TestCase):
    """红线是开关，不是参数。"""

    def test_flag_stops_everything(self) -> None:
        state = complete_state().set("red_flags", ("膝盖疼",))
        status = state.status()
        self.assertEqual(status.code, "stopped")
        self.assertFalse(status.can_build_plan)
        self.assertFalse(status.can_fill_paces)
        self.assertEqual(status.questions, ())
        self.assertIn("膝盖疼", status.stop_reason)
        self.assertIn("不排计划", status.stop_reason)

    def test_flag_wins_over_complete_data(self) -> None:
        """数据全齐也照样停——这是这条规则的意义。"""
        state = complete_state().set("recent_result", (5000.0, 1692.0))
        state.set("red_flags", ("跟腱炎",))
        self.assertEqual(state.status().code, "stopped")

    def test_unasked_flag_is_missing_not_clean(self) -> None:
        """没问过不等于没问题。"""
        state = (
            d.IntakeState()
            .set("goal_distance_km", 21.1)
            .set("race_date", "2027-03-21")
            .set("weekly_km", 19.0)
            .set("longest_recent_km", 8.0)
            .set("days_per_week", 3)
        )
        status = state.status()
        self.assertEqual(status.code, "need_info")
        self.assertEqual([s.key for s in status.missing], ["red_flags"])

    def test_explicit_none_completes_the_layer(self) -> None:
        state = complete_state().set("recent_result", (5000.0, 1692.0))
        self.assertEqual(state.status().code, "ready")

    def test_empty_string_counts_as_none(self) -> None:
        state = complete_state().set("red_flags", "")
        self.assertEqual(state.red_flags(), ())


class TestReady(unittest.TestCase):
    """齐了以后的行为。"""

    def test_ready_when_result_present(self) -> None:
        state = complete_state().set("recent_result", (5000.0, 1692.0))
        status = state.status()
        self.assertEqual(status.code, "ready")
        self.assertTrue(status.can_build_plan)
        self.assertTrue(status.can_fill_paces)

    def test_paces_match_the_library(self) -> None:
        """5 公里 28:12 → VDOT 33.2，配速与 pace_set 完全一致。"""
        state = complete_state().set("recent_result", (5000.0, 1692.0))
        paces = d.paces_from_intake(state)
        self.assertAlmostEqual(paces.vdot, 33.1952, places=3)
        self.assertAlmostEqual(paces.m.seconds_per_km, 380.08, places=1)
        self.assertAlmostEqual(paces.t.seconds_per_km, 354.64, places=1)
        self.assertAlmostEqual(paces.i.seconds_per_km, 326.80, places=1)

    def test_altitude_flows_into_paces(self) -> None:
        state = complete_state().set("recent_result", (5000.0, 1692.0))
        state.set("altitude_m", 1524)
        sea = d.paces_from_intake(complete_state().set(
            "recent_result", (5000.0, 1692.0)
        ))
        high = d.paces_from_intake(state)
        self.assertGreater(high.t.seconds_per_km, sea.t.seconds_per_km)

    def test_status_dict_is_json_safe(self) -> None:
        import json

        payload = (
            complete_state().set("recent_result", (5000.0, 1692.0))
            .status().as_dict()
        )
        json.dumps(payload, ensure_ascii=False)
        self.assertEqual(payload["code"], "ready")


class TestValidation(unittest.TestCase):
    """不许悄悄放进去的输入。"""

    def test_unknown_field(self) -> None:
        with self.assertRaises(KeyError):
            d.IntakeState().set("身高", 175)

    def test_bad_goal_distance(self) -> None:
        for value in (0, -1, 100):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    d.IntakeState().set("goal_distance_km", value)

    def test_bad_result_shape(self) -> None:
        with self.assertRaises(ValueError):
            d.IntakeState().set("recent_result", 1692)
        with self.assertRaises(ValueError):
            d.IntakeState().set("recent_result", (5000.0, -1))

    def test_result_distance_range(self) -> None:
        with self.assertRaises(ValueError):
            d.IntakeState().set("recent_result", (100.0, 20.0))

    def test_bad_weekly(self) -> None:
        for value in (0, -5, "19"):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    d.IntakeState().set("weekly_km", value)

    def test_bad_days(self) -> None:
        for value in (0, 15, 3.5, True):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    d.IntakeState().set("days_per_week", value)

    def test_bad_surface(self) -> None:
        with self.assertRaises(ValueError):
            d.IntakeState().set("surface", "treadmill")

    def test_defaults(self) -> None:
        state = d.IntakeState()
        self.assertEqual(state.get("surface"), "road")
        self.assertEqual(state.get("altitude_m"), 0.0)


class TestContradictions(unittest.TestCase):
    """每一项单独合法、合在一起不成立——这类输入最危险。"""

    def state(self, **fields) -> d.IntakeState:
        s = (
            d.IntakeState()
            .set("goal_distance_km", 21.0975)
            .set("race_date", "2027-03-21")
            .set("red_flags", ())
            .set("recent_result", (5000.0, 1692.0))
        )
        for key, value in fields.items():
            s.set(key, value)
        return s

    def test_weekly_smaller_than_longest(self) -> None:
        """一次跑不可能比一周总量还多。"""
        status = self.state(
            weekly_km=20.0, longest_recent_km=25.0, days_per_week=4
        ).status()
        self.assertEqual(status.code, "contradictory")
        self.assertFalse(status.can_build_plan)
        self.assertIn("小于最长一次", status.contradictions[0])

    def test_average_exceeds_longest(self) -> None:
        """3 天 60 km 平均每次 20 km，可最长只有 15——不可能。"""
        status = self.state(
            weekly_km=60.0, longest_recent_km=15.0, days_per_week=3
        ).status()
        self.assertEqual(status.code, "contradictory")
        self.assertIn("平均", status.contradictions[0])

    def test_two_days_case(self) -> None:
        status = self.state(
            weekly_km=40.0, longest_recent_km=12.0, days_per_week=2
        ).status()
        self.assertEqual(status.code, "contradictory")

    def test_normal_input_still_ready(self) -> None:
        status = self.state(
            weekly_km=20.0, longest_recent_km=10.0, days_per_week=4
        ).status()
        self.assertEqual(status.code, "ready")
        self.assertEqual(status.contradictions, ())

    def test_exactly_at_the_bound_is_fine(self) -> None:
        """平均正好等于最长是合法的（天天跑同一个距离）。"""
        status = self.state(
            weekly_km=40.0, longest_recent_km=10.0, days_per_week=4
        ).status()
        self.assertEqual(status.code, "ready")

    def test_no_questions_asked_when_contradictory(self) -> None:
        """对不上的数据不该靠"再问一句"解决。"""
        status = self.state(
            weekly_km=60.0, longest_recent_km=15.0, days_per_week=3
        ).status()
        self.assertEqual(status.questions, ())

    def test_brief_shows_the_conflict(self) -> None:
        text = self.state(
            weekly_km=60.0, longest_recent_km=15.0, days_per_week=3
        ).brief()
        self.assertIn("数据对不上", text)

    def test_missing_field_does_not_fake_a_contradiction(self) -> None:
        """只给周跑量、没给最长距离时，不能凭空判矛盾。"""
        s = (
            d.IntakeState()
            .set("goal_distance_km", 21.0975)
            .set("race_date", "2027-03-21")
            .set("weekly_km", 20.0)
        )
        self.assertEqual(s.contradictions(), ())


class TestRaceDateValidation(unittest.TestCase):
    """比赛日期是十六轮实测里闯祸最多的字段：被编过两次、被改过一次。

    它原来接受任何字符串——「明年3月」「2027/03/21」「2027-13-45」、空串——
    全都返回 ready。所以现在只收 ISO 日期。
    """

    def test_accepts_iso_string(self) -> None:
        state = d.IntakeState().set("race_date", "2027-03-21")
        self.assertEqual(state.race_date, dt.date(2027, 3, 21))

    def test_accepts_date_object(self) -> None:
        state = d.IntakeState().set("race_date", dt.date(2027, 3, 21))
        self.assertEqual(state.race_date, dt.date(2027, 3, 21))

    def test_stored_as_date_so_it_can_feed_dates_module(self) -> None:
        """存成 date 才能直接喂给 /dates/，不用再解析一次。"""
        state = d.IntakeState().set("race_date", "2027-03-21")
        self.assertEqual(d.weeks_until(dt.date(2026, 11, 13), state.race_date), (18, 2))

    def test_rejects_vague_text(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            d.IntakeState().set("race_date", "明年3月")
        self.assertIn("YYYY-MM-DD", str(ctx.exception))

    def test_rejects_wrong_separator(self) -> None:
        with self.assertRaises(ValueError):
            d.IntakeState().set("race_date", "2027/03/21")

    def test_rejects_impossible_date(self) -> None:
        with self.assertRaises(ValueError):
            d.IntakeState().set("race_date", "2027-13-45")

    def test_rejects_empty(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            d.IntakeState().set("race_date", "   ")
        self.assertIn("不能为空", str(ctx.exception))

    def test_rejects_non_string(self) -> None:
        with self.assertRaises(ValueError):
            d.IntakeState().set("race_date", 20270321)

    def test_none_when_unset(self) -> None:
        self.assertIsNone(d.IntakeState().race_date)


class TestScenariosFromRealRounds(unittest.TestCase):
    """把十轮里真实出现过的输入原样搬过来。"""

    def test_round_one_input_is_not_enough(self) -> None:
        """「一周三次、每次 35 分钟、最长 8 公里」——不能出任何数。"""
        state = (
            d.IntakeState()
            .set("goal_distance_km", 21.0975)
            .set("days_per_week", 3)
            .set("longest_recent_km", 8.0)
        )
        status = state.status()
        self.assertEqual(status.code, "need_info")
        keys = [spec.key for spec in state.missing()]
        self.assertIn("race_date", keys)
        self.assertIn("weekly_km", keys)
        self.assertIn("red_flags", keys)
        self.assertEqual(status.questions[0][:4], "比赛是哪")
        self.assertFalse(status.can_build_plan)
        self.assertFalse(status.can_fill_paces)

    def test_knee_pain_scenario(self) -> None:
        state = (
            d.IntakeState()
            .set("goal_distance_km", 21.0975)
            .set("race_date", "2027-03-21")
            .set("weekly_km", 19.0)
            .set("longest_recent_km", 8.0)
            .set("days_per_week", 3)
            .set("red_flags", ("右膝上下楼梯疼",))
        )
        status = state.status()
        self.assertEqual(status.code, "stopped")
        self.assertIn("医生", status.stop_reason)


if __name__ == "__main__":
    unittest.main()
