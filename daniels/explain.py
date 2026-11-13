# -*- coding: utf-8 -*-
"""丹尼尔斯训练法的解释层（叙述层）。

这一层回答「为什么」和「区别在哪」，不负责算数——
凡是需要具体配速、具体上限的，都指回 :mod:`daniels.vdot` 与
:mod:`daniels.dose` 里的函数，由调用方现场计算。

三条约束
--------
1. **不搬运原文。** 每个词条的 ``answer`` 是对书中论述的改写，
   不是引用。书里的句子不进仓库，也不进 API 响应。
2. **每个词条带出处。** ``sources`` 给到章与行号，读者可以自己回去核对。
3. **冲突不掩盖。** 书里前后说法不一致的地方，单独设词条说明两种说法
   各自在哪、本模块默认取哪一侧。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple

__all__ = [
    "Topic",
    "TOPICS",
    "explain",
    "search",
    "topic_ids",
]


@dataclass(frozen=True)
class Topic:
    """一个解释词条。"""

    topic_id: str
    question: str
    keywords: Tuple[str, ...]
    answer: str
    sources: Tuple[str, ...]
    related: Tuple[str, ...] = ()
    computed_by: str | None = None
    """若该词条涉及可计算的数值，这里给出 :mod:`daniels` 里的函数名。"""

    def as_dict(self) -> Dict[str, object]:
        return {
            "topic_id": self.topic_id,
            "question": self.question,
            "answer": self.answer,
            "sources": list(self.sources),
            "related": list(self.related),
            "computed_by": self.computed_by,
        }


#: 全部词条。键即 ``topic_id``。
TOPICS: Dict[str, Topic] = {
    # ---------------- VDOT 本身 ----------------
    "vdot-vs-vo2max": Topic(
        topic_id="vdot-vs-vo2max",
        question="VDOT 和我实验室测的最大摄氧量为什么不一样？",
        keywords=("vdot", "vo2max", "最大摄氧量", "实验室", "不一样"),
        answer=(
            "VDOT 是用比赛成绩反推出来的等效最大摄氧量，它把最大摄氧量、"
            "跑步经济性、乳酸门槛和比赛心理一起折进一个数里。"
            "所以它和实验室测的值经常不等：测出来更高说明你的经济性不如"
            "回归方程的假设，更低则说明更好。这不是错误，而且用比赛成绩"
            "来定训练强度本来就比实验室数据更贴近实际。"
        ),
        sources=("第5章 L1742-L1746",),
        related=("no-short-race-prediction",),
    ),
    "no-short-race-prediction": Topic(
        topic_id="no-short-race-prediction",
        question="能用短距离成绩去预测长距离吗？",
        keywords=("预测", "马拉松", "半马", "短距离", "5k", "800米", "1公里", "外推"),
        answer=(
            "书里明确说的只有两条：1 公里的表现不足以预测全程或半程马拉松；"
            "跑马拉松的训练配速最好用 10 公里以上的比赛来定，而且越近越好。"
            "至于「5 公里的成绩能不能直接套到半马」，书中没有给出判断，"
            "它只说过半马成绩比 1.6 公里更能预测马拉松配速。"
            "所以拿 5 公里 VDOT 直接排半马计划属于外推，回答时必须说明这一点，"
            "不要声称有书中依据。"
        ),
        sources=("第5章 L1748", "第4章 L1388", "第14章 L3402"),
        related=("vdot-vs-vo2max",),
    ),
    # ---------------- 五个强度 ----------------
    "why-easy-is-slow": Topic(
        topic_id="why-easy-is-slow",
        question="E 跑为什么要跑那么慢？",
        keywords=("e跑", "e配速", "轻松跑", "慢", "59", "74"),
        answer=(
            "E 跑定在最大摄氧量的 59%~74%，目的是让心脏、血管和肌肉纤维"
            "在低压力下累积适应，同时保证还能正常说话。跑快一点并不会让"
            "这些适应来得更快，只会把本该留给高质量训练的恢复提前用掉。"
        ),
        sources=("第4章 L1331", "第4章 L1339", "第4章 L1355"),
        related=("why-30-min-floor", "why-150-min-cap"),
        computed_by="pace_set",
    ),
    "why-30-min-floor": Topic(
        topic_id="why-30-min-floor",
        question="E 跑为什么至少要 30 分钟？",
        keywords=("30分钟", "下限", "最短", "e跑", "e配速"),
        answer=(
            "30 分钟是书中给出的 E 跑最短时间。低于这个量，心血管与肌肉"
            "承受的刺激太短，收益不明显，不如把这一天当作休息。"
        ),
        sources=("第4章 L1345",),
        related=("why-easy-is-slow",),
    ),
    "why-150-min-cap": Topic(
        topic_id="why-150-min-cap",
        question="长距离跑为什么要封顶 150 分钟？",
        keywords=("150分钟", "长距离", "l跑", "封顶", "上限", "2.5小时"),
        answer=(
            "书中把单次定速跑的上限定在 150 分钟，理由是顶尖跑者跑 32 公里"
            "大约只要 2~2.5 小时；让跑得慢的人花 5 小时去凑同样的距离，"
            "承受的压力远大于收益。跑走结合备赛的人可以超过这个时间。"
        ),
        sources=("第4章 L1345", "第4章 L1367-L1371"),
        related=("l-cap-conflict",),
        computed_by="long_run_cap",
    ),
    "why-m-is-mental": Topic(
        topic_id="why-m-is-mental",
        question="M 配速跑的生理作用大吗？",
        keywords=("m跑", "m配速", "马拉松配速", "作用", "意义", "心理"),
        answer=(
            "生理上它和 E 跑差别不大，主要价值在心理和实操：把配速调准、"
            "在目标配速下练喝水与补给，从而对比赛配速建立信心。"
        ),
        sources=("第4章 L1394",),
        related=("why-easy-is-slow",),
        computed_by="marathon_pace_cap",
    ),
    "t-comfortably-hard": Topic(
        topic_id="t-comfortably-hard",
        question="T 配速到底是什么感觉？",
        keywords=("t跑", "t配速", "门槛", "乳酸", "感觉", "舒适", "艰苦", "多快"),
        answer=(
            "是「舒适的艰苦」：能维持 30~40 分钟以上，训练有素者约能撑 60 分钟。"
            "判断办法不是看有多难受，而是问自己还能不能再撑下去——撑不住就说明"
            "跑快了。训练有素者的门槛配速大约在最大摄氧量的 86%~88%。"
        ),
        sources=("第4章 L1415", "第4章 L1421"),
        related=("tempo-vs-cruise", "six-second-rule-varies"),
        computed_by="pace_set",
    ),
    "tempo-vs-cruise": Topic(
        topic_id="tempo-vs-cruise",
        question="定速节奏跑和巡航间歇有什么区别？",
        keywords=("节奏跑", "巡航间歇", "tempo", "区别", "定速"),
        answer=(
            "定速节奏跑是一次不间断的 T 配速跑，通常约 20 分钟；巡航间歇把它"
            "切成几段，段间做短暂恢复。前者练「维持住」的信心，后者让身体在"
            "门槛强度上待得更久。两者用同一套 T 配速，不要因为中间有休息就跑快。"
        ),
        sources=("第4章 L1425", "第4章 L1427", "第4章 L1449"),
        related=("t-comfortably-hard",),
        computed_by="threshold_cap",
    ),
    "why-i-reps-3-to-5": Topic(
        topic_id="why-i-reps-3-to-5",
        question="I 训练为什么每个回合只跑 3~5 分钟？",
        keywords=("i跑", "i配速", "间歇", "3分钟", "5分钟", "回合", "为什么"),
        answer=(
            "从安静状态升到最大摄氧量大约需要 90~120 秒，回合太短就摸不到峰值；"
            "太长又撑不住，后面的回合会掉速。3~5 分钟是这两头之间的窗口，"
            "所以能以 I 配速跑 1.6 公里的最低 VDOT 是 66。"
        ),
        sources=("第4章 L1480", "第4章 L1484", "第5章 L1784"),
        related=("why-i-recovery-short",),
        computed_by="interval_cap",
    ),
    "why-i-recovery-short": Topic(
        topic_id="why-i-recovery-short",
        question="I 训练的恢复为什么反而要短？",
        keywords=("恢复", "休息", "间歇", "短", "为什么", "i跑", "i配速"),
        answer=(
            "恢复短于跑的时间，氧气摄入来不及回落，下一轮能更快回到峰值，"
            "整个训练累计在最大摄氧量上的时间才够。恢复拖长会让每轮都从"
            "低点重新爬升，浪费回合。"
        ),
        sources=("第4章 L1484", "第4章 L1514", "第4章 L1518"),
        related=("why-i-reps-3-to-5",),
    ),
    "why-h-by-time": Topic(
        topic_id="why-h-by-time",
        question="H 跑为什么按时间而不是按距离？",
        keywords=("h跑", "艰苦跑", "时间", "距离", "为什么"),
        answer=(
            "H 跑只需要「主观上能维持 10~12 分钟的强度」，不规定距离。"
            "地形起伏、有风或在高海拔时，按时间跑不会因为速度达不到预期而"
            "失去训练目的，还便于把不同水平的跑者放在同一堂课里。"
        ),
        sources=("第4章 L1526", "第12章 L3063", "第13章 L3318"),
        related=("why-i-reps-3-to-5",),
        computed_by="h_time_cap",
    ),
    "why-r-needs-full-recovery": Topic(
        topic_id="why-r-needs-full-recovery",
        question="R 跑为什么必须充分恢复？",
        keywords=("r跑", "r配速", "重复", "恢复", "充分", "为什么", "速度"),
        answer=(
            "R 练的是速度、无氧能力和跑步技术。跑不到目标速度，或者跑到技术"
            "变形，这堂课就没有达成目的。所以宁可把恢复拉长到跑时长的 2~3 倍，"
            "也不要靠缩短休息去「加难度」。"
        ),
        sources=("第4章 L1571-L1573", "第4章 L1581"),
        related=("six-second-rule-varies",),
        computed_by="repetition_cap",
    ),
    # ---------------- 周期 ----------------
    "why-phase-order-e-r-i-t": Topic(
        topic_id="why-phase-order-e-r-i-t",
        question="四个阶段为什么按 E→R→I→T 的顺序？",
        keywords=("阶段", "顺序", "四个阶段", "周期", "先练什么"),
        answer=(
            "原则是一个阶段只加一个新压力。从 E 到 R 只增加了速度；从 E 直接"
            "跳到 I 会同时增加速度和有氧压力，身体要同时应付两件事。所以先练"
            "R，再进入 I，最后转 T。"
        ),
        sources=("第6章 L2020", "第6章 L2036", "第6章 L2038"),
        related=("why-phase-4-drops-i",),
        computed_by="plan_schedule",
    ),
    "why-phase-4-drops-i": Topic(
        topic_id="why-phase-4-drops-i",
        question="阶段四为什么要停掉 I 训练？",
        keywords=("阶段四", "停", "i训练", "为什么", "比赛"),
        answer=(
            "5~20 分钟的比赛对有氧系统的压力和一次 I 训练相当，赛季后段的比赛"
            "本身就替代了 I。所以阶段四转向 T，让比赛去承担 I 的作用。"
        ),
        sources=("第6章 L2040", "第6章 L2034"),
        related=("why-phase-order-e-r-i-t",),
    ),
    # ---------------- 剂量与规则 ----------------
    "percent-is-per-session": Topic(
        topic_id="percent-is-per-session",
        question="周跑量 10% 的 T 配速，是每周要凑够 10% 吗？",
        keywords=("百分比", "10%", "上限", "周目标", "单次"),
        answer=(
            "不是。所有这类百分比都是**单次训练**的上限，而不是每周应该达到的量。"
            "书里特意强调过一次：这是建议不要超过的最大量，不是要求你练到的量。"
            "而且违规要按单次判——一周做两次 6 公里的 T，不是「合计 12 公里」才超标，"
            "而是每次 6 公里各自超标。反过来，只要单次没超，一周做几次都不违反这一条；"
            "另设每周次数上限的只有 I（每周不超过两次）。"
        ),
        sources=("第12章 L3154", "第12章 L3156"),
        related=("l-cap-conflict",),
        computed_by="cap_for",
    ),
    "l-cap-conflict": Topic(
        topic_id="l-cap-conflict",
        question="L 跑的上限有 25%、30%、60 分钟、150 分钟几种说法，到底用哪个？",
        keywords=("l跑", "上限", "25%", "30%", "150分钟", "60分钟", "冲突"),
        answer=(
            "按场景分派，不是任选一个：公路且周跑量低于 64 公里用 30%，"
            "达到 64 公里改用 25%，两种情况都与 150 分钟取小；"
            "越野跑阶段一把时间压到 60 分钟；半程马拉松阶段一用 25% 与 150 分钟取小。"
            "本模块把这些分成不同分支实现，不取平均。"
        ),
        sources=("第4章 L1363", "第12章 L3160", "第13章 L3276", "第14章 L3484"),
        related=("why-150-min-cap", "percent-is-per-session"),
        computed_by="long_run_cap",
    ),
    "six-second-rule-varies": Topic(
        topic_id="six-second-rule-varies",
        question="「6 秒规则」是不是所有跑者都适用？",
        keywords=("6秒", "六秒", "规则", "秒差", "i配速", "r配速", "t配速"),
        answer=(
            "只是高水平跑者的近似。VDOT 越低，I 与 R、T 与 I 之间的每 400 米秒差"
            "越大——书里说 VDOT 50 左右用 7 秒，40 左右用 8 秒。所以本模块不强制"
            "秒差为常数，而是按强度定义算出配速后，把实际秒差作为诊断值报出来。"
        ),
        sources=("第5章 L1804",),
        related=("t-comfortably-hard", "why-r-needs-full-recovery"),
        computed_by="pace_set",
    ),
    "why-vdot-update-slow": Topic(
        topic_id="why-vdot-update-slow",
        question="比赛跑好了，为什么不能马上按新成绩提速？",
        keywords=("vdot", "更新", "提速", "频率", "3周", "为什么"),
        answer=(
            "提高训练配速的频率不高于每 3 周一次，即便成绩显示应该更快。"
            "身体需要在一个压力级别上适应几周，刚变好就立刻提速会把适应过程打断，"
            "也容易把短期的状态高峰误当成能力提升。"
        ),
        sources=("第9章 L2605", "第11章 L3009", "第2章 L837"),
        related=("why-hold-4-weeks",),
    ),
    "why-hold-4-weeks": Topic(
        topic_id="why-hold-4-weeks",
        question="为什么加量前要先维持四周？",
        keywords=("加量", "四周", "维持", "为什么", "增加跑量"),
        answer=(
            "先把当前跑量稳定约 4 周，让身体对这个压力完全适应，再往上加。"
            "书里另一处给的是 4~6 周；本模块默认取 4 周，并在文档里标注了区间。"
            "训练不足要好过过度训练。"
        ),
        sources=("第2章 L934", "第15章 L3764", "第11章 L2954"),
        related=("why-vdot-update-slow",),
        computed_by="volume_step_km",
    ),
    "why-novice-table": Topic(
        topic_id="why-novice-table",
        question="表 5—3 和表 5—2 有什么区别？",
        keywords=("表5—3", "新手", "初跑", "低vdot", "区别", "保守"),
        answer=(
            "表 5—3 是后来补的，专门给 VDOT 20~30、在主表里查不到配速的人用。"
            "它的 M 配速按固定的 VDOT 百分比排，比表 5—2 的马拉松等时算法约慢 3%，"
            "对初跑者更保守。本模块默认给引擎值，同时把表 5—3 的整行原值一并给出。"
        ),
        sources=("第5章 L1810-L1812",),
        related=("vdot-vs-vo2max",),
        computed_by="pace_set",
    ),
    # ---------------- 心率与生理 ----------------
    "why-220-age-fails": Topic(
        topic_id="why-220-age-fails",
        question="为什么不能用 220 减年龄估最大心率？",
        keywords=("220", "最大心率", "年龄", "公式", "不准"),
        answer=(
            "这个公式只能估群体，用在个体上误差可以很大。书里举了两个实测例子："
            "一个 30 岁时实测只有 148，另一个 50 岁反而有 192。要用心率指导训练，"
            "就必须实测自己的最大心率。"
        ),
        sources=("第3章 L1184-L1190",),
        related=("why-hr-not-pace",),
    ),
    "why-hr-not-pace": Topic(
        topic_id="why-hr-not-pace",
        question="能不能用心率来控制配速？",
        keywords=("心率", "配速", "控制", "为什么", "热", "风", "坡"),
        answer=(
            "要看目的是什么。热、风、坡、海拔都会让同一配速下的心率变化，"
            "盯着心率跑会让配速偏离计划；反过来，想跑准某个配速就不该看心率。"
            "如果目的是控制强度而不是速度，心率反而很好用。"
        ),
        sources=("第3章 L1166-L1180",),
        related=("why-220-age-fails",),
    ),
    "why-altitude-less-than-vo2max": Topic(
        topic_id="why-altitude-less-than-vo2max",
        question="上高海拔后最大摄氧量掉那么多，为什么成绩没有掉那么多？",
        keywords=("高海拔", "摄氧量", "掉", "成绩", "为什么"),
        answer=(
            "到中等海拔时最大摄氧量会降 12%~16%，但比赛表现只差 6%~8%。"
            "因为空气稀薄，跑同样速度的氧气需求也降低了，损失被效率改善抵回一部分。"
            "短于 800 米的比赛基本不受影响。"
        ),
        sources=("第8章 L2343", "第3章 L1114", "第8章 L2481"),
        related=("why-altitude-same-volume", "why-altitude-r-unchanged"),
        computed_by="altitude_correction",
    ),
    "why-altitude-same-volume": Topic(
        topic_id="why-altitude-same-volume",
        question="上高海拔要不要减跑量？",
        keywords=("高海拔", "跑量", "减量", "要不要"),
        answer=(
            "不必减。所有配速都会自然变慢，对应的是同一个相对强度，所以各强度的"
            "训练时间也可以维持。要注意的是别因为空闲变多就主动加量——加量的"
            "方式和在海平面一样。"
        ),
        sources=("第8章 L2381-L2383", "第8章 L2395"),
        related=("why-altitude-less-than-vo2max",),
    ),
    "why-altitude-r-unchanged": Topic(
        topic_id="why-altitude-r-unchanged",
        question="高海拔时 R 配速要不要调慢？",
        keywords=("高海拔", "r配速", "调慢", "要不要调", "不调", "怎么调"),
        answer=(
            "不用调，只需要增加两次之间的恢复时间。R 练的是速度与技术，跑不到"
            "目标速度就失去意义；而 I、T、M 则要按海拔下调。"
        ),
        sources=("第8章 L2387", "第14章 L3582"),
        related=("why-altitude-less-than-vo2max",),
        computed_by="altitude_correction",
    ),
    # ---------------- 恢复与技术 ----------------
    "why-rest-is-training": Topic(
        topic_id="why-rest-is-training",
        question="休息算不算偷懒？",
        keywords=("休息", "休整", "偷懒", "为什么", "恢复"),
        answer=(
            "休整是训练的组成部分，不是缺席。身体是在两次压力之间的恢复期变强的，"
            "所以拿不准该练哪个时，选压力小的那个通常更划算。"
        ),
        sources=("第2章 L761", "第15章 L3603", "第15章 L3662"),
        related=("why-cross-train", "train-less-not-more"),
    ),
    "why-cross-train": Topic(
        topic_id="why-cross-train",
        question="受伤跑不了，做什么能少掉一点体能？",
        keywords=("受伤", "交叉训练", "替代", "不能跑", "椭圆仪", "游泳"),
        answer=(
            "选不产生冲击、又不会让伤情恶化的方式：水中跑、椭圆仪、单车，"
            "或者在跑步机上走坡。腿部骨折这类完全不能承重的情况，只能靠上肢"
            "做有氧。判断标准只有一条——做完之后伤没有更糟。"
        ),
        sources=("第15章 L3642-L3658",),
        related=("why-rest-is-training",),
    ),
    "train-less-not-more": Topic(
        topic_id="train-less-not-more",
        question="两次训练之间拿不准该练哪个怎么办？",
        keywords=("拿不准", "选择", "过度训练", "保守", "压力小"),
        answer=(
            "选压力小的那个。训练不足要好过过度训练：前者只是慢一点，后者会"
            "用几周甚至几个月来还。"
        ),
        sources=("第2章 L763", "第15章 L3764"),
        related=("why-rest-is-training",),
    ),
    "cadence-180": Topic(
        topic_id="cadence-180",
        question="步频为什么要接近每分钟 180 步？",
        keywords=("步频", "180", "步幅", "为什么"),
        answer=(
            "步频慢意味着滞空时间长、身体被抬得更高，落地时的冲击也更大。"
            "书里观察的 50 名精英跑者中只有一位低于 180；距离变长时减少的是"
            "步幅，而不是步频。"
        ),
        sources=("第2章 L951", "第2章 L965"),
        related=("breathing-2-2",),
    ),
    "breathing-2-2": Topic(
        topic_id="breathing-2-2",
        question="跑步时该怎么呼吸？",
        keywords=("呼吸", "2—2", "2-2", "节奏", "换气"),
        answer=(
            "多数强度下用两步吸、两步呼。这个节奏每分钟换气次数最多、单次气量"
            "又不至于太小，综合换气效率最好。比赛时前三分之二用 2—2，最后三分之一"
            "再转成 2—1 或 1—2；如果前三分之二就撑不住 2—2，说明起跑太快了。"
        ),
        sources=("第2章 L1016-L1028", "第2章 L1042"),
        related=("cadence-180",),
    ),
    "restart-after-break": Topic(
        topic_id="restart-after-break",
        question="停训或受伤中断之后，怎么接回来？",
        keywords=(
            "中断", "停训", "停练", "断训", "伤后", "休息一段", "接回来", "重启",
            "恢复训练", "多久没跑",
        ),
        answer=(
            "不要想着「把缺的补回来」——书里把这件事说得很直接："
            "对休息过一阵的跑者来说，最糟糕的事情莫过于抱着补偿失去的时间的想法"
            "去进行要求较高的训练。它给的办法是退回编号系统的起点：按图 6—2 的顺序"
            "把基础周补回来，再谈质量。同一页还有一句值得记住——"
            "状态稍微欠佳但是身体健康，始终好过因为训练过度或者生病而没法比赛。"
            "接回来之后，先把当前跑量稳住 4~6 周，再按每 3~4 周每次加 1.6 公里的节奏往上走。"
        ),
        sources=("第6章 L2071", "第2章 L934", "第11章 L2956"),
        related=("why-hold-4-weeks", "why-rest-is-training"),
        computed_by="growth_path",
    ),
    "no-periodic-deload": Topic(
        topic_id="no-periodic-deload",
        question="「每四周减量一周」这个安排，书里怎么说的？",
        keywords=(
            "减量", "减量周", "周期性", "恢复周", "每四周", "减多少", "加回来",
        ),
        answer=(
            "书里没有这个概念。全书的减量只有两类：**赛前减量**和**赛后恢复**，"
            "没有任何「每 N 周减 X%」的周期性减量。所以 daniels.deload 只给算术——"
            "哪几周减、各强度的上限变成多少、加到目标跑量要多少周、周表有没有违规——"
            "不生成周表；引用之前必须先说明这是外推，不是书中规则。"
            "赛前减量的具体规则见第 14 章。"
        ),
        sources=("第14章 L3496",),
        related=("why-hold-4-weeks", "why-rest-is-training"),
        computed_by="deload_weeks",
    ),
}


def topic_ids() -> Tuple[str, ...]:
    """全部词条的 id，按字典序。"""
    return tuple(sorted(TOPICS))


#: 检索时忽略的泛词。它们几乎出现在每个提问里，计分只会带来噪声。
_STOPWORDS = frozenset(
    {"为什么", "怎么", "如何", "什么", "是不是", "要不要", "区别"}
)


def explain(topic_id: str) -> Topic:
    """按 id 取词条。

    Raises
    ------
    KeyError
        id 不存在。错误信息里会列出相近的 id。
    """
    if topic_id in TOPICS:
        return TOPICS[topic_id]
    close = [t for t in TOPICS if topic_id.lower() in t.lower()]
    hint = f"，相近的有 {close}" if close else ""
    raise KeyError(f"没有这个词条：{topic_id!r}{hint}")


def search(query: str, limit: int = 3) -> List[Topic]:
    """按关键词检索词条。

    Parameters
    ----------
    query : str
        自然语言提问或几个关键词。
    limit : int, optional
        最多返回几条，默认 3。

    Returns
    -------
    list of Topic
        按匹配得分降序。没有命中时返回空列表，不抛异常。

    Notes
    -----
    这是一个朴素的子串匹配：得分等于命中的关键词长度之和，
    长关键词（如「高海拔」）比短关键词（如「i跑」）权重更高。
    「为什么」「怎么」这类泛词在计分时被忽略，否则它们会把
    几乎所有词条都拉进结果。

    **匹配前会把提问里的空白全部去掉。** 用户习惯在数字两侧留空格，
    「只跑 3 到 5 分钟」里的「5 分钟」被空格切断，不去空白就匹配不到
    「5分钟」这个关键词，整句会变成零命中。

    它的定位是兜底，不是语义检索——真正的语义检索交给上层 RAG。
    """
    if not isinstance(query, str):
        raise TypeError(f"query 必须是字符串，收到 {type(query).__name__}")
    if limit <= 0:
        raise ValueError(f"limit 必须为正，收到 {limit}")

    text = "".join(query.split()).lower()
    scored: List[Tuple[int, Topic]] = []
    for topic in TOPICS.values():
        score = 0
        for keyword in topic.keywords:
            if keyword in _STOPWORDS:
                continue
            if keyword.lower() in text:
                score += len(keyword)
        if score > 0:
            scored.append((score, topic))

    scored.sort(key=lambda item: (-item[0], item[1].topic_id))
    return [topic for _, topic in scored[:limit]]


def _bigrams(text: str) -> set:
    """去掉空白后切成双字组。零依赖的粗粒度相似度就靠它。"""
    cleaned = "".join(ch for ch in text.lower() if not ch.isspace())
    if len(cleaned) < 2:
        return {cleaned} if cleaned else set()
    return {cleaned[i : i + 2] for i in range(len(cleaned) - 1)}


def closeness(query: str, haystack: str) -> float:
    """查询里有几成的双字组出现在候选文本里。0~1。"""
    left, right = _bigrams(query), _bigrams(haystack)
    if not left or not right:
        return 0.0
    return len(left & right) / len(left)


def did_you_mean(
    query: str, limit: int = 2, min_score: float = 0.3
) -> Tuple[Topic, ...]:
    """没有精确命中时，给几个**字面相近**的词条当提示。

    这不是检索，是「你是不是想问」。``search`` 返回空是对的——
    空就代表没命中，不该为了好看硬凑。但只说「没有」对用户没帮助，
    所以单独给一个提示函数，让调用方自己决定要不要印出来。

    相似度只看双字组重合比例：问到「乳酸奶值」（打错「乳酸阈值」）时，
    能靠「乳酸」两个字找到 ``t-comfortably-hard``。

    Parameters
    ----------
    query : str
        用户原话。
    limit : int, optional
        最多给几条，默认 2。
    min_score : float, optional
        相似度门槛，默认 0.3。**这个参数是关键**：没有门槛的话，
        「减量周之后怎么加回来」会提示「跑步时该怎么呼吸」——
        一个错误的提示比没有提示更糟。0.3 是实测出来的：
        打错一个字（「乳酸奶值」）能救回来，纯噪音会被滤掉。

    Returns
    -------
    tuple of Topic
        按相似度降序；没有够格的候选时返回空元组。
    """
    if not isinstance(query, str):
        raise TypeError(f"query 必须是字符串，收到 {type(query).__name__}")
    if limit <= 0:
        raise ValueError(f"limit 必须为正，收到 {limit}")

    scored: List[Tuple[float, Topic]] = []
    for topic in TOPICS.values():
        haystack = " ".join([topic.topic_id, topic.question, *topic.keywords])
        score = closeness(query, haystack)
        if score >= min_score:
            scored.append((score, topic))
    scored.sort(key=lambda item: (-item[0], item[1].topic_id))
    return tuple(topic for _, topic in scored[:limit])
