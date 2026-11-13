# -*- coding: utf-8 -*-
"""行号查询层的测试。

十轮里行号引错三次，每次结论都对、只有出处错。这一组守住三件事：
**32 条规则都查得到、三条改过的能查、别处不许再手写行号。**
"""

from __future__ import annotations

import json
import unittest

import daniels as d


class TestCite(unittest.TestCase):
    """按规则号取出处。"""

    def test_threshold_cap(self) -> None:
        self.assertEqual(d.cite("D-T-02").label, "第14章 L3478")

    def test_long_run(self) -> None:
        self.assertEqual(d.cite("D-L-01").label, "第4章 L1363")

    def test_shorthand_accepted(self) -> None:
        self.assertEqual(d.cite("t-02").key, "D-T-02")
        self.assertEqual(d.cite(" D-t-02 ").key, "D-T-02")

    def test_unknown_rule_raises_with_hint(self) -> None:
        with self.assertRaises(KeyError) as ctx:
            d.cite("D-T-99")
        self.assertIn("D-T-", str(ctx.exception))

    def test_non_string_rejected(self) -> None:
        with self.assertRaises(TypeError):
            d.cite(5)  # type: ignore[arg-type]


class TestCorrectedCitations(unittest.TestCase):
    """回原文核出来的三条错误，改完之后不许再错。"""

    def test_interval_rep_length_points_at_chapter_four(self) -> None:
        """原引 第5章 L1784（那是 VDOT 51 的配速例）。"""
        item = d.cite("D-I-02")
        self.assertEqual(item.chapter, "第4章")
        self.assertEqual(item.lines, "L1480")

    def test_twice_weekly_interval_points_at_next_line(self) -> None:
        """原引 L2978（讲的是 I ≤ 8%），"每周两次"在 L2980。"""
        self.assertEqual(d.cite("D-I-03").lines, "L2980")

    def test_repetition_rep_length_points_at_chapter_five(self) -> None:
        """原引 第4章 L1583（讲 R 总量），2 分钟回合在 第5章 L1786。"""
        item = d.cite("D-R-02")
        self.assertEqual(item.chapter, "第5章")
        self.assertEqual(item.lines, "L1786")

    def test_audit_log_records_the_fixes(self) -> None:
        log = " ".join(d.RULE_AUDIT_LOG)
        for rule_id in ("D-I-02", "D-I-03", "D-R-02"):
            self.assertIn(rule_id, log)

    def test_audit_record_counts(self) -> None:
        record = d.audit_record()
        self.assertEqual(record["rule_count"], len(d.RULES))
        self.assertEqual(len(record["fixes"]), 4)


class TestCompleteness(unittest.TestCase):
    """每条规则都要有章号和行号，不许半截。"""

    def test_every_rule_has_chapter_and_lines(self) -> None:
        for rule_id, rule in d.RULES.items():
            with self.subTest(rule_id=rule_id):
                self.assertTrue(rule.chapter.strip())
                self.assertIn("L", rule.lines)
                self.assertTrue(rule.summary.strip())

    def test_lines_look_like_line_numbers(self) -> None:
        """行号里必须有阿拉伯数字，防止写成「第4章 前半」。"""
        for rule_id, rule in d.RULES.items():
            with self.subTest(rule_id=rule_id):
                self.assertRegex(rule.lines, r"L\d+")

    def test_citations_covers_rules_and_provenance(self) -> None:
        keys = {item.key for item in d.citations()}
        self.assertTrue(set(d.RULES).issubset(keys))
        self.assertIn("altitude", keys)

    def test_citation_labels_are_unique_per_key(self) -> None:
        """同一条规则多次出现时，key 仍然唯一。"""
        keys = [item.key for item in d.citations()]
        self.assertEqual(len(keys), len(set(keys)))


class TestSearch(unittest.TestCase):
    """中文提问要能命中，因为摘要里写的是「L 跑」这种形式。"""

    def test_chinese_alias_for_long_run(self) -> None:
        labels = {c.label for c in d.search_citations("长跑", 5)}
        self.assertIn("第4章 L1363", labels)

    def test_threshold_alias(self) -> None:
        keys = {c.key for c in d.search_citations("门槛", 5)}
        self.assertIn("D-T-01", keys)

    def test_interval_alias(self) -> None:
        keys = {c.key for c in d.search_citations("间歇", 5)}
        self.assertIn("D-I-01", keys)

    def test_altitude_points_at_provenance(self) -> None:
        hits = d.search_citations("海拔", 3)
        self.assertTrue(hits)
        self.assertEqual(hits[0].key, "altitude")

    def test_rule_id_wins_ranking(self) -> None:
        self.assertEqual(d.search_citations("D-T-02", 1)[0].key, "D-T-02")

    def test_no_match_returns_empty(self) -> None:
        self.assertEqual(d.search_citations("红烧肉"), [])

    def test_whitespace_ignored(self) -> None:
        self.assertEqual(
            [c.key for c in d.search_citations(" 长 跑 ", 3)],
            [c.key for c in d.search_citations("长跑", 3)],
        )

    def test_bad_arguments(self) -> None:
        with self.assertRaises(TypeError):
            d.search_citations(1)  # type: ignore[arg-type]
        with self.assertRaises(ValueError):
            d.search_citations("T", limit=0)

    def test_empty_query(self) -> None:
        self.assertEqual(d.search_citations("   "), [])


class TestManifest(unittest.TestCase):
    """清单里要能读到核对记录。"""

    def test_manifest_exposes_audit_record(self) -> None:
        payload = d.manifest()
        self.assertIn("citation_audit", payload)
        self.assertEqual(
            payload["citation_audit"]["rule_count"], len(d.RULES)
        )

    def test_manifest_declares_no_handwritten_lines(self) -> None:
        areas = " ".join(item["area"] for item in d.manifest()["unsupported"])
        self.assertIn("手写行号", areas)

    def test_manifest_json_safe(self) -> None:
        json.dumps(d.manifest(), ensure_ascii=False)


if __name__ == "__main__":
    unittest.main()
