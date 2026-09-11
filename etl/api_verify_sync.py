#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""工作区 ↔ GitHub 远端 同步校验（不依赖本地 .git 对象库）。

背景
----
本项目用 GitHub Git Data API 提交后，commit/tree/blob 对象只存在于远端，
本地 .git/objects 缺这些对象，导致 `git status` / `git diff` 报
`fatal: bad object HEAD`，无法用常规方式判断"有没有没推上去的改动"。

本脚本绕开该限制：直接用 GitHub API 拉远端 tree，把每个 blob 的 SHA
与本地文件重算的 git blob SHA 对比，逐文件判定是否同步。

依赖的本地 git 能力（这些不读对象库，实测仍可用）：
  - `git ls-files -z`                        → 已跟踪文件清单
  - `git ls-files -o --exclude-standard -z`  → 未跟踪且未被忽略的新文件

用法
----
  python3 etl/api_verify_sync.py            # 校验
  python3 etl/api_verify_sync.py --quiet    # 只输出结论行（供脚本串联）

退出码：0 = 完全同步；1 = 存在未推送改动 / 新增未提交文件；2 = 执行出错。
"""
import hashlib
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request

REPO = "Brooke-boom/beijing-hospital-spark"
ROOT = "/Users/brooke/Desktop/毕设"
API = "https://api.github.com"
BRANCH = "main"

QUIET = "--quiet" in sys.argv


def sh(cmd):
    """执行命令，返回原始字节（避免非 ASCII 路径被 git 加引号转义）。"""
    return subprocess.run(cmd, shell=True, capture_output=True).stdout


def sh_lines(cmd):
    """按 NUL 切分，取得原始路径字符串列表。"""
    out = sh(cmd)
    return [b.decode("utf-8", "surrogateescape") for b in out.split(b"\0") if b]


def blob_sha(raw: bytes) -> str:
    """与 git hash-object 等价的 blob SHA-1。"""
    h = hashlib.sha1()
    h.update(b"blob %d\0" % len(raw))
    h.update(raw)
    return h.hexdigest()


def api(path):
    pat = subprocess.run(
        ["security", "find-internet-password", "-s", "github.com", "-w"],
        capture_output=True, text=True,
    ).stdout.strip()
    if not pat:
        sys.exit("❌ 未从 macOS 钥匙串取到 GitHub PAT（service=github.com）")
    req = urllib.request.Request(
        API + path,
        headers={
            "Authorization": "Bearer " + pat,
            "Accept": "application/vnd.github+json",
            "User-Agent": "hospital-dashboard-verify",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        sys.exit("❌ HTTP %s %s\n%s" % (e.code, path, e.read().decode()[:500]))


def main():
    ref = api(f"/repos/{REPO}/git/refs/heads/{BRANCH}")
    head = ref["object"]["sha"]
    commit = api(f"/repos/{REPO}/git/commits/{head}")
    tree = api(f"/repos/{REPO}/git/trees/{commit['tree']['sha']}?recursive=1")
    remote = {n["path"]: n["sha"] for n in tree["tree"] if n["type"] == "blob"}
    truncated = tree.get("truncated")

    tracked = sh_lines("cd '%s' && git ls-files -z" % ROOT)
    untracked = sh_lines("cd '%s' && git ls-files -o --exclude-standard -z" % ROOT)

    modified, missing_local, in_sync = [], [], []
    for rel in tracked:
        p = os.path.join(ROOT, rel)
        if not os.path.exists(p):
            missing_local.append(rel)
            continue
        raw = open(p, "rb").read()
        rsha = remote.get(rel)
        if rsha is None:
            modified.append((rel, "远端不存在（本地新增但未提交）", len(raw)))
        elif blob_sha(raw) != rsha:
            modified.append((rel, "内容不一致（本地有未推送改动）", len(raw)))
        else:
            in_sync.append(rel)

    # 注意：`git ls-files` 读的是本地索引，而本项目用 API 提交后本地索引不会更新，
    # 因此「未跟踪」清单里会混入大量其实早已在远端的文件。这里以远端 tree 为权威
    # 清单做二次过滤，只保留「远端确实没有」的新文件，避免误报。
    new_local = [rel for rel in untracked if rel not in remote]
    index_stale = [rel for rel in untracked if rel in remote]

    # 远端有、本地已跟踪清单里没有的（索引过期或已删除/改名的残留）
    gone = sorted(set(remote) - set(tracked))

    if not QUIET:
        print("远端 HEAD : %s" % head)
        print("远端文件数: %d%s" % (len(remote), "（tree 被截断，结果可能不完整！）" if truncated else ""))
        print("本地跟踪数: %d" % len(tracked))
        print()
        if modified:
            print("⚠️  有 %d 个文件未同步到远端：" % len(modified))
            for rel, why, n in modified:
                print("    • %-38s %8.1f KB  %s" % (rel, n / 1024, why))
        if new_local:
            print("⚠️  有 %d 个文件远端不存在（本地新增，需确认是否入库）：" % len(new_local))
            for rel in new_local:
                print("    + %s" % rel)
        if index_stale:
            print("ℹ️  %d 个文件已在远端但不在本地索引（API 提交后索引未更新，属正常）：" % len(index_stale))
        if missing_local:
            print("ℹ️  本地索引有但磁盘已无（%d，索引过期或文件已删除，非远端问题）：" % len(missing_local))
            for rel in missing_local:
                print("    - %s" % rel)
        if gone:
            print("ℹ️  远端存在但本地已不在跟踪清单（%d）：" % len(gone))
            for rel in gone[:20]:
                print("    ~ %s" % rel)
        print()

    ok = not modified and not new_local
    if ok:
        print("✅ 完全同步：%d 个已跟踪文件与远端 HEAD 逐字节一致（%s）" % (len(in_sync), head[:12]))
        return 0
    print(
        "❌ 未完全同步：%d 个文件待推送 / %d 个新文件远端不存在（远端 HEAD %s）"
        % (len(modified), len(new_local), head[:12])
    )
    return 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception as e:  # noqa: BLE001
        print("❌ 校验过程出错：%r" % (e,))
        sys.exit(2)
