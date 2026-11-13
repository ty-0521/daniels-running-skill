# -*- coding: utf-8 -*-
"""20 周半马周表 v3：全部约束一起满足，送整表裁决。"""
import sys, datetime
from pathlib import Path
import sys

# 仓库根目录：docs/test-runs/<本文件> -> 上三层。别写死本机路径。
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
import daniels as d

# 每档：(周跑量, 长跑, 两次轻松跑, 第三次轻松跑)
LEVELS = [
    (20.0, 6.0, 4.7, 4.6),
    (26.2, 7.6, 6.2, 6.2),
    (32.3, 9.2, 7.7, 7.7),
    (38.4, 10.8, 9.2, 9.2),
    (44.5, 12.4, 10.7, 10.7),
    (50.6, 14.0, 12.2, 12.2),
]
STEP_AT = {4: 1, 7: 2, 10: 3, 13: 4, 16: 5}
QUALITY = {5: ("R", 1.2), 6: ("R", 1.2), 7: ("R", 1.6), 8: ("R", 1.6), 9: ("R", 1.6),
           10: ("R", 1.8),
           11: ("I", 3.0), 12: ("I", 3.0), 13: ("I", 3.2), 14: ("I", 3.2),
           15: ("I", 3.2), 16: ("I", 3.6), 17: ("T", 5.0)}
TAPER = {18: (33.7, 10.0, 7.9, 7.9), 19: (25.3, 7.5, 5.9, 6.0)}

import datetime

# 起点由 plan_window 推，不手写。写死的话，换一个比赛日整张表就静默错位。
import daniels as _d

RACE = datetime.date(2027, 4, 18)
START = _d.plan_window(20, RACE)[0]


def level_of(w):
    lv = 0
    for k, v in STEP_AT.items():
        if w >= k:
            lv = v
    return lv


rows, weeks = [], []
for wk in range(1, 21):
    if wk == 20:
        total, L, e1, e2 = 28.1, None, 3.5, 3.5
        parts = (3.5, 3.5, 21.1)
        sessions = (d.Session("L", 21.1),)
        race = 21.1
    elif wk in TAPER:
        total, L, e1, e2 = TAPER[wk]
        e3 = round(total - L - e1 - e2, 1)
        parts = (L, e1, e2, e3)
        sessions = (d.Session("L", L),)
        race = None
        e3 = e3
    else:
        total, L, e1, e2 = LEVELS[level_of(wk)]
        e3 = round(total - L - e1 - e2, 1)
        parts = (L, e1, e2, e3)
        sessions = (d.Session("L", L),)
        race = None
    if wk in QUALITY:
        k, km = QUALITY[wk]
        sessions = sessions + (d.Session(k, km),)
    weeks.append(d.WeekEntry(week=wk, weekly_km=total, sessions=sessions,
                             race_km=race, part_km=parts))
    d0 = START + datetime.timedelta(days=7 * (wk - 1))
    d1 = d0 + datetime.timedelta(days=6)
    rows.append((wk, d0, d1, total, L, e1, e2, e3, QUALITY.get(wk)))

res = d.audit_plan(weeks, sessions_per_week=4, base_source="user", every_weeks=3,
                   paces=d.pace_set(d.vdot_from_race(5000, 32 * 60)))
print("passed =", res.passed)
print(res.report())
print()
for wk, d0, d1, total, L, e1, e2, e3, q in rows:
    print(f"  w{wk:>2} {d0}~{d1}  {total:>5.1f}  L {str(L):>5}  E {e1}/{e2}/{e3}  Q {q}")
