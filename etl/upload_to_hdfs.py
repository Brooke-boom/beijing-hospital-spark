# -*- coding: utf-8 -*-
"""
原始数据入湖：本地治理后 CSV + MySQL 行为日志 → HDFS /hospital/ods/raw/
================================================================================
复盘标准①：数据分析读取的数据应来自 HDFS。
本源文件负责把"所有分析输入"统一灌入 HDFS，后续 Spark 作业一律从 HDFS 读取。

入湖清单：
  1. data/processed/master_institutions.csv   机构主表（9,789 家）
  2. data/processed/hospital_depts.csv        机构-科室关系
  3. data/processed/dept_dict.csv             标准科室字典
  4. data/processed/specialty_departments.csv 重点专科名单
  5. data/processed/geocode_cache.csv         地理编码缓存（经纬度）
  6. data/processed/disease_dept_map.csv      疾病→科室知识库（导诊）
  7. fact_user_event.csv                      用户行为日志（从 MySQL 导出，供时间维度分析）

幂等：同名文件覆盖（先 delete 再 put，避免 HDFS 覆盖时残留旧块）。
校验：上传后逐个比对 HDFS 文件大小与本地字节数，并统计行数。

运行：
  python3 etl/upload_to_hdfs.py
"""

import os
import subprocess
import sys

import pymysql

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROCESSED = os.path.join(BASE, "data", "processed")
HDFS_RAW = "/hospital/ods/raw"
CONTAINER = "hdfs-namenode"
# 容器内路径：compose 把宿主 ./data 只读挂载到 /opt/workspace/data
CONTAINER_DATA = "/opt/workspace/data/processed"
DOCKER = "/usr/local/bin/docker"

# 本地 CSV → HDFS 文件名
CSV_FILES = [
    "master_institutions.csv",
    "hospital_depts.csv",
    "dept_dict.csv",
    "specialty_departments.csv",
    "geocode_cache.csv",
    "disease_dept_map.csv",
]

MYSQL = dict(host="127.0.0.1", port=3307, user="root", password="hospital123",
             database="hospital", charset="utf8mb4")


def hdfs(*args, check=True, timeout=300):
    """在 namenode 容器内执行 hdfs dfs 命令"""
    cmd = [DOCKER, "exec", CONTAINER, "hdfs", "dfs"] + list(args)
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if check and p.returncode != 0:
        raise RuntimeError("hdfs %s 失败: %s" % (" ".join(args), (p.stderr or p.stdout).strip()[:400]))
    return p.stdout.strip()


def export_behavior_csv():
    """把 MySQL 的用户行为日志导出为 CSV（时间维度的真实数据源）"""
    out = os.path.join(PROCESSED, "fact_user_event.csv")
    conn = pymysql.connect(**MYSQL)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id, ev, k1, k2, num, sid, created_at FROM fact_user_event ORDER BY id")
            rows = cur.fetchall()
    finally:
        conn.close()
    with open(out, "w", encoding="utf-8", newline="") as f:
        f.write("id,ev,k1,k2,num,sid,created_at\n")
        for r in rows:
            vals = []
            for v in r:
                s = "" if v is None else str(v)
                # CSV 转义：逗号/引号/换行
                if any(c in s for c in ',"\n'):
                    s = '"' + s.replace('"', '""') + '"'
                vals.append(s)
            f.write(",".join(vals) + "\n")
    print("  [导出] fact_user_event.csv  %d 行" % len(rows))
    return "fact_user_event.csv"


def upload(name, hdfs_name=None):
    """本地 CSV → HDFS（幂等覆盖）"""
    local = os.path.join(PROCESSED, name)
    if not os.path.exists(local):
        raise FileNotFoundError(local)
    dst = "%s/%s" % (HDFS_RAW, hdfs_name or name)
    hdfs("-rm", "-f", dst, check=False)
    hdfs("-put", "%s/%s" % (CONTAINER_DATA, name), dst)
    return dst


def count_lines_in_hdfs(dst_path):
    """统计 HDFS 文本行数（去掉表头）"""
    out = hdfs("-cat", dst_path, timeout=600)
    return max(len(out.splitlines()) - 1, 0)


def main():
    print("=" * 64)
    print("  原始数据入湖：本地 CSV / MySQL 行为日志 → HDFS %s" % HDFS_RAW)
    print("=" * 64)

    # 0. 确认 HDFS 可用
    try:
        hdfs("-ls", "/")
    except Exception as e:
        print("❌ HDFS 不可用（请先 docker compose up -d namenode datanode）：%s" % e)
        return 1

    hdfs("-mkdir", "-p", HDFS_RAW)
    export_behavior_csv()

    print("\n📤 上传到 HDFS")
    all_files = list(CSV_FILES) + ["fact_user_event.csv"]
    ok = 0
    for name in all_files:
        local = os.path.join(PROCESSED, name)
        local_size = os.path.getsize(local)
        dst = upload(name)
        # 校验：HDFS 文件大小 == 本地字节数
        listing = hdfs("-ls", dst)
        parts = listing.split()
        hdfs_size = int(parts[4]) if len(parts) >= 5 else -1
        flag = "✓" if hdfs_size == local_size else "✗"
        print("  %s %-30s %8d B → %s" % (flag, name, local_size, dst))
        if hdfs_size == local_size:
            ok += 1

    print("\n📊 HDFS 现状（%s）" % HDFS_RAW)
    print(hdfs("-ls", "-h", HDFS_RAW))
    print("\n✅ 入湖完成：%d/%d 个文件字节数一致" % (ok, len(all_files)))
    return 0 if ok == len(all_files) else 1


if __name__ == "__main__":
    sys.exit(main())
