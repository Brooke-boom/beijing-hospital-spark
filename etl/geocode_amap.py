# -*- coding: utf-8 -*-
"""
高德地图批量地理编码脚本（地址 -> 经纬度）
=============================================
输入：毕设/data/processed/master_institutions.csv（9,791 家机构主表）
输出：毕设/data/processed/geocode_cache.csv（增量缓存，断点续跑）

特性：
  - 断点续跑：已编码的机构自动跳过（按 id 判断），中断后直接重跑即可
  - 限流控制：QPS 间隔 0.15s（个人开发者 QPS 上限 3/s，留安全余量）
  - 失败重试：QPS 超限自动退避重试；地址查不到时降级用「区+机构名」再查
  - 每日额度：--limit 控制本次最多新编码条数（个人免费额度 5,000 次/天）

用法：
  python geocode_amap.py                 # 继续编码（默认本次最多 4600 条）
  python geocode_amap.py --limit 100     # 只编 100 条（试跑）
  python geocode_amap.py --limit 0       # 0 = 不新编码，仅合并输出宽表
"""

import argparse
import csv
import json
import os
import sys
import time
import urllib.parse
import urllib.request

BASE = os.path.expanduser("~/Desktop/毕设")
MASTER = os.path.join(BASE, "data/processed/master_institutions.csv")
CACHE = os.path.join(BASE, "data/processed/geocode_cache.csv")
KEY_FILE = os.path.join(BASE, "data/.amap_key.txt")

API = "https://restapi.amap.com/v3/geocode/geo"
QPS_INTERVAL = 0.15          # 请求间隔（秒）
DAILY_DEFAULT = 4600         # 单次运行默认上限（留余量，防止超 5000/天）


def load_key():
    if not os.path.exists(KEY_FILE):
        sys.exit("未找到 Key 文件：%s\n请把高德 Web服务 Key 存入该文件（单行）。" % KEY_FILE)
    key = open(KEY_FILE, encoding="utf-8").read().strip()
    if len(key) < 20:
        sys.exit("Key 文件内容异常，请检查。")
    return key


def load_cache():
    """读取已有编码缓存：{机构id: (lng, lat, level, formatted, source)}"""
    done = {}
    if os.path.exists(CACHE):
        with open(CACHE, encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                if row.get("id") and row.get("lng"):
                    done[row["id"]] = (
                        row["lng"], row["lat"], row.get("level", ""),
                        row.get("formatted", ""), row.get("src", ""),
                    )
    return done


def geocode(key, address, city="北京"):
    """调用高德地理编码，返回 (lng, lat, level, formatted) 或 None"""
    qs = urllib.parse.urlencode(
        {"address": address, "key": key, "city": city, "citylimit": "true"}
    )
    url = API + "?" + qs
    for attempt in range(4):
        try:
            with urllib.request.urlopen(url, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            if data.get("status") == "1":
                geos = data.get("geocodes") or []
                if geos:
                    g = geos[0]
                    lng, lat = g["location"].split(",")
                    return lng, lat, g.get("level", ""), g.get("formatted_address", "")
                return None          # 查无此地址
            infocode = data.get("infocode", "")
            if infocode in ("10021", "10014"):     # QPS 超限，退避重试
                time.sleep(0.5 * (attempt + 1) + 0.5)
                continue
            if infocode == "10044":                # 日配额用尽
                sys.exit("今日免费额度已用完（infocode=10044），请明天重跑本脚本续跑。")
            if infocode == "10001":
                sys.exit("Key 无效或权限受限（infocode=10001），请检查 Key 与 IP 白名单设置。")
            print("  ! infocode=%s info=%s" % (infocode, data.get("info", "")))
            return None
        except Exception as e:
            if attempt == 3:
                print("  ! 请求异常:", e)
                return None
            time.sleep(1)
    return None


def _s(v):
    """安全转字符串：NaN/None -> ''"""
    if v is None or (isinstance(v, float) and v != v):
        return ""
    return str(v).strip()


def make_addr(rec):
    """构造送入 API 的地址：优先详细地址，缺地址时用 区+机构名 兜底"""
    addr = _s(rec.get("addr"))
    district = _s(rec.get("district"))
    name = _s(rec.get("name"))
    if addr:
        a = addr
    elif district and name:
        a = district + name          # 无地址：区 + 机构名
    else:
        a = name
    if a and not a.startswith("北京"):
        a = "北京市" + a
    return a


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=DAILY_DEFAULT,
                    help="本次最多新编码条数，0 表示不编码")
    args = ap.parse_args()

    key = load_key()
    import pandas as pd
    df = pd.read_csv(MASTER, dtype={"id": str})
    cache = load_cache()
    print("主表机构数: %d | 已有编码: %d | 待编码: %d" % (
        len(df), len(cache), max(0, len(df) - len(cache))))

    if args.limit == 0:
        print("仅统计，不编码。")
        return

    todo = df[~df["id"].isin(cache)].head(args.limit)
    if todo.empty:
        print("全部机构均已编码完成，无需续跑。")
        return
    print("本次计划编码 %d 条..." % len(todo))

    new_file = not os.path.exists(CACHE)
    ok = fail = 0
    t0 = time.time()
    with open(CACHE, "a", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        if new_file:
            w.writerow(["id", "name", "lng", "lat", "level", "formatted", "src"])
        for i, (_, rec) in enumerate(todo.iterrows(), 1):
            rid = rec["id"]
            a1 = make_addr(rec)
            r = geocode(key, a1)
            src = "addr"
            if r is None and _s(rec.get("addr")):
                # 详细地址查不到 -> 降级用 区+机构名
                a2 = "北京市" + _s(rec.get("district")) + _s(rec.get("name"))
                r = geocode(key, a2)
                src = "name"
                time.sleep(QPS_INTERVAL)
            if r:
                lng, lat, level, formatted = r
                w.writerow([rid, rec["name"], lng, lat, level, formatted, src])
                ok += 1
            else:
                w.writerow([rid, rec["name"], "", "", "", "", "failed"])
                fail += 1
            if i % 200 == 0:
                f.flush()
                spd = i / (time.time() - t0)
                print("  进度 %d/%d (成功%d 失败%d) %.1f条/秒 预计剩余%.0f分钟" % (
                    i, len(todo), ok, fail, spd, (len(todo) - i) / max(spd, 0.01) / 60))
            time.sleep(QPS_INTERVAL)
    print("本次完成：成功 %d，失败 %d，耗时 %.1f 分钟" % (ok, fail, (time.time() - t0) / 60))
    print("结果已写入: %s" % CACHE)
    print("明天额度恢复后直接重跑本脚本即可续跑剩余机构。")


if __name__ == "__main__":
    main()
