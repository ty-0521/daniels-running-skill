# -*- coding: utf-8 -*-
"""丹尼尔斯配速引擎（数值层）。

本模块只做一件事：把「一次比赛成绩」变成「训练配速」，或反过来。
不含任何训练量规则、周期安排、文本解释——那些属于 dose / periodize / explain 层。

设计原则
--------
1. 所有公式来自 Daniels & Gilbert 的公开回归方程，不是拟合出来的经验值。
2. 每个输出都对应书中可查的数值（见 PROVENANCE），并有回归测试（tests/test_vdot.py）。
3. 书中没有的数据不外推：超范围一律抛 VdotRangeError / AltitudeRangeError。

一个必须知道的版本差异
----------------------
书中「1.6 公里」这个说法，在不同表里指的不是同一个距离：

* 表 5—1 / 5—2 的「1.6 公里」列实际是 **1 英里（1609.344 m）**
  —— 因为 VDOT 51 ↔ 5:44 只有在按英里算时才成立（1600 m 会给出 VDOT 50.6）。
* 附录 D 的「1.6 公里成绩」用的是 **1600 m**
  —— 因为 4:40 ↔ VDOT 63.8 只在按 1600 m 算时成立（按英里算是 64.2）。

两者相差约 0.4 个 VDOT。本模块的处理：
* ``vdot_from_race`` 由调用方给出真实距离，不做假设；
* R 配速按 **1 英里** 比赛配速推导（与表 5—2 的 R 列一致）。

误差边界（实测，见 tests/test_vdot.py）
---------------------------------------
===========  ==========================================
量            最大误差
===========  ==========================================
VDOT 正反算   0.21 VDOT (0.3%)
M 配速        0.14%（VDOT >= 30）
T 配速        0.72%
I 配速        0.45%（VDOT >= 30）/ 3.5%（VDOT < 30）
R 配速        1.43%
E 配速区间    1.23%
===========  ==========================================

低 VDOT（< 30）的 I 配速偏差不是公式错，而是书里「强度的物理定义」与
「表 5—3 的印刷值」本身不一致：表 5—3 的 I 列是按 R 加 7~8 秒/400 m 排的。
本模块统一按物理定义（98% vVO2max）输出，同时把表 5—3 的整行原值
放在 ``PaceSet.novice_row`` 里，由调用方决定对初跑者用哪一套。
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, Tuple

__all__ = [
    "DanielsError",
    "VdotRangeError",
    "AltitudeRangeError",
    "Pace",
    "PaceSet",
    "AltitudeCorrection",
    "PROVENANCE",
    "TABLE5_3",
    "vo2_of_speed",
    "pct_max",
    "speed_of_vo2",
    "vdot_from_race",
    "race_time",
    "altitude_correction",
    "pace_set",
    "h_time_cap",
    "parse_time",
    "format_time",
]

# ---------------------------------------------------------------------------
# 方程常数（Daniels & Gilbert）
# ---------------------------------------------------------------------------
_VO2_A = -4.60
_VO2_B = 0.182258
_VO2_C = 0.000104

_PCT_A = 0.8
_PCT_B = 0.1894393
_PCT_C = -0.012778
_PCT_D = 0.2989558
_PCT_E = -0.1932605

#: 支持的 VDOT 区间。20~30 来自表 5—3，30~85 来自表 5—1/5—2。
VDOT_MIN = 20.0
VDOT_MAX = 85.0
#: 表 5—3 的上界。落在此值及以下时，``PaceSet.novice_row`` 会同时给出
#: 书中初跑者表的 M 配速（比引擎默认的马拉松等时约慢 3%），供调用方选择。
VDOT_NOVICE_UPPER = 30.0

#: 支持的距离区间：800 m ~ 全程马拉松。
DISTANCE_MIN_M = 800.0
DISTANCE_MAX_M = 42195.0

METER_PER_MILE = 1609.344

# ---------------------------------------------------------------------------
# 强度系数
# ---------------------------------------------------------------------------
#: E 区间 = 1 英里比赛配速 + 75~113 秒/公里（第 4 章 L1359 的换算式）
_E_OFFSET_FAST_S_PER_KM = 75.0
_E_OFFSET_SLOW_S_PER_KM = 113.0
#: E 区的上沿：VDOT 的 74%（第 4 章 L1331 给出 59%~74%）。
#: 这条换算式在低 VDOT 会失效——算出的 E 会快于 M，属于逻辑倒挂，
#: 所以用 E 区的上沿作为下限兜底。
_E_ZONE_TOP = 0.74
#: E 区间的最小宽度（秒/公里）。只为避免低 VDOT 下区间塌缩，不是训练模型。
_E_MIN_WIDTH_S_PER_KM = 15.0
#: T = VDOT 的 88%（以 VO2 口径计）。表 5—4 给出 T 区 85%~90%。
_K_T = 0.880
#: I = 98% 的 vVO2max。表 5—4 称 I 区「达到或者非常接近」100% VDOT。
_K_I = 0.980
#: FR（快速重复）= R 每 200 m 快 3 秒（第 9 章 L2659）
_FR_OFFSET_S_PER_200M = 3.0
#: 表 5—3 中 M 配速固定为 VDOT 的 77.37%（以 VO2 口径计，11 行实测均值）
_K_M_NOVICE = 0.7737

# ---------------------------------------------------------------------------
# 海拔
# ---------------------------------------------------------------------------
#: 914 m 以下无影响（第 8 章 L2341）。
ALT_NEGLIGIBLE_M = 914.0
#: 书中的参照高度：2130 m。此处 I/T/M 各慢 4 秒/400 m，R 不变（第 14 章 L3582）。
ALT_REFERENCE_M = 2130.0
#: 书中讨论的上限 2500 m（第 8 章 L2341 称「中等高度」为 1200~2500 m）。
ALT_MAX_M = 2500.0
#: 参照高度下 I/T/M 的每 400 m 罚时（秒）。
ALT_PENALTY_S_PER_400M = 4.0

# ---------------------------------------------------------------------------
# 溯源表：每个量对应书里的位置
# ---------------------------------------------------------------------------
PROVENANCE: Dict[str, Tuple[str, str, str]] = {
    "vo2": ("全书", "第5章 L1724", "回归方程 VO2 = -4.60 + 0.182258v + 0.000104v^2"),
    "pct_max": ("全书", "图5—2 / L1724", "可维持时长对应的 %VO2max 曲线"),
    "E": ("第4章", "L1331 / L1359", "强度 59%~74% VO2max；配速 = 1 英里配速 + 1:15~1:53/km"),
    "M": ("第4章", "L1388 / L1390", "马拉松目标配速；VDOT 表按马拉松等时给出"),
    "T": ("第4章", "L1421", "训练有素者门槛配速 86%~88% VO2max"),
    "I": ("第4章", "L1478 / L1480", "I 强度应达到或非常接近 VO2max；单回合 3~5 分钟"),
    "R": ("第4章", "L1583 / L1806", "R = 当前 1.6 公里或 1500 米比赛配速；单回合不超过 2 分钟"),
    "FR": ("第9章", "L2659", "FR 比 R 每 200 米快 3 秒"),
    "H": ("第13章", "L3318", "H 与 I 同配速，但不规定距离，按时间跑"),
    "altitude": ("第8章 / 第14章", "L2397 / L3582", "2130 m：R 不变，I/T/M 每 400 米慢 4 秒"),
    "novice": ("第5章", "L1810-L1812 / 表5—3", "VDOT 20~30 的初跑者专用表"),
}


# ---------------------------------------------------------------------------
# 异常
# ---------------------------------------------------------------------------
class DanielsError(ValueError):
    """本模块所有可预期错误的基类。"""


class VdotRangeError(DanielsError):
    """VDOT 超出书中有数据的范围。"""


class AltitudeRangeError(DanielsError):
    """海拔超出书中讨论的范围。"""


# ---------------------------------------------------------------------------
# 基础方程
# ---------------------------------------------------------------------------
def vo2_of_speed(speed_m_per_min: float) -> float:
    """按跑道效率曲线求有氧需求。

    Parameters
    ----------
    speed_m_per_min : float
        速度，米/分钟。必须为正。

    Returns
    -------
    float
        每公斤体重每分钟耗氧量（ml/kg/min）。

    Raises
    ------
    DanielsError
        速度不是正数。
    """
    if not speed_m_per_min > 0:
        raise DanielsError(f"速度必须为正数，收到 {speed_m_per_min!r}")
    return _VO2_A + _VO2_B * speed_m_per_min + _VO2_C * speed_m_per_min ** 2


def pct_max(duration_min: float) -> float:
    """求某个比赛时长下能维持的 %VO2max 分数。

    Parameters
    ----------
    duration_min : float
        比赛时长，分钟。

    Returns
    -------
    float
        0~1.2 之间的分数。30 分钟约为 0.93。

    Raises
    ------
    DanielsError
        时长不是正数。
    """
    if not duration_min > 0:
        raise DanielsError(f"时长必须为正数，收到 {duration_min!r}")
    return (
        _PCT_A
        + _PCT_B * math.exp(_PCT_C * duration_min)
        + _PCT_D * math.exp(_PCT_E * duration_min)
    )


def speed_of_vo2(vo2_ml: float) -> float:
    """反解 :func:`vo2_of_speed`，返回正根。

    Parameters
    ----------
    vo2_ml : float
        耗氧量，ml/kg/min。

    Returns
    -------
    float
        速度，米/分钟。

    Raises
    ------
    DanielsError
        无正根（输入过低）。
    """
    # 解 0.000104·v^2 + 0.182258·v - (4.60 + vo2) = 0
    a, b, c = _VO2_C, _VO2_B, -(4.60 + vo2_ml)
    disc = b * b - 4 * a * c
    if disc <= 0:
        raise DanielsError(f"耗氧量 {vo2_ml!r} 无对应的正速度")
    return (-b + math.sqrt(disc)) / (2 * a)


def _check_vdot(vdot: float) -> None:
    if not isinstance(vdot, (int, float)) or isinstance(vdot, bool):
        raise DanielsError(f"VDOT 必须是数字，收到 {type(vdot).__name__}")
    if not math.isfinite(vdot):
        raise DanielsError(f"VDOT 必须是有限数，收到 {vdot!r}")
    if vdot < VDOT_MIN or vdot > VDOT_MAX:
        raise VdotRangeError(
            f"VDOT {vdot} 超出书中数据范围 [{VDOT_MIN}, {VDOT_MAX}]。"
            "20~30 见本书表 5—3，30~85 见表 5—1/5—2；"
            "《氧气的力量》另收 25.0~85.0。不要在本模块外自行外推。"
        )


def vdot_from_race(distance_m: float, time_s: float) -> float:
    """由一次比赛成绩求 VDOT。

    Parameters
    ----------
    distance_m : float
        比赛距离，米。支持 800~42195。
    time_s : float
        成绩，秒。

    Returns
    -------
    float
        VDOT 值（保留全部精度，不做四舍五入）。

    Raises
    ------
    DanielsError
        距离或成绩非法。
    """
    if not (DISTANCE_MIN_M <= distance_m <= DISTANCE_MAX_M):
        raise DanielsError(
            f"距离 {distance_m} m 超出支持范围 "
            f"[{DISTANCE_MIN_M:.0f}, {DISTANCE_MAX_M:.0f}] m"
        )
    if not time_s > 0:
        raise DanielsError(f"成绩必须为正数秒，收到 {time_s!r}")
    minutes = time_s / 60.0
    speed = distance_m / minutes
    return vo2_of_speed(speed) / pct_max(minutes)


def race_time(distance_m: float, vdot: float) -> float:
    """由 VDOT 求某个距离的等效比赛成绩（二分求解）。

    Parameters
    ----------
    distance_m : float
        距离，米。
    vdot : float
        VDOT 值。

    Returns
    -------
    float
        成绩，秒。

    Raises
    ------
    VdotRangeError
        VDOT 超范围。
    DanielsError
        距离超范围。

    Notes
    -----
    参数顺序与 :func:`vdot_from_race` 一致——**距离在前**。

    早先这里是 ``(vdot, distance_m)``，和正向函数正好相反。两个参数都是数字，
    写反了不会立刻看出问题，只会报一句「VDOT 5000 超出范围」，让人以为是公式错。
    写这个库的人自己都在探针里踩过一次，所以统一了顺序。
    """
    # 写反的专门检查：两个数都落在「另一个参数」的合法区间里，几乎肯定是反了。
    # 不查的话只会报一句「VDOT 5000 超出范围」，让人以为是公式错。
    if distance_m <= VDOT_MAX and vdot >= DISTANCE_MIN_M:
        raise DanielsError(
            f"参数顺序像是写反了：收到 distance_m={distance_m}、vdot={vdot}。"
            "正确顺序是 (距离米, VDOT)，例如 race_time(5000.0, 35.0)"
        )
    _check_vdot(vdot)
    if not (DISTANCE_MIN_M <= distance_m <= DISTANCE_MAX_M):
        raise DanielsError(
            f"距离 {distance_m} m 超出支持范围 "
            f"[{DISTANCE_MIN_M:.0f}, {DISTANCE_MAX_M:.0f}] m"
        )
    lo, hi = 30.0, 28800.0
    for _ in range(200):
        mid = (lo + hi) / 2.0
        if vdot_from_race(distance_m, mid) > vdot:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2.0


# ---------------------------------------------------------------------------
# 配速值对象
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Pace:
    """一个配速。内部统一用「秒/公里」保存，对外提供多种单位。"""

    seconds_per_km: float

    def __post_init__(self) -> None:
        if not self.seconds_per_km > 0:
            raise DanielsError(f"配速必须为正数，收到 {self.seconds_per_km!r}")

    # -- 单位换算 ---------------------------------------------------------
    @property
    def seconds_per_400m(self) -> float:
        """每 400 米用时（秒）。"""
        return self.seconds_per_km * 0.4

    @property
    def seconds_per_mile(self) -> float:
        """每英里用时（秒）。"""
        return self.seconds_per_km * METER_PER_MILE / 1000.0

    @property
    def meters_per_minute(self) -> float:
        """速度，米/分钟。"""
        return 60000.0 / self.seconds_per_km

    @property
    def kph(self) -> float:
        """速度，公里/小时。"""
        return 3600.0 / self.seconds_per_km

    @property
    def mph(self) -> float:
        """速度，英里/小时。"""
        return self.kph / 1.609344

    # -- 派生 -------------------------------------------------------------
    def plus_seconds_per_400m(self, delta: float) -> "Pace":
        """返回每 400 米慢 ``delta`` 秒后的新配速。"""
        return Pace(self.seconds_per_km + delta / 0.4)

    def time_for(self, meters: float) -> float:
        """按本配速跑完指定距离所需时间（秒）。"""
        if not meters > 0:
            raise DanielsError(f"距离必须为正数，收到 {meters!r}")
        return self.seconds_per_km * meters / 1000.0

    def distance_in(self, duration_s: float) -> float:
        """按本配速跑指定时间能跑多远（米）。"""
        if not duration_s > 0:
            raise DanielsError(f"时长必须为正数，收到 {duration_s!r}")
        return duration_s / self.seconds_per_km * 1000.0

    def format_km(self) -> str:
        """格式化为 ``m:ss`` 每公里。"""
        return format_time(self.seconds_per_km)

    def format_400m(self) -> str:
        """格式化为 ``m:ss`` 每 400 米。"""
        return format_time(self.seconds_per_400m)

    def format_400m_ceil(self) -> str:
        """按书中表格的习惯，把每 400 米用时向上取整到整秒。"""
        return format_time(math.ceil(self.seconds_per_400m - 1e-9))

    def format_mile(self) -> str:
        """格式化为 ``m:ss`` 每英里。"""
        return format_time(self.seconds_per_mile)


@dataclass(frozen=True)
class AltitudeCorrection:
    """一次海拔修正的结果。"""

    altitude_m: float
    factor: float
    """相对 2130 m 罚时的比例系数（0~1 为内插，>1 为外推）。"""
    penalty_s_per_400m: float
    """I/T/M 在该海拔下每 400 米应加上的秒数。"""
    extrapolated: bool
    """是否已超出书中 2130 m 的参照点。"""


@dataclass(frozen=True)
class NoviceRow:
    """表 5—3 的整行原值，供 VDOT 20~30 的跑者直接照书执行。

    引擎默认值（马拉松等时 / 98% vVO2max）在低 VDOT 区与书里的印刷值
    最多差 3.5%，因为表 5—3 的 I 列是按 R 加 7~8 秒/400 m 排的，
    不是按 98% vVO2max 算的。对初跑者来说，书上的值更保守、更安全，
    所以两种都给，由调用方决定。
    """

    vdot: float
    m: Pace
    t: Pace
    i: Pace
    r: Pace


@dataclass(frozen=True)
class PaceSet:
    """一个 VDOT 对应的全部训练配速。"""

    vdot: float
    e_fast: Pace
    e_slow: Pace
    m: Pace
    t: Pace
    i: Pace
    r: Pace
    fr: Pace
    h: Pace
    altitude: AltitudeCorrection
    novice: bool
    novice_row: NoviceRow | None = None

    # -- 诊断 -------------------------------------------------------------
    @property
    def step_i_minus_r_s_per_400m(self) -> float:
        """I 比 R 每 400 米慢多少秒。

        书中称「6 秒规则」，但同一段（L1804）也说明：VDOT 50 左右是 7 秒，
        VDOT 40 左右是 8 秒。本属性给出实际值，不做四舍五入。
        """
        return self.i.seconds_per_400m - self.r.seconds_per_400m

    @property
    def step_t_minus_i_s_per_400m(self) -> float:
        """T 比 I 每 400 米慢多少秒。"""
        return self.t.seconds_per_400m - self.i.seconds_per_400m

    def as_dict(self) -> Dict[str, object]:
        """导出为可序列化的字典，便于写进规则命中记录或 API 响应。

        每个键都带单位后缀，因为书中不同强度习惯用不同距离表述
        （E/M/T 讲每公里，T/I/R 讲每 400 米，R/FR 讲每 200 米）。
        所有时间值四舍五入到整秒。
        """
        return {
            "vdot": round(self.vdot, 2),
            "E_per_km": [_fmt_round(self.e_fast.seconds_per_km),
                         _fmt_round(self.e_slow.seconds_per_km)],
            "M_per_km": _fmt_round(self.m.seconds_per_km),
            "T_per_km": _fmt_round(self.t.seconds_per_km),
            "T_per_400m": _fmt_round(self.t.seconds_per_400m),
            "I_per_km": _fmt_round(self.i.seconds_per_km),
            "I_per_400m": _fmt_round(self.i.seconds_per_400m),
            "R_per_400m": _fmt_round(self.r.seconds_per_400m),
            "R_per_200m": _fmt_round(self.r.seconds_per_400m / 2.0),
            "FR_per_200m": _fmt_round(self.fr.seconds_per_400m / 2.0),
            "H_per_km": _fmt_round(self.h.seconds_per_km),
            "step_I_minus_R_s_per_400m": round(
                self.step_i_minus_r_s_per_400m, 2
            ),
            "step_T_minus_I_s_per_400m": round(
                self.step_t_minus_i_s_per_400m, 2
            ),
            "altitude_m": round(self.altitude.altitude_m, 0),
            "altitude_penalty_s_per_400m": round(
                self.altitude.penalty_s_per_400m, 2
            ),
            "altitude_extrapolated": self.altitude.extrapolated,
            "novice": self.novice,
            "novice_M_per_km": (
                _fmt_round(self.novice_row.m.seconds_per_km)
                if self.novice_row is not None
                else None
            ),
            "novice_T_per_km": (
                _fmt_round(self.novice_row.t.seconds_per_km)
                if self.novice_row is not None
                else None
            ),
            "novice_I_per_400m": (
                _fmt_round(self.novice_row.i.seconds_per_400m)
                if self.novice_row is not None
                else None
            ),
            "novice_R_per_200m": (
                _fmt_round(self.novice_row.r.seconds_per_400m / 2.0)
                if self.novice_row is not None
                else None
            ),
        }


# ---------------------------------------------------------------------------
# 海拔
# ---------------------------------------------------------------------------
def altitude_correction(altitude_m: float) -> AltitudeCorrection:
    """计算海拔对配速的修正。

    模型来自书中三句话的联立（不是外推）：

    1. 第 8 章 L2341：「真正的问卷直到大约海拔 914 米时才会出现」
       → 914 m 以下不修正。
    2. 第 14 章 L3582：2130 m 时 I/T/M 各比海平面每 400 米慢 4 秒，R 不变。
    3. 第 8 章 L2341：「2130 米的高度带来的压力几乎是 1524 米的两倍」
       → 914~2130 m 之间按线性内插。这个内插在 1524 m 处恰好给出
       2130 m 罚时的一半（610/1216 = 0.5017），与第 3 句自洽。

    2130 m 以上书中未给数据，按同一斜率延续但标记 ``extrapolated=True``；
    超过 2500 m 直接报错。

    Raises
    ------
    AltitudeRangeError
        海拔为负或超过 2500 m。
    """
    if not isinstance(altitude_m, (int, float)) or not math.isfinite(altitude_m):
        raise AltitudeRangeError(f"海拔必须是有限数字，收到 {altitude_m!r}")
    if altitude_m < 0:
        raise AltitudeRangeError(f"海拔不能为负，收到 {altitude_m}")
    if altitude_m > ALT_MAX_M:
        raise AltitudeRangeError(
            f"海拔 {altitude_m} m 超出书中讨论范围（上限 {ALT_MAX_M:.0f} m）。"
            "第 8 章称 1200~2500 m 为「中等高度」，更高海拔无数据可依。"
        )
    if altitude_m <= ALT_NEGLIGIBLE_M:
        factor = 0.0
    else:
        factor = (altitude_m - ALT_NEGLIGIBLE_M) / (
            ALT_REFERENCE_M - ALT_NEGLIGIBLE_M
        )
    return AltitudeCorrection(
        altitude_m=float(altitude_m),
        factor=factor,
        penalty_s_per_400m=factor * ALT_PENALTY_S_PER_400M,
        extrapolated=altitude_m > ALT_REFERENCE_M,
    )


# ---------------------------------------------------------------------------
# 表 5—3（初跑者表，VDOT 20~30）
# ---------------------------------------------------------------------------
#: 由 epub 图片 00053.jpeg 恢复的 11 行数据，单位为秒。
#:
#: 每行 = (VDOT, M 秒/公里, T 秒/公里, I 秒/400 m, R 秒/200 m)。
#: 交叉校验：VDOT 28 一行与书中正文 L1812 的「7:27 / 12:02 / 5:15」逐字一致。
#: 不确定项：VDOT 26 的 T 列 OCR 被截断，按等差补为 7:08（428 秒）。
TABLE5_3: Tuple[Tuple[float, float, float, float, float], ...] = (
    (30.0, 423.0, 384.0, 144.0, 68.0),
    (29.0, 435.0, 394.0, 148.0, 70.0),
    (28.0, 447.0, 405.0, 154.0, 73.0),
    (27.0, 461.0, 416.0, 158.0, 75.0),
    (26.0, 476.0, 428.0, 164.0, 78.0),
    (25.0, 490.0, 441.0, 168.0, 81.0),
    (24.0, 506.0, 455.0, 175.0, 84.0),
    (23.0, 523.0, 470.0, 181.0, 87.0),
    (22.0, 539.0, 486.0, 187.0, 90.0),
    (21.0, 556.0, 503.0, 193.0, 93.0),
    (20.0, 574.0, 521.0, 201.0, 97.0),
)


def _interp_column(vdot: float, column: int) -> float:
    """在 :data:`TABLE5_3` 的某一列上做线性插值，超出 20~30 时钳制到端点。"""
    lo = TABLE5_3[-1]  # VDOT 20
    hi = TABLE5_3[0]  # VDOT 30
    if vdot <= lo[0]:
        return lo[column]
    if vdot >= hi[0]:
        return hi[column]
    for i in range(len(TABLE5_3) - 1):
        a = TABLE5_3[i]
        b = TABLE5_3[i + 1]
        if b[0] <= vdot <= a[0]:
            ratio = (vdot - b[0]) / (a[0] - b[0])
            return b[column] + ratio * (a[column] - b[column])
    raise DanielsError(f"表 5—3 插值失败：VDOT {vdot}")  # pragma: no cover


def _novice_row(vdot: float) -> NoviceRow:
    """取表 5—3 的整行（四档），列单位换算成统一的 Pace 对象。"""
    return NoviceRow(
        vdot=float(vdot),
        m=Pace(_interp_column(vdot, 1)),
        t=Pace(_interp_column(vdot, 2)),
        i=Pace(_interp_column(vdot, 3) / 0.4),
        r=Pace(_interp_column(vdot, 4) / 0.2),
    )


# ---------------------------------------------------------------------------
# 主入口
# ---------------------------------------------------------------------------
def pace_set(vdot: float, altitude_m: float = 0.0) -> PaceSet:
    """给出一个 VDOT 对应的五档配速（外加 FR 与 H）。

    Parameters
    ----------
    vdot : float
        VDOT 值，20~85。
    altitude_m : float, optional
        训练地海拔（米），默认 0。见 :func:`altitude_correction`。

    Returns
    -------
    PaceSet
        含 E 区间、M、T、I、R、FR、H，以及低 VDOT 的对照 M 配速。

    Raises
    ------
    VdotRangeError
        VDOT 超范围。
    AltitudeRangeError
        海拔超范围。

    Notes
    -----
    * E 由「1 英里比赛配速 + 75~113 秒/公里」得到区间，不是单点。
    * T 取 VDOT 的 88%（VO2 口径），对应表 5—4 的 85%~90%。
    * I 取 98% vVO2max，对应表 5—4「达到或者非常接近 VO2max」。
    * R 取 1 英里比赛配速，对应第 4 章 L1806 的定义。
    * FR = R 每 200 m 快 3 秒；H 与 I 同配速，但不规定距离。
    """
    _check_vdot(vdot)
    corr = altitude_correction(altitude_m)
    penalty_per_km = corr.penalty_s_per_400m / 0.4

    mile_time = race_time(METER_PER_MILE, vdot)
    mile_pace_s_per_km = mile_time / METER_PER_MILE * 1000.0

    # E 区间。用「1 英里配速 + 75~113 秒」作主轴，但低 VDOT 时这条式子会
    # 算出比 M 还快的 E（VDOT 20 时 E 快端 9:17，而 M 是 9:34），属于倒挂。
    # 因此用 E 区上沿（VDOT 的 74%）兜底，并保证区间不塌缩。
    e_top_by_zone = 60000.0 / speed_of_vo2(vdot * _E_ZONE_TOP)
    e_fast_s = max(
        mile_pace_s_per_km + _E_OFFSET_FAST_S_PER_KM, e_top_by_zone
    )
    e_slow_s = max(
        mile_pace_s_per_km + _E_OFFSET_SLOW_S_PER_KM,
        e_fast_s + _E_MIN_WIDTH_S_PER_KM,
    )
    e_fast = Pace(e_fast_s)
    e_slow = Pace(e_slow_s)

    # M：让 42.195 km 的等效成绩正好等于该 VDOT
    m_pace = Pace(race_time(42195.0, vdot) / 42.195)

    t_pace = Pace(60000.0 / speed_of_vo2(vdot * _K_T))
    i_pace = Pace(60000.0 / (speed_of_vo2(vdot) * _K_I))
    r_pace = Pace(mile_pace_s_per_km)

    # FR 比 R 每 200 米快 3 秒，即每 400 米快 6 秒
    fr_pace = r_pace.plus_seconds_per_400m(-_FR_OFFSET_S_PER_200M * 2.0)

    # 海拔：R 与 E 不修正；I/T/M 按每 400 米罚时上调
    def _shift(p: Pace) -> Pace:
        return Pace(p.seconds_per_km + penalty_per_km)

    novice = vdot <= VDOT_NOVICE_UPPER
    return PaceSet(
        vdot=float(vdot),
        e_fast=e_fast,
        e_slow=e_slow,
        m=_shift(m_pace),
        t=_shift(t_pace),
        i=_shift(i_pace),
        r=r_pace,
        fr=fr_pace,
        h=_shift(i_pace),
        altitude=corr,
        novice=novice,
        novice_row=_novice_row(vdot) if novice else None,
    )


def h_time_cap(weekly_km: float, five_k_time_s: float, ten_k_time_s: float) -> float:
    """H（艰苦）跑单次训练的时间上限，单位秒。

    第 13 章 L3318：单次训练中以 H 配速跑的总时间，应控制在
    「10 公里时间」与「完成周跑量 8% 所需时间」两者的较小值上，
    两者都按当前的 5 公里比赛配速折算。

    书中算例：周跑量 80 km、5 km 18:45 → 8% 为 6.4 km → 6.4 × 3:45 = 24 分钟。

    Parameters
    ----------
    weekly_km : float
        周跑量，公里。
    five_k_time_s : float
        当前 5 公里比赛成绩，秒。
    ten_k_time_s : float
        当前 10 公里比赛成绩，秒。

    Returns
    -------
    float
        上限，秒。

    Raises
    ------
    DanielsError
        任一参数非正。
    """
    for name, value in (
        ("weekly_km", weekly_km),
        ("five_k_time_s", five_k_time_s),
        ("ten_k_time_s", ten_k_time_s),
    ):
        if not value > 0:
            raise DanielsError(f"{name} 必须为正数，收到 {value!r}")
    five_k_pace_s_per_km = five_k_time_s / 5.0
    cap_by_volume = weekly_km * 0.08 * five_k_pace_s_per_km
    return min(ten_k_time_s, cap_by_volume)


# ---------------------------------------------------------------------------
# 时间格式化
# ---------------------------------------------------------------------------
def format_time(total_seconds: float) -> str:
    """把秒格式化成 ``m:ss`` 或 ``h:mm:ss``。

    Examples
    --------
    >>> format_time(267)
    '4:27'
    >>> format_time(3725)
    '1:02:05'
    """
    if not math.isfinite(total_seconds) or total_seconds < 0:
        raise DanielsError(f"时间必须是非负有限数，收到 {total_seconds!r}")
    total = int(round(total_seconds))
    hours, rem = divmod(total, 3600)
    minutes, seconds = divmod(rem, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    return f"{minutes}:{seconds:02d}"


def _fmt_round(seconds: float) -> str:
    """四舍五入到整秒后格式化。

    书中表 5—2 的 T 列是四舍五入（100.46 → 1:40），R 列却像进位
    （85.4 → 1:26），两列规则并不一致。本模块不去复现这种不一致，
    统一按最接近的整秒输出；需要按书中习惯进位时用 ``Pace.format_400m_ceil``。
    """
    return format_time(math.floor(seconds + 0.5))


def parse_time(text: str) -> float:
    """把 ``5:44`` / ``1:02:05`` 解析成秒。

    Raises
    ------
    DanielsError
        格式无法识别。
    """
    if not isinstance(text, str):
        raise DanielsError(f"需要字符串，收到 {type(text).__name__}")
    parts = text.strip().replace("：", ":").split(":")
    if not 1 <= len(parts) <= 3 or any(p.strip() == "" for p in parts):
        raise DanielsError(f"无法解析时间：{text!r}")
    try:
        numbers = [float(p) for p in parts]
    except ValueError as exc:
        raise DanielsError(f"无法解析时间：{text!r}") from exc
    if any(n < 0 for n in numbers):
        raise DanielsError(f"时间不能为负：{text!r}")
    total = 0.0
    for n in numbers:
        total = total * 60.0 + n
    return total
