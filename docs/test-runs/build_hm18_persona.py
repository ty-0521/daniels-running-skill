# -*- coding: utf-8 -*-
"""18 周半马计划（虚拟人物演示）生成与整表审计。

人物数据为本演示虚构；脚本里每个配速、上限、周数都由 daniels 函数算出，
不手算。跑完打印 audit 报告，并写出 plan_hm18_persona.json 供 CLI 复核。
"""
import datetime
import json
import sys
from pathlib import Path

# 仓库根目录：docs/test-runs/<本文件> -> 上三层
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
import daniels as d

# ---------------------------------------------------------------------------
# 1. 接诊：虚拟人物的具体数据（逐层录入，红线明确为无）
# ---------------------------------------------------------------------------
state = (
    d.IntakeState()
    .set("goal_distance_km", 21.1)
    .set("race_date", "2027-03-21")
    .set("red_flags", ())
    .set("recent_result", (10000.0, d.parse_time("43:00")))
    .set("weekly_km", 30.0)
    .set("longest_recent_km", 10.0)
    .set("days_per_week", 4)
    .set("surface", "road")
    .set("altitude_m", 0.0)
)
status = state.status()
print(state.brief())
assert status.code == "ready", f"接诊未就绪：{status.code} {status.questions}"

VDOT = d.vdot_from_race(10000.0, d.parse_time("43:00"))
PACES = d.pace_set(VDOT)
HM_SEC = d.race_time(21097.5, VDOT)
print(f"\nVDOT = {VDOT:.2f}")
print("配速表：", PACES.as_dict())
print(f"等效半马成绩：{d.format_time(HM_SEC)}")

# ---------------------------------------------------------------------------
# 2. 日历与阶段（18 周不在书内记录，显式允许推导，documented=False）
# ---------------------------------------------------------------------------
TODAY = datetime.date(2026, 11, 13)
RACE = state.race_date
start, end = d.plan_window(18, RACE)
print(f"\n18 周窗口：{start} ~ {end}")
sch = d.plan_schedule(18, allow_undocumented=True)
print("阶段划分：", sch.as_dict())

# ---------------------------------------------------------------------------
# 3. 逐周安排
#    每周 4 跑：周二质量课、周四 E、周六 E、周日长跑。
#    sessions 只登记 L 与质量课；E 跑用 weekly_km 体现。
#    part_km 为逐次实际距离，合计必须等于 weekly_km。
# ---------------------------------------------------------------------------
# 每档：周跑量, 长跑 L, 周二质量(强度, 距离), 周二总距离, 周四, 周六
LEVELS = {
    "p1": dict(weekly=30.0, L=8.0, quality=None, tue=7.0, thu=7.0, sat=8.0),
    "p2": dict(weekly=36.0, L=10.0, quality=("R", 1.6), tue=8.0, thu=9.0, sat=9.0),
    "p3": dict(weekly=42.0, L=12.0, quality=("I", 3.2), tue=9.0, thu=10.5, sat=10.5),
    "p4": dict(weekly=48.0, L=13.5, quality=("T", 4.8), tue=10.5, thu=12.0, sat=12.0),
}
PHASE_OF_WEEK = {w: sch.phase_of_week(w) for w in range(1, 19)}
LEVEL_BY_PHASE = {1: "p1", 2: "p2", 3: "p3", 4: "p4"}

weeks = []
rows = []
for w in range(1, 19):
    d0 = start + datetime.timedelta(days=7 * (w - 1))
    d1 = d0 + datetime.timedelta(days=6)
    taper = d.week_taper(w, 18, race_week=18)

    if w == 18:  # 比赛周
        weekly, L, race = 28.1, None, 21.1
        parts = (3.5, 3.5, 21.1)
        sessions = ()
    elif w == 16:  # 赛前 2 周：减量，长跑中段插 M
        weekly, L, race = 38.4, 10.5, None
        parts = (10.5, 9.3, 9.3, 9.3)
        sessions = (d.Session("L", L), d.Session("M", 6.0))
    elif w == 17:  # 赛前 1 周：L ≤ 90 分钟
        weekly, L, race = 34.0, 9.0, None
        parts = (9.0, 8.3, 8.3, 8.4)
        sessions = (d.Session("L", L),)
    else:
        lv = LEVELS[LEVEL_BY_PHASE[PHASE_OF_WEEK[w]]]
        weekly, L = lv["weekly"], lv["L"]
        race = None
        parts = (L, lv["tue"], lv["thu"], lv["sat"])
        sessions = [d.Session("L", L)]
        if lv["quality"]:
            sessions.append(d.Session(*lv["quality"]))
        sessions = tuple(sessions)

    weeks.append(
        d.WeekEntry(
            week=w,
            weekly_km=weekly,
            sessions=sessions,
            race_km=race,
            part_km=parts,
        )
    )
    rows.append((w, d0, d1, weekly, L, race, sessions, taper))

# ---------------------------------------------------------------------------
# 4. 整表裁决
# ---------------------------------------------------------------------------
result = d.audit_plan(
    weeks,
    sessions_per_week=4,
    base_source="user",
    paces=PACES,
    surface="road",
    every_weeks=4,
)
print("\n===== 整表审计 =====")
print(result.report())
print("\npassed =", result.passed)

# ---------------------------------------------------------------------------
# 5. 写出 JSON（CLI 可复核：python daniels_cli.py audit <json>）
# ---------------------------------------------------------------------------
payload = {
    "sessions_per_week": 4,
    "base_source": "user",
    "every_weeks": 4,
    "weeks": [
        {
            "week": wk.week,
            "weekly_km": round(wk.weekly_km, 2),
            "sessions": [[s.intensity, round(s.km, 2)] for s in wk.sessions],
            "part_km": [round(x, 2) for x in wk.part_km],
            **({"race_km": wk.race_km} if wk.race_km is not None else {}),
        }
        for wk in weeks
    ],
}
out = ROOT / "docs" / "test-runs" / "plan_hm18_persona.json"
out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
print("\nJSON 已写出：", out)

# 逐周速览
print("\n===== 逐周速览 =====")
for w, d0, d1, weekly, L, race, sessions, taper in rows:
    q = "+".join(f"{s.intensity}{s.km:g}" for s in sessions if s.intensity != "L") or "—"
    print(f"  第{w:2d}周 {d0}~{d1}  {weekly:5.1f}  L={str(L):>5}  质量={q}  减量={taper.is_taper_week}")
