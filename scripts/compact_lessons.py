#!/usr/bin/env python3
"""
Sebastian — Lessons Compactor (v2.6.0)

Anchored compression governance for lessons.json (flat record list).

Rule: lessons.json keeps the newest MAX_KEEP records verbatim. When the list
grows past the threshold, `--cut` moves the OLDEST records into a per-primary-
skill pending bucket file, then the model digests each bucket into a fixed-
section digest entry (identifiers verbatim), which `--merge` folds into
lessons-archive.json. Digest entries anchor on skill+period; re-digesting the
same window MERGES sections instead of rewriting (anchored incremental merge).

Usage:
    python3 compact_lessons.py --status
    python3 compact_lessons.py --cut
    python3 compact_lessons.py --merge <digest.json>
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

MAX_KEEP = 50          # records kept verbatim in lessons.json
WARN_AT = 40           # warn once records exceed this


def _real_home():
    env_home = os.environ.get("SEBASTIAN_HOME")
    if env_home:
        return os.path.abspath(env_home)
    home = os.path.expanduser("~")
    if os.path.isdir(os.path.join(home, ".sebastian")):
        return home
    if sys.platform == "win32" or os.name == "nt":
        username = os.environ.get("USERNAME")
        if username:
            real_home = f"C:\\Users\\{username}"
            if os.path.isdir(os.path.join(real_home, ".sebastian")):
                return real_home
    return home


def _sebastian_dir():
    return os.path.join(_real_home(), ".sebastian")


def _lessons_path():
    return os.path.join(_sebastian_dir(), "lessons.json")


def _archive_path():
    return os.path.join(_sebastian_dir(), "lessons-archive.json")


def _pending_path():
    return os.path.join(_sebastian_dir(), "pending-archive.json")


def _load(path, default=None):
    if not os.path.exists(path):
        return default
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _save(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _primary(record):
    wf = record.get("workflow") or []
    return wf[0] if wf else "unknown"


def _stamp():
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _load_lessons():
    lessons = _load(_lessons_path())
    if lessons is None:
        print(f"[compact] ERROR: lessons.json not found: {_lessons_path()}",
              file=sys.stderr)
        sys.exit(2)
    if not isinstance(lessons, list):
        print("[compact] ERROR: lessons.json must be a flat JSON array",
              file=sys.stderr)
        sys.exit(2)
    return lessons


def status():
    lessons = _load_lessons()
    n = len(lessons)
    by_result = {}
    by_skill = {}
    for r in lessons:
        by_result[r.get("result", "?")] = by_result.get(r.get("result", "?"), 0) + 1
        s = _primary(r)
        by_skill[s] = by_skill.get(s, 0) + 1

    print(f"[compact] lessons.json: {n} 条 (保留上限 {MAX_KEEP}, 警告线 {WARN_AT})")
    print(f"  按结果: " + "  ".join(f"{k}={v}" for k, v in sorted(by_result.items()))
          or "  (空)")
    print(f"  按主技能: " + "  ".join(
        f"{k}×{v}" for k, v in sorted(by_skill.items(), key=lambda kv: -kv[1])))

    archive = _load(_archive_path())
    if archive and archive.get("digests"):
        dig = archive["digests"]
        print(f"  归档摘要: {len(dig)} 段 ("
              + ", ".join(f"{d.get('skill')}:{d.get('period')}" for d in dig) + ")")
    else:
        print("  归档摘要: 无 (lessons-archive.json 尚不存在)")

    if n > MAX_KEEP:
        cut = n - MAX_KEEP
        print(f"  ⚠️ 超出上限 {cut} 条 → 建议执行: python3 compact_lessons.py --cut")
    elif n > WARN_AT:
        print(f"  ⚠️ 接近上限 (>{WARN_AT}) → 再积累 {MAX_KEEP - n} 条后建议压缩")
    else:
        print(f"  ✓ 未超阈值, 无需压缩")


def cut():
    lessons = _load_lessons()
    n = len(lessons)
    if n <= MAX_KEEP:
        print(f"[compact] 仅 {n} 条 (≤ {MAX_KEEP}) — 无需压缩")
        return
    n_cut = n - MAX_KEEP
    cut_records = lessons[:n_cut]          # oldest first (records are chronological)
    keep_records = lessons[n_cut:]
    oldest = cut_records[0].get("timestamp", "?")[:10]
    newest = cut_records[-1].get("timestamp", "?")[:10]

    buckets = {}
    for r in cut_records:
        buckets.setdefault(_primary(r), []).append(r)
    pending = {
        "meta": {"schema": 1, "cut_at": _stamp(), "period": f"{oldest} ~ {newest}"},
        "buckets": buckets,
    }
    _save(_pending_path(), pending)
    _save(_lessons_path(), keep_records)

    print(f"[compact] 已移出 {n_cut} 条最老记录 → pending-archive.json")
    print(f"          保留 {len(keep_records)} 条在 lessons.json")
    print(f"          分桶 {len(buckets)} 个主技能: "
          + ", ".join(f"{k}×{len(v)}" for k, v in sorted(buckets.items())))
    print()
    print("下一步 (模型执行锚定摘要):")
    print("  对每个桶生成固定章节的摘要, 章节模板:")
    print('  {"skill": "<主技能名, 逐字>",')
    print('   "period": "<YYYY-MM-DD ~ YYYY-MM-DD>",')
    print('   "stats": {"ok": n, "modified": n, "failed": n},')
    print('   "decisions": ["<结论性要点; 涉及技能名/文件路径逐字保留>"],')
    print('   "failures": [{"phenomenon": "<失败现象>",')
    print('                  "root_cause": "<机制原因>", "fix": "<修复>",')
    print('                  "rung": "skill|template|harness",')
    print('                  "result": "ok|failed"}]}')
    print("  规则: 只做增量合并, 绝不整体重写; workflow 数组逐字保留")
    print(f"  完成后执行: python3 compact_lessons.py --merge <digest.json>")


def merge(digest_path):
    digests = _load(digest_path)
    if digests is None or not isinstance(digests, list) or not digests:
        print(f"[compact] ERROR: {digest_path} must be a non-empty JSON array of "
              f"digest entries", file=sys.stderr)
        sys.exit(2)

    archive = _load(_archive_path())
    if archive is None:
        archive = {"meta": {"schema": 1, "created": _stamp()}, "digests": []}
    if "digests" not in archive:
        archive["digests"] = []

    merged = 0
    extended = 0
    for d in digests:
        skill = d.get("skill")
        period = d.get("period")
        if not skill or not period or not isinstance(d.get("stats"), dict):
            print(f"[compact] ERROR: digest entry missing skill/period/stats — "
                  f"rejecting batch", file=sys.stderr)
            sys.exit(2)
        key = (skill, period)
        for existing in archive["digests"]:
            if (existing.get("skill"), existing.get("period")) == key:
                # anchored incremental: extend sections, keep identifiers
                for sec in ("decisions", "failures"):
                    existing.setdefault(sec, [])
                    existing[sec].extend(d.get(sec) or [])
                ext = existing.get("stats", {})
                for k, v in (d.get("stats") or {}).items():
                    ext[k] = ext.get(k, 0) + v
                existing["stats"] = ext
                existing["extended_at"] = _stamp()
                extended += 1
                break
        else:
            archive["digests"].append(d)
            merged += 1

    _save(_archive_path(), archive)
    print(f"[compact] 归档完成: 新增 {merged} 段, 增量扩展 {extended} 段")
    print(f"           → lessons-archive.json (共 {len(archive['digests'])} 段)")
    print("          注意: pending-archive.json 已消费, 可删除")


def main():
    ap = argparse.ArgumentParser(description="Sebastian lessons compactor")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status", help="show lessons/archive state vs threshold")
    sub.add_parser("cut", help="move oldest over-threshold records to pending-archive.json")
    sp = sub.add_parser("merge", help="fold model-produced digests into lessons-archive.json")
    sp.add_argument("digest", help="digest JSON file (array of entries)")
    if len(sys.argv) > 1 and sys.argv[1].startswith("-"):
        sys.argv[1] = sys.argv[1].lstrip("-")   # accept both `--status` and `status`
    args = ap.parse_args()

    if args.cmd == "status":
        status()
    elif args.cmd == "cut":
        cut()
    elif args.cmd == "merge":
        merge(os.path.abspath(args.digest))


if __name__ == "__main__":
    main()
