# -*- coding: utf-8 -*-
"""用户真会碰到的边界：CLI 的兜底输出、构造函数的参数校验。

这些分支不影响算数，但决定「输入写错时它说的是人话还是栈回溯」。
覆盖率统计里它们原来整片未执行，所以单独补一组。
"""

from __future__ import annotations

import io
import unittest
from contextlib import redirect_stderr, redirect_stdout

import daniels as d
from daniels.__main__ import main


def run(*argv: str) -> tuple:
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = main(list(argv))
    return code, out.getvalue(), err.getvalue()


class TestExplainFallbacks(unittest.TestCase):
    def test_miss_suggests_candidates(self) -> None:
        """「放松跑」没有精确命中，但要给出「你是不是想问 E 跑为什么慢」。"""
        code, out, _ = run("explain", "放松跑")
        self.assertEqual(code, 0)
        self.assertIn("没有匹配", out)
        self.assertIn("你是不是想问", out)
        self.assertIn("E 跑", out)

    def test_boundary_lists_related_topics(self) -> None:
        """越界问题先给边界声明，再把相关的词条列在下面。"""
        code, out, _ = run("explain", "我是女的，VDOT 要减多少")
        self.assertEqual(code, 0)
        self.assertIn("相关但不是这个问题的答案", out)


class TestAuditFileError(unittest.TestCase):
    def test_missing_file_says_so(self) -> None:
        code, _, err = run("audit", "no-such-plan.json")
        self.assertEqual(code, 1)
        self.assertIn("找不到文件", err)

    def test_unreadable_path_says_so(self) -> None:
        """给一个目录：读不了要说清是「读不了」，不是抛栈回溯。"""
        code, _, err = run("audit", "docs")
        self.assertEqual(code, 1)
        self.assertIn("读不了", err)


class TestWeekEntryValidation(unittest.TestCase):
    """周表的四个字段各自都要挡住错误类型，且报错要指出是哪一项。"""

    def test_week_must_be_int(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            d.WeekEntry(week="1", weekly_km=30.0)  # type: ignore[arg-type]
        self.assertIn("week", str(ctx.exception))

    def test_weekly_km_must_be_number(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            d.WeekEntry(week=1, weekly_km="30")  # type: ignore[arg-type]
        self.assertIn("weekly_km", str(ctx.exception))

    def test_weekly_km_must_be_positive(self) -> None:
        with self.assertRaises(ValueError):
            d.WeekEntry(week=1, weekly_km=0.0)

    def test_race_km_must_be_positive(self) -> None:
        with self.assertRaises(ValueError):
            d.WeekEntry(week=1, weekly_km=30.0, race_km=0.0)

    def test_part_km_must_be_numbers(self) -> None:
        with self.assertRaises(ValueError):
            d.WeekEntry(week=1, weekly_km=30.0, part_km=(8, "9"))  # type: ignore[arg-type]

    def test_part_km_cannot_be_negative(self) -> None:
        with self.assertRaises(ValueError):
            d.WeekEntry(week=1, weekly_km=30.0, part_km=(8, -1))


class TestPlanFromDictValidation(unittest.TestCase):
    def test_week_must_be_object(self) -> None:
        payload = {
            "sessions_per_week": 4,
            "base_source": "user",
            "weeks": [1, 2],
        }
        with self.assertRaises(ValueError) as ctx:
            d.plan_from_dict(payload)  # type: ignore[arg-type]
        self.assertIn("必须是对象", str(ctx.exception))


class TestCitationApiValidation(unittest.TestCase):
    def test_query_must_be_str(self) -> None:
        with self.assertRaises(TypeError):
            d.search_citations(123)  # type: ignore[arg-type]

    def test_limit_must_be_positive(self) -> None:
        with self.assertRaises(ValueError):
            d.search_citations("长跑", limit=0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
