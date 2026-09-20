# -*- coding: utf-8 -*-
"""
自然语言机构筛选 —— 解析器 / 执行器 / 统计器 / 摘要器
=============================================================================
定位（务必与论文口径一致）：

  本模块只做一件事——把用户的中文自然语言**翻译成结构化的机构筛选条件**，
  再交给数据库去查询真实数据。它不诊断疾病、不推荐医院、不生成任何数字。

  数据流：
    用户自然语言 → 本模块解析 → 结构化条件 → Flask → MySQL（ads_inst_search）
                 → 真实机构数据 → 前端展示 / ECharts 图表

  硬性纪律（答辩必答）：
    ① 本模块**不产生任何机构名称、数量或排名**；所有数字来自 SQL 查询结果。
    ② 解析结果只是一个「条件字典」，用户可在界面上增删改后再查询。
    ③ 无法识别的部分进 unmatched 列表，绝不猜、绝不补默认值。
    ④ 输入若是病征描述（"老人心慌胸闷"），直接拒答并引导到条件式表达，
       因为本项目的数据是**医疗机构资源数据**，不含患者诊疗数据。

  与前端的关系：
    web/app.nlq.js 是本模块的等价 JavaScript 实现（单文件形态离线跑），
    两边词表由 export_lexicon() 统一导出，任何人改词表只需改这一个文件，
    再由 etl/verify_offline_nlq.py 逐用例比对两端结果是否一致。
"""

import re

# =============================================================================
#  一、词表（前端 app.nlq.js 由 export_lexicon() 取用，勿手抄）
# =============================================================================

# 北京市 16 个市辖区 + 经济技术开发区（与 ads_district_overview 实际取值一致）
DISTRICTS = [
    "东城区", "西城区", "朝阳区", "丰台区", "石景山区", "海淀区",
    "门头沟区", "房山区", "通州区", "顺义区", "昌平区", "大兴区",
    "怀柔区", "平谷区", "密云区", "延庆区", "经济技术开发区",
]

DISTRICT_ALIAS = {
    "东城": "东城区", "西城": "西城区", "朝阳": "朝阳区", "丰台": "丰台区",
    "石景山": "石景山区", "海淀": "海淀区", "门头沟": "门头沟区", "房山": "房山区",
    "通州": "通州区", "顺义": "顺义区", "昌平": "昌平区", "大兴": "大兴区",
    "怀柔": "怀柔区", "平谷": "平谷区", "密云": "密云区", "延庆": "延庆区",
    "开发区": "经济技术开发区", "亦庄": "经济技术开发区",
}

# 等级：数据库 level_norm 的取值域
LEVELS = ["三级", "二级", "一级", "未定级"]
LEVEL_RANK = {"三级": 3, "二级": 2, "一级": 1, "未定级": 0}
LEVEL_ALIAS = {
    "三级甲等": "三级", "三级乙等": "三级", "三级丙等": "三级",
    "二级甲等": "二级", "二级乙等": "二级", "二级丙等": "二级",
    "一级甲等": "一级", "一级乙等": "一级", "一级丙等": "一级",
    "三甲": "三级", "三乙": "三级", "三丙": "三级",
    "二甲": "二级", "二乙": "二级", "二丙": "二级",
    "一甲": "一级", "一乙": "一级",
}
# 等级下限表达（"二级以上"）
LEVEL_MIN_WORDS = [
    ("三级以上", 3), ("三级及以上", 3), ("至少三级", 3), ("不低于三级", 3),
    ("二级以上", 2), ("二级及以上", 2), ("至少二级", 2), ("不低于二级", 2),
    ("一级以上", 1), ("一级及以上", 1),
]

# 机构类型：数据库 category_norm 的取值域
# 注意：前 7 项是原有口径；后 3 项（社区卫生服务中心 / 社区卫生服务站 / 村卫生室）
# 由 spark/jobs/layer_dwd.py 的 category_norm 追加分支产出（原先把它们并入"其他机构"）。
CATEGORIES = [
    "医院", "社区卫生服务中心", "社区卫生服务站", "村卫生室",
    "门诊部", "诊所", "妇幼保健", "体检中心", "急救中心", "其他机构",
]
# 长词必须排在短词前面（"社区卫生服务中心" 要先于 "社区卫生服务" 命中）
CATEGORY_ALIAS = {
    "社区卫生服务中心": "社区卫生服务中心", "社区卫生中心": "社区卫生服务中心",
    "社区医院": "社区卫生服务中心", "社区中心": "社区卫生服务中心",
    "社区卫生服务站": "社区卫生服务站", "社区卫生站": "社区卫生服务站",
    "卫生服务站": "社区卫生服务站", "社区站": "社区卫生服务站",
    "村卫生室": "村卫生室", "村级卫生室": "村卫生室", "卫生室": "村卫生室",
    "卫生所": "村卫生室",
    "综合医院": "医院", "专科医院": "医院", "中医医院": "医院", "民营医院": "医院",
    "公立医院": "医院", "医院": "医院",
    "门诊部": "门诊部", "门诊": "门诊部",
    "诊所": "诊所",
    "妇幼保健院": "妇幼保健", "妇幼保健": "妇幼保健", "妇幼": "妇幼保健",
    "体检中心": "体检中心", "体检机构": "体检中心", "体检": "体检中心",
    "急救中心": "急救中心", "急救站": "急救中心", "急救机构": "急救中心", "急救": "急救中心",
    "其他机构": "其他机构", "医务室": "其他机构", "卫生院": "其他机构",
}

# 所有制：数据库 ownership 的取值域
OWNERSHIPS = ["公立", "民营", "未标注"]
OWNERSHIP_ALIAS = {
    "公立": "公立", "公办": "公立", "国立": "公立", "公有制": "公立", "国有": "公立",
    "民营": "民营", "私立": "民营", "民办": "民营", "社会办医": "民营", "社会办": "民营",
    "非公立": "民营", "营利性": "民营",
}

# 数据来源：对 source_files 字段（"|" 分隔的源文件名列表）做规则匹配。
# 这是一条**可追溯**的规则：每个类别的 pattern 直接对源文件名生效，
# 机构是否命中可以在 MySQL 里用同一条正则复算，不存在人工标注。
#   pattern  —— 用于 SQL REGEXP（对源文件名匹配）
#   triggers —— 用于自然语言识别。刻意写得很具体（"医保定点""社区卫生服务机构"），
#               否则"社区卫生服务中心"会被误判成"筛选数据来源"，而不是"筛选机构类型"。
SOURCE_RULES = [
    {"key": "insurance", "label": "医保定点名单", "pattern": "定点|医保",
     "triggers": ["医保定点", "医保", "定点医疗机构", "定点医药", "定点", "医保局"],
     "desc": "市 / 区医保局发布的定点医疗机构名单"},
    {"key": "community", "label": "社区卫生服务机构名录", "pattern": "社区卫生|基层",
     "triggers": ["社区卫生服务机构", "社区卫生服务名录", "基层医疗机构名录", "基层名录"],
     "desc": "社区卫生服务中心 / 服务站基层机构专项名录"},
    {"key": "district_gov", "label": "区级卫健委公开数据",
     "pattern": "东城|西城|朝阳|丰台|石景山|海淀|门头沟|房山|通州|顺义|昌平|大兴|怀柔|平谷|密云|延庆",
     "triggers": ["区级卫健委", "区卫健委", "卫健委公开数据", "卫健委名单", "卫健委"],
     "desc": "各区卫健委发布的辖区医疗机构名录"},
    {"key": "municipal", "label": "市级专项名单", "pattern": "中医|专科|急救|体检|床位|A类|驻区",
     "triggers": ["市级名单", "市级专项", "专项名单", "市卫健委名单"],
     "desc": "中医机构名录、重点专科、急救机构、体检机构等市级专项公开数据"},
]

# 排序：口语 → 后端 sort 取值
SORT_WORDS = [
    ("离我最近", "distance"), ("距离最近", "distance"), ("从近到远", "distance"),
    ("由近及远", "distance"), ("近到远", "distance"), ("按距离", "distance"),
    ("距离优先", "distance"), ("距离升序", "distance"), ("就近", "distance"),
    ("离家近", "distance"), ("离得近", "distance"), ("最近", "distance"),
    ("等级高", "level"), ("等级优先", "level"), ("级别高", "level"),
    ("科室多", "depts"), ("科室数量", "depts"), ("科室覆盖", "depts"),
    ("名称", "name"), ("按名称", "name"), ("拼音", "name"),
    ("匹配度", "score"), ("综合", "score"),
]

# 统计意图：出现这些词 → 用户要的是"数量 / 分布"，不是"清单"
STATS_WORDS = [
    "哪个区", "哪些区", "各区", "每个区", "各区县", "分布", "数量", "有多少", "几家",
    "家数", "统计", "占比", "比重", "比较", "对比", "排名", "排行", "最多", "最少",
    "多少家", "前几", "top", "TOP", "构成", "结构",
]
# 统计维度：口语 → 维度键
DIM_WORDS = [
    ("行政区", "district"), ("区域", "district"), ("区县", "district"),
    ("哪个区", "district"), ("各区", "district"), ("每个区", "district"), ("区", "district"),
    ("机构类型", "category"), ("类型", "category"), ("类别", "category"),
    ("等级", "level"), ("级别", "level"),
    ("所有制", "ownership"), ("办别", "ownership"), ("公立和民营", "ownership"),
    ("主办方", "ownership"), ("经济类型", "ownership"),
    ("数据来源", "source"), ("来源", "source"), ("数据源", "source"),
]
DIM_LABEL = {"district": "行政区", "category": "机构类型", "level": "医院等级",
             "ownership": "所有制", "source": "数据来源"}
# 维度 → 图表类型（前端据此选 ECharts 图形）
DIM_CHART = {"district": "bar", "category": "bar", "level": "pie",
             "ownership": "pie", "source": "bar"}

# =============================================================================
#  二、安全边界：病征 / 诊疗类输入
# =============================================================================
# 本项目的数据是**机构资源数据**，没有患者诊疗数据，也不做医学知识问答。
# 一旦用户输入病征描述，必须明确拒答，而不是硬凑一个"看起来像"的结果。
MEDICAL_WORDS = [
    # 症状
    "发烧", "发热", "咳嗽", "咳痰", "咽痛", "流鼻涕", "鼻塞", "打喷嚏",
    "疼", "痛", "头痛", "头晕", "眩晕", "腹痛", "胃痛", "腰痛", "腿痛", "关节痛",
    "恶心", "呕吐", "腹泻", "便秘", "腹胀", "消化不良", "食欲不振",
    "失眠", "睡不着", "心慌", "心悸", "胸闷", "气短", "呼吸困难", "憋气", "喘",
    "乏力", "水肿", "浮肿", "皮疹", "瘙痒", "过敏", "荨麻疹", "长痘",
    "骨折", "扭伤", "外伤", "流血", "出血", "昏迷", "抽搐", "晕倒", "摔伤",
    # 疾病 / 病情描述（只收词组，避免误伤"疾病预防控制中心"这类机构名）
    "高血压", "糖尿病", "冠心病", "脑梗", "中风", "肿瘤", "癌", "结石", "囊肿",
    "椎间盘", "腰椎", "颈椎", "滑脱", "增生", "风湿", "痛风", "哮喘", "鼻炎",
    "胃病", "胃溃疡", "肝炎", "贫血", "甲亢", "甲状腺", "抑郁", "焦虑", "多动",
    "自闭", "发育迟缓", "营养不良", "近视", "龋齿", "牙疼", "牙痛", "视力下降",
    "看不清", "听不清", "说不清", "走路困难", "活动不便", "精神状态",
    "怀孕", "孕检", "产检", "月经", "备孕",
    # 就诊诉求
    "吃什么药", "用什么药", "吃啥药", "买什么药", "怎么治", "能治好吗", "如何治疗",
    "需要手术", "要手术", "做什么检查", "该做什么检查", "确诊", "是不是得", "是不是患",
    "我得了", "得了什么", "什么病", "严重吗", "严不严重", "怎么办", "挂什么科",
    "该挂哪个科", "挂哪个科", "看什么科", "我应该去", "去哪家医院好", "哪个医院好",
    "能治", "要不要紧", "住院", "预后", "复发",
]
# 就诊者叙述特征：出现"人群词 + 不适/病程词"且全文没有任何机构筛选词时，
# 判定为病征描述（如"75岁女性 腰椎滑脱走路困难"）。这是兜底规则，
# 用来兜住 MEDICAL_WORDS 没收录的新写法。
NARRATIVE_CROWD = ["岁", "患者", "老人", "老年人", "孩子", "小孩", "儿童", "婴儿",
                   "女性", "男性", "孕妇", "我妈", "我爸", "我家"]
NARRATIVE_COURSE = ["困难", "不适", "不舒服", "不好", "厉害", "严重", "反复", "一直",
                    "最近", "总是", "老是", "几天", "好几天", "多年", "加重", "越来越",
                    "很久", "半天", "一周", "疼", "痛"]
MEDICAL_REFUSAL = (
    "当前系统用于北京医疗机构**资源数据的查询与筛选**，不提供疾病诊断、"
    "用药建议或治疗推荐——本项目的数据集里没有患者诊疗数据，也不做医学知识问答。\n"
    "您可以改为描述想查找的机构条件，例如行政区、机构类型、医院等级、所有制、"
    "数据来源或具体科室。"
)

# 免责 / 口径说明（前端"数据来源说明"区块直接展示，保证 AI 边界对用户可见）
AI_SCOPE_NOTE = (
    "AI 只负责理解您的中文描述并生成结构化筛选条件；"
    "机构数量、等级分布等所有数字均来自系统医疗机构数据库的真实查询结果，"
    "AI 不生成机构名称，也不编造任何统计数字。"
)


# =============================================================================
#  三、文本归一
# =============================================================================
_FULL2HALF = {ord(c): ord(c) - 0xFEE0 for c in
              "０１２３４５６７８９ＡＢＣＤＥＦＧＨＩＪＫＬＭＮＯＰＱＲＳＴＵＶＷＸＹＺ"
              "ａｂｃｄｅｆｇｈｉｊｋｌｍｎｏｐｑｒｓｔｕｖｗｘｙｚ（）"}


def normalize(text):
    """全角转半角 + 去空白。空格会破坏"社区卫生服务中心"这类多字词匹配。"""
    t = (text or "").translate(_FULL2HALF)
    return re.sub(r"\s+", "", t)


def _find_all(text, table):
    """在 text 中找出 table 里所有命中的词，返回 [(原始词, 命中位置)]，长词优先。"""
    hits = []
    for word in sorted(table, key=len, reverse=True):
        start = text.find(word)
        while start >= 0:
            hits.append((word, start, len(word)))
            start = text.find(word, start + 1)
    # 长词优先 + 位置靠前优先，避免"社区卫生服务站"被"社区卫生服务"截断
    hits.sort(key=lambda h: (-h[2], h[1]))
    picked, occupied = [], []
    for word, start, ln in hits:
        span = range(start, start + ln)
        if any(i in occupied for i in span):
            continue
        picked.append((word, start, ln))
        occupied.extend(span)
    picked.sort(key=lambda h: h[1])
    return picked


def _mask(text, spans):
    """把已命中的位置替换成占位符，剩下的字符才是"没被理解"的部分。"""
    chars = list(text)
    for start, ln in spans:
        for i in range(start, min(start + ln, len(chars))):
            chars[i] = "\u0000"
    return "".join(chars)


# 剥离残留文本用的功能短语（**必须按长度降序**，否则"医疗机构"会被"机构"先截断）。
# 刻意不收单字"和/中/里/面"这类会出现在机构名里的字。
STOP_PHRASES = sorted([
    # ⚠️ 裸"北京"/"北京市"**不在**这张表里，见下面的 CITY_SCOPE_WORDS：
    #   它是大量真实机构名的前缀（北京大学第一医院 / 北京协和医院 / 北京儿童医院），
    #   全局 replace 会把机构名打成残渣（"北大第一医院"→"大学第一"）。
    "全市", "全域",
    "帮我筛选", "帮我查找", "帮我找", "帮我查", "帮我", "帮忙",
    "查询一下", "查找一下", "筛选一下", "统计一下", "查一下", "看一下",
    "查询", "查找", "筛选", "统计", "检出", "列出", "显示", "看一下", "看看",
    "我想", "我要", "想要", "需要", "请", "麻烦",
    "有哪些", "哪些", "哪种", "哪个区", "哪一个", "哪个", "什么地方", "哪儿",
    "是多少", "多少家", "多少个", "多少", "几家", "几个", "数量", "数目", "家数",
    "分别是", "分别", "各自", "各", "每个区", "每区", "各区", "各个", "所有", "全部",
    "分布情况", "分布", "构成", "结构", "占比", "比例", "比重", "排名", "排行",
    "比较", "对比", "最多", "最少", "最多的是", "的前几", "排名前",
    "数据来源", "来源", "相关", "有关",
    # 统计维度的说法本身不是机构名关键词。
    # 不剥掉的话，「按行政区统计三级医院的数量」会留下 kw="按行政区" 这种残渣，
    # 条件被悄悄收紧 → 统计结果全空，而且**两端一致地错**（一致性校验查不出来）。
    "按行政区", "按区域", "按区县", "按机构类型", "按类型", "按类别",
    "按等级", "按级别", "按所有制", "按办别", "按数据来源", "按来源", "按",
    "行政区", "区域", "区县", "机构类型", "类别", "级别", "所有制", "办别",
    # 统计维度词的**裸词**也要剥：「按机构类型统计全市各类型机构数量」里，
    # "机构类型"被剥掉后仍会剩下一个"类型"，会被当成机构名关键词 → 统计直接归零。
    # 与"按行政区"是同一类残渣，凡是维度说法都要在关键词提取前清干净。
    "类型", "等级", "维度", "统计维度", "方面",
    "的机构", "机构", "医疗机构", "医疗卫生机构", "单位",
    "信息", "详细", "情况", "数据", "列表", "清单",
    # 「医保定点名单里有多少家」里的"名单里"是方位残渣：不剥掉会被当成机构名关键词，
    # 条件被悄悄收紧 → 统计/筛选结果全空。与上一组"按行政区"同类，故在此一并收口。
    "名单里", "名单内", "名单中", "名录里", "名单", "名录", "里面", "其中",
    # ---------- 口语填充词："想找个靠谱的大医院""海淀那边有哪些大医院" ----------
    # 为什么必须收：这些词表达的是**意图**，不是机构名。留在 rest 里会被当成机构名
    # 关键词，而机构表里没有任何名字含"想找靠谱大"→ 结果恒为 0，而且**两端一致地错**，
    # 一致性校验查不出来（与上面"按行政区""名单里"是同一类残渣，故在此一并收口）。
    # 收录标准只有一条：**不可能出现在医疗机构名称里**。会出现在机构名里的字
    # （"大""和""中""里"）一律不收 —— "大医院"的"大"改用 DEGREE_ONLY_CHARS 处理。
    "想找找", "想找个", "想找家", "想找", "想看看", "想查询", "想看", "想查",
    "帮我找找", "帮我搜", "帮我看看", "给我找", "给我查",
    "找个", "找家", "找找", "找一下", "找一找", "搜寻", "搜一下", "搜搜", "搜索", "找",
    "有没有", "有的是", "有什么", "能看", "可以看", "能治", "可以治",
    "哪家", "哪几家", "哪几所", "什么样", "怎么样", "如何", "是否", "什么", "啥",
    # 模糊评价词：用户想表达"质量好一点"，不是想按名字搜"靠谱"。
    "靠谱", "好点", "好一点", "好一些", "好些", "不错", "优质", "知名", "有名",
    "著名", "口碑", "正规", "权威", "专业", "厉害",
    # 方位/指代口语："那边/附近"在机构名里不存在。
    "那边", "这边", "那儿", "这儿", "哪里", "附近", "周边", "周围", "身边",
    "就近", "本地",
    "开设有", "开设", "设有", "设置的",
    "有地址", "有详细地址", "有坐标",
    "的", "家", "个", "间", "所", "只", "是", "有", "在", "从", "到", "为", "取自",
    "吗", "呢", "啊", "吧", "请给我", "给我",
    "？", "?", "。", ".", "，", ",", "、", "；", ";", "：", ":", "！", "!", "「", "」",
    "（", "）", "(", ")", "的机构有哪些",
], key=len, reverse=True)


# 城市作用域词："北京市三级医院"里的"北京市"说的是**范围**（整个市），不是机构名前缀。
# 但它同时是大量真实机构名的前缀（北京大学第一医院 / 北京协和医院 / 北京儿童医院），
# 放进 STOP_PHRASES 做全局 replace 会把机构名打成残渣（"北京大学第一" → "大学第一"）。
# 所以单独处理：只有**剥掉之后什么都不剩**时，才认定为范围词并丢弃。
CITY_SCOPE_WORDS = ("北京市", "北京")


# 纯程度/规模残渣：用户说"大医院""好点的医院"时，机构类型"医院"已被识别并遮掉，
# 剩下的"大""好点"是程度词而不是机构名关键词。
# 机构名里确实有"大"（北大医院、人大、大栅栏、大道），所以**不能**做全局剥离，
# 只在 rest 整段都由这些字组成且长度 ≤2 时才丢弃 —— "北京大学第一"这种会被保住。
DEGREE_ONLY_CHARS = "大小好多少远近高低"


# =============================================================================
#  四、解析主函数
# =============================================================================
def parse(text, dept_names=None):
    """把自然语言解析成结构化筛选条件。

    参数
      text        用户输入原文
      dept_names  真实科室名列表（来自 dws_dept_coverage），用于识别"骨科相关机构"。
                  为 None 时不识别科室维度（离线形态可带上快照里的科室表）。

    返回
      {
        ok, intent, conditions, districts, dimension, chart,
        applied[], unmatched[], engine, message, scope_note
      }
      intent ∈ filter | stats | unsupported
    """
    raw = (text or "").strip()
    t = normalize(raw)
    out = {
        "ok": True, "intent": "filter", "query": raw,
        "conditions": {}, "districts": [], "dimension": None, "chart": None,
        "applied": [], "unmatched": [], "engine": "rule",
        "message": "", "scope_note": AI_SCOPE_NOTE,
    }
    if not t:
        out.update(ok=False, intent="unsupported", message="请输入您想查找的机构条件。")
        return out

    spans = []
    cond = {}

    # ---------- 1. 行政区（多值：支持"比较朝阳区和海淀区"） ----------
    dist_hits = _find_all(t, {**{d: d for d in DISTRICTS}, **DISTRICT_ALIAS})
    dists, seen = [], set()
    for word, start, ln in dist_hits:
        name = DISTRICTS[DISTRICTS.index(word)] if word in DISTRICTS else DISTRICT_ALIAS[word]
        if name not in seen:
            seen.add(name)
            dists.append(name)
        spans.append((start, ln))
    if dists:
        cond["district"] = dists

    # ---------- 2. 等级（先认"二级以上"这类下限表达，再认精确等级） ----------
    # 顺序很重要：「二级以上」里含有「二级」，若先认精确等级就会同时产出
    # level=二级 与 level_min=二级，语义互相打架。先占位、再排除重叠。
    level_min = None
    min_spans = []
    for word, rank in sorted(LEVEL_MIN_WORDS, key=lambda x: -len(x[0])):
        pos = t.find(word)
        if pos >= 0:
            level_min = rank
            min_spans.append((pos, len(word)))
            spans.extend(min_spans)
            break
    lv_hits = _find_all(t, {**{d: d for d in LEVELS}, **LEVEL_ALIAS})
    levels, seen_lv = [], set()
    for word, start, ln in lv_hits:
        if any(i in range(start, start + ln) for i in _occupied(min_spans)):
            continue
        name = LEVEL_ALIAS.get(word, word)
        if name not in seen_lv:
            seen_lv.add(name)
            levels.append(name)
        spans.append((start, ln))
    if levels:
        cond["level"] = levels
    if level_min is not None:
        cond["level_min"] = level_min

    # ---------- 3. 机构类型（长词优先，已被等级占用的位置跳过） ----------
    cat_hits = _find_all(t, CATEGORY_ALIAS)
    cats, seen_cat = [], set()
    for word, start, ln in cat_hits:
        if any(i in range(start, start + ln) for i in _occupied(spans)):
            continue
        name = CATEGORY_ALIAS[word]
        if name not in seen_cat:
            seen_cat.add(name)
            cats.append(name)
        spans.append((start, ln))
    if cats:
        cond["category"] = cats

    # ---------- 4. 所有制 ----------
    own_hits = _find_all(t, OWNERSHIP_ALIAS)
    owns, seen_own = [], set()
    for word, start, ln in own_hits:
        name = OWNERSHIP_ALIAS[word]
        if name not in seen_own:
            seen_own.add(name)
            owns.append(name)
        spans.append((start, ln))
    if owns:
        cond["ownership"] = owns

    # ---------- 5. 数据来源（只认"来源类"的具体说法，避免与机构类型抢词） ----------
    srcs = []
    for rule in SOURCE_RULES:
        for w in sorted(rule["triggers"], key=len, reverse=True):
            pos = t.find(w)
            if pos < 0:
                continue
            # "医保定点机构"里的"定点"已属来源语义；但"社区卫生服务中心"里的
            # "社区卫生"不算——所以 triggers 里就没有收录裸"社区卫生"。
            if rule["key"] not in srcs:
                srcs.append(rule["key"])
            spans.append((pos, len(w)))
            break
    if srcs:
        cond["source"] = srcs

    # ---------- 6. 科室（基于真实科室表，不是疾病知识库） ----------
    dept = ""
    if dept_names:
        dh = _find_all(t, {d: d for d in dept_names})
        if dh:
            word, start, ln = dh[0]
            dept = word
            spans.append((start, ln))
            cond["dept"] = word

    # ---------- 7. 结构性附加条件 ----------
    if re.search(r"有地址|有详细地址|地址信息|填了地址", t):
        cond["has_addr"] = True
        spans.append((t.find("地址"), 2))
    if re.search(r"有坐标|有定位|能在地图|地图上", t):
        cond["has_coord"] = True
    if re.search(r"多院区|多个来源|交叉验证|多源", t):
        cond["src_min"] = 2

    # ---------- 7.5 排序偏好（必须先于关键词提取，否则"离我最近"会漏进机构名） ----------
    # 排序词要避开已识别的片段：「综合医院」里的"综合"是机构类型，
    # 不是"按综合评分排序"；「最近」在病征叙述里是"lately"而不是"按距离"。
    _occ = _occupied(spans)
    for word, sort_key in SORT_WORDS:
        pos = t.find(word)
        if pos >= 0 and not any(i in _occ for i in range(pos, pos + len(word))):
            cond["_sort"] = sort_key
            spans.append((pos, len(word)))
            break

    # ---------- 8. 剩余文本 → 机构名关键词 ----------
    # 用**短语**剥离而不是逐字剥离：逐字会把"协和医院"的"和"当成连接词删掉。
    masked = _mask(t, spans)
    # 只有夹在两个已识别片段之间的连接词才是真的连接词（"朝阳区[和]海淀区"）
    masked = re.sub(r"(?<=\x00)[和与及或、](?=\x00)", "", masked)
    rest = masked.replace("\x00", "")
    for phrase in STOP_PHRASES:          # 已按长度降序，长词先删
        rest = rest.replace(phrase, "")
    # 排序说法是"意图"而不是"机构名"。命中的那一个已被 mask 掉，但整句里可能还剩下
    # 别的排序词（「按距离从近到远」命中了"从近到远"，却留下一个"按距离"），
    # 留着就会被当成机构名关键词，把结果掐成 0 条。
    for word, _sort in SORT_WORDS:
        rest = rest.replace(word, "")
    # ① 城市作用域词：剥掉之后什么都不剩 → 用户说的是"整个北京市"这个范围，
    #    不是机构名前缀。只要还剩东西（"北京协和"→"协和"）就原样保留。
    _probe = rest
    for _w in CITY_SCOPE_WORDS:
        _probe = _probe.replace(_w, "")
    if not _probe:
        rest = ""
    # ② 纯程度残渣（"大医院"剩下一个"大"）：不是机构名关键词，也不算"没听懂"。
    if rest and len(rest) <= 2 and all(c in DEGREE_ONLY_CHARS for c in rest):
        rest = ""
    if len(rest) >= 2 and not re.fullmatch(r"[0-9]+", rest):
        cond["kw"] = rest
    elif rest and not re.fullmatch(r"[0-9]+", rest):
        out["unmatched"].append(rest)

    # ---------- 8.5 数据年份：本数据集没有机构级年份字段 ----------
    # 与其假装支持，不如明确告知边界（论文 3.x "数据边界"一节引用此处）。
    if re.search(r"(19|20)\d{2}\s*年?", t):
        out["notice"] = ("当前数据集的机构记录未保留「数据来源年份」字段，"
                         "因此无法按年份筛选；数据来源与批次时效可在「数据整合」"
                         "与「数据质量」页查看。")
        if cond.get("kw") and re.fullmatch(r"(19|20)\d{2}年?", cond["kw"]):
            cond.pop("kw")

    # ---------- 10. 意图判定 ----------
    has_structured = bool(dists or levels or level_min is not None or owns or dept)
    med_hits = [w for w in MEDICAL_WORDS if w in t]
    narrative = (any(w in t for w in NARRATIVE_CROWD)
                 and any(w in t for w in NARRATIVE_COURSE))
    if (med_hits or narrative) and not has_structured:
        out.update(intent="unsupported", conditions={}, districts=[],
                   medical_hits=(med_hits or ["就诊者叙述"])[:5],
                   message=MEDICAL_REFUSAL)
        return out

    stats_like = any(w in t for w in STATS_WORDS)
    dimension = None
    if stats_like:
        for word, dim in DIM_WORDS:
            if word in t:
                dimension = dim
                break
        if dimension is None:
            dimension = "district"
        out["intent"] = "stats"
        out["dimension"] = dimension
        out["chart"] = DIM_CHART.get(dimension, "bar")

    # ---------- 11. 用于展示的"AI 理解了什么" ----------
    out["conditions"] = cond
    out["districts"] = dists
    out["applied"] = describe(cond)
    out["unmatched"] = out["unmatched"][:6]
    if not out["applied"] and out["intent"] == "filter":
        out["message"] = ("暂未识别出明确的机构筛选条件。您可以描述行政区、机构类型、"
                          "医院等级、所有制或数据来源，例如「朝阳区三级公立医院」。")
    return out


def _occupied(spans):
    s = set()
    for start, ln in spans:
        s.update(range(start, start + ln))
    return s


def describe(cond):
    """把条件字典翻译成给人看的标签列表（前端渲染成可删除的条件卡片）。"""
    chips = []
    if cond.get("district"):
        chips.append({"key": "district", "label": "行政区", "values": cond["district"],
                      "text": "、".join(cond["district"])})
    if cond.get("level"):
        chips.append({"key": "level", "label": "医院等级", "values": cond["level"],
                      "text": "、".join(cond["level"])})
    if cond.get("level_min") is not None:
        name = {3: "三级", 2: "二级", 1: "一级"}.get(cond["level_min"], "")
        chips.append({"key": "level_min", "label": "等级下限", "values": [cond["level_min"]],
                      "text": name + "及以上"})
    if cond.get("category"):
        chips.append({"key": "category", "label": "机构类型", "values": cond["category"],
                      "text": "、".join(cond["category"])})
    if cond.get("ownership"):
        chips.append({"key": "ownership", "label": "所有制", "values": cond["ownership"],
                      "text": "、".join(cond["ownership"])})
    if cond.get("source"):
        labels = {r["key"]: r["label"] for r in SOURCE_RULES}
        chips.append({"key": "source", "label": "数据来源", "values": cond["source"],
                      "text": "、".join(labels.get(k, k) for k in cond["source"])})
    if cond.get("dept"):
        chips.append({"key": "dept", "label": "科室", "values": [cond["dept"]],
                      "text": cond["dept"]})
    if cond.get("has_addr"):
        chips.append({"key": "has_addr", "label": "数据完整度", "values": [True],
                      "text": "含地址信息"})
    if cond.get("has_coord"):
        chips.append({"key": "has_coord", "label": "数据完整度", "values": [True],
                      "text": "含坐标"})
    if cond.get("src_min"):
        chips.append({"key": "src_min", "label": "数据来源数", "values": [cond["src_min"]],
                      "text": "至少 %d 个来源" % cond["src_min"]})
    if cond.get("kw"):
        chips.append({"key": "kw", "label": "机构名称关键词", "values": [cond["kw"]],
                      "text": cond["kw"]})
    if cond.get("_sort"):
        chips.append({"key": "_sort", "label": "排序方式", "values": [cond["_sort"]],
                      "text": SORT_LABEL.get(cond["_sort"], cond["_sort"])})
    return chips


# =============================================================================
#  五、条件 → SQL
# =============================================================================
def build_where(cond):
    """把条件字典编译成 WHERE 子句（全部参数化，杜绝拼接注入）。

    表别名固定为 t，指向 ads_inst_search。
    """
    where, params = ["1=1"], []
    if cond.get("district"):
        marks = ",".join(["%s"] * len(cond["district"]))
        where.append("t.district IN (%s)" % marks)
        params.extend(cond["district"])
    if cond.get("level"):
        marks = ",".join(["%s"] * len(cond["level"]))
        where.append("t.level_norm IN (%s)" % marks)
        params.extend(cond["level"])
    if cond.get("level_min") is not None:
        allowed = [lv for lv, rk in LEVEL_RANK.items() if rk >= cond["level_min"]]
        marks = ",".join(["%s"] * len(allowed))
        where.append("t.level_norm IN (%s)" % marks)
        params.extend(allowed)
    if cond.get("category"):
        marks = ",".join(["%s"] * len(cond["category"]))
        where.append("t.category_norm IN (%s)" % marks)
        params.extend(cond["category"])
    if cond.get("ownership"):
        marks = ",".join(["%s"] * len(cond["ownership"]))
        where.append("t.ownership IN (%s)" % marks)
        params.extend(cond["ownership"])
    if cond.get("source"):
        rules = {r["key"]: r["pattern"] for r in SOURCE_RULES}
        ors, args = [], []
        for key in cond["source"]:
            pat = rules.get(key)
            if not pat:
                continue
            ors.append("t.source_files REGEXP %s")
            args.append(pat)
        if ors:
            where.append("(" + " OR ".join(ors) + ")")
            params.extend(args)
    if cond.get("dept"):
        where.append("t.id IN (SELECT hospital_id FROM dwd_dept_relation_clean"
                     " WHERE dept_name = %s)")
        params.append(cond["dept"])
    if cond.get("has_addr"):
        where.append("t.addr IS NOT NULL AND t.addr <> ''")
    if cond.get("has_coord"):
        where.append("t.lng IS NOT NULL AND t.lat IS NOT NULL")
    if cond.get("src_min"):
        where.append("t.src_count_int >= %s")
        params.append(int(cond["src_min"]))
    if cond.get("kw"):
        where.append("(t.name LIKE %s OR t.addr LIKE %s)")
        params.extend(["%%%s%%" % cond["kw"]] * 2)
    return " AND ".join(where), params


# 条件匹配度：只统计"用户明确说了的条件里，该机构满足几条"，不做任何实力打分。
# 公式（答辩要能写出来）：
#     match = Σ(命中条件的权重) / Σ(全部条件的权重)
# 权重：行政区 0.30 / 等级 0.25 / 类型 0.20 / 所有制 0.15 / 来源 0.10
# 该值只反映"与本次筛选条件的吻合程度"，与医院好坏无关。
MATCH_WEIGHTS = {"district": 0.30, "level": 0.25, "category": 0.20,
                 "ownership": 0.15, "source": 0.10}
MATCH_FORMULA = ("条件匹配度 = 命中条件权重之和 ÷ 本次筛选条件权重之和；"
                 "权重 行政区 0.30 / 等级 0.25 / 类型 0.20 / 所有制 0.15 / 来源 0.10。"
                 "该指标只衡量「与本次条件的吻合程度」，不代表机构实力或好坏。")

ORDER_BY = {
    "score": "score DESC, t.name ASC",
    "distance": "distance_km IS NULL, distance_km ASC, t.name ASC",
    "level": ("CASE t.level_norm WHEN '三级' THEN 3 WHEN '二级' THEN 2"
              " WHEN '一级' THEN 1 ELSE 0 END DESC, t.name ASC"),
    "depts": "t.dept_count DESC, t.name ASC",
    "name": "t.name ASC",
}
SORT_LABEL = {"score": "条件匹配度", "distance": "距离（近→远）", "level": "医院等级",
              "depts": "科室收录量", "name": "机构名称"}


def match_score_sql(cond):
    """按用户实际给出的条件生成匹配度表达式；没有可打分条件时返回常量 1。"""
    parts, total = [], 0.0
    for key, weight in MATCH_WEIGHTS.items():
        if not cond.get(key):
            continue
        total += weight
        if key == "district":
            labels = cond["district"]
            col = "t.district"
        elif key == "level":
            labels = cond["level"]
            col = "t.level_norm"
        elif key == "category":
            labels = cond["category"]
            col = "t.category_norm"
        elif key == "ownership":
            labels = cond["ownership"]
            col = "t.ownership"
        else:
            rules = {r["key"]: r["pattern"] for r in SOURCE_RULES}
            labels = None
            col = None
            for k in cond["source"]:
                parts.append("(t.source_files REGEXP '%s')" % rules[k].replace("'", ""))
            continue
        marks = ",".join("'%s'" % str(v).replace("'", "") for v in labels)
        parts.append("(CASE WHEN %s IN (%s) THEN 1 ELSE 0 END)" % (col, marks))
    if not parts or total <= 0:
        return "1.0", 0.0
    return "ROUND((%s) / %.2f, 4)" % ("+".join(parts), total), total


# =============================================================================
#  六、执行器（由 app.py 注入数据库查询函数，便于单测）
# =============================================================================
# 距离基准：与 /api/institutions 保持同一口径——未指定时按天安门计算，
# 前端把这种情况标注为「距市中心」，避免出现一个"距离"却说不清距离哪里。
DEFAULT_BASE = (116.397428, 39.90923)   # (lng, lat)


def haversine_sql(base_lng, base_lat):
    """生成本次基准点下的球面距离表达式。

    返回 (SQL 片段, 参数列表)。**参数顺序必须与片段中 %s 的出现顺序严格一致**：
    依次是 t.lat 差值的被减数、COS(RADIANS(基准纬))、t.lng 差值的被减数。
    """
    expr = (
        "CASE WHEN t.lng IS NOT NULL AND t.lat IS NOT NULL THEN ROUND(6371 * 2 * ASIN(SQRT("
        " POWER(SIN(RADIANS(t.lat - %s) / 2), 2) + COS(RADIANS(%s)) * COS(RADIANS(t.lat)) *"
        " POWER(SIN(RADIANS(t.lng - %s) / 2), 2))), 2) ELSE NULL END"
    )
    return expr, [base_lat, base_lat, base_lng]


def run_filter(q, cond, page=1, page_size=20, base=None):
    """按条件查真实机构数据。q 是 app.py 的 query(sql, args, one) 函数。

    base 为 (lng, lat) 基准点；不传则按天安门算（与 /api/institutions 一致）。
    """
    where, params = build_where(cond)
    score_sql, _ = match_score_sql(cond)
    lng, lat = base or DEFAULT_BASE
    dist_expr, dist_args = haversine_sql(lng, lat)

    # 计数查询与距离无关：不要把距离 JOIN 拖进来。既省掉一次全表表达式计算，
    # 也避免"占位符比参数多"——那正是这里此前会直接抛 SQL 异常的原因。
    total = q("SELECT COUNT(*) AS n FROM ads_inst_search t WHERE " + where, params, one=True)["n"]

    sort = cond.get("_sort") or "score"
    if sort not in ORDER_BY:
        sort = "score"
    offset = max(0, (page - 1) * page_size)
    # 占位符在 SQL 文本中的先后顺序：score 表达式（无占位符）→ 距离表达式(3) →
    # WHERE 条件(m) → LIMIT / OFFSET(2)。参数必须按同一顺序拼。
    # 距离直接算在 SELECT 列表里（不再套一层 JOIN 子查询）：
    # 子查询里没有 t 这个别名，`t.lng` 会解析失败——这是原先的第二个缺陷。
    rows = q(
        "SELECT t.id, t.name, t.district, t.category_norm AS category, t.category_sub,"
        " t.level_norm AS level, t.ownership, t.addr, t.phone, t.lng, t.lat,"
        " t.coord_precision, t.dept_count, t.src_count_int, t.source_files,"
        " COALESCE(NULLIF(t.key_depts,''), '') AS key_depts,"
        " %s AS distance_km, %s AS score" % (dist_expr, score_sql) +
        " FROM ads_inst_search t WHERE %s ORDER BY %s LIMIT %%s OFFSET %%s"
        % (where, ORDER_BY[sort]),
        dist_args + params + [page_size, offset])
    return {"total": total, "page": page, "page_size": page_size, "sort": sort,
            "base": {"lng": lng, "lat": lat}, "items": rows}


def run_stats(q, cond, dimension):
    """按维度分组统计真实数量。dimension ∈ district/category/level/ownership/source"""
    where, params = build_where(cond)
    if dimension == "district":
        sql = ("SELECT t.district AS name, COUNT(*) AS cnt,"
               " SUM(CASE WHEN t.level_norm='三级' THEN 1 ELSE 0 END) AS level3,"
               " SUM(CASE WHEN t.ownership='公立' THEN 1 ELSE 0 END) AS public_cnt"
               " FROM ads_inst_search t WHERE %s GROUP BY t.district"
               " ORDER BY cnt DESC" % where)
    elif dimension == "category":
        sql = ("SELECT t.category_norm AS name, COUNT(*) AS cnt,"
               " SUM(CASE WHEN t.level_norm='三级' THEN 1 ELSE 0 END) AS level3,"
               " SUM(CASE WHEN t.ownership='公立' THEN 1 ELSE 0 END) AS public_cnt"
               " FROM ads_inst_search t WHERE %s GROUP BY t.category_norm"
               " ORDER BY cnt DESC" % where)
    elif dimension == "level":
        sql = ("SELECT t.level_norm AS name, COUNT(*) AS cnt,"
               " COUNT(DISTINCT t.district) AS district_cnt"
               " FROM ads_inst_search t WHERE %s GROUP BY t.level_norm"
               " ORDER BY cnt DESC" % where)
    elif dimension == "ownership":
        sql = ("SELECT t.ownership AS name, COUNT(*) AS cnt,"
               " SUM(CASE WHEN t.level_norm='三级' THEN 1 ELSE 0 END) AS level3"
               " FROM ads_inst_search t WHERE %s GROUP BY t.ownership"
               " ORDER BY cnt DESC" % where)
    elif dimension == "source":
        conds, args = [where], list(params)
        union = []
        for rule in SOURCE_RULES:
            union.append("SELECT '%s' AS name, COUNT(*) AS cnt FROM ads_inst_search t"
                         " WHERE %s AND t.source_files REGEXP %%s"
                         % (rule["label"], where))
            args.append(rule["pattern"])
        sql = " UNION ALL ".join(union) + " ORDER BY cnt DESC"
        return {"dimension": dimension, "label": DIM_LABEL[dimension],
                "rows": q(sql, args), "chart": DIM_CHART[dimension]}
    else:
        raise ValueError("不支持的统计维度：" + str(dimension))
    rows = q(sql, params)
    return {"dimension": dimension, "label": DIM_LABEL[dimension], "rows": rows,
            "chart": DIM_CHART[dimension]}


def summarize_stats(cond, stats):
    """把统计结果写成一句大白话（**纯模板拼接，不改动任何数字**）。

    这是刻意的设计：大模型可以重写句子，但数字必须来自 SQL。
    模板拼接保证即使模型不可用，用户也能拿到可读的结论。
    """
    rows = [r for r in stats["rows"] if r.get("cnt")]
    if not rows:
        return "按当前条件没有查询到任何机构记录。"
    dim = stats["label"]
    total = sum(r["cnt"] for r in rows)
    head = "根据当前系统数据集，"
    scope = "满足筛选条件的机构共 %d 家，" % total if len(rows) > 1 else ""
    top = rows[0]
    if stats["dimension"] == "district":
        first3 = "；".join("%s %d 家" % (r["name"], r["cnt"]) for r in rows[:3])
        return (head + scope + "按行政区分布，机构数量最多的是 %s（%d 家）。前三位：%s。"
                % (top["name"], top["cnt"], first3))
    if stats["dimension"] == "level":
        order = {"三级": 0, "二级": 1, "一级": 2, "未定级": 3}
        rows = sorted(rows, key=lambda r: order.get(r["name"], 9))
        detail = "；".join("%s %d 家" % (r["name"], r["cnt"]) for r in rows)
        return head + "按医院等级分布：" + detail + "。（" + stats["label"] + "口径）"
    if stats["dimension"] == "ownership":
        detail = "；".join("%s %d 家" % (r["name"], r["cnt"]) for r in rows)
        return head + "按所有制分布：" + detail + "。"
    if stats["dimension"] == "category":
        detail = "；".join("%s %d 家" % (r["name"], r["cnt"]) for r in rows[:6])
        return head + "按机构类型分布，数量最多的是 %s（%d 家）。前六位：%s。" % (
            top["name"], top["cnt"], detail)
    return head + "按%s统计：" % dim + "；".join(
        "%s %d 家" % (r["name"], r["cnt"]) for r in rows) + "。"


def summarize_filter(cond, result):
    """筛选结果的口径说明（同样只做模板拼接）。"""
    if not result["items"]:
        return "按当前条件没有查询到任何机构记录，可放宽条件后重试。"
    chips = describe(cond)
    cond_text = "、".join("%s=%s" % (c["label"], c["text"]) for c in chips) or "全部机构"
    return ("按「%s」在系统数据库中查询到 %d 家机构，本页展示其中 %d 家。"
            % (cond_text, result["total"], len(result["items"]))
            + "列表中的每一项都可以点开查看详情数据来源。")


# =============================================================================
#  七、词表导出（给前端 / 离线形态用，避免手抄漂移）
# =============================================================================
def export_lexicon():
    return {
        "districts": DISTRICTS,
        "district_alias": DISTRICT_ALIAS,
        "levels": LEVELS,
        "level_alias": LEVEL_ALIAS,
        "level_min_words": LEVEL_MIN_WORDS,
        "categories": CATEGORIES,
        "category_alias": CATEGORY_ALIAS,
        "ownerships": OWNERSHIPS,
        "ownership_alias": OWNERSHIP_ALIAS,
        "source_rules": SOURCE_RULES,
        "sort_words": SORT_WORDS,
        "stats_words": STATS_WORDS,
        "dim_words": DIM_WORDS,
        "dim_label": DIM_LABEL,
        "dim_chart": DIM_CHART,
        "medical_words": MEDICAL_WORDS,
        "narrative_crowd": NARRATIVE_CROWD,
        "narrative_course": NARRATIVE_COURSE,
        "stop_phrases": STOP_PHRASES,
        "city_scope_words": list(CITY_SCOPE_WORDS),
        "degree_only_chars": DEGREE_ONLY_CHARS,
        "level_rank": LEVEL_RANK,
        "sort_label": SORT_LABEL,
        "medical_refusal": MEDICAL_REFUSAL,
        "scope_note": AI_SCOPE_NOTE,
        "match_weights": MATCH_WEIGHTS,
        "match_formula": MATCH_FORMULA,
    }
