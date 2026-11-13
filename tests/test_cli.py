# -*- coding: utf-8 -*-
"""命令行入口的测试。

CLI 是对外契约的一部分，退出码尤其重要（脚本会据此判断），
所以这里逐条断言退出码与关键输出。

运行：
    cd D:\\training
    python -m unittest discover -s tests -v
"""

from __future__ import annotations

import io
import json
import unittest
from contextlib import redirect_stderr, redirect_stdout

from daniels.__main__ import CliError, main, parse_distance, parse_session


def run(*argv: str) -> tuple:
    """执行一次 CLI，返回 (退出码, 标准输出, 标准错误)。"""
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = main(list(argv))
    return code, out.getvalue(), err.getvalue()


class TestExitCodeContract(unittest.TestCase):
    """三个退出码必须互斥。

    ``argparse`` 默认用 2 报用法错误，而 ``check`` / ``audit`` 用 2 报
    「发现了问题」。撞在一起的话，调用方分不清是命令写错了还是表不合规。
    """

    def test_usage_error_is_one_not_two(self) -> None:
        with self.assertRaises(SystemExit) as ctx:
            with redirect_stderr(io.StringIO()):
                main([])
        self.assertEqual(ctx.exception.code, 1)

    def test_unknown_command_is_one(self) -> None:
        with self.assertRaises(SystemExit) as ctx:
            with redirect_stderr(io.StringIO()):
                main(["nosuchcommand"])
        self.assertEqual(ctx.exception.code, 1)

    def test_domain_error_is_one(self) -> None:
        code, _, err = run("calendar", "--race", "2027-13-45")
        self.assertEqual(code, 1)
        self.assertIn("错误", err)

    def test_findings_are_two(self) -> None:
        import json as _json
        import tempfile
        import os

        payload = {
            "sessions_per_week": 5,
            "weeks": [
                {"week": 1, "weekly_km": 24, "sessions": [["L", 8]]},
                {"week": 2, "weekly_km": 24, "sessions": [["L", 8]]},
            ],
        }
        path = "_test_exit_code.json"
        with open(path, "w", encoding="utf-8") as handle:
            _json.dump(payload, handle)
        try:
            code, _, _ = run("audit", path)
        finally:
            os.remove(path)
        self.assertEqual(code, 2)

    def test_success_is_zero(self) -> None:
        code, out, _ = run("vdot", "5k", "20:00")
        self.assertEqual(code, 0)
        self.assertIn("49.81", out)

    def test_constants_are_distinct(self) -> None:
        from daniels.__main__ import EXIT_ERROR, EXIT_FINDINGS, EXIT_OK

        self.assertEqual({EXIT_OK, EXIT_ERROR, EXIT_FINDINGS}, {0, 1, 2})


class TestParseDistance(unittest.TestCase):
    """距离别名解析。"""

    def test_aliases(self) -> None:
        cases = {
            "5k": 5000.0,
            "10K": 10000.0,
            "1600m": 1600.0,
            "mile": 1609.344,
            "hm": 21097.5,
            "fm": 42195.0,
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertAlmostEqual(parse_distance(text), expected, places=3)

    def test_raw_meters(self) -> None:
        self.assertAlmostEqual(parse_distance("3000"), 3000.0)
        self.assertAlmostEqual(parse_distance("3000m"), 3000.0)

    def test_invalid(self) -> None:
        for bad in ("abc", "", "0", "-5"):
            with self.subTest(text=bad):
                with self.assertRaises(CliError):
                    parse_distance(bad)


class TestParseSession(unittest.TestCase):
    """训练写法解析。"""

    def test_valid(self) -> None:
        session = parse_session("t6.4")
        self.assertEqual(session.intensity, "T")
        self.assertAlmostEqual(session.km, 6.4)

    def test_colon_form(self) -> None:
        session = parse_session("L:18")
        self.assertEqual(session.intensity, "L")
        self.assertAlmostEqual(session.km, 18.0)

    def test_invalid(self) -> None:
        for bad in ("X10", "T", "Tabc", "T0", "T-3"):
            with self.subTest(text=bad):
                with self.assertRaises(CliError):
                    parse_session(bad)


class TestVdotCommand(unittest.TestCase):
    def test_five_k(self) -> None:
        code, out, _ = run("vdot", "5k", "20:00")
        self.assertEqual(code, 0)
        self.assertIn("VDOT = 49.81", out)

    def test_bad_time(self) -> None:
        code, _, err = run("vdot", "5k", "不是时间")
        self.assertEqual(code, 1)
        self.assertIn("错误", err)

    def test_out_of_range_distance(self) -> None:
        code, _, err = run("vdot", "400", "60")
        self.assertEqual(code, 1)
        self.assertIn("错误", err)


class TestPacesCommand(unittest.TestCase):
    def test_default(self) -> None:
        code, out, _ = run("paces", "49.8")
        self.assertEqual(code, 0)
        for token in ("E", "M", "T", "I", "R", "FR", "H"):
            self.assertIn(token, out)
        self.assertIn("4:32", out)

    def test_altitude_is_reported(self) -> None:
        code, out, _ = run("paces", "49.8", "--altitude", "2130")
        self.assertEqual(code, 0)
        self.assertIn("海拔", out)
        self.assertIn("4", out)

    def test_novice_table_is_reported(self) -> None:
        code, out, _ = run("paces", "28")
        self.assertEqual(code, 0)
        self.assertIn("新手表", out)

    def test_vdot_out_of_range(self) -> None:
        code, _, err = run("paces", "19")
        self.assertEqual(code, 1)
        self.assertIn("VDOT", err)


class TestCapCommand(unittest.TestCase):
    def test_threshold(self) -> None:
        code, out, _ = run("cap", "64", "T")
        self.assertEqual(code, 0)
        data = json.loads(out)
        self.assertAlmostEqual(data["max_km"], 6.4)
        self.assertEqual(data["rule_ids"], ["D-T-01", "D-T-02"])

    def test_with_vdot_adds_effective_value(self) -> None:
        code, out, _ = run("cap", "64", "T", "--vdot", "49.8")
        self.assertEqual(code, 0)
        data = json.loads(out)
        self.assertIn("effective_km", data)
        self.assertIn("binding", data)

    def test_trail_branch(self) -> None:
        code, out, _ = run(
            "cap", "64", "L", "--surface", "trail", "--phase", "1"
        )
        self.assertEqual(code, 0)
        data = json.loads(out)
        self.assertEqual(data["max_minutes"], 60.0)


class TestCheckCommand(unittest.TestCase):
    def test_violation_exits_two(self) -> None:
        code, out, _ = run(
            "check", "--weekly", "64", "--vdot", "49.8", "L18", "T9"
        )
        self.assertEqual(code, 2)
        self.assertIn("超限", out)
        self.assertIn("D-T-01", out)

    def test_clean_exits_zero(self) -> None:
        code, out, _ = run(
            "check", "--weekly", "64", "--vdot", "49.8", "L16", "T6", "I3"
        )
        self.assertEqual(code, 0)
        self.assertIn("合规", out)

    def test_bad_session_exits_one(self) -> None:
        code, _, err = run("check", "--weekly", "64", "XYZ")
        self.assertEqual(code, 1)
        self.assertIn("错误", err)


class TestPlanCommand(unittest.TestCase):
    def test_documented(self) -> None:
        code, out, _ = run("plan", "24")
        self.assertEqual(code, 0)
        self.assertIn("B/FIP", out)
        self.assertIn("周一", out)

    def test_undocumented_refused(self) -> None:
        code, _, err = run("plan", "16")
        self.assertEqual(code, 1)
        self.assertIn("没有记录", err)
        self.assertIn("allow_undocumented", err)

    def test_undocumented_opt_in(self) -> None:
        code, out, _ = run("plan", "16", "--allow-undocumented")
        self.assertEqual(code, 0)
        data, _ = json.JSONDecoder().raw_decode(out)
        self.assertFalse(data["documented"])


class TestExplainCommand(unittest.TestCase):
    def test_hit(self) -> None:
        code, out, _ = run("explain", "定速节奏跑和巡航间歇的区别", "--limit", "1")
        self.assertEqual(code, 0)
        self.assertIn("出处", out)
        self.assertIn("第4章", out)

    def test_miss_is_graceful(self) -> None:
        code, out, _ = run("explain", "量子力学与红烧肉")
        self.assertEqual(code, 0)
        self.assertIn("没有匹配", out)

    def test_topics_listing(self) -> None:
        code, out, _ = run("topics")
        self.assertEqual(code, 0)
        self.assertIn("why-easy-is-slow", out)
        self.assertIn("l-cap-conflict", out)


class TestManifestCommand(unittest.TestCase):
    def test_stdout_is_valid_json(self) -> None:
        code, out, _ = run("manifest")
        self.assertEqual(code, 0)
        data = json.loads(out)
        self.assertEqual(data["name"], "daniels-running-skill")
        self.assertIn("error_bounds", data)

    def test_write_to_file(self) -> None:
        import os
        import tempfile

        handle, path = tempfile.mkstemp(suffix=".json")
        os.close(handle)
        try:
            code, out, _ = run("manifest", "-o", path)
            self.assertEqual(code, 0)
            self.assertIn("已写入", out)
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
            self.assertEqual(data["name"], "daniels-running-skill")
        finally:
            os.unlink(path)


class TestArgumentErrors(unittest.TestCase):
    """argparse 层面的错误应当以 SystemExit 结束。"""

    def test_missing_command(self) -> None:
        with self.assertRaises(SystemExit), redirect_stderr(io.StringIO()):
            main([])

    def test_unknown_command(self) -> None:
        with self.assertRaises(SystemExit), redirect_stderr(io.StringIO()):
            main(["不存在的命令"])

    def test_bad_intensity_choice(self) -> None:
        with self.assertRaises(SystemExit), redirect_stderr(io.StringIO()):
            main(["cap", "64", "Z"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
