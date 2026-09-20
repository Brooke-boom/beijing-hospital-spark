#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
把自然语言筛选的词表从 web/nlq.py 导出为 JSON，供前端（尤其离线单文件形态）使用。
================================================================================
为什么要有这个脚本：
  单文件形态（dashboard_offline.html）不连后端，解析逻辑必须在前端再实现一份。
  如果词表靠人手抄，改一处漏一处，两端结果就会悄悄分叉——这类问题不会报错，
  只会让"离线算出来的"和"后端算出来的"对不上，属于最难查的一类 bug。

做法：
  唯一的词表来源是 web/nlq.py（Python 字面量）。本脚本直接 import 它并调用
  export_lexicon()，写成 web/nlq_lexicon.json。
  前端 app.nlq.js 只读这份 JSON，一行词表都不硬编码。

一致性校验：
  python3 etl/verify_offline_nlq.py   # 同一批问句在两端解析，逐字段比对

用法：
  python3 etl/export_nlq_lexicon.py
"""

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "web"))

import nlq  # noqa: E402


def main():
    lex = nlq.export_lexicon()
    out = ROOT / "web" / "nlq_lexicon.json"
    payload = {
        "meta": {
            "generated_from": "web/nlq.py::export_lexicon()",
            "note": "由 etl/export_nlq_lexicon.py 自动导出，请勿手工编辑",
            "districts": len(lex["districts"]),
            "categories": len(lex["categories"]),
            "source_rules": len(lex["source_rules"]),
        },
        "lex": lex,
    }
    out.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
                   encoding="utf-8")
    print("  ✓ %s | %.1f KB" % (out.relative_to(ROOT), out.stat().st_size / 1024))
    print("    行政区 %d · 等级 %d · 机构类型 %d · 所有制 %d · 来源规则 %d · 科室别名 %d"
          % (len(lex["districts"]), len(lex["levels"]), len(lex["categories"]),
             len(lex["ownerships"]), len(lex["source_rules"]),
             len(lex["category_alias"])))
    # 自检：词表里不允许出现会互相吞并的短词（"社区卫生服务" 必须排在长词之后）
    long_first = sorted(lex["category_alias"], key=len, reverse=True)
    assert long_first[0] == "社区卫生服务中心", "机构类型别名未按长度降序导出"
    assert lex["medical_refusal"], "缺少医疗边界话术"
    print("  ✓ 词表自检通过（长词优先顺序正确）")


if __name__ == "__main__":
    main()
