# -*- coding: utf-8 -*-
"""预热 Agnes 大模型缓存（智能导诊兜底链路）
============================================

为什么需要预热
--------------
Agnes 免费额度实测约 **1 次 / 30~40 秒**，现场连续提问极易触发 429（限流），
界面会长时间停在「导诊中…」。本脚本在演示/答辩前把常用问法跑一遍，
把「问题 → 科室」结果写入 MySQL 的 `dim_ai_cache`，之后同样的提问
零额度、零等待（实测 0.05s 返回）。

用法
----
    # 1) 先启动服务
    bash web/start.sh

    # 2) 预热（默认一批口语长尾问法；约每条 30 秒，请耐心等待）
    python etl/warm_ai_cache.py

    # 自定义问法（用 | 分隔）
    python etl/warm_ai_cache.py --queries "手抖还瘦了很多|眼睛干涩发痒"

    # 预热自然语言筛选解析（NL → 筛选条件）
    python etl/warm_ai_cache.py --kind parse \
        --queries "朝阳区看心脏病的三级医院|离家最近的口腔诊所"

说明
----
- 本地知识库已覆盖的问法会被自动跳过（标 skipped_local），不浪费额度。
- 结果持久化在 MySQL，重启 Flask 依然有效。
"""
import argparse
import json
import urllib.parse
import urllib.request

# 默认预热清单：刻意选「本地 262 条知识库覆盖不到」的口语长句，
# 它们才会真正走大模型兜底，正好是答辩演示最有说服力的样例。
DEFAULT_QUERIES = [
    "我父亲最近手抖得厉害人还瘦了一大圈",
    "眼睛干涩发痒还老想揉",
    "腰背酸痛翻身都费劲",
    "总觉得心口发闷喘不上气",
    "最近掉头发特别厉害",
    "小孩老是抓耳朵还哭闹",
    "手指关节早上起来又僵又痛",
    "晚上睡觉老是盗汗",
]


def main():
    ap = argparse.ArgumentParser(description="预热 Agnes 大模型缓存")
    ap.add_argument("--base", default="http://127.0.0.1:5001",
                    help="Flask 服务地址（默认 http://127.0.0.1:5001）")
    ap.add_argument("--kind", default="triage", choices=["triage", "parse"],
                    help="预热类型：triage(导诊) 或 parse(筛选解析)")
    ap.add_argument("--queries", default="",
                    help="自定义问法，用 | 分隔；留空则用内置清单")
    args = ap.parse_args()

    qs = [x.strip() for x in args.queries.split("|") if x.strip()] \
        if args.queries else DEFAULT_QUERIES

    # 绕过系统代理：沙箱/公司网络代理常拦截 localhost
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    url = (args.base.rstrip("/") + "/api/ai/warm?kind=" + args.kind
           + "&queries=" + urllib.parse.quote("|".join(qs)))
    print(f"预热 {len(qs)} 条问法（kind={args.kind}），免费额度约 1 次/30 秒，"
          f"预计 {len(qs) * 30 // 60} 分钟…\n")
    try:
        with opener.open(urllib.request.Request(url,
                                                headers={"Host": "127.0.0.1"}),
                         timeout=1800) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        print("❌ 预热失败：", e)
        print("   请确认 Flask 已启动（bash web/start.sh）")
        raise SystemExit(1)

    if not data.get("ok"):
        print("❌ 预热未生效：", data)
        raise SystemExit(1)

    icon = {"ok": "✅", "cached": "♻️", "skipped_local": "⏭️",
            "rate_limited": "⏳", "error": "⚠️"}
    n_ok = n_cached = n_skip = n_bad = 0
    for r in data["results"]:
        st = r.get("status")
        line = f"  {icon.get(st, '?')} [{st}] {r['q']}"
        if st == "ok":
            n_ok += 1
            line += "  → " + ("、".join(r["depts"]) if r.get("depts")
                              else str(r.get("conditions")))
        elif st == "cached":
            n_cached += 1
        elif st == "skipped_local":
            n_skip += 1
        else:
            n_bad += 1
            if r.get("detail"):
                line += "  " + str(r["detail"])[:80]
        print(line)

    print(f"\n完成：新增 {n_ok} / 已有缓存 {n_cached} / "
          f"本地已覆盖跳过 {n_skip} / 失败 {n_bad}")
    if n_bad:
        print("提示：失败多为免费额度限流，隔几分钟重跑本脚本即可（已成功的不会重复消耗）。")


if __name__ == "__main__":
    main()
