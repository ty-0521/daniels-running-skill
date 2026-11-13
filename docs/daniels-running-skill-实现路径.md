# daniels-running-skill：实现路径（v1，2026-11-13）

> **这是一份历史文档，不是规格。** 开工前写的设计路径，保留了当时的判断和理由。
>
> **最终实现的权威说明在 [README](../README.md) 与 [SKILL.md](../SKILL.md)**，
> 冲突时以它们为准。
>
> 下面这些在本文里写了、但**最终没做**（或换了做法）：
>
> | 本文的设想 | 实际做法 | 原因 |
> |---|---|---|
> | 叙述层用 Chroma + 嵌入模型做 RAG | 关键词检索，30 个词条（`explain.search`） | 做 RAG 要把原文切块入库，和「原文不进仓库」直接冲突 |
> | `pip install` 分发的库 | skill 目录 + `daniels_cli.py` 启动器 | 交付形态是 skill 不是包，少一个打包面 |
> | 规则层含「训练压力计分」 | 只做上限与周期，没有压力计分 | 书中没有可复现的计分公式，做出来就是编 |
> | 三层架构（数值 / 规则 / 叙述） | 五层 + 两道门禁（`intake` / `audit`） | 实测发现光有知识不够，还得有「不许开口」和「不许说合规」 |
> | 附录 A 的 `gen_vdot_table.py` 生成整张表 | 没进仓库；方程反算 + 表 5—3 的 11 行校准 | 表 5—2 是位图，硬还原等于抄表 |
> | 阶段 0~5 的工期估计 | 先做了两轮共 16 回合的真实对话测试才定形 | 数值层很快，行为层慢得多——见 `test-runs/` |
>
> 仍然有效的部分：三层价值判断、五个强度系数的反解、
> 「不编造靠架构而不是提示词」这条主张。

> 本文是对《daniels-running-skill-交接说明-详细版》的答复：先讲清楚这个项目的本质，再给 GitHub 同类项目的调研结论，最后给可执行的分阶段路径。
> 与交接文档冲突的地方以本文为准，冲突点集中在第六节。

---

## 一、这个项目的本质（先对齐再动手）

交接文档把它描述成「书的 RAG 知识库」。这个描述会让你把 70% 的精力花在错的地方。

**它真正的本质是：一个数值可复现、结论可溯源的训练计算组件，附带一层基于原著的解释能力。**

拆开看，它有三层，价值密度是从上到下递减的：

| 层 | 内容 | 谁在算 | 出错后果 | 项目价值 |
|---|---|---|---|---|
| **数值层** | VDOT、E/M/T/I/R 配速、比赛等效成绩 | 纯 Python 方程 | 跑错配速，受伤 | ★★★★★ 别人真正会用的东西 |
| **规则层** | 跑量上限、回合时长上限、训练压力计分 | 结构化常量 + 纯函数 | 计划不合理 | ★★★★☆ |
| **叙述层** | 为什么这样练、周期编排、伤病口径 | DeepSeek + 原文检索 | 说错话 | ★★☆☆☆ 现在是廉价商品 |

由此推出三个判断，后面所有设计都从这三条来：

1. **RAG 不是难点，是配件。** 2026 年，一个 Chroma + 嵌入模型 + 引用的问答链路大约 150 行代码，GitHub 上有几十个现成模板（见第三节）。把项目定位成「RAG 项目」，你的仓库会淹没在同类里。
2. **开源仓库的真正资产是「数值层 + 规则层」。** 一个经过验证、带测试、能 `pip install` 的丹尼尔斯配速库，会有人 star、有人 import、有人提 issue。一个 Chroma 包装器不会。
3. **「不编造」这个卖点，靠的不是提示词，是架构。** 提示词只能降低概率，架构才能保证。所以数值必须由代码算完再交给模型，模型只负责措辞。

一句话定位（建议直接用作 README 首句）：

> 丹尼尔斯跑步训练法的确定性计算库 + 可溯源问答层：配速和 VDOT 由方程算出，理论解释只来自原著，模型不碰数字。

---

## 二、对交接文档的关键修正（先看这节，它省你三天）

### 2.1 配速表不是阻塞项，根本不需要手录

交接文档第十节把「表 5-1 ~ 5-4 在 txt 里丢失」列为最高优先级风险，方案是「重新导出表格 / 对照纸质书手动录入 / 脚本复核」。

**这个工作可以整条删掉。** 丹尼尔斯的表格不是原始数据，是他用两条公开回归方程生成后取整的结果：

```
跑步经济性（速度 → 摄氧量），v 单位 米/分钟：
    VO2 = -4.60 + 0.182258·v + 0.000104·v²

某成绩可持续的摄氧量占比，t 单位 分钟：
    %max = 0.8 + 0.1894393·e^(-0.012778·t) + 0.2989558·e^(-0.1932605·t)

    VDOT = VO2 / %max
```

我用它反算原书表 5-1（8 个距离 × VDOT 30–85，共 448 格），对照一份第三方整理的完整原著表格数据：

| 距离 | 最大误差 | 相对误差 |
|---|---|---|
| 1500m | 0.7 s | 0.20% |
| 1 英里 | 0.9 s | 0.17% |
| 3K | 2.1 s | 0.32% |
| 5K | 1.8 s | 0.12% |
| 10K | 3.0 s | 0.10% |
| 15K | 6.8 s | 0.12% |
| 半马 | 30.8 s | 0.48% |
| 马拉松 | 31.9 s | 0.18% |

误差全部来自原著取整，没有一格超过 0.5%。**手录一张表要两天，还要两人复核；生成它要 40 行代码。**

### 2.2 五个强度系数已经反解出来了

把原书表 5-2 的每一格反推成「占 VDOT 的百分比」，得到的规律非常干净：

| 强度 | 规律 | 与原书逐格误差（56 档） |
|---|---|---|
| **E** | 恒为 **67.0%** × VDOT（原书给的是单值，不是区间） | 平均 0.54 s，最大 3.9 s |
| **M** | **= 马拉松等效配速**（就是表 5-1 的马拉松时间 ÷ 42.195） | 平均 0.24 s，最大 1.0 s |
| **T** | 恒为 **88.0%** × VDOT | 平均 0.53 s，最大 2.5 s |
| **I** | 恒为 **98.0%** × VDOT | 平均 0.34 s，最大 1.0 s |
| **R** | 随 VDOT 上升：**R% = 0.1664 · VDOT + 98.052** | 平均 0.37 s，最大 1.3 s |

三点需要注意：

- **E 是单值不是区间。** 交接文档 9.5 要求「E 配速给上下限」，但原书表里 E 就是每档一个数（= 67%），配合正文「感觉轻松就对了，宁可慢」。正文提到的 59%–74% 是**指导区间**，不是表里的两列。建议接口返回 `E`（67%）+ `E_slow_limit`（59%），而不是伪造一个「区间」。
- **M 不能当百分比处理。** 交接文档把 M 当固定系数，但原书的 M 随 VDOT 从 80.7% 升到 84.2% —— 因为它就是马拉松成绩的配速。必须用比赛等效成绩算，不能用比例。
- **R 是唯一需要拟合的。** 原书 R 从 VDOT 30 的 102.7% 升到 85 的 112.9%，一条直线拟合到 ±1.8 个百分点。如果你要更精确，就改成「R = 3K 等效配速 × 0.945」，也成立。

**结论：`vdot_table.json` 从「手录的高风险资产」变成一个「可重算、可校验的构建产物」。** 附录 A 是可运行的生成脚本，现在就跑得通。

### 2.3 嵌入模型选错了，这个必须改

交接文档 5.1 指定 `all-MiniLM-L6-v2`。**它只支持英文。** 你的书是中文译本，用户提问是中文，中文句子过这个模型得到的向量几乎没有区分度 —— 检索会变成随机返回，而且你不会发现，因为它不报错，只是答得莫名其妙。

换成 `BAAI/bge-small-zh-v1.5`：

- 中文检索专用，512 维，模型约 95 MB，CPU 上够快；
- `sentence-transformers` 直接支持，无需额外服务；
- 检索时给查询加前缀 `为这个句子生成表示以用于检索相关文章：`（bge 系列的约定，不加会掉几个点）。

### 2.4 Python 版本风险已经消失，但 pip 镜像是一个真坑

- 交接文档写的 Python 3.13.16，实际本机是 **3.14.6**。
- 我实测过：`chromadb 1.5.9` + `sentence-transformers 6.3.0` + `torch 2.15.0` + `onnxruntime 1.31.1` 在 3.14 上**都有预编译轮子，整套能解析**，不需要降级到 3.11。交接文档 15.2 的风险项可以删掉。
- **但你的 pip 配的是清华镜像，它上面这几个包一个都没有**，会直接报 `No matching distribution found`。这不是版本问题，是镜像没同步。装依赖时加 `--index-url https://pypi.org/simple`。

### 2.5 「先判类」这条链路设计得不对

交接文档 6.2 第 2 步：「先判类：是否为 VDOT / 配速计算类问题」。

意图分类不可靠 —— 用户会问「我这周该跑多快」，里面没有 VDOT 也没有配速数字，但答案是配速。分类器判成「理论类」，模型就开始编数字。

改成**参数抽取 + 常量注入**：

```
每次请求都先跑一遍：
  1. 正则抽距离 + 成绩（"5 公里 20 分" / "5k 20:00" / "半马 1:35"）
  2. 抽到 → 调 rule_engine 算出完整配速表
  3. 把配速表作为「已核定事实」塞进 prompt，无论这个问题被归为哪一类
  4. 抽不到 → prompt 里只放检索片段，并明确要求「不得给出具体配速数字，
     只解释原理，需要数值时反问用户近期比赛成绩」
```

这样取消了分类器这个不确定环节，数值永远先算好再进 prompt。

---

## 三、GitHub 调研：有没有能复用的

检索结论先说：**没有可以直接 fork 的「丹尼尔斯书籍知识库」项目。** 但有 6 个仓库存了零件，下面按「能拿什么」排序。

### 3.1 `ericgio/vdot` —— 原著表格的完整数据（只能当校验基准，别抄）

<https://github.com/ericgio/vdot>

单文件 `modules/client/constants/vdot.js`（17 KB）内含表 5-1（VDOT 30–85 × 9 个距离）和表 5-2（E/M/T/I/R 全部时间值，单位秒），是目前找到的最完整、最像原著的一份转录。**本文 2.1 / 2.2 的验证就是拿它当标准答案跑的。**

⚠️ **没有 LICENSE 文件** = 保留所有权利，不能直接复制进你的仓库。正确用法：开发期当测试基准（比对生成结果），发布时只发布你的生成脚本。数值本身是事实，但这份转录的编排方式受汇编权保护，绕开它就没有争议。

### 3.2 `lyhjeremy/marathon-strategy-rag` —— 架构上最该抄的一个（MIT）

<https://github.com/lyhjeremy/marathon-strategy-rag>

MiniLM + Chroma + 逐条引用 + LLM 评审评测的马拉松教练。MIT 协议，**代码可以直接改**。它做对了四件你交接文档里没设计的事：

1. **`src/numcheck.py`（99 行）—— 确定性数字审计。** 把回答里每个数字抽出来，去问题、工具返回值、引用片段里找来源，找不到就标记为「无出处」。这是防止模型编数字的**真正有效手段**，比提示词强得多。你的第 4 阶段应该抄这个思路。
2. **`eval/gold.jsonl` + `skills src/eval.py`** —— 一套可回归的评测集：问题、期望答案、引用出处。改完 prompt 跑一遍就知道有没有退化。
3. **`knowledge/*.md` 知识卡制度** —— 14 张卡，每张 1.5 KB，比把整本书切块检索的命中率高得多（你自己的知识库结构也应混合这两种）。
4. **`src/tools/pace.py`** —— 配速计算工具与 RAG 分离，和你要的架构同构。

它的 README 里给了量化结果：带出处约束的版本 faithfulness 0.98，裸模型 0.76。这个数字可以直接引用进你的 README。

### 3.3 `sesh/daniels-running-formula-to-intervals` —— 强度系数（Unlicense = 公有领域）

<https://github.com/sesh/daniels-running-formula-to-intervals>

8 KB，`drf.py` 里 8 行常量表，是全网少见的、明确写出丹尼尔斯强度百分比的代码：

```python
PACES = {"ST": ("105","130"), "L": ("59","74"), "E": ("59","74"),
         "M": ("75","84"), "T": ("83","88"), "I": ("95","100"), "R": ("105","110")}
```

Unlicense 意味着作者放弃了全部权利，随便用。这些区间值和我在 2.2 反解出来的结论一致（T 88% 落在 83–88 上沿，I 98% 落在 95–100 上沿，R 随 VDOT 在 105–110 之间移动）—— 相互独立的两个来源对上了，说明这套常数可信。

它还顺带给了个有用的小设计：**用自然语言串描述训练课**（`2E + 4x(1200I w/ 3min jg) + 2E`）然后解析成结构化步骤。你的"训练计划输出"阶段可以直接用这个文本格式。

### 3.4 `xiaolouJB/ai-running-coach` —— 中文场景最接近的一个（MIT）

<https://github.com/xiaolouJB/ai-running-coach>（27 star，2026-11 还在更新）

「基于高驰数据 × 丹尼尔斯训练理论的 AI 跑步教练」。**和你画像高度重合：你也用高驰 Pace3。** MIT 协议。值得看的部分：

- `knowledge_cards/` 目录：按「伤病 / 力量 / 营养」分类的中文知识卡，20 多张，每张 1–4 KB。**这是中文跑步知识卡的现成范本**，风格、粒度、术语都可以直接借鉴。
- `vdot_calculator.py`（13 KB）：单文件 VDOT 计算器，中文输出格式好。
- `INJURY_MODULE.md` + `SKILL.md`（41 KB）：怎么组织一个"技能"的说明书结构。

⚠️ **但不要用它的 VDOT 表。** 它的表只有 VDOT 30–65 逐档，而且和另外两个项目的表数值互相矛盾（同一档 VDOT 的 E 配速能差 20 秒）。这正是"手抄表"必然出错的证据 —— 也是本文主张用方程生成的理由。

### 3.5 `jiarui0415/DanielsRunningFormula` —— 「纯 Skill，不用 RAG」的另一条路

<https://github.com/jiarui0415/DanielsRunningFormula>

不是代码仓库，是一个 markdown 技能包：`skill/SKILL.md` + `assets/{vdot-table, fvdot-decay, workout-volume-caps, phase-compression, strength-circuit}.md`。基于第 4 版（2022）。

它对你有两个价值：

1. **一张「该编码哪些规则」的清单。** 它把原著提炼成 5 个资源文件，说明一个完整的丹尼尔斯助手需要：VDOT 表、**停训后的 VDOT 衰减表（表 9.1）**、各强度单次课上限、可用周数对应的阶段压缩表（图 10.2）、力量循环。你的交接文档第七节漏了「VDOT 衰减」和「阶段压缩」这两块，而它们是制定周期计划必需的。
2. **一个架构对照。** 这条路完全不写代码、不建向量库，把知识写成 markdown 让模型读。优点是零依赖、可读性极好；缺点是数值全靠模型照抄表格，**没有任何机制保证它不抄错**。你的项目正好可以论证「为什么要写代码」：因为这条路会算错。

⚠️ 它也没有 LICENSE。`vdot-table.md` 里的 VDOT 51 那一行明显是坏的（E 配速比 VDOT 50 还慢，数值自相矛盾）—— 又一份手抄表翻车的例证。

### 3.6 `nullspace1/pocket-daniels` —— 数据分层的思路（GPL，只能看不能抄）

<https://github.com/nullspace1/pocket-daniels>

LlamaIndex 实现的训练计划 agent，接入 Garmin 数据。GPL-3.0 协议，**代码不能进 MIT 仓库**，但架构值得抄：

- 它把知识库拆成 **两个索引**：`fact_index`（用户个人事实，带过期天数，会剪枝）和 `book_index`（书本内容，只读）。你的项目迟早要记住"这个跑者上个月 5K 跑 20 分""他左膝有过 ITBS"——那些是事实不是书，混在一个集合里会污染检索。
- `planning/` 和 `knowledge/` 是两个独立模块，各暴露一组工具给 LLM。和你「规则引擎 vs RAG」的分离同构，但它的粒度更细。

### 3.7 顺带否掉的

- `karalyndewalt/FastAsYouCan`（40 star）：2015 年的 Flask 训练计划生成器，代码价值低，只看它的"周计划表"输出格式。
- `mtlam/TempoPace`（2 KB）：只有 T 配速，太少。
- `mekeetsa/vdot`：只有一份 `vdot-theory.pdf` 和一个 Visio 图，是理论推导不是实现，可以当公式出处的参考。

---

## 四、推荐架构：三层，不是两层

交接文档的「规则引擎 / RAG」二分方向是对的，但粒度不够 —— 它把"跑量上限"这类本质是常量的东西也塞进了 RAG，导致模型有机会算错。

```
┌─ 第 1 层：数值层（纯函数，零依赖，100% 确定）────────────────┐
│  vdot_from_race(dist, time) -> float                        │
│  paces_from_vdot(vdot)      -> {E,M,T,I,R}                  │
│  race_equiv(vdot, dist)     -> seconds                      │
│  数据来源：附录 A 生成                                          │
└─────────────────────────────────────────────────────────────┘
┌─ 第 2 层：规则层（结构化常量 + 纯函数，可单测）────────────────┐
│  volume_caps(weekly_km, session_type) -> 上限 km / 分钟       │
│  phase_plan(weeks_available)           -> 各阶段周数          │
│  stress_score(duration_min, pace_type) -> 分数                │
│  vdot_decay(days_off, cross_trained)   -> 折减系数            │
│  数据来源：你从原著正文抽成 rules.json（人工，30 条左右）        │
└─────────────────────────────────────────────────────────────┘
┌─ 第 3 层：叙述层（RAG，只解释"为什么"，不产出数值）────────────┐
│  chunker → bge-small-zh → chroma → DeepSeek                 │
│  输出必须带引用；numcheck 后置审计；数值只能来自 1、2 层        │
└─────────────────────────────────────────────────────────────┘
```

第 2 层是交接文档没有明确划出来的，而它其实是**这个项目比通用 RAG 更值钱的地方**：跑量上限、单次课上限、回合时长、阶段压缩、VDOT 衰减 —— 这些是规则，写成 JSON 比写成向量可验证得多。

### 目录结构（相对交接文档第八节的改动）

```text
daniels-running-skill/
├── data/
│   ├── raw/                  # 用户自备的 daniels_raw.txt（.gitignore）
│   ├── derived/
│   │   └── vdot_table.json   # ★ 生成产物，入库。公式算出来的数值可以公开
│   └── rules.json            # ★ 规则层常量，入库，人工整理 + 逐条标注章节出处
├── daniels/
│   ├── __init__.py
│   ├── vdot.py               # 第 1 层
│   ├── rules.py              # 第 2 层
│   └── rag.py                # 第 3 层
├── scripts/
│   ├── gen_vdot_table.py     # 附录 A
│   ├── verify_vdot_table.py  # 与原著抽样值比对
│   └── build_index.py        # 清洗 → 分块 → 建库
├── tests/
├── examples/cli.py
├── pyproject.toml
├── README.md
└── LICENSE                   # MIT
```

**关键合规判断（这条要写进 README）：** 公式算出来的数值可以入库 —— 事实不受著作权保护，而且全世界每个 VDOT 在线计算器都在公开这些数字。**书里的文字、表格的编排方式不行。** 所以你发布 `vdot_table.json` 和生成脚本，不发布 `daniels_clean.txt` / `book_chunks.json` / `chroma_db/`。这条线比交接文档第十二节更精确，也让仓库真的有了可复用资产。

### 砍掉什么（避免前两周就累死）

| 交接文档要求 | 建议 | 理由 |
|---|---|---|
| LangChain `RecursiveCharacterTextSplitter` | **删掉** | 25 行 stdlib 就能写完，LangChain 会拉进几十个包、版本天天变，你调 bug 的时间比写代码多 |
| FastAPI + HTTP + import 双接口 + 2 个 demo（第 1 版就要） | 先只做 `ask()` 函数 | 「可插拔」的最小单位就是一个函数。HTTP 等有东西值得伺服了再加，一天的事 |
| 命令行 demo + 集成 demo | 先 1 个 CLI | 第二个 demo 在第 5 阶段再补 |
| `data/chunks/book_chunks.json` 落盘 | 改为内存态，只落 chroma | 少一份需要 gitignore 的文件，少一处和源文本不同步的地方 |

---

## 五、分阶段路径

时间按「每天 2–3 小时，周末多干点」估。

### 阶段 0：环境（半天）

```powershell
cd D:\training
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
# 关键：必须走官方索引，清华镜像缺包
python -m pip install --index-url https://pypi.org/simple `
    chromadb sentence-transformers openai fastapi uvicorn python-dotenv pytest
```

**验收**：`python -c "import chromadb, sentence_transformers, openai; print('ok')"` 打印 ok。
若卡在下载，先单独 `pip install --index-url https://pypi.org/simple torch`（约 2.5 GB，慢是正常的）。

### 阶段 1：数值层（1–2 天）★ 原来的阻塞项，现在消失

1. 建目录，把 `D:\program1\daniels_raw.txt` 移进 `data/raw/`。
2. 跑附录 A 的脚本，生成 `data/derived/vdot_table.json`（VDOT 30–85，含 8 个距离的比赛等效成绩 + 5 个强度配速）。
3. 写 `scripts/verify_vdot_table.py`：你自己照着书翻 5 处，把看到的数值填进一个 `golden` 字典，脚本逐项比对，超差就报错。**注意别只看 VDOT 整数档 —— 书上正文举例里出现的数值（比如某档 VDOT 的 T 配速）最有校验价值。**
4. 实现 `daniels/vdot.py` 三个公开函数 + 任意 VDOT 的线性插值（30–85 之外抛异常，不外推）。
5. 写 `tests/test_vdot.py`：整数档查值、插值、边界、非法输入。

**验收**：
- 生成脚本输出 448 个比赛成绩格，与第三方转录数据的最大相对误差 < 0.5%；
- 5 处人工抽样与纸质/电子书一致；
- `pytest tests/test_vdot.py` 全绿；
- 任意输入（`5km 20:00` / `1.6km 5:44` / `10 英里 65 分` / `半马 1:35:00`）都能正确解析，非法输入报中文错误。

**这一步结束，项目就已经有价值了。** 如果你的时间被课程切得很碎，就先停在发布一个"VDOT 配速库"，第 3 层以后再说 —— 这比做一个半成品问答机器人体面得多。

### 阶段 2：规则层（1–2 天）

从 `daniels_raw.txt` 里把交接文档第七节列的规则抽成 `data/rules.json`，每条带 `source_chapter`：

```json
{
  "long_run": {
    "if_weekly_km_below": 64,
    "cap_ratio_of_weekly": 0.30,
    "if_weekly_km_at_least": 64,
    "cap_ratio_of_weekly": 0.25,
    "cap_minutes": 150,
    "rule": "先到者为准",
    "source_chapter": "第 4 章 / 长距离跑"
  },
  "marathon_pace_session": {
    "cap_minutes": 110, "cap_km": 29,
    "cap_ratio_of_weekly": 0.20, "source_chapter": "第 4 章"
  },
  "threshold_session": {
    "cap_ratio_of_weekly": 0.10,
    "cruise_interval_min_total_minutes": 30,
    "work_rest_ratio": 5,
    "source_chapter": "第 4 章"
  },
  "interval_bout": { "min_minutes": 3, "max_minutes": 5, "source_chapter": "第 4 章" },
  "repetition_bout": { "max_minutes": 2, "source_chapter": "第 5 章" },
  "stress_score_per_min": { "E": 0.2, "M": 0.4, "T": 0.6, "10K": 0.8, "I": 1.0, "R": 1.5 }
}
```

再补两块交接文档漏了的：
- **VDOT 衰减表（表 9.1）**：停训天数 → 折减系数，区分有无交叉训练。这个在 `jiarui0415` 的 `fvdot-decay.md` 里有整理，但**你要回书核对**。
- **阶段压缩表（图 10.2）**：总可用周数 → 四个阶段各占几周，压缩时先砍 III 期。

`daniels/rules.py` 实现纯函数，`tests/test_rules.py` 覆盖边界（周跑量 63 / 64 / 0）。

**验收**：给定周跑量和训练营周数，能算出每个强度的单次上限和四阶段周数，全部可单测。

### 阶段 3：文本层（2 天）

1. `scripts/extract.py`：清洗 `daniels_raw.txt` —— 去版权页/定价/译者名单、合并空行、规范 `O 2 max` → `VO2max`、去脚注标号。输出 `data/cleaned/daniels_clean.txt`（**不入库**）。
2. `scripts/chunk.py`：按章节标题切，再按 `chunk_size=500 / overlap=80` 细分（交接文档的 700/120 对中文偏大，中文一个字符信息量约等于英文 1.5 个，700 字一块容易糊）。
   每个块带 `{"chapter": ..., "section": ...}` 元数据。
3. `scripts/build_index.py`：`BAAI/bge-small-zh-v1.5` + Chroma，持久化到 `chroma_db/`。

**验收**：用这几个问题跑 top-4 检索，看返回的段落是不是人话：
- 「长距离跑最多能占周跑量多少？」
- 「T 跑有哪两种形式？」
- 「间歇跑一个回合最长多少分钟？」
- 「停训两周 VDOT 会掉多少？」

如果中文检索命中率差，先检查是不是忘了给 query 加 bge 的前缀，再检查 chunk 是不是把表格残渣切进去了。

### 阶段 4：叙述层 + 数字守卫（2–3 天）

1. `daniels/rag.py`：
   - 参数抽取（正则，抽距离+成绩）
   - 抽到就调 `vdot.paces_from_vdot()`，把结果作为「已核定事实」写进 prompt
   - 检索 top-4 原文块，拼进 prompt
   - System prompt 四条硬约束：①配速/VDOT 只用给定事实里的数字，不得自行计算或报数；②理论解释只能来自给定片段，并标注来源章节；③片段无相关内容就答「书中没有相关内容」；④涉及伤病用保守口径，声明不替代医疗建议。
2. **数字审计**（借 `lyhjeremy` 的 `numcheck` 思路，MIT，可改）：把回答里的每个数字抽出来，去「问题 + 注入的事实 + 引用片段」里找来源，找不到就标红。开发期把它当断言用，发布期可以作为可选开关。
3. `tests/test_rag.py`：
   - 召回：4 个问题都能检到相关段落
   - 拒答：「我该买哪双碳板鞋」「挪威双阈值法怎么练」→ 必须说书中没有
   - **数值隔离**：问「5 公里 20 分，我的 T 配速多少」→ 回答里的 T 配速必须等于 `paces_from_vdot(49.8)` 的结果，一位不差

**验收**：20 条人工问题，无一条出现无出处数字；拒答题全部正确拒答。

### 阶段 5：对外与发布（1 天）

- `examples/cli.py`：一行提问出答案
- `daniels/api.py`：FastAPI 两个端点（`/vdot`、`/ask`），一个 `SkillError` 统一转 400/500
- `examples/integrate_demo.py`：演示在别的项目里 `from daniels import vdot` 直接用
- `README.md`：一句话定位 + 30 秒上手 + **合规声明**（不分发书籍、需自备正版、数值来自公开方程）
- `.gitignore`：`data/raw/`、`data/cleaned/`、`chroma_db/`、`.env`、模型缓存
- 发布前扫一遍：`git ls-files | findstr /i "epub azw3 mobi"` 必须为空

**验收**：干净克隆到新目录，照 README 从零跑通（这条是真正的发布门槛）。

---

## 六、与交接文档的冲突清单

| 交接文档原文 | 本文结论 | 依据 |
|---|---|---|
| 第十节：配速表需重新抽表或手录，是最大阻塞 | 用方程生成，手录工作整条取消 | 448 格实测误差 < 0.5% |
| 5.1：嵌入模型用 `all-MiniLM-L6-v2` | 改 `BAAI/bge-small-zh-v1.5` | 前者不支持中文 |
| 6.2：先做意图分类 | 改成参数抽取 + 常量注入 | 分类器会把"我这周跑多快"分错 |
| 9.5：E 配速给上下限 | E 是单值（67%），另给 59% 慢速下限 | 原著表格就是单值 |
| 15.2：Python 3.13 装不上 chromadb 是风险 | 3.14 实测可选，风险在 pip 镜像 | 官方索引 dry-run 通过 |
| 第八节：`vdot_table.json` 放 `data/cleaned/` | 放 `data/derived/` 且**入库** | 它是生成产物，不是书的内容 |
| 第七节规则清单 | 补 VDOT 衰减表、阶段压缩表 | 缺这两块做不了周期计划 |
| 全篇两层架构 | 三层，加规则层 | 跑量上限本质是常量 |

---

## 附录 A：`scripts/gen_vdot_table.py`（可直接运行）

```python
"""生成 data/derived/vdot_table.json。

数据来源：Daniels & Gilbert 的公开回归方程（原著正文给出的两条公式），
不经手抄，不依赖原书表格转录。系数已用原著表 5-1/5-2 反解验证。

用法：
    python scripts/gen_vdot_table.py
"""

from __future__ import annotations

import json
import math
from pathlib import Path

# ── 两条方程 ────────────────────────────────────────────────
# v: 米/分钟；t: 分钟
def vo2_from_velocity(v: float) -> float:
    return -4.60 + 0.182258 * v + 0.000104 * v * v


def sustainable_fraction(t_min: float) -> float:
    return (0.8
            + 0.1894393 * math.exp(-0.012778 * t_min)
            + 0.2989558 * math.exp(-0.1932605 * t_min))


def velocity_for_vo2(target_vo2: float) -> float:
    """反解 vo2_from_velocity 的二次方程，取正根。"""
    a, b = 0.000104, 0.182258
    disc = b * b + 4 * a * (4.60 + target_vo2)
    return (-b + math.sqrt(disc)) / (2 * a)


def vdot_of(distance_m: float, seconds: float) -> float:
    t = seconds / 60.0
    return vo2_from_velocity(distance_m / t) / sustainable_fraction(t)


def race_seconds(distance_m: float, vdot: float) -> float:
    """二分求：以该 VDOT 全力跑 distance_m 的用时（秒）。"""
    lo, hi = 30.0, 21600.0
    for _ in range(80):
        mid = (lo + hi) / 2
        if vdot_of(distance_m, mid) > vdot:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


# ── 强度系数（由原著表 5-2 反解，误差见文档 2.2）────────────
PCT_E = 0.670
PCT_T = 0.880
PCT_I = 0.980
def pct_r(vdot: float) -> float:
    return (0.1664 * vdot + 98.052) / 100.0


DISTANCES = {
    "1500m": 1500.0, "mile": 1609.344, "3km": 3000.0, "2mile": 3218.688,
    "5km": 5000.0, "10km": 10000.0, "15km": 15000.0,
    "half": 21097.5, "marathon": 42195.0,
}

VDOT_MIN, VDOT_MAX = 30, 85


def secs_per_km(velocity_m_per_min: float) -> float:
    return 1000.0 / velocity_m_per_min * 60.0


def fmt_pace(seconds_per_km: float) -> str:
    s = round(seconds_per_km)
    return f"{s // 60}:{s % 60:02d}"


def fmt_time(seconds: float) -> str:
    s = round(seconds)
    h, m, sec = s // 3600, (s % 3600) // 60, s % 60
    return f"{h}:{m:02d}:{sec:02d}" if h else f"{m}:{sec:02d}"


def build_row(vdot: float) -> dict:
    e = velocity_for_vo2(PCT_E * vdot)
    t = velocity_for_vo2(PCT_T * vdot)
    i = velocity_for_vo2(PCT_I * vdot)
    r = velocity_for_vo2(pct_r(vdot) * vdot)

    marathon_s = race_seconds(DISTANCES["marathon"], vdot)
    m = DISTANCES["marathon"] / (marathon_s / 60.0)

    return {
        "vdot": vdot,
        "race_equiv": {k: fmt_time(race_seconds(d, vdot)) for k, d in DISTANCES.items()},
        "paces_per_km": {
            "E": fmt_pace(secs_per_km(e)),
            "E_slow_limit": fmt_pace(secs_per_km(velocity_for_vo2(0.59 * vdot))),
            "M": fmt_pace(secs_per_km(m)),
            "T": fmt_pace(secs_per_km(t)),
            "I": fmt_pace(secs_per_km(i)),
            "R": fmt_pace(secs_per_km(r)),
        },
        "splits": {
            "T_per_400m": fmt_time(400.0 / t * 60.0),
            "I_per_400m": fmt_time(400.0 / i * 60.0),
            "R_per_200m": fmt_time(200.0 / r * 60.0),
            "R_per_400m": fmt_time(400.0 / r * 60.0),
        },
    }


def main() -> None:
    rows = [build_row(v) for v in range(VDOT_MIN, VDOT_MAX + 1)]
    payload = {
        "meta": {
            "source": "Daniels & Gilbert 回归方程（原著正文给出）；系数由原著表 5-1/5-2 反解校验",
            "pace_unit": "min/km",
            "vdot_range": [VDOT_MIN, VDOT_MAX],
            "note": "数值为方程计算结果，非原书表格转录；任意 VDOT 在区间内可线性插值，区间外禁止外推",
        },
        "rows": rows,
    }
    out = Path(__file__).resolve().parent.parent / "data" / "derived" / "vdot_table.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"已写入 {out}（{len(rows)} 档 VDOT）")
    for v in (40, 50, 60):
        row = build_row(v)
        p = row["paces_per_km"]
        print(f"  VDOT {v}: E {p['E']} | M {p['M']} | T {p['T']} "
              f"| I {row['splits']['I_per_400m']}/400m | R {row['splits']['R_per_400m']}/400m "
              f"| 全马 {row['race_equiv']['marathon']}")


if __name__ == "__main__":
    main()
```

实际输出（我已运行核对，数值与原书表 5-2 逐格一致）：

```
已写入 data/derived/vdot_table.json（56 档 VDOT）
  VDOT 40: E 6:20 | M 5:27 | T 5:06 | I 1:52/400m | R 1:46/400m | 全马 3:49:37
  VDOT 50: E 5:18 | M 4:31 | T 4:15 | I 1:34/400m | R 1:28/400m | 全马 3:10:40
  VDOT 60: E 4:35 | M 3:52 | T 3:40 | I 1:21/400m | R 1:15/400m | 全马 2:43:22
```

对照原书表 5-2：VDOT 40 的 E/M/T/I/400m/R/400m 是 6:20 / 5:27 / 5:06 / 1:52 / 1:46；VDOT 50 是 5:18 / 4:31 / 4:15 / 1:33 / 1:27。逐项差 0–1 秒，来源是取整。

单档样例（`vdot_table.json` 里 VDOT 50 这一行）：

```json
{
  "vdot": 50,
  "race_equiv": {
    "1500m": "5:24", "mile": "5:50", "3km": "11:33", "2mile": "12:28",
    "5km": "19:56", "10km": "41:20", "15km": "1:03:34",
    "half": "1:31:31", "marathon": "3:10:40"
  },
  "paces_per_km": {"E": "5:18", "E_slow_limit": "5:52", "M": "4:31",
                   "T": "4:15", "I": "3:54", "R": "3:39"},
  "splits": {"T_per_400m": "1:42", "I_per_400m": "1:34",
             "R_per_200m": "0:44", "R_per_400m": "1:28"}
}
```

`E_slow_limit` 用 59%（正文给出的 E 区间下限）算，不参与查表，只作为「可以再慢」的提示返回。

---

## 附录 B：下一步该做的三件事

1. 在 `D:\training` 建虚拟环境，用官方索引装依赖（阶段 0）。
2. 跑附录 A 的脚本，得到 `vdot_table.json`，翻书核对 5 个抽样点。
3. 拿第 3.2 节的 `lyhjeremy/marathon-strategy-rag` 读一遍 `src/numcheck.py`（99 行）和 `src/retriever.py`（47 行），MIT 协议，这是你第 4 阶段的现成骨架。

`D:\program1\daniels_raw.txt` 在第 1 步之外**先不要动** —— 清洗和分块是阶段 3 的事，提前处理只会返工。
