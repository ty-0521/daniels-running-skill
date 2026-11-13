# -*- coding: utf-8 -*-
"""行号查询层。

为什么单开一层
--------------
十轮真实测试里，行号引错出现了三次，每一次都不是算错，是**凭记忆手写行号**：

* 把 ``第4章 L1392`` 当成 T 的规则——那一行讲的是 **M**（110 分钟 / 29 km / 20%）；
* 把 ``第12章 L3160`` 当成半马阶段一的 25%/150 分钟——那一行是**越野**的 30%/60 分钟，
  半马那条在 ``第13章 L3276``；
* 把 ``第11章 L2978`` 当成「每周两次 I」——那一行讲的是 I ≤ 8%、≤ 10 km，
  两句在 ``L2980``。

三次错的形状一模一样：**结论对，出处错**。这种人最难被发现，因为读者核不到。

所以定一条硬规矩：**回答里出现的任何行号，必须来自本模块的查询结果，不许手写。**
数据源只有 :data:`daniels.dose.RULES` 与 :data:`daniels.vdot.PROVENANCE`，
两者都已逐条回原文核过，核对记录见 :data:`RULE_AUDIT_LOG`。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple

from .dose import RULES
from .vdot import PROVENANCE

__all__ = [
    "Citation",
    "RULE_AUDIT_LOG",
    "audit_record",
    "cite",
    "citations",
    "rules_by_id",
    "search_citations",
]


@dataclass(frozen=True)
class Citation:
    """一条可引用的出处。"""

    key: str
    """规则号（``D-T-02``）或配速来源的关键字。"""
    chapter: str
    lines: str
    summary: str

    @property
    def label(self) -> str:
        """可以直接写进回答的出处串，例如 ``第14章 L3478``。"""
        if self.chapter and self.lines:
            return f"{self.chapter} {self.lines}"
        return self.chapter or self.lines or "（无出处）"

    def as_dict(self) -> Dict[str, str]:
        return {
            "key": self.key,
            "label": self.label,
            "chapter": self.chapter,
            "lines": self.lines,
            "summary": self.summary,
        }

    def __str__(self) -> str:  # pragma: no cover - 便利方法
        return f"{self.label} · {self.summary}"


#: 逐条回原文核对的结果。只记「改了什么」，不存原书文字。
#:
#: 核对方式：把 ``RULES`` 里每条的行号取出来，打印该书对应行的原文，
#: 与 ``summary`` 逐条比对。32 条里有 3 条对不上，已改正，余 29 条一致。
RULE_AUDIT_LOG: Tuple[str, ...] = (
    "D-I-02：原引 第5章 L1784（该行是 VDOT 51 的一组配速例），"
    "5 分钟回合的出处是 第4章 L1480；1200 m 这个当量确实在 L1784，已写进摘要。",
    "D-I-03：原引 第11章 L2978（该行讲的是 I ≤ 周跑量 8% 且 ≤ 10 km），"
    "「每周两次就够」在下一行 L2980。",
    "D-R-02：原引 第4章 L1583（该行讲 R 的总量 ≤ 8 km 与 5%），"
    "「单个回合不超过 2 分钟」在 第5章 L1786。",
    "其余 29 条逐字比对一致，未改动。",
)


def rules_by_id() -> Dict[str, Citation]:
    """全部规则，按 rule_id 索引。"""
    return {
        rule_id: Citation(
            key=rule_id,
            chapter=rule.chapter,
            lines=rule.lines,
            summary=rule.summary,
        )
        for rule_id, rule in RULES.items()
    }


def citations() -> Tuple[Citation, ...]:
    """全部出处，规则在前、配速来源在后，各自按 key 排序。"""
    out: List[Citation] = [
        rules_by_id()[rule_id] for rule_id in sorted(RULES)
    ]
    for key in sorted(PROVENANCE):
        chapter, lines, summary = PROVENANCE[key]
        out.append(
            Citation(
                key=key,
                chapter=str(chapter),
                lines=str(lines),
                summary=str(summary),
            )
        )
    return tuple(out)


def cite(rule_id: str) -> Citation:
    """按规则号取一条出处。

    Parameters
    ----------
    rule_id : str
        形如 ``D-T-02``。也接受 ``t-02`` 这类省略前缀的写法。

    Raises
    ------
    KeyError
        找不到，错误信息里会列出相近的规则号。

    Examples
    --------
    >>> from daniels.citations import cite
    >>> cite("D-T-02").label
    '第14章 L3478'
    """
    if not isinstance(rule_id, str):
        raise TypeError(f"rule_id 必须是字符串，收到 {type(rule_id).__name__}")
    key = rule_id.strip().upper()
    table = rules_by_id()
    if key in table:
        return table[key]
    if not key.startswith("D-"):
        key = f"D-{key}"
        if key in table:
            return table[key]
    close = [k for k in table if key.split("-")[-1] in k]
    hint = f"，相近的有 {close}" if close else ""
    raise KeyError(f"没有这条规则：{rule_id!r}{hint}")


#: 强度别称。用户不会搜「L 跑」，他会搜「长跑」「长距离」。
_INTENSITY_ALIASES: Dict[str, str] = {
    "E": "轻松跑 有氧 恢复",
    "L": "长跑 长距离 耐力",
    "M": "马拉松配速 比赛配速",
    "T": "门槛 节奏 巡航 乳酸",
    "I": "间歇 最大摄氧量",
    "R": "重复 速度",
    "FR": "快速重复",
    "H": "艰苦跑",
    "G": "通用 阶段 加量 增量 恢复 比赛",
}

#: 配速来源里的非强度条目。
_EXTRA_ALIASES: Dict[str, str] = {
    "vo2": "摄氧量 回归方程 公式",
    "pct_max": "百分比 最大摄氧量 可维持时长 曲线",
    "altitude": "海拔 高原",
    "novice": "新手 初跑 低vdot 表5—3",
}


def _tag_of(key: str) -> str:
    """把规则号或来源名映射成中文别称串。"""
    if key in _EXTRA_ALIASES:
        return _EXTRA_ALIASES[key]
    if key in _INTENSITY_ALIASES:
        return _INTENSITY_ALIASES[key]
    if key.startswith("D-"):
        parts = key.split("-")
        if len(parts) >= 2:
            return _INTENSITY_ALIASES.get(parts[1], _INTENSITY_ALIASES["G"])
    return _INTENSITY_ALIASES["G"]


def _haystack(item: Citation) -> str:
    return "".join(f"{item.key}{_tag_of(item.key)}{item.summary}".split()).lower()


def search_citations(query: str, limit: int = 3) -> List[Citation]:
    """在规则摘要与强度别称里做子串检索。

    Parameters
    ----------
    query : str
        关键词，如 ``T``、``长跑``、``加量``、``海拔``。
    limit : int, optional
        最多返回几条，默认 3。

    Returns
    -------
    list of Citation
        按匹配得分降序；没有命中返回空列表，不抛异常。

    Notes
    -----
    两条归一化：

    * 提问与正文都去掉空白——用户会在数字两侧留空格；
    * 规则号里的强度字母会展开成中文别称，所以搜「长跑」能命中 ``D-L-*``，
      搜「门槛」能命中 ``D-T-*``。摘要本身用的是「L 跑」这种写法，
      不展开的话中文提问基本搜不到。
    """
    if not isinstance(query, str):
        raise TypeError(f"query 必须是字符串，收到 {type(query).__name__}")
    if limit <= 0:
        raise ValueError(f"limit 必须为正，收到 {limit}")
    text = "".join(query.split()).lower()
    if not text:
        return []
    scored: List[Tuple[int, Citation]] = []
    for item in citations():
        if text not in _haystack(item):
            continue
        # 排序权重：命中规则号 > 命中摘要 > 只命中中文别称
        if text in item.key.lower():
            weight = 1000
        elif text in "".join(item.summary.split()).lower():
            weight = 200 + len(text)
        else:
            weight = 100 + len(text)
        scored.append((weight, item))
    scored.sort(key=lambda pair: (-pair[0], pair[1].key))
    return [item for _, item in scored[:limit]]


def audit_record() -> Dict[str, object]:
    """把核对记录导成可序列化结构，供 ``manifest()`` 与 CLI 使用。"""
    return {
        "rule_count": len(RULES),
        "fixes": list(RULE_AUDIT_LOG),
        "note": (
            "行号必须来自 citations.cite() / search_citations()，"
            "禁止在回答里手写行号"
        ),
    }
