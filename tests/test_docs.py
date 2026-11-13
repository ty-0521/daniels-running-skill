# -*- coding: utf-8 -*-
"""文档里的代码块必须真的能跑。

这一组是补的。写 README 的「完整流程」时，我给的审计示例其实**会失败**
（4 次/周却按 +8 km 加量，上限只有 6.4），而没有任何测试会发现——
因为文档没人执行。读者照着抄会拿到一个"不通过"，然后以为是自己抄错了。

所以：``README.md`` 与 ``SKILL.md`` 里所有 ```python 块，按顺序在同一个命名空间里
真跑一遍。跑不过就失败。
"""

from __future__ import annotations

import io
import re
import unittest
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCS = ("README.md", "SKILL.md")


def python_blocks(path: Path) -> list[str]:
    """把一个 markdown 文件里的 python 代码块抽出来，保持顺序。"""
    text = path.read_text(encoding="utf-8")
    return re.findall(r"```python\n(.*?)```", text, re.S)


class TestDocCodeBlocks(unittest.TestCase):
    """逐个文件跑一遍，输出同时收集起来供断言。"""

    def _run(self, name: str) -> str:
        path = ROOT / name
        self.assertTrue(path.exists(), f"找不到 {name}")
        blocks = python_blocks(path)
        self.assertTrue(blocks, f"{name} 里没有 python 代码块")
        namespace: dict = {}
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            for index, code in enumerate(blocks, start=1):
                try:
                    exec(compile(code, f"{name}#{index}", "exec"), namespace)
                except Exception as exc:  # noqa: BLE001 - 故意捕获全部
                    self.fail(
                        f"{name} 第 {index} 个代码块跑不通："
                        f"{type(exc).__name__}: {exc}\n{code}"
                    )
        return buffer.getvalue()

    def test_readme_blocks_run(self) -> None:
        self._run("README.md")

    def test_skill_blocks_run(self) -> None:
        self._run("SKILL.md")

    def test_readme_audit_example_passes(self) -> None:
        """README 里那张示例表必须真的通过，否则读者会以为是自己抄错。"""
        output = self._run("README.md")
        self.assertIn("通过：", output)
        self.assertNotIn("!!", output)

    def test_skill_md_has_identity_statement(self) -> None:
        """定位那句要写死在文档里，不是藏在末尾。"""
        text = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("第二意见", text)
        self.assertIn("不是教练", text)

    def test_readme_has_caveats(self) -> None:
        """开源门面必须有注意事项一节。"""
        text = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("## 注意事项", text)
        for needle in ("不是医疗器械", "它的错，长什么样", "你要怎么核对它"):
            self.assertIn(needle, text)

    def test_no_handwritten_line_number_rule_documented(self) -> None:
        """「行号只许查不许写」这条要出现在给 agent 看的文档里。"""
        text = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("行号只许查不许写", text)
        self.assertIn("cite(", text)

    def test_compliance_word_is_gated(self) -> None:
        text = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("只能由 `audit_plan` 出具", text)


class TestDocLinks(unittest.TestCase):
    """文档里的相对链接必须指得到。

    开源仓库里一个坏链接很难被读者容忍，也很难被作者自己发现。
    """

    MARKDOWN = (
        "README.md",
        "SKILL.md",
        "docs/test-runs/README.md",
        "docs/test-runs/round2-branches.md",
        "docs/daniels-running-skill-实现路径.md",
    )

    def test_relative_links_resolve(self) -> None:
        import re

        broken = []
        for name in self.MARKDOWN:
            path = ROOT / name
            if not path.exists():
                continue
            base = path.parent
            text = path.read_text(encoding="utf-8")
            for match in re.finditer(r"\]\(([^)#][^)]*)\)", text):
                target = match.group(1).strip()
                if target.startswith(("http://", "https://", "mailto:")):
                    continue
                resolved = (base / target).resolve()
                if not resolved.exists():
                    broken.append(f"{name} -> {target}")
        self.assertEqual(broken, [], f"坏链接：{broken}")


class TestManifestInDocs(unittest.TestCase):
    """文档里承诺的清单字段，manifest 里要真的有。"""

    def test_documented_keys_exist(self) -> None:
        import daniels as d

        payload = d.manifest()
        for key in (
            "layers",
            "error_bounds",
            "unsupported",
            "deload_provenance",
            "citation_audit",
            "rules",
            "topics",
            "phases",
        ):
            self.assertIn(key, payload)
        for layer in ("vdot", "dose", "periodize", "deload", "audit",
                      "intake", "citations", "explain"):
            self.assertIn(layer, payload["layers"])


class TestArchivedCounterexample(unittest.TestCase):
    """docs/test-runs/plan.json 是十轮测试里那张错表。

    它必须**永远**判为不通过。一旦某次改动让它"通过"了，说明检查被改松了——
    这比任何一个功能 bug 都严重，因为它意味着以后所有表都会"通过"。
    """

    def test_counterexample_still_fails(self) -> None:
        import json

        import daniels as d

        path = ROOT / "docs" / "test-runs" / "plan.json"
        self.assertTrue(path.exists(), "反例文件不见了")
        payload = json.loads(path.read_text(encoding="utf-8"))
        weeks, kwargs = d.plan_from_dict(payload)
        result = d.audit_plan(weeks, **kwargs)  # type: ignore[arg-type]
        self.assertFalse(result.passed)
        self.assertGreaterEqual(len(result.errors), 10)

    def test_counterexample_has_the_week_13_error(self) -> None:
        """那张表的核心错误：第 13 周加量只隔了 2 周。"""
        import json

        import daniels as d

        payload = json.loads(
            (ROOT / "docs" / "test-runs" / "plan.json").read_text(encoding="utf-8")
        )
        weeks, kwargs = d.plan_from_dict(payload)
        result = d.audit_plan(weeks, **kwargs)  # type: ignore[arg-type]
        progression = [
            f.week for f in result.errors if f.check == "progression"
        ]
        self.assertEqual(progression, [13])

    def test_counterexample_base_is_assumed(self) -> None:
        """起点是估的这件事，必须由 base 那条 warn 挡住。"""
        import json

        import daniels as d

        payload = json.loads(
            (ROOT / "docs" / "test-runs" / "plan.json").read_text(encoding="utf-8")
        )
        weeks, kwargs = d.plan_from_dict(payload)
        result = d.audit_plan(weeks, **kwargs)  # type: ignore[arg-type]
        self.assertEqual([f.check for f in result.warnings], ["base"])


if __name__ == "__main__":
    unittest.main()
