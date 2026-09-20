#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
机构级「数据来源」字段导出 / 回填
================================================================================
背景（论文「数据模型」一节会写）：
  系统要支持"按数据来源筛选机构"，就必须把**每条记录来自哪些源文件**保留下来。
  这个信息在 ETL 阶段就产生了（master_institutions.csv 的 source_files / src_count），
  并且已经随 DWD → ADS 落进 MySQL 的 ads_inst_search.src_count_int / source_files。

本脚本做两件事：
  1. 从 data/processed/master_institutions.csv 抽出 (id, src_count, source_files)
     → data/processed/inst_source.csv（可追溯的中间产物）
  2. 把这两个字段回填进 web/snapshot_data.json（单文件形态的数据源）

关于第 2 步：正常路径是 web/build_spa.sh 从 MySQL 拉全量快照，SQL 里直接带这两个字段。
  但本机 Docker 守护进程无法启动、MySQL 不可用，无法重跑快照。由于 master 表正是
  DWD 的输入、字段口径完全一致，用它回填与 MySQL 返回的值相同——脚本会在末尾
  打印覆盖率供核对。下次完整构建会自动带上这两个字段，本脚本的第 2 步即可省略。

用法：
  python3 etl/export_inst_source.py            # 导出 + 回填快照
  python3 etl/export_inst_source.py --no-patch # 只导出中间产物
"""

import argparse
import csv
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MASTER = ROOT / "data" / "processed" / "master_institutions.csv"
OUT_CSV = ROOT / "data" / "processed" / "inst_source.csv"
SNAPSHOT = ROOT / "web" / "snapshot_data.json"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-patch", action="store_true", help="只导出中间产物，不改快照")
    args = ap.parse_args()

    if not MASTER.exists():
        print("✗ 缺少 %s（请先跑 ETL 主链路生成机构主表）" % MASTER.relative_to(ROOT))
        return 1

    with open(MASTER, encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    print("  机构主表 %d 行" % len(rows))

    recs = {}
    multi = 0
    for r in rows:
        iid = str(r.get("id") or "").strip()
        if not iid:
            continue
        files = (r.get("source_files") or "").strip()
        try:
            cnt = int((r.get("src_count") or "0").strip() or 0)
        except ValueError:
            cnt = 0
        if not files:
            cnt = 0
        if cnt >= 2:
            multi += 1
        recs[iid] = {"src_count": cnt, "source_files": files}

    with open(OUT_CSV, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["id", "src_count", "source_files"])
        for iid, v in recs.items():
            w.writerow([iid, v["src_count"], v["source_files"]])
    print("  ✓ %s（%d 行，多来源机构 %d 家）" % (OUT_CSV.relative_to(ROOT), len(recs), multi))

    if args.no_patch:
        return 0

    if not SNAPSHOT.exists():
        print("  · 快照不存在，跳过回填")
        return 0
    snap = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    hit = 0
    for inst in snap.get("institutions", []):
        rec = recs.get(str(inst.get("id")))
        if not rec:
            inst.setdefault("src_count", 0)
            inst.setdefault("source_files", "")
            continue
        inst["src_count"] = rec["src_count"]
        inst["source_files"] = rec["source_files"]
        hit += 1
    total = len(snap.get("institutions", []))
    SNAPSHOT.write_text(json.dumps(snap, ensure_ascii=False, separators=(",", ":")),
                        encoding="utf-8")
    print("  ✓ 快照回填 source 字段：%d / %d 命中（%.1f%%）| %.2f MB"
          % (hit, total, hit * 100.0 / max(1, total), SNAPSHOT.stat().st_size / 1048576))
    return 0


if __name__ == "__main__":
    sys.exit(main())
