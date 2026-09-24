# -*- coding: utf-8 -*-
"""
挂牌名（别名）映射裁定 —— 第二轮治理
====================================
第一轮 `merge_dup_institutions.py` 按「合并挂牌名、保留院区」口径把 9,789 条
收拢为 9,678 条。当时有 9 个名字**既没单独立条、也没保留在任何地方**，
只以「待下一轮联网核实后补录为独立机构」的形式留在报告里 —— 这是一个
**结论错误的待办**：第二轮逐文件回查 + 联网核实后确认，它们全都不是
被误删的独立机构，而是宿主机构执业许可证上的**另一块牌子**
（同一个「医疗机构编码 / 医保定点编码」）。

本脚本不改主表一个字节，只做两件事：
  1. 把 9 条「挂牌名 → 宿主机构」的映射连同**逐条证据**落盘为
     `data/processed/alias_map.csv`（可被论文、答辩、后续检索扩展引用）；
  2. 生成 `data/processed/govern_report_alias.md`，把第一轮那句
     「待补录」改写成**有证据的裁定**，并量化「为什么不单列」。

为什么不是「补 9 行」也不是「把牌子写回 name」
------------------------------------------------
- **补 9 行**：机构总数虚增到 9,687，9 行里只有名字非空（地址/坐标/电话全无，
  而「凭名字臆造地址电话」正是本项目明令禁止的）；且要级联重算快照、三份前端
  产物、线上演示、全套文档与简历。代价与收益完全不成比例。
- **把牌子写回 `name`**：与既有设计冲突。`merge_dup_institutions.py:strip_affix()`
  的既定口径是**合并后的保留行只留主名、剥掉挂牌括注**
  （`北京市中关村医院（中国科学院中关村医院）` → `北京市中关村医院`）。
  写回 name 会被下一轮 `--apply` 原样剥掉，除非另开一张例外名单 —— 那等于
  在一个脚本里放两套互相打架的命名口径。
- **本方案**：`name` 保持主名不变（不动任何统计口径），别名单独成表留档。
  这是「一证一行」口径的自然延伸：一块牌子不是一家机构。

这样处理之后，主表仍然 **9,678 行**，任何字段完整率、任何分布统计都不变。

用法
----
    python etl/build_alias_map.py            # 干跑（只检查并打印）
    python etl/build_alias_map.py --apply    # 落盘 alias_map.csv + 治理报告
"""

import csv
import io
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MASTER = os.path.join(ROOT, "data/processed/master_institutions.csv")
ALIAS_CSV = os.path.join(ROOT, "data/processed/alias_map.csv")
REPORT = os.path.join(ROOT, "data/processed/govern_report_alias.md")

# ---------------------------------------------------------------------------
# 唯一真源：9 条挂牌名 → 宿主机构。
#   alias      被第一轮折掉的挂牌名（原 PENDING_INSTITUTIONS 里的写法）
#   host_id    宿主机构在主表里的 id
#   source     证据出处（文件 + 关键字段），答辩时直接举这一列
#   evidence   依据全文
# ---------------------------------------------------------------------------
ALIASES = [
    {"alias": "北京市东城区交道口社区卫生服务中心", "host_id": "1165",
     "source": "东城区定点医疗机构信息.csv / 医疗机构编码 01110007",
     "evidence": "该表「医疗机构全称」即「北京市第六医院（北京市东城区交道口社区卫生服务中心、"
                 "北京市东城区北新桥社区卫生服务中心）」—— 一个执业编码下三块牌子"},
    {"alias": "北京市东城区北新桥社区卫生服务中心", "host_id": "1165",
     "source": "东城区定点医疗机构信息.csv / 医疗机构编码 01110007",
     "evidence": "同上，与交道口中心同属第六医院一个执业编码；"
                 "《北京市社区卫生服务机构基本信息表》中该街道只有「独立站」（青龙/民安/十三条/海运仓），"
                 "无独立「中心」行"},
    {"alias": "北京市东城区景山社区卫生服务中心", "host_id": "1166",
     "source": "东城区定点医疗机构信息.csv / 医疗机构编码 01110009",
     "evidence": "全称「北京市隆福医院（北京市东城区老年病医院）（东城区景山社区卫生服务中心）」，"
                 "与隆福医院同一编码；该街道在社区机构表中亦只有「独立站」（宽街/魏家/吉祥）"},
    {"alias": "北京市海淀区四季青镇社区卫生服务中心", "host_id": "1494",
     "source": "北京市区属二级三级医院名单.csv / 医疗保险定点医疗机构名单.csv / "
               "北京市健康体检机构信息.csv / 医保编码 08120008",
     "evidence": "三份官方表一致写作「北京四季青医院（北京市海淀区四季青镇社区卫生服务中心）」，"
                 "医保编码同为 08120008、地址同为远大路 32 号"},
    {"alias": "中国科学院中关村医院", "host_id": "1503",
     "source": "市医保局-区属二三级定点医疗机构.csv / 医院编码 8110025；海淀区政府公告 2025-04-18",
     "evidence": "官方写作「北京市中关村医院（中国科学院中关村医院、北京市海淀区老年康复医院）」；"
                 "海淀区政府公告同式，并据此于 2025-04-16 由二级升为三级康复医院"},
    {"alias": "北京市海淀区老年康复医院", "host_id": "1503",
     "source": "同上",
     "evidence": "与中关村医院同为一块牌子（非独立二级医院），故不单列"},
    {"alias": "北京市怀柔区汤河口镇社区卫生服务中心", "host_id": "1308",
     "source": "北京市社区卫生服务机构基本信息表.csv / 怀柔区 1612",
     "evidence": "该表写作「北京市怀柔区第二医院（北京市怀柔区汤河口镇社区卫生服务中心）」，"
                 "地址汤河口大街 5 号、电话 89671926，与宿主行一致；"
                 "同表怀柔区 1610「怀北镇卫生院（怀北镇社区卫生服务中心）」即同一写法，"
                 "主表里本来就是一条记录"},
    {"alias": "北京市顺义区后沙峪镇社区卫生服务中心", "host_id": "1633",
     "source": "市医保局-区属二三级定点医疗机构.csv / 北京市顺义区定点医药机构.csv / 编码 13120002",
     "evidence": "两份官方表一致写作「北京市顺义区空港医院（北京市顺义区后沙峪镇社区卫生服务中心）」，"
                 "地址「后沙峪镇、火沙路 13 号」；社区机构表顺义区 1315 记作"
                 "「后沙峪社区卫生服务中心（空港）」，电话 80496842 与宿主行一致"},
    {"alias": "北京市顺义区牛栏山社区卫生服务中心", "host_id": "1634",
     "source": "北京市顺义区定点医药机构.csv / 顺义区定点医疗机构名单.csv / 编码 13110003",
     "evidence": "写作「北京市顺义区第三医院（北京市顺义区牛栏山社区卫生服务中心）」，"
                 "地址「牛栏山镇、顺焦路 81 号」，编码 13110003；"
                 "⚠️ 宿主不能只按地名挑：同镇的 id 592「北京市顺义区牛栏山镇卫生院」是**另一家**"
                 "（其下属站 5153/5154 各有独立编码 H11011300283 / H11011300284）"},
    {"alias": "北京市平谷区妇幼保健计划生育服务中心", "host_id": "1656",
     "source": "平谷区定点医疗机构信息.csv / 市医保局-区属二三级定点医疗机构.csv / 医院编码 26152001",
     "evidence": "全称「北京市平谷区妇幼保健院(北京市平谷区妇幼保健计划生育服务中心、"
                 "北京市平谷区牙病防治所）」，同一个医院编码"},
    {"alias": "北京市平谷区牙病防治所", "host_id": "1656",
     "source": "同上",
     "evidence": "与平谷妇幼保健院同一执业编码，属挂牌；注意与 id 1307 怀柔区牙病防治所、"
                 "id 1659 延庆区牙病防治所不同 —— 那两家是独立编码的独立机构，本表已单列"},
]


def read_master():
    with io.open(MASTER, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.reader(f))
    return rows[0], rows[1:]


def main():
    apply = "--apply" in sys.argv
    hdr, body = read_master()
    by_id = {r[hdr.index("id")]: r for r in body}
    names = [r[hdr.index("name")] for r in body]

    print("主表：%s" % os.path.relpath(MASTER, ROOT))
    print("机构数：%d（本脚本不改主表）\n" % len(body))

    problems = []
    for a in ALIASES:
        host = by_id.get(a["host_id"])
        if host is None:
            problems.append("宿主 id=%s 不存在" % a["host_id"])
            continue
        a["host_name"] = host[hdr.index("name")]
        a["district"] = host[hdr.index("district")]
        a["category"] = host[hdr.index("category")]
        # 断言：这个挂牌名**从未**作为独立机构存在于主表 —— 证明第一轮没有丢记录
        stand = [n for n in names if n == a["alias"]]
        if stand:
            problems.append("挂牌名「%s」在主表里已是独立记录，映射多余" % a["alias"])

    if problems:
        print("✗ 校验未通过：")
        for p in problems:
            print("   -", p)
        return 2

    print("11 条挂牌名 → %d 家宿主机构（校验通过：均未独立成行）\n"
          % len({a["host_id"] for a in ALIASES}))
    for a in ALIASES:
        print("  %-24s → %s  %s" % (a["alias"], a["host_id"], a["host_name"]))

    n_host = len({a["host_id"] for a in ALIASES})
    print("\n若改为「补 %d 条新行」：机构总数 9,678 → %s，"
          "其中 %d 行除名称外全空。" % (len(ALIASES), format(len(body) + len(ALIASES), ","), len(ALIASES)))

    if not apply:
        print("\n（干跑模式，未写盘。加 --apply 生成 alias_map.csv 与治理报告）")
        return 0

    # ---- alias_map.csv ----
    with io.open(ALIAS_CSV, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["alias_name", "host_id", "host_name", "district", "category",
                    "relation", "source", "evidence"])
        for a in ALIASES:
            w.writerow([a["alias"], a["host_id"], a["host_name"], a["district"],
                        a["category"], "挂牌 / 别名（同一执业编码）",
                        a["source"], a["evidence"]])
    print("[落盘] %s（%d 条映射）" % (os.path.relpath(ALIAS_CSV, ROOT), len(ALIASES)))

    # ---- 治理报告 ----
    with io.open(REPORT, "w", encoding="utf-8") as f:
        f.write("# 挂牌名（别名）裁定报告 —— 第二轮治理\n\n")
        f.write("## 一句话结论\n\n")
        f.write("第一轮合并留下的 9 个「疑似被折叠的独立机构」，经逐文件回查 + 联网核实，"
                "**全部确认为宿主机构执业许可证上的另一块牌子**（同一个医疗机构编码 / "
                "医保定点编码），不是被误删的独立机构。因此**不新增行**，"
                "机构总数仍为 **%s**；映射落盘为 `alias_map.csv`。\n\n" % format(len(body), ","))
        f.write("## 逐条依据（%d 条挂牌名 / %d 家宿主机构）\n\n" % (len(ALIASES), n_host))
        f.write("| 挂牌名 | 宿主 id | 宿主主名 | 区 | 依据出处 |\n|---|---|---|---|---|\n")
        for a in ALIASES:
            f.write("| %s | %s | %s | %s | %s |\n"
                    % (a["alias"], a["host_id"], a["host_name"], a["district"], a["source"]))
        f.write("\n<details><summary>依据全文（点击展开）</summary>\n\n")
        for a in ALIASES:
            f.write("- **%s** → %s %s\n  - %s\n" % (a["alias"], a["host_id"],
                                                     a["host_name"], a["evidence"]))
        f.write("\n</details>\n\n")

        f.write("## 判据：怎么区分「挂牌」和「独立机构」\n\n")
        f.write("同一份《北京市社区卫生服务机构基本信息表》里，两类写法是分开的：\n\n")
        f.write("- **独立机构** —— 以独立的「中心」行出现，有各自的医疗机构编码/医保编码，"
                "例：东城区朝阳门、建国门、和平里…共 9 家；顺义区杨镇、怀柔区各镇卫生院。\n")
        f.write("- **挂牌（别名）** —— 出现在宿主行的括注里，或用同一个编码登记，"
                "例：本次 11 条。\n\n")
        f.write("主表第一轮即按「一证一行」收拢，故挂牌不单列。\n\n")
        f.write("> ⚠️ 挑宿主**不能只按地名**。踩过一次：牛栏山社区卫生服务中心看上去该挂"
                "「牛栏山镇卫生院」，但官方定点表写的是「北京市顺义区**第三医院**"
                "（北京市顺义区牛栏山社区卫生服务中心）」（编码 13110003）—— 同镇两家机构，"
                "挂错了整条链都错。**判据是编码，不是地名。**\n\n")

        f.write("## 为什么不补成新行（代价量化）\n\n")
        f.write("| 方案 | 机构总数 | 空字段 | 级联改动 |\n|---|---|---|---|\n")
        f.write("| 新增 %d 行 | 9,678 → **%s** | %d 行仅名称非空（地址/坐标/电话全无）"
                " | 快照 + 3 份前端产物 + 线上演示 + 全套文档 + 简历/网申全部重算 |\n"
                % (len(ALIASES), format(len(body) + len(ALIASES), ","), len(ALIASES)))
        f.write("| **别名留档（本方案）** | 9,678（**不变**） | 0 | 无 —— 主表零改动 |\n\n")
        f.write("补新行还会与「不写占位值、不凭名字臆造地址电话」的红线冲突："
                "%d 行的地址、坐标、电话在公开渠道均无独立出处。\n\n" % len(ALIASES))

        f.write("## 残留的已知局限（如实记录）\n\n")
        f.write("- 平台当前的机构检索走 `name` 字段，因此按这 11 个挂牌名**直接搜不到宿主行**。\n")
        f.write("  - 部分可间接命中：下属站的名字里带了中心名，例如搜「牛栏山社区卫生服务中心」"
                "会返回其 4 个下属站（5149-5152）。\n")
        f.write("- 后续若要打通，正确做法是让检索同时匹配 `alias_map.csv`，"
                "而不是把牌子塞回 `name` —— 后者与 `merge_dup_institutions.py:strip_affix()` "
                "「保留行只留主名」的既定口径冲突。\n")
    print("[落盘] %s" % os.path.relpath(REPORT, ROOT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
