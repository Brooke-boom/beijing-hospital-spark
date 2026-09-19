# -*- coding: utf-8 -*-
"""
科室实力指数（department strength）
================================================================================
业务用途：
  为「就医决策」提供**可解释的科室实力分级**。用户问"心慌该去哪家"时，
  系统不只是给出一串医院，而是能说明每家的依据（国家级重点专科 / 市级重点
  专科 / 官网重点科室 / 仅登记开展）。

为什么要在 Spark 层做：
  1. 三个专科来源（national_specialty / municipal_specialty / feature）写法不一，
     需要用同一套归一字典切分、清洗、对齐——这是典型的批处理任务；
  2. 结果被反复查询（每次分诊都要用），预计算一次落库，避免后端每次做字符串匹配；
  3. 这一步让大数据链路真正服务于业务，而不是"为了用 Spark 而用 Spark"。

输入：HDFS /hospital/dwd/dwd_institution_clean
      HDFS /hospital/dwd/dwd_dept_relation_clean
输出：HDFS /hospital/dws/dept/dws_dept_strength
      MySQL ads_dept_strength（服务层）

证据层级（tier，越高越强）：
  4 国家临床重点专科   ← national_specialty
  3 市级重点专科       ← municipal_specialty
  2 官网重点科室       ← feature_level=1
  1 登记重点专科       ← dwd_dept_relation_clean.is_key_specialty=1
  0 已开设             ← dwd_dept_relation_clean 基础关系

实力分（strength）= 层级基准 + 机构等级微调 + 协作网络加成 + 专科集中度加成，
其中"专科集中度"= 本专科在该机构全部重点专科中的占比，用来打破同层级并列，
避免排序退化成按机构名（详见 build_strength 内注释）。

运行（单独）：
  spark-submit --master 'local[*]' jobs/dim_dept_strength.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import DWD, DWS, get_spark, print_section, write_mysql, write_parquet  # noqa: E402
from dept_dict import DEPT_ALIAS, DEPT_CATEGORY  # noqa: E402

from pyspark.sql import functions as F  # noqa: E402

OUT = DWS + "/dept"

# 各层级的基准分（百分制）与机构等级微调 —— 保证同一 tier 内三级高于二级。
# 刻意留出 headroom：实力分 = 层级基准 + 等级微调(≤8) + 网络(≤4) + 专科集中度(≤8)，
# tier4 若从 88 起算，头部机构全部撞上 100 上限被拉平，排序又会退化成按机构名
# （实测"孩子发烧"时北大一与北京儿童医院同分、并列后综合医院反而在前）。
# 取 80 后最高约 100，同层级之间靠集中度拉开差距，层级之间仍保持足够间隔。
TIER_BASE = {4: 80, 3: 64, 2: 46, 1: 28, 0: 10}
TIER_LABEL = {
    4: "国家临床重点专科",
    3: "市级重点专科",
    2: "官网重点科室",
    1: "登记重点专科",
    0: "已开设",
}
# 协作网络 → 对应科室（成员身份作为实力加成，也用于前端标注）
NET_DEPT = {
    "net_pediatric": ["儿科"],
    "net_stroke": ["神经内科", "神经外科", "急诊科", "重症医学科", "康复医学科"],
    "net_neonatal": ["儿科"],
    "net_maternal": ["妇产科", "妇科", "产科"],
}


def _clean_expr(col):
    """切分段的清洗表达式。

    实测源数据里有大量**不成对括号**（如"针灸理疗康复（国家级重点专科"、
    "医信平台口径）"），只删成对括号会留下半截文本当成科室名，
    因此这里按「成对 → 未闭合左 → 未闭合右」三刀清理。
    """
    c = F.trim(col)
    c = F.regexp_replace(c, r"[（(][^（）()]{0,80}[)）]", "")          # 成对括号连内容
    c = F.regexp_replace(c, r"[（(][^（）()]*$", "")                    # 未闭合的左括号及其后
    c = F.regexp_replace(c, r"^[^（()）]*[)）]", "")                    # 未闭合的右括号及其前
    c = F.regexp_replace(c, r"^(另有|另设|另|含|包括|其中|国家|省|市|院级|首都区域|地区)\s*", "")
    c = F.regexp_replace(c, r"^[（()）\s]+", "")
    c = F.regexp_replace(c, r"[;；、,，。.'\"]+$", "")
    return F.trim(c)


def _explode_source(inst, src_col, tier, extra_filter=None):
    """把一个专科来源切分成 (机构 × 科室 × 层级) 长表，并归一科室名。

    分隔符必须同时认「; ； 、 , ，」四种写法：实测 national_specialty 有 22 家医院
    （阜外 / 同仁 / 北京儿童医院 / 人民医院 / 宣武 / 友谊 等）用**顿号**分隔，
    如果只按分号切，整串会被当成一个"科室名"，再被长度上限 14 过滤掉——
    结果是这些国家级重点专科医院在系统里整个丢失国家级证据（阜外的心血管内科
    一度被判成"市级重点专科"，排在综合医院后面）。这正是"就医决策"最不能错的地方。
    """
    df = inst.filter(F.col(src_col).isNotNull() & (F.length(F.col(src_col)) > 0))
    if extra_filter is not None:
        df = df.filter(extra_filter)
    return (
        df.select(
            F.col("id").alias("hospital_id"), "name", "district", "level_norm",
            F.explode(F.split(F.col(src_col), "[;；、,，]")).alias("seg"),
        )
        .withColumn("seg", _clean_expr(F.col("seg")))
        .filter((F.length("seg") >= 2) & (F.length("seg") <= 14))
        .select("hospital_id", "name", "district", "level_norm", "seg",
                F.lit(tier).alias("tier"))
    )


def build_strength(spark, inst, depts):
    print_section("科室实力指数：三来源归一 + 分级")

    # ---------- 1) 归一字典做成维表，用 broadcast join 替代 Python UDF ----------
    alias_rows = [(k, v) for k, v in DEPT_ALIAS.items()] + [(k, k) for k in DEPT_CATEGORY]
    alias_df = spark.createDataFrame(alias_rows, ["seg", "dept_name"]).dropDuplicates(["seg"])
    cat_df = spark.createDataFrame(list(DEPT_CATEGORY.items()), ["dept_name", "dept_category"])

    def _normalize(df):
        """seg → 标准科室名 → 科室大类；识别不了的段落直接丢弃。"""
        return (
            df.join(F.broadcast(alias_df), "seg", "left")
            .withColumn("dept_name", F.coalesce(F.col("dept_name"), F.col("seg")))
            .join(F.broadcast(cat_df), "dept_name", "inner")
            .drop("seg")
        )

    # ---------- 2) 四个证据来源 ----------
    src_nat = _normalize(_explode_source(inst, "national_specialty", 4))
    src_mun = _normalize(_explode_source(inst, "municipal_specialty", 3))
    src_ft = _normalize(_explode_source(inst, "feature", 2,
                                        extra_filter=F.col("feature_level") == "1"))
    # 登记关系层：is_key_specialty=1 → tier 1，否则 tier 0
    src_reg = (
        depts.select(
            F.col("hospital_id"), "dept_name",
            F.when(F.col("is_key_specialty") == "1", 1).otherwise(0).alias("tier"),
        )
        .join(inst.select(F.col("id").alias("hid"), "name", "district", "level_norm"),
              F.col("hospital_id") == F.col("hid"), "inner")
        .drop("hid")
        .join(F.broadcast(cat_df), "dept_name", "inner")
    )

    all_src = src_nat.unionByName(src_mun).unionByName(src_ft).unionByName(src_reg)
    print("    来源切分总量：国家 %d 条 / 市级 %d 条 / feature %d 条 / 登记 %d 条"
          % (src_nat.count(), src_mun.count(), src_ft.count(), src_reg.count()))

    # ---------- 3) 同一(机构,科室)取最高层级为最终层级 ----------
    from pyspark.sql import Window  # noqa: E402
    w = Window.partitionBy("hospital_id", "dept_name").orderBy(F.desc("tier"))
    best = (all_src.withColumn("rn", F.row_number().over(w))
            .filter(F.col("rn") == 1).drop("rn"))

    # ---------- 4) 协作网络成员身份 ----------
    net_cols = [c for c in NET_DEPT if c in inst.columns]
    net_map_rows = [(c, d) for c in net_cols for d in NET_DEPT[c]]
    net_df = spark.createDataFrame(net_map_rows, ["net_col", "dept_name"])
    inst_net = inst.select(F.col("id").alias("hospital_id"), *net_cols)
    net_long = (
        inst_net.select("hospital_id",
                        F.explode(F.array(*[
                            F.struct(F.lit(c).alias("net_col"),
                                     F.when(F.col(c).isNotNull() & (F.length(F.col(c)) > 0),
                                            F.lit(1)).otherwise(F.lit(0)).alias("is_mem"))
                            for c in net_cols
                        ])).alias("nf"))
        .select("hospital_id", F.col("nf.net_col").alias("net_col"), F.col("nf.is_mem").alias("is_mem"))
        .filter(F.col("is_mem") == 1)
        .join(F.broadcast(net_df), "net_col", "inner")
        .select("hospital_id", "dept_name").dropDuplicates()
        .withColumn("is_network", F.lit(1))
    )
    best = best.join(net_long, ["hospital_id", "dept_name"], "left").na.fill({"is_network": 0})

    # ---------- 4.5) 专科集中度：本专科在这家机构全部重点专科里的占比 ----------
    # 为什么需要它：同一层级的机构（都是国家临床重点专科 + 三级）此前各项完全打平，
    # 排序只能退化成按机构名——结果"心慌胸闷"把中医药大学附属医院排在阜外前面。
    # 集中度回答的是"这家机构到底是不是看这个病的地方"：
    #   阜外的重点专科几乎都围绕心血管（2/4 = 0.5），协和摊在二十多个专科上（1/22 ≈ 0.05），
    #   所以同样的国家级证据，阜外的"心血管"身份更明确。
    key_src = (src_nat.select("hospital_id", "dept_name")
               .unionByName(src_mun.select("hospital_id", "dept_name"))
               .unionByName(src_ft.select("hospital_id", "dept_name")))
    hosp_total = key_src.groupBy("hospital_id").agg(F.count(F.lit(1)).alias("key_total"))
    dept_cnt = key_src.groupBy("hospital_id", "dept_name").agg(F.count(F.lit(1)).alias("key_dept"))
    conc = (dept_cnt.join(hosp_total, "hospital_id")
            .withColumn("concentration", F.col("key_dept") / F.col("key_total"))
            .select("hospital_id", "dept_name", "concentration"))
    best = best.join(conc, ["hospital_id", "dept_name"], "left").na.fill({"concentration": 0.0})

    # ---------- 5) 实力分 = 层级基准 + 机构等级微调 + 网络加成 + 专科集中度 ----------
    # 集中度最多 +8 分：只用来打破"同层级同等级"的并列，不会让低层级机构反超高层级
    # （层级基准间隔 20 分，远超 8 分）。
    tier_case = F.when(F.col("tier") == 4, TIER_BASE[4]) \
        .when(F.col("tier") == 3, TIER_BASE[3]) \
        .when(F.col("tier") == 2, TIER_BASE[2]) \
        .when(F.col("tier") == 1, TIER_BASE[1]) \
        .otherwise(TIER_BASE[0])
    level_case = F.when(F.col("level_norm") == "三级", 8) \
        .when(F.col("level_norm") == "二级", 2) \
        .when(F.col("level_norm") == "一级", -2) \
        .otherwise(-6)
    label_case = F.when(F.col("tier") == 4, TIER_LABEL[4]) \
        .when(F.col("tier") == 3, TIER_LABEL[3]) \
        .when(F.col("tier") == 2, TIER_LABEL[2]) \
        .when(F.col("tier") == 1, TIER_LABEL[1]) \
        .otherwise(TIER_LABEL[0])
    conc_case = F.round(F.col("concentration") * 8)

    out = (
        best.withColumn("tier_label", label_case)
        .withColumn("concentration", F.round(F.col("concentration"), 3))
        .withColumn("strength",
                    F.greatest(F.lit(0), F.least(F.lit(100),
                              tier_case + level_case + F.col("is_network") * 4 + conc_case)))
        .select("hospital_id", F.col("name").alias("hospital_name"), "district",
                "level_norm", "dept_name", "dept_category", "tier", "tier_label",
                "is_network", "concentration", "strength")
    )
    return out


def main(spark):
    inst = spark.read.parquet("%s/dwd_institution_clean" % DWD).cache()
    depts = spark.read.parquet("%s/dwd_dept_relation_clean" % DWD).cache()

    out = build_strength(spark, inst, depts).cache()
    write_parquet(out, "%s/dws_dept_strength" % OUT)

    n_all = out.count()
    n_dept = out.select("dept_name").distinct().count()
    n_hosp = out.select("hospital_id").distinct().count()
    print("  ✓ dws_dept_strength: %d 条（%d 家机构 × %d 个科室）" % (n_all, n_hosp, n_dept))
    for t in (4, 3, 2, 1, 0):
        c = out.filter(F.col("tier") == t).count()
        print("      %s：%d 条" % (TIER_LABEL[t], c))

    write_mysql(out, "ads_dept_strength")
    print("  ✓ MySQL ads_dept_strength 落库完成")


if __name__ == "__main__":
    s = get_spark("HospitalDW-DeptStrength")
    try:
        main(s)
    finally:
        s.stop()
