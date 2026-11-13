# -*- coding: utf-8 -*-
"""独立校验器：核验 daniels 包的数值输出。

这个脚本**故意不复用** :mod:`daniels` 的方程，而是自己写一遍
Daniels–Gilbert 回归式，然后：

1. 比对独立实现与包内实现的结果（同一套公式，两份代码）；
2. 比对包内输出与书中可直接读到的数值（真值来自正文与附录）。

任何一个 FAIL 都会让脚本以退出码 1 结束，便于接进 CI 或提交前钩子。

运行：
    python pace_audit.py
"""

from __future__ import annotations

import math
import sys
from typing import List, Tuple

import daniels
from daniels import dose, periodize

# ---------------------------------------------------------------------------
# 独立实现（不 import 包内方程）
# ---------------------------------------------------------------------------
A, B, C = 0.000104, 0.182258, -4.60
P0, P1, P2, P3 = 0.8, 0.1894393, -0.012778, 0.2989558
Q1 = -0.1932605
MILE = 1609.344


def ref_vo2(v: float) -> float:
    return C + B * v + A * v * v


def ref_pct(t_min: float) -> float:
    return P0 + P1 * math.exp(P2 * t_min) + P3 * math.exp(Q1 * t_min)


def ref_vdot(distance_m: float, seconds: float) -> float:
    minutes = seconds / 60.0
    return ref_vo2(distance_m / minutes) / ref_pct(minutes)


def ref_speed(vo2: float) -> float:
    """解 A·v^2 + B·v - (4.60 + vo2) = 0 的正根。"""
    return (-B + math.sqrt(B * B + 4 * A * (4.60 + vo2))) / (2 * A)


def ref_time(distance_m: float, target: float) -> float:
    lo, hi = 30.0, 28800.0
    for _ in range(200):
        mid = (lo + hi) / 2
        if ref_vdot(distance_m, mid) > target:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


# ---------------------------------------------------------------------------
# 检查框架
# ---------------------------------------------------------------------------
RESULTS: List[Tuple[bool, str, str]] = []


def check(ok: bool, label: str, detail: str) -> None:
    RESULTS.append((ok, label, detail))


def close(actual: float, expected: float, tol: float) -> bool:
    return abs(actual - expected) <= tol


def rel(actual: float, expected: float) -> float:
    return abs(actual - expected) / abs(expected) * 100.0


def section(title: str) -> None:
    print()
    print("=" * 78)
    print(title)
    print("=" * 78)


# ---------------------------------------------------------------------------
# 1. 独立实现 vs 包内实现
# ---------------------------------------------------------------------------
section("1. 方程层：独立实现 vs 包内实现")

max_vo2_diff = 0.0
for v in range(100, 401, 5):
    max_vo2_diff = max(
        max_vo2_diff, abs(ref_vo2(float(v)) - daniels.vo2_of_speed(float(v)))
    )
check(close(max_vo2_diff, 0.0, 1e-9), "VO2 方程一致", f"最大差 {max_vo2_diff:.3e}")

max_pct_diff = 0.0
for t in range(3, 400):
    max_pct_diff = max(
        max_pct_diff, abs(ref_pct(float(t)) - daniels.pct_max(float(t)))
    )
check(close(max_pct_diff, 0.0, 1e-12), "%VO2max 曲线一致", f"最大差 {max_pct_diff:.3e}")

max_speed_diff = 0.0
for target in range(15, 86):
    max_speed_diff = max(
        max_speed_diff,
        abs(ref_speed(float(target)) - daniels.speed_of_vo2(float(target))),
    )
check(close(max_speed_diff, 0.0, 1e-6), "反解速度一致", f"最大差 {max_speed_diff:.3e}")

max_vdot_diff = 0.0
for distance in (800.0, 1600.0, 5000.0, 10000.0, 42195.0):
    for seconds in (150.0, 300.0, 600.0, 1200.0, 2400.0):
        max_vdot_diff = max(
            max_vdot_diff,
            abs(
                ref_vdot(distance, seconds)
                - daniels.vdot_from_race(distance, seconds)
            ),
        )
check(close(max_vdot_diff, 0.0, 1e-9), "VDOT 正算一致", f"最大差 {max_vdot_diff:.3e}")

# ---------------------------------------------------------------------------
# 2. 附录 D 的四个 VDOT 分界
# ---------------------------------------------------------------------------
section("2. 附录 D 的分界值（1600 m）")

APPENDIX_D = [(280.0, 63.8), (320.0, 54.8), (321.0, 54.7), (372.0, 46.3)]
worst = 0.0
for seconds, expected in APPENDIX_D:
    got = daniels.vdot_from_race(1600.0, seconds)
    worst = max(worst, abs(got - expected))
    check(
        close(got, expected, 0.10),
        f"1600 m {daniels.format_time(seconds)}",
        f"{got:.3f} 对 {expected}，差 {got - expected:+.3f}",
    )
check(close(worst, 0.0, 0.10), "附录 D 整体偏差", f"最大 {worst:.3f} 个 VDOT")

# ---------------------------------------------------------------------------
# 3. 第 3 章的两个 5 km 对应点与 93% 曲线
# ---------------------------------------------------------------------------
section("3. 第 3 章的三个数值")

for seconds, expected in ((1196.0, 50.0), (1022.0, 60.0)):
    got = daniels.vdot_from_race(5000.0, seconds)
    check(
        close(got, expected, 0.15),
        f"5 km {daniels.format_time(seconds)}",
        f"{got:.3f} 对 {expected}",
    )
check(
    close(daniels.pct_max(30.0), 0.93, 0.004),
    "%max(30 分钟)",
    f"{daniels.pct_max(30.0):.4f} 对 0.93",
)

# ---------------------------------------------------------------------------
# 4. 表 5—1 / 5—2 的 VDOT 51 与 60
# ---------------------------------------------------------------------------
section("4. 表 5—1 / 5—2（VDOT 51 与 60）")

ps51 = daniels.pace_set(51.0)
BOOK_51 = [
    ("E 快", 292.0, ps51.e_fast.seconds_per_km, 1.5),
    ("E 慢", 329.0, ps51.e_slow.seconds_per_km, 1.5),
    ("M", 267.0, ps51.m.seconds_per_km, 0.6),
    ("T", 251.0, ps51.t.seconds_per_km, 0.5),
    ("I", 231.0, ps51.i.seconds_per_km, 0.5),
    ("R", 215.0, ps51.r.seconds_per_km, 1.0),
]
for name, expected, actual, tol_pct in BOOK_51:
    err = rel(actual, expected)
    check(err <= tol_pct, f"VDOT 51 {name}", f"{err:.2f}% ≤ {tol_pct}%")

check(
    close(daniels.race_time(MILE, 51.0), 344.0, 2.0),
    "VDOT 51 ↔ 1 英里 5:44",
    f"{daniels.format_time(daniels.race_time(MILE, 51.0))}",
)
check(
    close(daniels.race_time(MILE, 60.0), 297.0, 2.0),
    "VDOT 60 ↔ 1 英里 4:57",
    f"{daniels.format_time(daniels.race_time(MILE, 60.0))}",
)

ps60 = daniels.pace_set(60.0)
for name, expected, actual in (
    ("T", 88.0, ps60.t.seconds_per_400m),
    ("I", 81.0, ps60.i.seconds_per_400m),
    ("R", 75.0, ps60.r.seconds_per_400m),
):
    check(
        close(actual, expected, 1.6),
        f"VDOT 60 {name} /400 m",
        f"{actual:.1f} 对 {expected}",
    )

# ---------------------------------------------------------------------------
# 5. 表 5—3（VDOT 20~30）
# ---------------------------------------------------------------------------
section("5. 表 5—3（11 行，VDOT 20~30）")

worst_t = worst_r = worst_i = 0.0
for row in daniels.TABLE5_3:
    vdot, _m, t_s, i_400, r_200 = row
    ps = daniels.pace_set(vdot)
    worst_t = max(worst_t, rel(ps.t.seconds_per_km, t_s))
    worst_r = max(worst_r, rel(ps.r.seconds_per_400m / 2.0, r_200))
    worst_i = max(worst_i, rel(ps.i.seconds_per_400m, i_400))

check(worst_t <= 0.9, "T 档复现", f"最大 {worst_t:.2f}%")
check(worst_r <= 1.8, "R 档复现", f"最大 {worst_r:.2f}%")
check(worst_i <= 3.8, "I 档复现（含书内不一致）", f"最大 {worst_i:.2f}%")

row28 = next(r for r in daniels.TABLE5_3 if r[0] == 28.0)
check(
    close(row28[1], 447.0, 0.01),
    "表 5—3 的 VDOT 28 行",
    f"M = {daniels.format_time(row28[1])}/km（书中 7:27）",
)

# ---------------------------------------------------------------------------
# 6. 剂量上限的书内算例
# ---------------------------------------------------------------------------
section("6. 剂量上限的算例")

check(
    close(dose.interval_cap(48.0).max_km, 3.84, 1e-9),
    "48 km → I 3.84 km",
    "第12章 L3152",
)
check(
    close(dose.interval_cap(96.0).max_km, 7.68, 1e-9),
    "96 km → I 7.68 km",
    "书中把 96 印成 97，此处按 96 复现",
)
check(
    close(dose.repetition_cap(48.0).max_km, 2.4, 1e-9),
    "48 km → R 2.40 km",
    "第4章 L1583",
)
check(
    close(dose.repetition_cap(190.0).max_km, 8.0, 1e-9),
    "190 km → R 8.00 km（非 9.5）",
    "第4章 L1583",
)
check(close(dose.post_race_easy_days(10.0), 3, 0), "10 km 赛后 3 天", "第14章 L3482")
check(close(dose.post_race_easy_days(15.0), 5, 0), "15 km 赛后 5 天", "第14章 L3482")
check(
    close(dose.post_race_easy_days(21.0975), 7, 0), "半马赛后 7 天", "第14章 L3482"
)
check(
    close(dose.post_race_easy_days(42.195), 14, 0), "全马赛后 14 天", "第14章 L3482"
)
check(close(dose.post_race_easy_days(5.0), 2, 0), "5 km 赛后 2 天", "第11章 L2990")
check(close(dose.volume_step_km(5), 8.0, 1e-9), "每周 5 次 → +8 km", "第11章 L2956")
check(close(dose.volume_step_km(14), 16.0, 1e-9), "每周 14 次 → +16 km", "第11章 L2956")
check(
    close(daniels.h_time_cap(80.0, 1125.0, 2340.0), 1440.0, 1.0),
    "H 上限 24 分钟",
    "第13章 L3318",
)

# ---------------------------------------------------------------------------
# 7. 周期层的书内分配
# ---------------------------------------------------------------------------
section("7. 周期层的周数分配")

for weeks, expected in periodize.DOCUMENTED_SPLITS.items():
    got = periodize.plan_schedule(weeks).weeks
    check(got == expected, f"{weeks} 周", f"{got} 对 {expected}")

check(periodize.quality_days() == (2, 4, 7), "默认 Q 日（周一/三/六）", "第6章 L2094")
check(
    periodize.quality_days(2, race_weekday=7) == (2, 4),
    "周六比赛 → 周一和周三",
    "第10章 L2842",
)
check(
    periodize.quality_days(2, race_weekday=6) == (2, 3),
    "周五比赛 → 周一和周二",
    "第10章 L2842",
)

# ---------------------------------------------------------------------------
# 8. 海拔修正
# ---------------------------------------------------------------------------
section("8. 海拔修正")

check(
    daniels.altitude_correction(0.0).penalty_s_per_400m == 0.0,
    "海平面不修正",
    "罚时 0",
)
check(
    daniels.altitude_correction(914.0).penalty_s_per_400m == 0.0,
    "914 m 及以下不修正",
    "第8章 L2341",
)

ALT_2130 = daniels.altitude_correction(2130.0)
ALT_1524 = daniels.altitude_correction(1524.0)
check(
    close(ALT_2130.penalty_s_per_400m, 4.0, 1e-9),
    "2130 m → 4 秒/400 m",
    "第14章 L3582",
)
check(
    close(ALT_1524.penalty_s_per_400m * 2, ALT_2130.penalty_s_per_400m, 0.08),
    "1524 m 的罚时恰为 2130 m 的一半",
    "第8章 L2341「几乎是两倍」",
)
check(ALT_2130.extrapolated is False, "2130 m 不算外推", "参照高度")
check(
    daniels.altitude_correction(2400.0).extrapolated is True,
    "2400 m 标记为外推",
    "超过 2130 m",
)

try:
    daniels.altitude_correction(2501.0)
    check(False, "2501 m 应被拒绝", "却返回了结果")
except daniels.AltitudeRangeError:
    check(True, "2501 m 被拒绝", "AltitudeRangeError")

SEA = daniels.pace_set(51.0)
HIGH = daniels.pace_set(51.0, altitude_m=2130.0)
for name in ("i", "t", "m"):
    delta = getattr(HIGH, name).seconds_per_km - getattr(SEA, name).seconds_per_km
    check(
        close(delta, 10.0, 1e-9),
        f"2130 m 时 {name.upper()} 慢 10 秒/公里",
        f"{delta:.2f} 秒/公里（即 4 秒/400 m）",
    )
check(
    HIGH.r.seconds_per_km == SEA.r.seconds_per_km,
    "2130 m 时 R 配速不变",
    "第14章 L3582",
)
check(
    HIGH.e_slow.seconds_per_km == SEA.e_slow.seconds_per_km,
    "2130 m 时 E 配速不变",
    "第8章 L2379 起 E/L 跟着感觉跑",
)

# ---------------------------------------------------------------------------
# 9. 衍生档位与秒差
# ---------------------------------------------------------------------------
section("9. 衍生档位与秒差")

for vdot_value in (20.0, 51.0, 85.0):
    ps = daniels.pace_set(vdot_value)
    gap = ps.r.seconds_per_400m - ps.fr.seconds_per_400m
    check(
        close(gap, 6.0, 1e-9),
        f"VDOT {vdot_value:.0f}：FR 比 R 快 6 秒/400 m",
        "第9章 L2659（每 200 m 快 3 秒）",
    )
    check(
        close(ps.h.seconds_per_km, ps.i.seconds_per_km, 1e-9),
        f"VDOT {vdot_value:.0f}：H 与 I 同配速",
        "第13章 L3318",
    )

STEPS = [
    daniels.pace_set(float(v)).step_t_minus_i_s_per_400m for v in range(40, 81, 10)
]
check(
    all(STEPS[i] > STEPS[i + 1] for i in range(len(STEPS) - 1)),
    "T−I 秒差随 VDOT 升高而收窄",
    f"{[round(s, 2) for s in STEPS]}",
)

STEP_IR = [
    daniels.pace_set(float(v)).step_i_minus_r_s_per_400m for v in (40, 60, 80)
]
check(
    all(6.0 <= s <= 8.0 for s in STEP_IR),
    "I−R 秒差落在书中说的 6~8 秒区间",
    f"{[round(s, 2) for s in STEP_IR]}（第5章 L1804）",
)

worst_novice = 0.0
for row in daniels.TABLE5_3:
    vd, m_s, t_s, i_400, r_200 = row
    novice_row = daniels.pace_set(vd).novice_row
    if novice_row is None:
        check(False, f"VDOT {vd:.0f} 的 novice_row 缺失", "")
        continue
    for got, expected in (
        (novice_row.m.seconds_per_km, m_s),
        (novice_row.t.seconds_per_km, t_s),
        (novice_row.i.seconds_per_400m, i_400),
        (novice_row.r.seconds_per_400m / 2.0, r_200),
    ):
        worst_novice = max(worst_novice, abs(got - expected))
check(
    close(worst_novice, 0.0, 1e-6),
    "表 5—3 的四档原值逐格复现",
    f"最大差 {worst_novice:.2e} 秒",
)

# ---------------------------------------------------------------------------
# 10. 整周合规检查
# ---------------------------------------------------------------------------
section("10. 整周合规检查")

PS20 = daniels.pace_set(20.0)
slow_long = dose.check_week([dose.Session("L", 19.0)], 80.0, paces=PS20)
check(
    len(slow_long) == 1 and slow_long[0].unit == "minutes",
    "VDOT 20 跑 19 km 触发 150 分钟上限",
    f"命中 {[v.unit for v in slow_long]}",
)
check(
    dose.check_week([dose.Session("L", 12.0)], 80.0, paces=PS20) == [],
    "同一配速下 12 km 合规",
    "",
)

MANY_I = dose.check_week([dose.Session("I", 1.0)] * 3, 64.0)
check(
    any(v.unit == "sessions" for v in MANY_I),
    "一周三次 I 训练被标记",
    "第11章 L2978",
)

SHORT_T = dose.check_week([dose.Session("T", 3.0)], 64.0)
check(
    any(v.rule_ids == ("D-T-02",) for v in SHORT_T),
    "T 跑低于 4.8 km 被标记",
    "第14章 L3478",
)

PS51 = daniels.pace_set(51.0)
LONG_R = dose.check_week([dose.Session("R", 5.0)], 64.0, paces=PS51)
check(
    len(LONG_R) == 1 and close(LONG_R[0].limit, 3.2, 1e-9),
    "周跑量 64 km 时 R 上限为 3.2 km",
    "第4章 L1583",
)

# ---------------------------------------------------------------------------
# 汇总
# ---------------------------------------------------------------------------
section("汇总")

passed = sum(1 for ok, _, _ in RESULTS if ok)
failed = [(label, detail) for ok, label, detail in RESULTS if not ok]

for ok, label, detail in RESULTS:
    if not ok:
        print(f"  FAIL  {label}: {detail}")

print()
print(f"  共 {len(RESULTS)} 项检查，通过 {passed} 项，失败 {len(failed)} 项")
print()
if failed:
    print("  结果：失败")
    sys.exit(1)
print("  结果：全部通过")
