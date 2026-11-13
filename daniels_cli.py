# -*- coding: utf-8 -*-
"""启动器：从任意工作目录调用本 skill。

    python <本文件路径> paces 51

之所以需要它：``python -m daniels`` 要求当前目录（或 PYTHONPATH）
里有 ``daniels`` 包。agent 的工作目录通常不是 skill 所在目录，
直接照 SKILL.md 敲 ``python -m daniels`` 会报 No module named 'daniels'。
这个脚本把自己的父目录塞进 sys.path，因此不在乎从哪里被调用。
"""

from __future__ import annotations

import pathlib
import sys

_HERE = pathlib.Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from daniels.__main__ import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
