# 给 agent 的说明

这个仓库是《丹尼尔斯经典跑步训练法（第3版）》的可验证计算库。

**你不是「读文档回答问题」，你是「调用函数回答问题」。** 所有配速、上限、周数都由
`daniels/` 里的方程算出来，不是查表也不是记忆。

## 第一步：自检

```bash
python daniels_cli.py vdot 5k 20:00
```

必须输出：

```
距离 5000 m，成绩 20:00
VDOT = 49.81
```

**不是 49.81，就说明环境不对**（Python 低于 3.10、或者没有执行权限）。
停下来告诉用户，不要带着错误的假设往下做。

**如果这个环境跑不了 Python**——直接说「这个仓库需要能执行 Python 的 agent，
我这里算不了」，然后把用户转给能跑的环境。**不要凭 SKILL.md 的内容手算。**

## 五条铁律

1. **任何配速、上限、周数、日期，必须来自函数或 CLI 的输出。** 不许手算。
   写这个库的人自己手算过两次，两次都错（起点差一天、加量周数差 4~5 周）。
2. **回答里的行号必须来自 `cite`**：`python daniels_cli.py cite D-T-02`。
   不许凭记忆写「第几章 L 多少」。
3. **说「合规」之前必须跑 `audit`**，且只有 `passed=True` 才能说。
   单项检查过了不等于整表合规。
4. **缺数据就问。** 不许把「每次 35 分钟」折成公里，不许把「年底前」当成日期，
   不许把「最长跑过 8 公里」当成成绩。
5. **提到疼痛、伤病、手术、怀孕、心血管问题 → 停。** 不给任何训练量，
   建议就医。带伤训练不该由一张周表决定。

## 常用命令

```bash
# 由成绩求 VDOT 和五档配速
python daniels_cli.py vdot 5k 20:00
python daniels_cli.py paces 49.8

# 单次训练上限（三联：周跑量 × 百分比 = 上限）
python daniels_cli.py cap 64 T

# 比赛日 → 能排哪些长度、从哪天开
python daniels_cli.py calendar --race 2027-04-18

# 整表裁决（不合规退出码 2）
python daniels_cli.py audit plan.json

# 出处
python daniels_cli.py cite D-T-02
```

Python 里也可以直接用：

```python
import daniels as d
d.vdot_from_race(5000, 1200)      # 49.81
d.pace_set(49.8)                  # 五档 + FR + H

# 整表裁决：自己搭 WeekEntry 列表
weeks = [
    d.WeekEntry(week=i, weekly_km=30.0, sessions=(d.Session("L", 9.0),))
    for i in (1, 2)
]
d.audit_plan(weeks, sessions_per_week=4).passed   # True
```

## 更细的行为准则

**见 `SKILL.md`** —— 里面有接诊顺序、术语表、13 条踩过的坑、以及每一条规则背后的实测记录。

## 校验它没坏

```bash
python -m unittest discover -s tests -t .   # 会打印 Ran N tests / OK
python pace_audit.py                        # 75 项独立校验，失败退出码 1
```

这两条绿，才说明你手上的代码是真的。
