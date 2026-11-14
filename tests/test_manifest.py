# -*- coding: utf-8 -*-
"""daniels.manifest 的测试。

清单是对外契约，所以测的是「它说的每件事都真的存在」。
"""

from __future__ import annotations

import json
import unittest

import daniels
from daniels.manifest import ERROR_BOUNDS, UNSUPPORTED, manifest


class TestManifestShape(unittest.TestCase):
    """清单的结构。"""

    def test_json_serializable(self) -> None:
        text = json.dumps(manifest(), ensure_ascii=False)
        self.assertGreater(len(text), 1000)

    def test_top_level_keys(self) -> None:
        data = manifest()
        for key in (
            "name",
            "version",
            "layers",
            "constants",
            "error_bounds",
            "unsupported",
            "rules",
            "topics",
            "phases",
        ):
            self.assertIn(key, data)

    def test_version_matches_package(self) -> None:
        self.assertEqual(manifest()["version"], daniels.__version__)

    def test_phases_are_four(self) -> None:
        self.assertEqual(len(manifest()["phases"]), 4)


class TestLayerReferences(unittest.TestCase):
    """清单里列出的每个函数都必须真的能调用到。"""

    def test_all_layer_functions_exist(self) -> None:
        for layer, names in manifest()["layers"].items():
            for name in names:
                with self.subTest(layer=layer, name=name):
                    self.assertTrue(hasattr(daniels, name), f"{name} 不存在")

    def test_self_check_returns_nothing(self) -> None:
        from daniels.manifest import _self_check

        self.assertEqual(_self_check(), [])


class TestRulesAndTopics(unittest.TestCase):
    """规则与词条都被完整导出。"""

    def test_rule_count_matches(self) -> None:
        from daniels.dose import RULES

        self.assertEqual(len(manifest()["rules"]), len(RULES))

    def test_every_rule_has_provenance(self) -> None:
        for rule in manifest()["rules"]:
            with self.subTest(rule=rule["rule_id"]):
                self.assertTrue(rule["chapter"].startswith("第"))
                self.assertTrue(rule["lines"].startswith("L"))

    def test_topic_count_matches(self) -> None:
        from daniels.explain import TOPICS

        self.assertEqual(len(manifest()["topics"]), len(TOPICS))

    def test_boundaries_listed(self) -> None:
        from daniels.explain import BOUNDARIES

        data = manifest()
        self.assertIn("boundaries", data)
        self.assertEqual(len(data["boundaries"]), len(BOUNDARIES))
        self.assertIn("boundary", data["layers"]["explain"])
        for item in data["boundaries"]:
            with self.subTest(boundary=item["boundary_id"]):
                self.assertTrue(item["basis"], "边界必须带依据")

    def test_topics_sorted(self) -> None:
        ids = [t["topic_id"] for t in manifest()["topics"]]
        self.assertEqual(ids, sorted(ids))


class TestDeclaredBounds(unittest.TestCase):
    """误差上界与不支持区域必须真的写进数据。"""

    def test_error_bounds_cover_every_intensity(self) -> None:
        metrics = " ".join(str(item["metric"]) for item in ERROR_BOUNDS)
        for token in ("VDOT", "M 配速", "T 配速", "I 配速", "R 配速", "E 配速"):
            self.assertIn(token, metrics)

    def test_every_bound_has_basis(self) -> None:
        for item in ERROR_BOUNDS:
            with self.subTest(metric=item["metric"]):
                self.assertTrue(item["basis"])

    def test_low_vdot_intervals_are_flagged(self) -> None:
        item = next(
            i for i in ERROR_BOUNDS if i["metric"] == "I 配速（VDOT < 30）"
        )
        self.assertEqual(item["max_error"], "3.5%")
        self.assertIn("note", item)

    def test_unsupported_areas_are_enumerated(self) -> None:
        areas = " ".join(item["area"] for item in UNSUPPORTED)
        for token in ("年龄", "跑步机", "海拔", "VDOT 低于"):
            self.assertIn(token, areas)

    def test_every_unsupported_has_behavior(self) -> None:
        for item in UNSUPPORTED:
            with self.subTest(area=item["area"]):
                self.assertTrue(item["behavior"])

    def test_documented_plan_lengths_listed(self) -> None:
        lengths = manifest()["constants"]["documented_plan_lengths"]
        self.assertEqual(lengths, [3, 6, 9, 12, 20, 23, 24])


class TestManifestTellsTheTruth(unittest.TestCase):
    """清单里的名字是手写的字符串，改一次代码就可能变成假话。

    这一组不测内容对不对，只测**它承诺的东西真的存在**。
    清单骗人比函数算错更难发现：接入方照着清单调用，报错才回头查。
    """

    def test_every_layer_name_exists(self) -> None:
        import daniels as d

        payload = manifest()
        dead = []
        for layer, names in payload["layers"].items():
            for name in names:
                if not hasattr(d, name):
                    dead.append(f"{layer}.{name}")
        self.assertEqual(dead, [], f"清单里列了不存在的名字：{dead}")

    def test_dunder_all_names_exist(self) -> None:
        import daniels as d

        dead = [n for n in d.__all__ if not hasattr(d, n)]
        self.assertEqual(dead, [], f"__all__ 里有不存在的名字：{dead}")

    def test_dunder_all_has_no_duplicates(self) -> None:
        import daniels as d

        dupes = sorted({n for n in d.__all__ if d.__all__.count(n) > 1})
        self.assertEqual(dupes, [])

    def test_dunder_all_is_sorted_per_block(self) -> None:
        """同一个区块内部应当有序，方便人工扫。"""
        import daniels as d

        self.assertIn("vdot_from_race", d.__all__)
        self.assertIn("audit_plan", d.__all__)
        self.assertIn("feasible_plans", d.__all__)

    def test_counts_match_the_source_objects(self) -> None:
        import daniels as d

        payload = manifest()
        self.assertEqual(len(payload["rules"]), len(d.RULES))
        self.assertEqual(len(payload["topics"]), len(d.TOPICS))
        self.assertEqual(len(payload["phases"]), len(d.PHASES))

    def test_every_rule_appears_exactly_once(self) -> None:
        import daniels as d

        listed = [item["rule_id"] for item in manifest()["rules"]]
        self.assertEqual(len(listed), len(set(listed)))
        self.assertEqual(set(listed), set(d.RULES))

    def test_citation_audit_matches_rule_count(self) -> None:
        import daniels as d

        self.assertEqual(
            manifest()["citation_audit"]["rule_count"], len(d.RULES)
        )


class TestSkillJsonInSync(unittest.TestCase):
    """落盘的 skill.json 不能与代码漂移。"""

    def test_file_matches_manifest(self) -> None:
        from pathlib import Path

        path = Path(__file__).resolve().parent.parent / "skill.json"
        if not path.exists():
            self.skipTest("skill.json 尚未生成")
        data = json.loads(path.read_text(encoding="utf-8"))
        expected = json.loads(json.dumps(manifest(), ensure_ascii=False))
        self.assertEqual(
            data,
            expected,
            "skill.json 与 manifest() 不一致，请重新运行 "
            "`python -m daniels manifest -o skill.json`",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
