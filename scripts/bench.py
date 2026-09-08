#!/usr/bin/env python3
"""
Sebastian — Router Benchmark Tool (v2.6.0)

Measures routing accuracy: model-produced predictions per benchmark case are
scored against expected skills. Deterministic checks run BEFORE model judging.

Workflow (executed by Claude per SKILL.md):
    /sebastian bench
      step 1: python3 bench.py validate
      step 2: python3 bench.py exam        # strip answers → bench.exam.json
              model reads bench.exam.json ONLY (never the full bench.json),
              runs Phase-1 weighted matching per case, writes predictions JSON
      step 3: python3 bench.py score <predictions.json>

Usage:
    python3 bench.py validate [--bench <bench.json>]
    python3 bench.py exam [--bench <bench.json>] [--out <path>]
    python3 bench.py score <predictions.json> [--bench <bench.json>]
    python3 bench.py history

Exit codes: 0 = ok (report printed; regression/absolute alarms are textual),
            2 = deterministic validation/format failure (nothing was scored).
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

# ---------------------------------------------------------------------------
# Sandbox-aware path resolution (mirrors scan.py — keep in sync)
# ---------------------------------------------------------------------------


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


def _default_bench_path():
    return os.path.join(_sebastian_dir(), "bench.json")


def _default_index_path():
    return os.path.join(_sebastian_dir(), "index.json")


def _history_path():
    return os.path.join(_sebastian_dir(), "bench-history.json")


def _runs_dir():
    return os.path.join(_sebastian_dir(), "bench-runs")


# ---------------------------------------------------------------------------
# Deterministic validation (before any model judgment)
# ---------------------------------------------------------------------------

ALLOWED_LEVELS = ("EXACT", "INDIRECT", "NOMATCH")
ALLOWED_LAYERS = ("single-output", "composite", "multi-step", "nomatch")


def load_json(path, what):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"[bench] ERROR: {what} not found: {path}", file=sys.stderr)
        sys.exit(2)
    except json.JSONDecodeError as e:
        print(f"[bench] ERROR: {what} is not valid JSON: {e}", file=sys.stderr)
        sys.exit(2)


def validate_bench(bench_path):
    """Deterministic checks on the benchmark dataset + index. Exit 2 on hard errors."""
    bench = load_json(bench_path, "benchmark dataset")
    ok = True

    if not isinstance(bench, dict) or "cases" not in bench:
        print("[bench] ERROR: bench.json must be {meta:{...}, cases:[...]}",
              file=sys.stderr)
        sys.exit(2)

    cases = bench["cases"]
    if not isinstance(cases, list) or not cases:
        print("[bench] ERROR: cases[] is empty — nothing to benchmark",
              file=sys.stderr)
        sys.exit(2)

    ids = [c.get("id") for c in cases]
    if any(i is None for i in ids) or len(set(ids)) != len(ids):
        print("[bench] ERROR: every case needs a unique integer id",
              file=sys.stderr)
        ok = False

    index = load_json(_default_index_path(), "index")
    index_names = {
        item.get("name")
        for item in index
        if isinstance(item, dict) and item.get("name")
    }
    if not index_names:
        print("[bench] ERROR: index.json holds no named entries — run "
              "'/sebastian update index' first", file=sys.stderr)
        ok = False

    unknown = set()
    for c in cases:
        if not isinstance(c, dict) or not c.get("prompt", "").strip():
            print(f"[bench] ERROR: case {c.get('id', '?')} has an empty prompt",
                  file=sys.stderr)
            ok = False
            continue
        level = c.get("expected_level", "EXACT").upper()
        if level not in ALLOWED_LEVELS:
            print(f"[bench] ERROR: case {c.get('id')} expected_level '{level}' "
                  f"not in {ALLOWED_LEVELS}", file=sys.stderr)
            ok = False
        layer = c.get("layer", "")
        if layer and layer not in ALLOWED_LAYERS:
            print(f"[bench] ERROR: case {c.get('id')} layer '{layer}' not in "
                  f"{ALLOWED_LAYERS}", file=sys.stderr)
            ok = False
        if level == "NOMATCH":
            if c.get("expected_skills"):
                print(f"[bench] ERROR: case {c.get('id')} is NOMATCH but lists "
                      f"expected_skills — NOMATCH cases expect an empty match",
                      file=sys.stderr)
                ok = False
        else:
            exp = c.get("expected_skills") or []
            if not exp:
                print(f"[bench] ERROR: case {c.get('id')} ({level}) lists no "
                      f"expected_skills", file=sys.stderr)
                ok = False
            for s in exp:
                if s not in index_names:
                    unknown.add(s)

    for s in sorted(unknown):
        print(f"[bench] WARNING: expected skill '{s}' not present in index.json "
              f"— matching can never hit it; run '/sebastian update index'")

    n = len(cases)
    n_exact = sum(1 for c in cases if c.get("expected_level", "EXACT").upper() != "NOMATCH")
    print(f"[bench] validate OK — {n} cases ({n_exact} EXACT, "
          f"{n - n_exact} NOMATCH), index {len(index_names)} entries")
    return ok


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def _load_history():
    if not os.path.exists(_history_path()):
        return []
    return load_json(_history_path(), "history")


def _save_history(history):
    with open(_history_path(), "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)


def _archive_run(pred, stamp):
    os.makedirs(_runs_dir(), exist_ok=True)
    path = os.path.join(_runs_dir(), f"{stamp}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(pred, f, ensure_ascii=False, indent=2)
    return path


def score(pred_path, bench_path):
    bench = load_json(bench_path, "benchmark dataset")
    pred = load_json(pred_path, "predictions")

    cases_by_id = {c["id"]: c for c in bench["cases"]}

    if not isinstance(pred, dict) or not isinstance(pred.get("cases"), list):
        print("[bench] ERROR: predictions must be {cases:[...]}", file=sys.stderr)
        sys.exit(2)

    preds = pred["cases"]
    pred_ids = [p.get("id") for p in preds]
    if len(pred_ids) != len(set(pred_ids)):
        print("[bench] ERROR: duplicate case ids in predictions", file=sys.stderr)
        sys.exit(2)
    if set(pred_ids) != set(cases_by_id):
        missing = set(cases_by_id) - set(pred_ids)
        extra = set(pred_ids) - set(cases_by_id)
        print(f"[bench] ERROR: prediction ids mismatch bench cases "
              f"(missing {sorted(missing)}, extra {sorted(extra)})",
              file=sys.stderr)
        sys.exit(2)

    # per-case results
    results = []
    for p in preds:
        case = cases_by_id[p["id"]]
        level = case.get("expected_level", "EXACT").upper()
        matched = p.get("matched_skills") or []
        exp = set(case.get("expected_skills") or [])
        if level == "NOMATCH":
            hit = len(matched) == 0 or matched[0] in ("NOMATCH",)
        else:
            hit = bool(matched) and matched[0] in exp
        hit3 = level != "NOMATCH" and any(m in exp for m in matched[:3])
        results.append({
            "id": p["id"], "layer": case.get("layer", "?"), "level": level,
            "matched": matched, "expected": sorted(exp), "hit": hit,
            "hit3": hit3 or hit,
            "template": (p.get("template") or "").upper() or None,
            "expected_template": (case.get("expected_template") or "").upper() or None,
        })

    total = len(results)
    hits = sum(1 for r in results if r["hit"])
    hits3 = sum(1 for r in results if r["hit3"])
    overall = hits / total if total else 0.0

    # per-layer report
    layers = {}
    for r in results:
        d = layers.setdefault(r["layer"], {"n": 0, "hit": 0})
        d["n"] += 1
        d["hit"] += 1 if r["hit"] else 0

    # template accuracy (EXACT multi-step cases only)
    t_n = sum(1 for r in results if r["expected_template"])
    t_hit = sum(
        1 for r in results if r["expected_template"]
        and r["template"] == r["expected_template"]
    )

    # regression vs history
    history = _load_history()
    prev_overall = None
    for run in history:
        prev_overall = run["overall"]  # history is append-only chronological
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    regressed = False
    if prev_overall is not None and overall < max(prev_overall - 0.03, prev_overall * 0.9):
        regressed = True
    absolute_fail = overall < 0.80

    # ---- report ----
    print("┌─────────────────────────────────────────────┐")
    print("│  Sebastian Router Bench 报告                │")
    print("├─────────────────────────────────────────────┤")
    print(f"│  日期: {stamp}")
    print(f"│  用例: {total}  |  EXACT {total - sum(1 for r in results if r['level'] == 'NOMATCH')} | NOMATCH {sum(1 for r in results if r['level'] == 'NOMATCH')}")
    print(f"│  命中: hit@1 = {hits}/{total} ({overall:.0%})  hit@3 = {hits3}/{total} ({hits3 / total:.0%})")
    print(f"│  模板: {t_hit}/{t_n} 命中" if t_n else "│  模板: 无标注")
    if prev_overall is not None:
        print(f"│  基线: 上次 {prev_overall:.0%} → 本次 {overall:.0%}"
              + ("  ⚠️ 回归!" if regressed else ""))
    print("├─────────────────────────────────────────────┤")
    for layer, d in sorted(layers.items()):
        bar = "#" * round(20 * d["hit"] / d["n"]) if d["n"] else ""
        print(f"│  {layer:<13} {d['hit']}/{d['n']:<3} ({d['hit'] / d['n']:.0%}) {bar}")
    if absolute_fail or regressed:
        print("├─────────────────────────────────────────────┤")
        if absolute_fail:
            print("│  ⚠️ 绝对阈值告警: overall < 80%")
        if regressed:
            print("│  ⚠️ 回归告警: 相比上次基线下降 ≥ 10% 或 3pt")
        print("│  处置: 检查 bench-runs/ 存档 → 逐条回看 miss 用例")
        print("│        → 如为索引质量问题, 更新索引/修复 SKILL.md 规则")
    print("└─────────────────────────────────────────────┘")

    miss_list = [r for r in results if not r["hit"]]
    if miss_list:
        print("\nMiss 用例:")
        for r in miss_list:
            print(f"  #{r['id']} [{r['level']}] 期望={r['expected']} "
                  f"实际={r['matched'] or ['(空)']}")

    history.append({
        "date": stamp, "total": total, "hits": hits, "overall": round(overall, 4),
        "hits3": hits3, "regressed": regressed, "template_hits": t_hit,
        "template_total": t_n, "miss_ids": [r["id"] for r in miss_list],
    })
    _save_history(history)
    archived = _archive_run(pred, stamp)
    print(f"\n[bench] 已存档 predictions → {archived}")

    return 1 if (regressed or absolute_fail) else 0


def exam(bench_path, out_path=None):
    """Strip answers from the dataset so the matching model cannot see them
    (self-grading bias: a model that reads expected_skills can 'cheat')."""
    bench = load_json(bench_path, "benchmark dataset")
    stripped = {
        "meta": {
            "schema": 1,
            "note": "exam 版: 已剥离 expected_* 与场景提示。模型只读此文件做匹配预测, 禁止参考原 bench.json",
        },
        "cases": [{"id": c["id"], "prompt": c["prompt"]} for c in bench["cases"]],
    }
    out_path = out_path or os.path.join(_sebastian_dir(), "bench.exam.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(stripped, f, ensure_ascii=False, indent=2)
    n = len(stripped["cases"])
    print(f"[bench] exam 版已生成 → {out_path} ({n} 例, 无答案字段)")
    print(f"[bench] 注意: 预测时只读 exam 版; 原 bench.json 含标准答案, 禁止作为预测依据")
    return out_path


def show_history():
    history = _load_history()
    if not history:
        print("[bench] 尚无历史记录 — 首次运行 score 后生成")
        return
    print(f"{'日期':<22}{'总体':>8}{'hit@1':>9}{'hit@3':>9}{'模板':>8}  回归")
    for run in history:
        t = f"{run['template_hits']}/{run['template_total']}" if run["template_total"] else "-"
        print(f"{run['date']:<22}{run['overall']:>7.0%}{run['hits']:>6}/{run['total']:<3}"
              f"{run['hits3']:>6}/{run['total']:<3}{t:>8}  "
              f"{'⚠️' if run['regressed'] else ''}")


def main():
    ap = argparse.ArgumentParser(description="Sebastian router benchmark")
    ap.add_argument("--bench", default=None, help="bench.json path")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("validate", help="deterministic checks on dataset + index")
    sub.add_parser("history", help="show past bench runs")

    sp = sub.add_parser("score", help="score model predictions against bench.json")
    sp.add_argument("predictions", help="predictions JSON file")

    sp = sub.add_parser("exam", help="emit answer-stripped dataset for the matcher")
    sp.add_argument("--out", default=None, help="output path (default ~/.sebastian/bench.exam.json)")

    if len(sys.argv) > 1 and sys.argv[1].startswith("-") and not sys.argv[1].startswith("--bench"):
        sys.argv[1] = sys.argv[1].lstrip("-")   # accept both `--validate` and `validate`
    args = ap.parse_args()
    bench_path = os.path.abspath(args.bench or _default_bench_path())

    if args.cmd == "validate":
        validate_bench(bench_path)
    elif args.cmd == "history":
        show_history()
    elif args.cmd == "exam":
        exam(bench_path, args.out)
    elif args.cmd == "score":
        sys.exit(score(os.path.abspath(args.predictions), bench_path))


if __name__ == "__main__":
    main()
