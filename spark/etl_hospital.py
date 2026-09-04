# -*- coding: utf-8 -*-
"""
医院数据 PySpark 数仓分层 ETL
================================
四层架构：ODS（原始）→ DWD（清洗）→ DWS（汇总）→ ADS（应用）

数据流：
  1. ODS：原样读取 CSV，schema 与源文件一致
  2. DWD：清洗（去空、去脏、统一编码）+ 关联坐标（join geocode_cache）
  3. DWS：按区域/等级/类型/科室 4 个维度轻度聚合
  4. ADS：服务应用的宽表与统计（写 MySQL，Flask 直接查）

输入：
  - /opt/workspace/data/processed/master_institutions.csv  (9,789 家机构，govern_master.py 治理后含
    ownership/ownership_basis/category_sub/feature/feature_level 5 个治理列)
  - /opt/workspace/data/processed/hospital_depts.csv       (16,310 条科室映射)
  - /opt/workspace/data/processed/dept_dict.csv            (32 个标准科室)
  - /opt/workspace/data/processed/specialty_departments.csv (20 家重点专科)
  - /opt/workspace/data/processed/geocode_cache.csv        (地理编码缓存)

输出（MySQL hospital 库）：
  - ods_institution / ods_dept_relation / ods_specialty / ods_geocode
  - dwd_institution_clean / dwd_dept_clean / dwd_specialty_clean
  - dws_inst_by_district / dws_inst_by_level / dws_inst_by_category / dws_dept_coverage
  - ads_inst_search / ads_district_overview / ads_specialty_hospital / ads_level_overview

运行：
  docker exec spark-master /opt/spark/bin/spark-submit \
    --master spark://spark-master:7077 \
    --jars /opt/workspace/jobs/mysql-connector-j-8.4.0.jar \
    --driver-class-path /opt/workspace/jobs/mysql-connector-j-8.4.0.jar \
    /opt/workspace/jobs/etl_hospital.py
"""

import os
from pyspark.sql import SparkSession
from pyspark.sql import functions as F
from pyspark.sql.types import StringType, DoubleType

# ============== 配置 ==============
DATA = "/opt/workspace/data/processed"
MYSQL_URL = "jdbc:mysql://hospital-mysql:3306/hospital?useSSL=false&allowPublicKeyRetrieval=true&serverTimezone=Asia/Shanghai"
MYSQL_PROPS = {
    "user": "root",
    "password": "hospital123",
    "driver": "com.mysql.cj.jdbc.Driver",
    "rewriteBatchedStatements": "true",
}
MYSQL_APP_URL = "jdbc:mysql://hospital-mysql:3306/hospital?useSSL=false&allowPublicKeyRetrieval=true&serverTimezone=Asia/Shanghai"
MYSQL_APP_PROPS = {
    "user": "app",
    "password": "app123",
    "driver": "com.mysql.cj.jdbc.Driver",
}


# ============== 工具函数 ==============
def write_mysql(df, table, mode="overwrite"):
    """DataFrame 写入 MySQL"""
    df.write.jdbc(
        url=MYSQL_URL,
        table=table,
        mode=mode,
        properties=MYSQL_PROPS,
    )


def print_section(title):
    print("\n" + "=" * 60)
    print("  %s" % title)
    print("=" * 60)


# ============== 主流程 ==============
def main():
    spark = (
        SparkSession.builder
        .appName("HospitalDataWarehouse")
        .config("spark.sql.adaptive.enabled", "true")
        .config("spark.driver.memory", "1g")
        .getOrCreate()
    )
    spark.sparkContext.setLogLevel("WARN")
    print("✅ Spark %s 已启动" % spark.version)

    # ============== ODS 层：原始数据落库 ==============
    print_section("ODS 层：原始数据入库")
    inst_ods = spark.read.csv(
        os.path.join(DATA, "master_institutions.csv"),
        header=True, encoding="utf-8", multiLine=True,
    )
    print("  ods_institution: %d 行 × %d 列" % (inst_ods.count(), len(inst_ods.columns)))
    write_mysql(inst_ods, "ods_institution")
    print("  ✓ 写入 ods_institution")

    depts_ods = spark.read.csv(
        os.path.join(DATA, "hospital_depts.csv"),
        header=True, encoding="utf-8", multiLine=True,
    )
    print("  ods_dept_relation: %d 行" % depts_ods.count())
    write_mysql(depts_ods, "ods_dept_relation")
    print("  ✓ 写入 ods_dept_relation")

    dept_dict_ods = spark.read.csv(
        os.path.join(DATA, "dept_dict.csv"),
        header=True, encoding="utf-8",
    )
    print("  ods_dept_dict: %d 行" % dept_dict_ods.count())
    write_mysql(dept_dict_ods, "ods_dept_dict")
    print("  ✓ 写入 ods_dept_dict")

    specialty_ods = spark.read.csv(
        os.path.join(DATA, "specialty_departments.csv"),
        header=True, encoding="utf-8",
    )
    print("  ods_specialty: %d 行" % specialty_ods.count())
    write_mysql(specialty_ods, "ods_specialty")
    print("  ✓ 写入 ods_specialty")

    geo_ods = spark.read.csv(
        os.path.join(DATA, "geocode_cache.csv"),
        header=True, encoding="utf-8", multiLine=True,
    )
    geo_count = geo_ods.count()
    print("  ods_geocode: %d 行" % geo_count)
    write_mysql(geo_ods, "ods_geocode")
    print("  ✓ 写入 ods_geocode")

    # ============== DWD 层：清洗 + 关联 ==============
    print_section("DWD 层：清洗关联")

    # 机构主表清洗 + 关联坐标
    # 防御性清洗：id 必须是纯数字（multiLine 修复前的历史脏行防御）+ 按 id 去重
    inst_dwd = (
        inst_ods
        .filter(F.col("id").isNotNull() & (F.length(F.col("id")) > 0))
        .filter(F.col("id").rlike("^\\d+$") & (F.length(F.col("id")) <= 6))
        .filter(F.col("name").isNotNull() & (F.length(F.col("name")) > 0))
        .dropDuplicates(["id"])
        # 区名清洗：去掉 "北京xx区" 中的 "北京"
        .withColumn(
            "district_clean",
                F.when(F.col("district").startswith("北京"), F.substring(F.col("district"), 3, 20))
                .when(F.col("district").endswith("县"), F.concat(F.col("district"), F.lit("")))
                .otherwise(F.col("district"))
        )
        # 等级归一化
        .withColumn(
            "level_norm",
            # 口径治理：诊所/村卫生室/门诊部/社区卫生服务站/医务室/急救/疾控/体检等
            # 机构不参加医院等级评审，单独归为"不适用医院分级"，
            # 避免与真正"应参评但缺等级"的"未定级"混为一谈（原实现会把 8504 家计入未定级）
            F.when(F.col("grade_scope") == "not_applicable", F.lit("不适用医院分级"))
            .when(F.col("level").isin("三级", "三级甲等", "三级乙等", "三级丙等"), F.lit("三级"))
            .when(F.col("level").isin("二级", "二级甲等", "二级乙等", "二级丙等"), F.lit("二级"))
            .when(F.col("level").isin("一级", "一级甲等", "一级乙等", "一级丙等"), F.lit("一级"))
            .when(F.col("level_sub").isin("甲等", "甲"), F.lit("甲"))
            .otherwise(F.lit("未定级"))
        )
        # 类型归一化
        .withColumn(
            "category_norm",
            F.when(F.col("category").contains("医院"), F.lit("医院"))
            .when(F.col("category").contains("诊所"), F.lit("诊所"))
            .when(F.col("category").contains("门诊"), F.lit("门诊部"))
            .when(F.col("category").contains("疾控"), F.lit("疾控中心"))
            .when(F.col("category").contains("妇幼"), F.lit("妇幼保健"))
            .when(F.col("category").contains("急救"), F.lit("急救中心"))
            .when(F.col("category").contains("血液"), F.lit("血站"))
            .when(F.col("category").contains("体检"), F.lit("体检中心"))
            .otherwise(F.lit("其他机构"))
        )
        # 坐标关联（geocode 缓存按 id 去重，防止 join 膨胀）
        .join(
            geo_ods.select("id", "lng", "lat", "level", "formatted", "src")
                   .dropDuplicates(["id"])
                   .withColumnRenamed("level", "coord_level")
                   .withColumnRenamed("formatted", "coord_formatted")
                   .withColumnRenamed("src", "coord_source"),
            on="id", how="left"
        )
        # 经纬度转 Double
        .withColumn("lng_d", F.col("lng").cast(DoubleType()))
        .withColumn("lat_d", F.col("lat").cast(DoubleType()))
        # 坐标精度桶
        .withColumn(
            "coord_precision",
            F.when(F.col("lng_d").isNull(), F.lit("missing"))
            .when(F.col("coord_level").isin("门址", "兴趣点"), F.lit("high"))
            .otherwise(F.lit("rough"))
        )
        # 数据来源计数（来自 src_count）
        .withColumn("src_count_int", F.col("src_count").cast("int"))
        .select(
            "id", "name", "district_clean", "category", "category_norm",
            "category_sub",
            "level", "level_sub", "level_norm", "grade_scope",
            "addr", "phone", "postal", "beds", "key_depts",
            "feature", "feature_level",
            "ownership", "ownership_basis",
            "lng_d", "lat_d", "coord_formatted", "coord_level", "coord_source", "coord_precision",
            "econ", "profit", "category_raw", "src_count_int", "source_files",
        )
        .withColumnRenamed("district_clean", "district")
        .withColumnRenamed("lng_d", "lng")
        .withColumnRenamed("lat_d", "lat")
    )
    n_dwd = inst_dwd.count()
    print("  dwd_institution_clean: %d 行（清洗后）" % n_dwd)
    write_mysql(inst_dwd, "dwd_institution_clean")
    print("  ✓ 写入 dwd_institution_clean")

    # 科室映射清洗
    depts_dwd = (
        depts_ods
        .filter(F.col("hospital_id").isNotNull())
        .filter(F.col("dept_name").isNotNull())
        .select("hospital_id", "dept_name", "source", "is_key_specialty")
    )
    write_mysql(depts_dwd, "dwd_dept_relation_clean")
    print("  ✓ 写入 dwd_dept_relation_clean")

    # 重点专科清洗
    specialty_dwd = (
        specialty_ods
        .filter(F.col("hospital").isNotNull())
        .select("hospital", "specialties")
        .withColumnRenamed("hospital", "hospital_name")
        .withColumnRenamed("specialties", "specialty_name")
    )
    write_mysql(specialty_dwd, "dwd_specialty_clean")
    print("  ✓ 写入 dwd_specialty_clean")

    # ============== DWS 层：4 个维度汇总 ==============
    print_section("DWS 层：多维汇总")

    # 按区统计
    dws_district = (
        inst_dwd.groupBy("district")
        .agg(
            F.count("id").alias("inst_count"),
            F.countDistinct("category_norm").alias("category_diversity"),
            F.sum(F.when(F.col("level_norm") == "三级", 1).otherwise(0)).alias("level_3_count"),
            F.sum(F.when(F.col("level_norm") == "二级", 1).otherwise(0)).alias("level_2_count"),
            F.sum(F.when(F.col("coord_precision") == "high", 1).otherwise(0)).alias("coord_high_count"),
            F.sum(F.when(F.col("coord_precision") == "rough", 1).otherwise(0)).alias("coord_rough_count"),
            F.sum(F.when(F.col("coord_precision") == "missing", 1).otherwise(0)).alias("coord_missing_count"),
            # 公立/民营归属（govern_master.py 规则引擎产出）
            F.sum(F.when(F.col("ownership") == "公立", 1).otherwise(0)).alias("public_count"),
            F.sum(F.when(F.col("ownership") == "民营", 1).otherwise(0)).alias("private_count"),
            F.sum(F.when(F.col("ownership") == "未标注", 1).otherwise(0)).alias("ownership_unknown_count"),
        )
        .filter(F.col("district").isNotNull() & (F.length(F.col("district")) > 0))
        .orderBy(F.desc("inst_count"))
    )
    write_mysql(dws_district, "dws_inst_by_district")
    print("  ✓ dws_inst_by_district: %d 行（按区）" % dws_district.count())

    # 按等级统计
    dws_level = (
        inst_dwd.groupBy("level_norm")
        .agg(
            F.count("id").alias("inst_count"),
            F.countDistinct("district").alias("district_count"),
            F.countDistinct("category_norm").alias("category_count"),
        )
        .orderBy(F.desc("inst_count"))
    )
    write_mysql(dws_level, "dws_inst_by_level")
    print("  ✓ dws_inst_by_level: %d 行（按等级）" % dws_level.count())

    # 按类型统计
    dws_category = (
        inst_dwd.groupBy("category_norm")
        .agg(
            F.count("id").alias("inst_count"),
            F.countDistinct("district").alias("district_count"),
            F.sum(F.when(F.col("level_norm") == "三级", 1).otherwise(0)).alias("level_3_count"),
        )
        .orderBy(F.desc("inst_count"))
    )
    write_mysql(dws_category, "dws_inst_by_category")
    print("  ✓ dws_inst_by_category: %d 行（按类型）" % dws_category.count())

    # 科室覆盖度统计
    dws_dept_cov = (
        depts_dwd.groupBy("dept_name")
        .agg(
            F.countDistinct("hospital_id").alias("hospital_count"),
            F.sum(F.when(F.col("is_key_specialty") == "1", 1).otherwise(0)).alias("key_specialty_count"),
        )
        .orderBy(F.desc("hospital_count"))
    )
    write_mysql(dws_dept_cov, "dws_dept_coverage")
    print("  ✓ dws_dept_coverage: %d 行（按科室）" % dws_dept_cov.count())

    # ============== ADS 层：服务应用 ==============
    print_section("ADS 层：应用服务层")

    # ADS1: 筛选排序主表（Flask 搜索用）
    # 关联机构 + 科室聚合 + 重点专科标记
    inst_with_dept_count = (
        depts_dwd.groupBy("hospital_id")
        .agg(
            F.count("dept_name").alias("dept_count"),
            F.sum(F.when(F.col("is_key_specialty") == "1", 1).otherwise(0)).alias("key_specialty_count"),
        )
    )
    # 重点专科数口径治理：
    # 原实现用 depts_dwd.is_key_specialty=='1' 计数，hospital_depts.csv 几乎无该标记，
    # 导致协和/北医/积水潭等真正重点三甲 key_specialty_count 全为 0。
    # 权威口径 = feature 三级分级（govern_master.py 产出）：
    #   L1(重点专科/重点科室) → 以 feature 分号数作为重点专科数
    #   L2(登记诊疗科目/优势科室) → 以 key_depts 项数作为优势科室数（非重点专科，标注 L2）
    #   L3(普通临床科室) / 无 feature → 0
    inst_feature_cnt = inst_dwd.select(
        "id", "feature", "feature_level"
    ).withColumn(
        "fk_cnt",
        F.when(F.col("feature_level") == "1", F.size(F.split(F.col("feature"), ";")))
        .otherwise(0)
    ).select("id", "fk_cnt")
    ads_inst_search = (
        inst_dwd
        .join(inst_with_dept_count,
              inst_dwd["id"] == inst_with_dept_count["hospital_id"], "left")
        .drop("hospital_id")
        .join(inst_feature_cnt, "id", "left")
        # 重点专科数：仅计入权威 feature L1（重点专科/重点科室）科系数，
        # L2(登记诊疗科目/优势科室) 与 L3(普通临床科室) 不属于"重点专科"，不计入；无则兜底 depts 计数
        .withColumn(
            "key_specialty_count",
            F.when(F.col("fk_cnt").isNotNull() & (F.col("fk_cnt") > 0), F.col("fk_cnt"))
            .otherwise(F.col("key_specialty_count"))
        )
        .drop("fk_cnt")
        .na.fill({"dept_count": 0, "key_specialty_count": 0})
    )
    write_mysql(ads_inst_search, "ads_inst_search")
    print("  ✓ ads_inst_search: %d 行（筛选主表）" % ads_inst_search.count())

    # ADS2: 区域概览（大屏用）
    ads_district = dws_district.select(
        "district", "inst_count", "category_diversity",
        "level_3_count", "level_2_count",
        "coord_high_count", "coord_rough_count", "coord_missing_count",
        "public_count", "private_count", "ownership_unknown_count",
    )
    write_mysql(ads_district, "ads_district_overview")
    print("  ✓ ads_district_overview: %d 行" % ads_district.count())

    # ADS3: 等级概览
    ads_level = dws_level.select("level_norm", "inst_count", "district_count", "category_count")
    write_mysql(ads_level, "ads_level_overview")
    print("  ✓ ads_level_overview: %d 行" % ads_level.count())

    # ADS4: 专科查医院列表
    # 口径治理：
    #   旧实现 depts_dwd.filter(is_key_specialty=='1') 依赖 hospital_depts.csv 中稀少的标记，
    #   只剩 20 家 / 16 组，而主表 key_specialty_count 已用 feature L1 权威口径(68 家)。
    #   二者不同步。故改为从 inst_dwd.feature(feature_level=='1') 分段展开科室名，
    #   与主表 key_specialty_count 同源，确保专科板与列表数据一致。
    def _clean_spec(seg):
        seg = F.trim(F.regexp_replace(seg, r"[（(][^（）()]{0,80}[)）]", ""))
        seg = F.trim(F.regexp_replace(seg, r"^(另有|另设|另|含|包括|国家|省|市|院级|首都区域|其中)\s*", ""))
        seg = F.trim(F.regexp_replace(seg, r"[;；、,，\s]+$", ""))
        return seg

    spec_flat = (
        inst_dwd
        .filter(F.col("feature_level") == "1")
        .filter(F.col("feature").isNotNull() & (F.length(F.col("feature")) > 0))
        .withColumn("seg", F.explode(F.split(F.col("feature"), "[;；]")))
        .withColumn("seg", _clean_spec(F.col("seg")))
        .filter(F.length(F.col("seg")) >= 2)   # 过滤空/超短噪声
        .filter(F.length(F.col("seg")) <= 14)  # 过滤超长注解残留
        .select(
            F.col("id").alias("hospital_id"),
            "name", "district", "level_norm", "lng", "lat",
            F.col("seg").alias("dept_name"),
            F.lit("feature_l1").alias("source"),
        )
    )
    write_mysql(spec_flat, "ads_specialty_hospital")
    print("  ✓ ads_specialty_hospital: %d 行（专科找医院，feature L1 权威口径）" % spec_flat.count())

    # ============== 验证 ==============
    print_section("校验")
    print("📊 各层表行数（抽样查询）：")
    for table in ["ods_institution", "dwd_institution_clean", "dws_inst_by_district",
                  "ads_inst_search", "ads_district_overview", "ads_specialty_hospital"]:
        df = spark.read.jdbc(MYSQL_URL, table, properties=MYSQL_PROPS)
        print("  %s: %d 行" % (table, df.count()))

    print("\n✅ 全部完成")
    spark.stop()


if __name__ == "__main__":
    main()