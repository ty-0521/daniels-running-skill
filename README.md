# daniels-running-skill

《丹尼尔斯经典跑步训练法（第3版）》的可验证知识库。

给 agent 用的训练分析引擎：输入一次比赛成绩，输出可执行的配速、训练量上限和周期安排，
每一处数字都能指回原书的行号，或者指回一个能复现的回归方程。

**它不是**训练计划手册的电子版，也**不是**一份 OCR 出来的表格抄本——书里的表格全是位图，
这个包里的数字要么来自方程，要么来自正文中可以直接读到的算例。

## 先说定位：它是第二意见，不是教练

**它看得见你写的字，看不见你跑。**

教练能从你的落地声里听出胫骨应力，它只能读你打出来的「膝盖有点疼」。所以：

- **给你一个能核对的第二意见** —— 每个数都能回到方程、规则号或你自己说的话
- **不替你做决定** —— 该不该跑、要不要比、这周扛不扛得住，是你的判断
- **不保证不出错** —— 保证的是**错了你能当场看见**，因为每个数都可复核

对新手它会显得啰嗦：拦你、问你、拒绝你几次。**那个麻烦就是安全本身。**

如果你要的是「给我一张 12 周表，别问那么多」——这不是那个东西。

```
daniels/
  vdot.py        VDOT 正反算、五档配速、FR/H、海拔修正
  dose.py        训练量上限（32 条带行号的规则）、整周合规检查
  periodize.py   四阶段划分、Q 日排布、赛前减量逐周动作
  dates.py       比赛日 ↔ 周数 ↔ 起点（日期一律查，不许手算）
  deload.py      周期性减量（**外推层，书中没有这个概念**）
  audit.py       整张周表的统一裁决
  intake.py      接诊门禁：缺一层就不许出数
  citations.py   行号查询（行号只许查，不许手写）
  explain.py     不带原文的解释词条
  manifest.py    对外清单
  __main__.py    命令行入口
tests/           回归测试（跑 discover 看当前条数）
pace_audit.py    独立校验器（自带第二套方程实现），75 项检查
SKILL.md         skill 描述文件（YAML frontmatter + 使用说明）
skill.json       由 manifest() 导出的清单，供接入方读取
```

## 接入

作为一个 skill 使用，需要三样东西：`SKILL.md`（告诉 agent 何时调用）、
`skill.json`（机器可读的能力与边界清单）、以及 `daniels` 包本身。

```bash
# 1. 生成清单（代码改动后重跑）
python -m daniels manifest -o skill.json

# 2. 放到 harness 的 skill 目录（按你的环境替换路径）
#    macOS / Linux:  ~/.dsh/skills/daniels-running-skill/
#    Windows:        %USERPROFILE%\.dsh\skills\daniels-running-skill\
```

零第三方依赖，Python 3.10+ 即可（只用标准库）。
`python -m daniels --help` 查看全部子命令。

**注意：这不是一个 pip 包。** 没有 `pyproject.toml`，`pip install` 装不上——
它是个 skill 目录，交付形态就是「一个文件夹 + 一个启动器」。
只想当库用的话，把 `daniels/` 拷进你的 `PYTHONPATH` 就行。

## 快速开始

```python
import daniels as d

# 1. 由比赛成绩求 VDOT
vdot = d.vdot_from_race(5000, 20 * 60)          # 5 km 跑 20:00 -> 49.81

# 2. 五档配速（默认海平面）
paces = d.pace_set(vdot)
info = paces.as_dict()
print(info["M_per_km"], info["T_per_400m"], info["I_per_400m"])
# 4:32 1:42 1:34

# 3. 单次训练的量上限
cap = d.threshold_cap(weekly_km=64)
print(cap.max_km)                                # 6.4
print(round(cap.limit_km(paces.t), 2))           # 6.4（距离上限先触发）
print([r.rule_id for r in cap.rules])            # ['D-T-01', 'D-T-02']

# 4. 整周合规检查
bad = [d.Session("L", 21.0), d.Session("T", 9.0)]
for v in d.check_week(bad, weekly_km=64, paces=paces):
    print(v.rule_ids, v.message)
# ('D-L-02', 'D-L-03') L 跑 21.0 km 超过上限 16.0 km（周跑量 64 km）
# ('D-T-01', 'D-T-02') T 跑 9.0 km 超过上限 6.4 km（周跑量 64 km）

# 5. 周期安排
plan = d.plan_schedule(24)
print(plan.as_dict()["weeks"])                   # {'B/FIP': 6, 'IQ': 6, 'TQ': 6, 'FQ': 6}
print(d.quality_days(3))                         # (2, 4, 7) -> 周一/周三/周六

# 6. 解释
top = d.search("I 训练为什么每个回合只跑 5 分钟")[0]
print(top.question, top.sources)
# I 训练为什么每个回合只跑 3~5 分钟？ ('第4章 L1480', '第4章 L1484', '第5章 L1784')

# 7. 赛前减量逐周推演
taper = d.week_taper(11, 12, race_week=12)
print(taper.drop_strides, taper.long_run_minutes_cap)   # True 90.0
```

周期性减量是**外推**，不是书中内容，所以单列一层。它只给算术，不生成周表：

```python
# 书里没有「每 4 周减量 20%」，引用前必须先看这段声明
print(d.DELOAD_PROVENANCE["book_position"])

# 12 周、每 4 周减一次、第 12 周比赛 -> 只有第 4、8 两周
rhythm = d.deload_weeks(12, 4, race_week=12)
print(rhythm.weeks)                                # (4, 8)
print(dict(rhythm.skipped))                        # {12: '比赛周本身已经是减量周…'}

# 减量周还有哪些强度能练
for item in d.deload_impact(60.0):
    print(item.intensity, round(item.base_cap_km, 2), "->",
          round(item.deload_cap_km, 2), "可行" if item.feasible_after else "不可行")
# L 18.0 -> 14.4 可行 / M 18.0 -> 14.4 可行 / T 6.0 -> 4.8 可行 / I 4.8 -> 3.84 可行 / R 3.0 -> 2.4 可行

print(round(d.t_peak_km(6.0), 1))                  # 75.0：保住 6 km T 需要的峰值
print(d.growth_path(35, 60, 4).total_weeks)        # 20：35 加到 60 要 20 周
print(len(d.check_progression([35,35,35,28,35,35,43], 4)))   # 1：加量跳了 8 km，超 6.4
```

## 完整流程：接诊 → 配速 → 排课 → 审计

这是推荐用法。四步里任何一步没走完，都不该交出带数字的结论。

```python
import daniels as d

# ── 1. 接诊：缺一层就问，不许自己补 ──────────────────────────
state = d.IntakeState()
state.set("goal_distance_km", 21.0975).set("days_per_week", 3)
state.set("longest_recent_km", 8.0)

status = state.status()
print(status.code)        # 'need_info' —— 还缺比赛日期和周跑量
print(status.questions)   # 只问最靠前那一层缺的，不会一次抛十个
# ('比赛是哪一天？请给具体日期。如果还没定，也说一声——那我只给训练方向，不排周表',)

state.set("race_date", "2027-03-21").set("weekly_km", 19.0).set("red_flags", ())
print(state.status().code)   # 'need_result' —— 能排跑量骨架，但配速全空

# ── 1b. 日期与周数：查，不许算 ─────────────────────────────
from datetime import date

today, race = date(2026, 11, 13), date(2027, 4, 18)
print(d.weeks_until(today, race))          # (22, 2)：已过去 22 周零 2 天
print(d.max_plan_weeks(today, race))       # 22：能排的最长周数
for option in d.feasible_plans(today, race, documented_only=True):
    print(option.weeks, option.start_date)  # 3/6/9/12/20 周，各自从哪天开
# 20 2026-11-30 —— 周一。11-29 是周日，装不满 20 周

# ── 2. 拿到成绩才能填配速 ───────────────────────────────
state.set("recent_result", (5000.0, 28 * 60 + 12))
print(state.status().code)                 # 'ready'
paces = d.paces_from_intake(state)
print(paces.as_dict()["E_per_km"])         # ['6:47', '7:06']

# ── 3. 排课（骨架，不是逐字课表）─────────────────────────
plan = d.plan_schedule(18, allow_undocumented=True)
print(plan.weeks, plan.documented)         # (5, 5, 4, 4) False —— 18 周是均分推的

# ── 4. 审计：六类检查全过才许说「合规」───────────────────
weeks = [
    d.WeekEntry(week=i, weekly_km=v, sessions=(d.Session("L", L),))
    for i, (v, L) in enumerate([(24, 7)] * 4 + [(32, 9)] * 4, start=1)
]
result = d.audit_plan(weeks, sessions_per_week=5, base_source="user")
print(result.passed)       # True —— 只有这里是 True 才能说合规
print(result.report())     # 否则逐条列出第几周、哪一条、超多少
```

同一张表，如果长跑多写 1 km，`passed` 立刻变 False——因为 24 km 周的 30% 上限是 7.2：

```python
weeks[0] = d.WeekEntry(week=1, weekly_km=24, sessions=(d.Session("L", 8.0),))
print(d.audit_plan(weeks, sessions_per_week=5).passed)   # False
```

红线是这样触发的：

```python
state.set("red_flags", ("右膝上下楼梯疼",))
print(state.status().code)        # 'stopped'
print(state.status().can_build_plan)   # False
# stop_reason：先停，去看医生或运动康复，在此之前不排计划、不给训练量
```

## 命令行

用启动器可以从任意目录跑（推荐）：

```bash
python daniels_cli.py vdot 5k 20:00
```

如果你 `cd` 到了仓库根目录，`python -m daniels` 等价。**在别的工作目录里直接用
`-m daniels` 会报 `No module named 'daniels'`**，这是 agent 调用时最常见的坑。

```bash
python -m daniels vdot 5k 20:00
# 距离 5000 m，成绩 20:00
# VDOT = 49.81

python -m daniels paces 49.8 --altitude 2130
python -m daniels cap 64 T --vdot 49.8
python -m daniels check --weekly 64 --vdot 49.8 L18 T9 I5   # 超限时退出码 2
python -m daniels plan 24
python -m daniels taper --weeks 12 --race-week 12
python -m daniels deload --base 35 --weeks 12 --race-week 12
python -m daniels progression 35 35 35 28 35 35 43 --sessions 4   # 违规退出码 2
python -m daniels audit plan.json            # 整表裁决，不合规退出码 2
python -m daniels calendar --race 2027-04-18   # 哪些长度还来得及、从哪天开
python -m daniels intake --goal 21.1 --date 2027-03-21 --weekly 19
python -m daniels cite D-T-02                # '第14章 L3478'
python -m daniels cite --search 长跑
python -m daniels explain "定速节奏跑和巡航间歇的区别"
python -m daniels topics
python -m daniels manifest -o skill.json
```

退出码约定：**三个值互斥**。

| 码 | 含义 |
|---|---|
| `0` | 正常 |
| `1` | 参数、格式或计算错误；`intake` 还没就绪 |
| `2` | 检查跑完了但**发现了问题**：超限、不合规、命中红线 |

`argparse` 默认用 `2` 报「命令写错了」，那会跟「发现了问题」撞车——一个 agent
分不清是它自己打错命令，还是这张表不合规。所以这里把用法错误也改成了 `1`。
脚本可以据此分流：`2` 一定意味着**输入是合法的，输出不合法**。

`audit` 吃一个 JSON 文件（`-` 从标准输入读）。格式见
`daniels.audit.plan_from_dict`：顶层 `sessions_per_week` + `base_source`，
`weeks` 里每周给 `week` / `weekly_km` / `sessions`（`[["L", 8], ["T", 4.8]]`），
比赛周另加 `race_km`。

## 五层结构

| 层 | 输入 | 输出 | 依据 |
|---|---|---|---|
| 数值层 `vdot` | 比赛距离与成绩 | 五档配速、海拔修正、H 时间上限 | Daniels–Gilbert 回归方程 |
| 规则层 `dose` / `periodize` | 周跑量、阶段、比赛周 | 上限、违规记录、Q 日排布、赛前减量逐周动作 | 32 条带行号的规则 |
| 日历层 `dates` | 今天、比赛日 | 还差几周、哪些长度来得及、各自从哪天开 | 纯算术（一周 7 天） |
| **外推层 `deload`** | 周期长度、减量比例 | 减量周落在哪几周、各强度上限怎么变、加量要多少周 | **不是书中内容**，是明确的算术外推 |
| **门禁层 `intake` / `audit`** | 用户的回答、整张周表 | 还缺什么 / 整表过不过 | 只做判断，不加新知识 |
| 叙述层 `explain` / `citations` | 提问、规则号 | 结论 + 出处 | 书中论述的改写 |

数值层不依赖规则层，规则层不依赖叙述层。外推层单独存在，是因为「每 N 周减量 X%」
在书里根本不存在——把它混进规则层，读代码的人会以为书里写过。
`DELOAD_PROVENANCE` 是这一层的自我声明，`manifest()["unsupported"]` 里也列了这一条。

`manifest()` 把各层的内容和边界导成一份 JSON，
接入方不必读源码即可知道能做什么、误差多大、什么情况会被拒绝。

## 可验证性

```bash
python -m unittest discover -s tests -t .   # 会打印 Ran N tests
python pace_audit.py                        # 75 项独立校验，失败时退出码 1
```

CI 就跑这两条，见 `.github/workflows/ci.yml`：Linux 上跑 Python 3.10~3.13，
Windows 上再跑一遍（作者本机就是 Windows，交付物得在它被开发的环境里也过）。
零第三方依赖，两条命令，二十秒。

`pace_audit.py` **不复用**包内方程，而是自己重写一遍 Daniels–Gilbert 公式再互相比对。
两份独立实现对上，才能排除「同一个笔误写了两遍」这种自证。

### 实测误差上界

| 量 | 上界 | 依据 |
|---|---|---|
| VDOT 正反算 | 0.21 个 VDOT | 附录 D 四个分界值 |
| M 配速 | 0.14% | 表 5—2，VDOT 51 |
| T 配速 | 0.72% | 表 5—2 与表 5—3 共 13 点 |
| I 配速（VDOT ≥ 30） | 0.45% | 表 5—2，VDOT 51 与 60 |
| I 配速（VDOT < 30） | 3.5% | 表 5—3，11 行 |
| R 配速 | 1.43% | 表 5—2 与表 5—3 |
| E 配速区间 | 1.23% | 表 5—2，VDOT 51 |
| 训练量上限 | 0（按公式精确） | 书中的百分比与封顶值 |

I 配速在低 VDOT 的 3.5% 不是公式误差，而是**书内两处说法本身不一致**：表 5—3 的 I 列按
「R 加 7~8 秒/400 m」排，而强度定义说的是 98% 的 vVO2max。本包默认给定义值，
同时把表 5—3 的整行原值放在 `PaceSet.novice_row`，需要照书执行时直接取用。

## 明确不做的部分

| 区域 | 原因 | 行为 |
|---|---|---|
| VDOT < 20 或 > 85 | 书中无数据 | 抛 `VdotRangeError` |
| 年龄与性别调整 | 表 5—7/5—8 是图片，无真值可校 | 不实现 |
| 跑步机坡度—速度换算 | 表 4—5/4—6 只有 1 个可读锚点 | 只保留「坡度加 2% 补风阻」 |
| 训练计划表逐字课目 | 表 7—1 至 14—9 全是位图 | 按规则生成，并声明非逐字一致 |
| 海拔 > 2500 m | 超出书中讨论范围 | 抛 `AltitudeRangeError` |
| 书中未记录的季长 | 只记录了 3/6/9/12/20/23/24 周 | 抛 `PhaseLengthError` |
| 周期性减量（每 N 周减 X%） | 书中没有这个概念，减量只有赛前与赛后两种 | `deload` 层只给算术与来源声明，不生成周表 |
| 完整周表生成 | 骨架不等于逐字课表 | 不给；只给合规性与阶段正确性 |
| 带伤、术后、孕期、心血管、疼痛 | 这不是训练量问题 | `intake` 返回 `stopped`，不给任何跑量或替代训练 |

最后一条是有意为之：16 周很常见，但书里确实没给它的阶段分配。默认拒绝，
需要的人显式传 `allow_undocumented=True`，结果会被标记 `documented=False`。

## 注意事项

这部分是给用的人看的，也是给自己划的边界。**请在用之前读完。**

### 1. 它不是医疗器械，也不是教练

- **不诊断、不建议治疗。** 出现疼痛、肿胀、打软腿、关节卡住、夜间静息痛、
  或症状几天内加重，去看医生或运动康复。
- 它收到「膝盖疼」这类输入会直接停下，不给任何跑量。**这不是保守，是边界。**
- 它不知道你今天睡了几小时、腿沉不沉、昨天有没有应酬。**这些只有你知道。**

### 2. 它的错，长什么样

写这个项目的过程里跑过十轮真实对话测试，错的形状很固定，值得你知道：

| 错法 | 例子 |
|---|---|
| **输入不齐就开口** | 用户只说「每次 35 分钟」，它自己折成 17–18 km，后面全建在这个数上 |
| **把假设说成事实** | 两轮之后又说「之前按 18 km/周 估的，这个数是对的」——可那是它自己估的 |
| **单项校验冒充整表合规** | 只跑了加量节奏那项，就说「12 周全部通过校验」，实际长跑超上限 48%–67% |
| **行号手写** | 把 M 的规则（L1392）当成 T 的；把越野的（L3160）当成半马的 |
| **自己把日期编出来** | 用户只给了「12 周」，它倒推出一个比赛日，写进了每一行 |
| **手算代替调用** | 20 周的起点算成 11-29（周日，只有 141 天，装不满）；加量到 48 km 的周数两行都错 4~5 周 |
| **无条件断言** | 「长跑始终 = 30%」（实际只有前 3 周顶到）；「你每次都在阈值附近」（只在 VDOT ≤35 成立，36 以上那配速本身就是 E） |

现在这些各有对应机制：`intake` 挡第一条和第五条（还会挡自相矛盾的组合），
`base_source="assumed"` 不通过挡第二条，`audit_plan` 挡第三条，
`cite()` 挡第四条，`dates` 与 `growth_path` 挡第六条。

第七条挡不住——它是措辞问题，只能靠 SKILL.md 里那句「凡是写出『始终』『都在』『一定』，
先问一句反例存在吗」。

**但这不等于不会犯。** 等于犯了你能看见。

### 3. 你要怎么核对它

它给的每个数，只有三个合法来源：

1. **你给它的** —— 你的成绩、你的周跑量、你的日期
2. **函数算的** —— 你可以自己跑同一个函数复核
3. **标着「假设」的** —— 那就不许被当成事实使用

看到任何一个数不属于这三类，那就是它编的。**这是你唯一需要的检查方法。**

### 4. 它能承诺什么，不能承诺什么

| 能 | 不能 |
|---|---|
| 配速误差 ≤1.5%，可复现 | 保证你按它练就不受伤 |
| 上限按公式精确，附规则号 | 知道你的实际体能今天如何 |
| 缺数据时拒绝出数 | 保证生成的表和书本印刷表逐字一致 |
| 每个行号可回原文查 | 处理书里本身冲突的地方（会给两种说法让你选） |
| 红线触发就停 | 做医疗判断 |

### 5. 书的五个内部冲突，我没有调和

遇到这些它会给你两个说法，你觉得「怎么没个准话」——那是故意的：

- L 跑上限：25% / 30% / 60 分钟 / 150 分钟，四种说法分属不同章节场景
- 6 秒规则：随 VDOT 漂移（VDOT 50 时 7 秒，40 时 8 秒，33 时 11 秒）
- 比赛周最后一个 Q：第 10 章说赛前 3 天，第 14 章说 4~5 天
- T 的 10% 上限与 4.8 km 下限：周跑量低于 48 km 时无解
- 表 5—3 的 I 列与 98% vVO2max 的定义不一致

**调和它们需要教练判断，不需要代码。** 硬造一个中间值，才是真的不负责任。

## 关于书上发现的错误

实现过程中发现原书（这个译本）有几处算术/前后不一致，代码按规则实现，测试把判断锁住：

| 位置 | 问题 | 处理 |
|---|---|---|
| 第 12 章 L3152 | 97 km 的 8% 印成 7.68（实为 7.76，7.68 是 96 的 8%） | 按 7.76 实现，另写测试锁定「书中值对应 96 km」 |
| 第 3 章 L1218 | 4000 ml ÷ 61.3 kg 印成 62.25（实为 65.25） | 不采用该数字 |
| 第 5 章 L1804 | 说 VDOT 51 时 T−I 为 7 秒，表值实为 8 秒 | 代码给实际值，差异写入 `Topic` |
| 第 14 章 L3412 | M 3:43 → T 3:35 用的是 −8 秒，规则说 −9.375 秒 | 按规则实现 |
| 第 10 章 vs 第 14 章 | 比赛周最后一个 Q 距比赛 3 天，减量规则要求 4~5 天 | 两条各自保留，冲突写在 `taper_rules().conflict_note`；并注明 L2842 的适用条件是 1500~3200 m 选手、24 周 4 阶段计划、**周六**比赛 |

## 版权与数据来源

* 代码、方程、生成的数值、规则摘要、解释词条均为本项目原创，MIT 许可。
* **书中的原文段落、清洗后的全文、切块数据、表格图片一律不进仓库**，
  也不出现在任何 API 响应里。`explain` 的答案是对书中论述的改写，不是引用。
* 每个结论都标注章与行号，读者可自行回到原书核对。
* 32 条规则的行号已逐条回原文核过，核对记录机器可读：
  `manifest()["citation_audit"]`。其中 3 条原先引错，已改正并写进 `RULE_AUDIT_LOG`。

## 尚未完成

* `explain` 目前是关键词匹配，不是语义检索。真正的 RAG 需要额外的文本库，且该库不入仓库。
* 训练计划只做加减法：能保证剂量合规、阶段正确，但不保证与书本印刷的第 17 周课表逐字一致。
* `deload` 层只给算术（哪几周减、上限怎么变、加多少周数），**不生成周表**。
  周表要由调用方组织，且必须跑 `audit_plan` 证明合规——
  这一层的定位是「让临场发挥有据可查」，不是「替你做决定」。
* `explain` 没有覆盖「训练中断了怎么接」「连续两场比赛怎么排」这类运营性问题。
* 没有 CI。测试是本地跑的；开源后第一件事应该是把
  `python -m unittest discover -s tests` 和 `python pace_audit.py` 接到 GitHub Actions。

## 怎么参与

发现数字不对，最有用的提交方式不是"这里错了"，而是：

1. 你用的输入（距离、成绩、周跑量）
2. 它给出的数
3. 你算出来的数，以及你依据的章与行号

有这三样，我就能判断是实现错了、还是书里本身冲突。
`tests/` 里每条回归用例都附了它来自哪一轮真实测试——照着这个格式加就行。

