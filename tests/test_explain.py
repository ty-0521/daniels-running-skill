# -*- coding: utf-8 -*-
"""daniels.explain 的回归测试。

这一层不产生数值，所以测试重点是数据完整性（出处、交叉引用）与检索行为。

运行：
    cd D:\\daniels-running-skill
    python -m unittest discover -s tests -v
"""

from __future__ import annotations

import unittest

import daniels
from daniels.explain import (
    BOUNDARIES,
    TOPICS,
    boundary,
    explain,
    search,
    topic_ids,
)


class TestTopicIntegrity(unittest.TestCase):
    """词条自身的数据完整性。"""

    def test_registry_not_empty(self) -> None:
        self.assertGreaterEqual(len(TOPICS), 20)

    def test_key_matches_topic_id(self) -> None:
        for key, topic in TOPICS.items():
            with self.subTest(key=key):
                self.assertEqual(key, topic.topic_id)

    def test_every_topic_has_sources(self) -> None:
        for topic in TOPICS.values():
            with self.subTest(topic=topic.topic_id):
                self.assertTrue(topic.sources, "缺出处")
                for source in topic.sources:
                    self.assertTrue(
                        source.startswith("第"),
                        f"出处格式应以「第」开头：{source}",
                    )
                    self.assertIn("L", source, f"出处应带行号：{source}")

    def test_every_topic_has_question_and_answer(self) -> None:
        for topic in TOPICS.values():
            with self.subTest(topic=topic.topic_id):
                self.assertTrue(topic.question.endswith("？"))
                self.assertGreater(len(topic.answer), 15)

    def test_answers_are_paraphrase_length(self) -> None:
        """答案要短。超过 220 字大概是抄了原文，而不是改写。"""
        for topic in TOPICS.values():
            with self.subTest(topic=topic.topic_id):
                self.assertLessEqual(len(topic.answer), 220)

    def test_related_ids_exist(self) -> None:
        for topic in TOPICS.values():
            for related in topic.related:
                with self.subTest(topic=topic.topic_id, related=related):
                    self.assertIn(related, TOPICS)

    def test_no_self_reference(self) -> None:
        for topic in TOPICS.values():
            with self.subTest(topic=topic.topic_id):
                self.assertNotIn(topic.topic_id, topic.related)

    def test_computed_by_points_to_real_function(self) -> None:
        """``computed_by`` 必须真的存在于 daniels 包里。"""
        for topic in TOPICS.values():
            if topic.computed_by is None:
                continue
            with self.subTest(topic=topic.topic_id):
                self.assertTrue(
                    hasattr(daniels, topic.computed_by),
                    f"{topic.computed_by} 不在 daniels 包中",
                )

    def test_keywords_are_not_single_latin_letters(self) -> None:
        """单个英文字母做关键词会造成大量误命中。"""
        for topic in TOPICS.values():
            for keyword in topic.keywords:
                with self.subTest(topic=topic.topic_id, keyword=keyword):
                    if len(keyword) == 1:
                        self.assertFalse(keyword.isascii(), f"关键词 {keyword!r} 过短")


class TestExplain(unittest.TestCase):
    """按 id 取词条。"""

    def test_known_id(self) -> None:
        topic = explain("why-easy-is-slow")
        self.assertEqual(topic.topic_id, "why-easy-is-slow")
        self.assertIn("第4章", topic.sources[0])

    def test_unknown_id_raises_with_hint(self) -> None:
        with self.assertRaises(KeyError) as ctx:
            explain("why-easy")
        message = str(ctx.exception)
        self.assertIn("why-easy", message)
        self.assertIn("why-easy-is-slow", message)

    def test_unknown_id_without_hint(self) -> None:
        with self.assertRaises(KeyError):
            explain("完全不存在")


class TestSearch(unittest.TestCase):
    """关键词检索。"""

    def test_interval_rep_length(self) -> None:
        hits = search("i跑 间歇 5分钟 为什么")
        self.assertTrue(hits)
        self.assertEqual(hits[0].topic_id, "why-i-reps-3-to-5")

    def test_vdot_vs_lab(self) -> None:
        hits = search("vdot 和最大摄氧量不一样")
        self.assertEqual(hits[0].topic_id, "vdot-vs-vo2max")

    def test_altitude_volume(self) -> None:
        hits = search("高海拔 跑量")
        self.assertEqual(hits[0].topic_id, "why-altitude-same-volume")

    def test_long_run_cap_in_results(self) -> None:
        hits = search("150分钟 上限", limit=5)
        ids = [t.topic_id for t in hits]
        self.assertIn("why-150-min-cap", ids)

    def test_cadence(self) -> None:
        hits = search("步频")
        self.assertEqual(hits[0].topic_id, "cadence-180")

    def test_english_keywords_are_case_insensitive(self) -> None:
        lower = search("vdot")
        upper = search("VDOT")
        self.assertEqual(
            [t.topic_id for t in lower], [t.topic_id for t in upper]
        )

    def test_no_match_returns_empty(self) -> None:
        self.assertEqual(search("量子力学与红烧肉"), [])

    def test_limit_is_respected(self) -> None:
        self.assertLessEqual(len(search("为什么", limit=1)), 1)

    def test_limit_ordering(self) -> None:
        all_hits = search("高海拔", limit=10)
        self.assertGreaterEqual(len(all_hits), 2)

    def test_stopwords_are_ignored(self) -> None:
        """纯泛词不产生结果，否则每个词条都会被拉进来。"""
        self.assertEqual(search("为什么"), [])
        self.assertEqual(search("怎么 如何 什么"), [])

    def test_stopword_does_not_crowd_results(self) -> None:
        """带泛词的提问仍应把真正相关的词条排在第一。"""
        hits = search("I 训练为什么每个回合只跑 5 分钟")
        self.assertEqual(hits[0].topic_id, "why-i-reps-3-to-5")

    def test_whitespace_does_not_break_matching(self) -> None:
        """用户在数字两侧留空格是常态：「3 到 5 分钟」不能被空格切断。

        SKILL.md 的示例原先就是这一句，而它在改成去空白之前是零命中。
        """
        hits = search("I 训练为什么只跑 3 到 5 分钟")
        self.assertTrue(hits, "去掉空白后这条提问必须能命中")
        self.assertEqual(hits[0].topic_id, "why-i-reps-3-to-5")

    def test_intensity_phrase_variants(self) -> None:
        """用户常写「X配速」而不是「X跑」，两种都要能命中。"""
        cases = {
            "T配速什么感觉": "t-comfortably-hard",
            "E配速为什么要这么慢": "why-easy-is-slow",
            "I配速为什么只跑3到5分钟": "why-i-reps-3-to-5",
            "R配速为什么要充分恢复": "why-r-needs-full-recovery",
            "M配速有什么意义": "why-m-is-mental",
        }
        for query, expected in cases.items():
            with self.subTest(query=query):
                hits = search(query)
                self.assertEqual(hits[0].topic_id, expected)

    def test_altitude_adjustment_query(self) -> None:
        """「怎么调」应落到「R 不用调」这条，因为它最可执行。"""
        hits = search("高海拔怎么调")
        self.assertEqual(hits[0].topic_id, "why-altitude-r-unchanged")

    def test_invalid_limit(self) -> None:
        for bad in (0, -1):
            with self.subTest(limit=bad):
                with self.assertRaises(ValueError):
                    search("vdot", limit=bad)

    def test_invalid_query_type(self) -> None:
        with self.assertRaises(TypeError):
            search(123)  # type: ignore[arg-type]


class TestTopicIds(unittest.TestCase):
    def test_sorted_and_complete(self) -> None:
        ids = topic_ids()
        self.assertEqual(list(ids), sorted(ids))
        self.assertEqual(len(ids), len(TOPICS))


class TestConflictTopics(unittest.TestCase):
    """书里前后不一致的地方必须单独成条，而不是被悄悄调和。"""

    def test_conflict_topics_exist(self) -> None:
        for topic_id in ("l-cap-conflict", "six-second-rule-varies"):
            with self.subTest(topic=topic_id):
                self.assertIn(topic_id, TOPICS)

    def test_conflict_answers_mention_both_sides(self) -> None:
        answer = TOPICS["l-cap-conflict"].answer
        for token in ("25%", "30%", "60 分钟", "150 分钟"):
            self.assertIn(token, answer)

    def test_percent_semantics_topic(self) -> None:
        """「百分比是单次上限」必须单独成条，这是最容易误解的一条。"""
        answer = TOPICS["percent-is-per-session"].answer
        self.assertIn("单次", answer)


class TestSearchPrecision(unittest.TestCase):
    """实测里被问出来的错答案，逐条钉住。

    这五条都不是刁难：越界问题（坡度、年龄、性别）本该答「书里没有」，
    而「长跑能跑多长」是正常问题，之前却零命中。
    根因是「得分 > 0 就算命中」，一个汉字或两个泛词就能把词条顶出来。
    """

    def test_out_of_scope_questions_do_not_get_topic_answers(self) -> None:
        queries = (
            "跑步机坡度换算表怎么用",
            "坡度",
            "我今年 45 岁，配速要不要调整",
            "连续两场比赛怎么排",
            "比赛周撞上了质量课怎么办",
        )
        for query in queries:
            with self.subTest(query=query):
                self.assertEqual(search(query), [], "越界问题不该拿词条顶上")

    def test_long_run_question_hits_the_cap_topics(self) -> None:
        ids = [t.topic_id for t in search("长跑能跑多长")]
        self.assertIn("l-cap-conflict", ids)
        self.assertIn("why-150-min-cap", ids)

    def test_taper_question_hits_the_taper_topic(self) -> None:
        self.assertEqual(
            search("赛前两周该去掉什么")[0].topic_id, "taper-what-to-drop"
        )
        self.assertEqual(
            search("最后一周还要跑跨步吗")[0].topic_id, "taper-what-to-drop"
        )

    def test_min_score_is_a_gate(self) -> None:
        self.assertTrue(search("比赛", min_score=2))
        self.assertEqual(search("比赛", min_score=3), [])

    def test_invalid_min_score(self) -> None:
        with self.assertRaises(ValueError):
            search("vdot", min_score=0)

    def test_invalid_min_coverage(self) -> None:
        for bad in (-0.1, 1.5):
            with self.subTest(coverage=bad):
                with self.assertRaises(ValueError):
                    search("vdot", min_coverage=bad)


class TestBoundary(unittest.TestCase):
    """边界闸门：支持不了的地方，答「没有」而不是「最像的」。"""

    def test_registry_integrity(self) -> None:
        ids = [item.boundary_id for item in BOUNDARIES]
        self.assertEqual(len(ids), len(set(ids)), "boundary_id 不能重复")
        self.assertGreaterEqual(len(BOUNDARIES), 3)
        for item in BOUNDARIES:
            with self.subTest(boundary=item.boundary_id):
                self.assertTrue(item.question.endswith("？"))
                self.assertTrue(item.keywords or item.patterns)
                self.assertTrue(item.basis, "边界必须写清依据")
                self.assertGreater(len(item.answer), 20)

    def test_treadmill_question(self) -> None:
        hit = boundary("跑步机坡度换算表怎么用")
        self.assertIsNotNone(hit)
        self.assertEqual(hit.boundary_id, "treadmill-grade")

    def test_single_keyword_still_hits_boundary(self) -> None:
        """边界没有「覆盖率」问题：一个「坡度」就够。"""
        self.assertEqual(boundary("坡度").boundary_id, "treadmill-grade")

    def test_age_question(self) -> None:
        hit = boundary("我今年 45 岁，配速要不要调整")
        self.assertEqual(hit.boundary_id, "age-sex-adjust")

    def test_sex_question(self) -> None:
        self.assertEqual(
            boundary("我是女的，VDOT 要减多少").boundary_id, "age-sex-adjust"
        )

    def test_weight_question(self) -> None:
        self.assertEqual(boundary("体重多少最合适").boundary_id, "weight-management")

    def test_normal_questions_have_no_boundary(self) -> None:
        for query in ("T 配速什么感觉", "I 训练为什么只跑 3 到 5 分钟"):
            with self.subTest(query=query):
                self.assertIsNone(boundary(query))

    def test_age_regex_does_not_swallow_the_hrmax_topic(self) -> None:
        """「220 减年龄」问的是心率公式，不是年龄调整。"""
        self.assertIsNone(boundary("为什么不能用 220 减年龄估最大心率"))
        self.assertEqual(
            search("为什么不能用 220 减年龄估最大心率")[0].topic_id,
            "why-220-age-fails",
        )

    def test_invalid_query_type(self) -> None:
        with self.assertRaises(TypeError):
            boundary(123)  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main(verbosity=2)
