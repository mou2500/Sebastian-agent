#!/usr/bin/env python3
"""
Sebastian — Tool Index Scanner

Reads ~/.sebastian/config.json, scans configured paths for SKILL.md files,
parses YAML frontmatter, and builds/updates ~/.sebastian/index.json.

Usage:
    python3 scan.py --scan          # Full scan, rebuild index
    python3 scan.py --list          # Print summary table
    python3 scan.py --find <kw>     # Search by name/tags/capabilities/scenarios
    python3 scan.py --diagnose      # Print index health report
"""

import json
import os
import re
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
#  Default paths
# ---------------------------------------------------------------------------
DEFAULT_CONFIG_PATH = os.path.expanduser("~/.sebastian/config.json")
DEFAULT_INDEX_PATH = os.path.expanduser("~/.sebastian/index.json")
DEFAULT_SKILL_PATHS = [
    os.path.expanduser("~/.claude/skills"),
    os.path.expanduser("~/.agents/skills"),
]

# ---------------------------------------------------------------------------
#  Config
# ---------------------------------------------------------------------------

DEFAULT_CONFIG = {
    "skill_paths": ["~/.claude/skills", "~/.agents/skills"],
    "index_path": "~/.sebastian/index.json",
    "last_scan": None,
}


def _ensure_sebastian_dir():
    """Create ~/.sebastian/ if it does not exist."""
    Path(os.path.expanduser("~/.sebastian")).mkdir(parents=True, exist_ok=True)


def load_config(config_path=None):
    """Load config from disk or create default."""
    path = config_path or DEFAULT_CONFIG_PATH
    expanded = os.path.expanduser(path)

    if not os.path.exists(expanded):
        print(f"[config] {expanded} not found, creating default.", file=sys.stderr)
        _ensure_sebastian_dir()
        save_config(DEFAULT_CONFIG, expanded)
        return dict(DEFAULT_CONFIG)

    with open(expanded, "r", encoding="utf-8") as f:
        cfg = json.load(f)

    # Ensure all keys exist
    for k, v in DEFAULT_CONFIG.items():
        cfg.setdefault(k, v)
    return cfg


def save_config(cfg, path=None):
    """Write config to disk."""
    p = path or DEFAULT_CONFIG_PATH
    _ensure_sebastian_dir()
    with open(os.path.expanduser(p), "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)
        f.write("\n")


# ---------------------------------------------------------------------------
#  Frontmatter parsing
# ---------------------------------------------------------------------------

YAML_DELIMITER = re.compile(r"^---\s*$", re.MULTILINE)


def parse_frontmatter(text):
    """
    Extract YAML frontmatter block from SKILL.md text.
    Returns (frontmatter_text, body_text) or (None, text) if no frontmatter.
    """
    # Match leading --- ... ---
    # Ensure the first line of the file starts the delimiter
    lines = text.split("\n")
    if not lines or lines[0].strip() != "---":
        return None, text

    # Find closing ---
    end_idx = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end_idx = i
            break

    if end_idx is None:
        return None, text

    frontmatter_lines = lines[1:end_idx]
    body_lines = lines[end_idx + 1:]
    return "\n".join(frontmatter_lines), "\n".join(body_lines).strip()


def parse_yaml_simple(yaml_text):
    """
    Minimal YAML parser for frontmatter fields.
    Handles: string, list, quoted values.
    """
    result = {}
    for line in yaml_text.split("\n"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        match = re.match(r"^(\w+):\s*(.*)", line)
        if not match:
            continue

        key = match.group(1)
        value = match.group(2).strip()

        # Remove surrounding quotes
        if len(value) >= 2 and value[0] in "\"'" and value[-1] == value[0]:
            value = value[1:-1]

        # List: [item1, item2, ...]
        if value.startswith("[") and value.endswith("]"):
            inner = value[1:-1]
            items = []
            for item in inner.split(","):
                item = item.strip().strip("\"'")
                if item:
                    items.append(item)
            result[key] = items
        # Inline list without brackets (tags: [a, b] or just comma separated)
        elif "," in value and not value.startswith("[") and key in (
            "tags",
            "paired_with",
        ):
            result[key] = [v.strip().strip("\"'") for v in value.split(",") if v.strip()]
        else:
            result[key] = value

    return result


# ---------------------------------------------------------------------------
#  Index record
# ---------------------------------------------------------------------------

EMPTY_RECORD = {
    "name": "",
    "path": "",
    "description": "",
    "version": "",
    "tags": [],
    "capabilities": "",
    "scenarios": "",
    "paired_with": [],
    "source": "",
    "external_url": "",
    "update_method": "",
    "usage_count": 0,
}


def record_from_frontmatter(fm, filepath):
    """Build an index record from parsed frontmatter dict."""
    rec = dict(EMPTY_RECORD)
    rec["path"] = filepath
    for k in ("name", "description", "version", "capabilities", "scenarios",
              "source", "external_url", "update_method"):
        if k in fm:
            rec[k] = fm[k]
    for k in ("tags", "paired_with"):
        if k in fm and isinstance(fm[k], list):
            rec[k] = fm[k]
    # usage_count stays 0; merged later from old index
    return rec


def record_from_body(filepath, text):
    """Build a minimal index record from file body when no frontmatter exists."""
    rec = dict(EMPTY_RECORD)
    basename = os.path.basename(os.path.dirname(filepath))
    rec["name"] = basename or Path(filepath).stem
    rec["path"] = filepath
    # First non-empty line as description
    for line in text.split("\n"):
        line = line.strip().strip("#").strip()
        if line:
            rec["description"] = line[:200]
            break
    return rec


# ---------------------------------------------------------------------------
#  Scan
# ---------------------------------------------------------------------------


def discover_skill_files(skill_paths):
    """Find all SKILL.md files under the given directories."""
    files = []
    for sp in skill_paths:
        expanded = os.path.expanduser(sp)
        if not os.path.isdir(expanded):
            continue
        for root, _dirs, fnames in os.walk(expanded):
            if "SKILL.md" in fnames:
                files.append(os.path.normpath(os.path.join(root, "SKILL.md")))
    return sorted(files)


def scan(config_path=None):
    """Full scan: read config, discover files, parse, merge, write index."""
    cfg = load_config(config_path)
    skill_paths = [os.path.expanduser(p) for p in cfg.get("skill_paths", [])]
    index_path = os.path.expanduser(cfg.get("index_path", DEFAULT_INDEX_PATH))

    print(f"[scan] Paths: {skill_paths}", file=sys.stderr)
    print(f"[scan] Index: {index_path}", file=sys.stderr)

    # Discover
    files = discover_skill_files(skill_paths)
    print(f"[scan] Found {len(files)} SKILL.md file(s)", file=sys.stderr)

    # Load old index to preserve usage_count
    old_index = load_old_index(index_path)

    # Parse each file
    records = []
    for fp in files:
        with open(fp, "r", encoding="utf-8") as f:
            text = f.read()

        fm_text, body = parse_frontmatter(text)
        if fm_text:
            fm = parse_yaml_simple(fm_text)
            rec = record_from_frontmatter(fm, fp)
        else:
            rec = record_from_body(fp, body)

        # Merge usage_count from old index
        old_rec = old_index.get(rec["name"])
        if old_rec:
            rec["usage_count"] = old_rec.get("usage_count", 0)

        records.append(rec)
        src = "frontmatter" if fm_text else "body"
        print(f"  [{src}] {rec['name']}", file=sys.stderr)

    # Write index
    _ensure_sebastian_dir()
    with open(index_path, "w", encoding="utf-8") as f:
        json.dump(records, f, indent=2, ensure_ascii=False)
        f.write("\n")

    # Update last_scan
    from datetime import datetime, timezone

    cfg["last_scan"] = datetime.now(timezone.utc).isoformat()
    save_config(cfg, config_path or DEFAULT_CONFIG_PATH)

    print(f"\n[scan] Done. {len(records)} skill(s) indexed.", file=sys.stderr)
    return records


def load_old_index(index_path):
    """Load existing index by name for merging usage_count."""
    if not os.path.exists(index_path):
        return {}
    try:
        with open(index_path, "r", encoding="utf-8") as f:
            records = json.load(f)
        return {r["name"]: r for r in records if r.get("name")}
    except (json.JSONDecodeError, KeyError):
        return {}


# ---------------------------------------------------------------------------
#  CLI: --list
# ---------------------------------------------------------------------------


def cmd_list(index_path=None):
    """Print a summary table of all indexed skills."""
    path = index_path or DEFAULT_INDEX_PATH
    expanded = os.path.expanduser(path)
    if not os.path.exists(expanded):
        print("Index not found. Run --scan first.", file=sys.stderr)
        return

    with open(expanded, "r", encoding="utf-8") as f:
        records = json.load(f)

    if not records:
        print("(empty index)")
        return

    # Column widths
    name_w = max(len(r.get("name", "")) for r in records)
    name_w = max(name_w, 4) + 2
    ver_w = max(len(r.get("version", "") or "") for r in records)
    ver_w = max(ver_w, 7) + 2
    src_w = max(len(r.get("source", "") or "") for r in records)
    src_w = max(src_w, 6) + 2
    cnt_w = 6

    sep = "+" + "-" * (name_w + 2) + "+" + "-" * (ver_w + 2) + "+" + "-" * (src_w + 2) + "+" + "-" * cnt_w + "+"

    # Header
    print(sep)
    print(f"| {'Name'.ljust(name_w - 1)}| {'Version'.ljust(ver_w - 1)}| {'Source'.ljust(src_w - 1)}| {'Uses'.ljust(cnt_w - 1)}|")
    print(sep.replace("-", "="))

    for r in records:
        name = r.get("name", "")[:name_w]
        ver = (r.get("version") or "")[: ver_w]
        src = (r.get("source") or "")[: src_w]
        cnt = str(r.get("usage_count", 0))
        print(f"| {name.ljust(name_w - 1)}| {ver.ljust(ver_w - 1)}| {src.ljust(src_w - 1)}| {cnt.rjust(cnt_w - 2)} |")

    print(sep)
    print(f"{len(records)} skill(s)")


# ---------------------------------------------------------------------------
#  CLI: --find
# ---------------------------------------------------------------------------


def cmd_find(keyword, index_path=None):
    """Search index by name/tags/capabilities/scenarios."""
    path = index_path or DEFAULT_INDEX_PATH
    expanded = os.path.expanduser(path)
    if not os.path.exists(expanded):
        print("Index not found. Run --scan first.", file=sys.stderr)
        return

    with open(expanded, "r", encoding="utf-8") as f:
        records = json.load(f)

    kw = keyword.lower()
    matches = []
    for r in records:
        name = (r.get("name") or "").lower()
        desc = (r.get("description") or "").lower()
        caps = (r.get("capabilities") or "").lower()
        scenarios = (r.get("scenarios") or "").lower()
        tags = " ".join(r.get("tags") or []).lower()

        if kw in name or kw in desc or kw in caps or kw in scenarios or kw in tags:
            matches.append(r)

    if not matches:
        print(f"No skills match '{keyword}'")
        return

    print(f"Found {len(matches)} skill(s) matching '{keyword}':\n")
    for r in matches:
        name = r.get("name", "?")
        desc = (r.get("description") or "(no description)")[:120]
        tags = r.get("tags") or []
        tag_str = f"  tags: [{', '.join(tags)}]" if tags else ""
        print(f"  {name}")
        print(f"    {desc}")
        if tag_str:
            print(tag_str)
        print()


def cmd_diagnose(index_path=None):
    """Print index health report."""
    path = index_path or DEFAULT_INDEX_PATH
    expanded = os.path.expanduser(path)
    if not os.path.exists(expanded):
        print("Index not found. Run --scan first.", file=sys.stderr)
        return

    with open(expanded, "r", encoding="utf-8") as f:
        records = json.load(f)

    if not records:
        print("(empty index)")
        return

    HEALTH_FIELDS = ["name", "description", "tags", "capabilities", "scenarios",
                     "paired_with", "version", "source"]

    total = len(records)
    complete = 0   # >= 6 fields populated
    basic = 0      # 4-5 fields
    sparse = 0     # <= 3 fields
    details = []

    for r in records:
        name = r.get("name", "?")
        populated = sum(1 for f in HEALTH_FIELDS if r.get(f) and
                        (not isinstance(r[f], list) or len(r[f]) > 0))
        if populated >= 6:
            complete += 1
        elif populated >= 4:
            basic += 1
        else:
            sparse += 1
        details.append((name, populated, populated < 4))

    # Summary bar
    bar_w = 30
    c_bar = int(bar_w * complete / total) if total else 0
    b_bar = int(bar_w * basic / total) if total else 0
    s_bar = bar_w - c_bar - b_bar

    print()
    print("Index Health Report")
    print("=" * 40)
    print(f"Total: {total} skills")
    print()
    print(f"  Complete (>=6 fields): {complete:>3}  {'#' * c_bar}{'.' * (bar_w - c_bar)}")
    print(f"  Basic   (4-5 fields): {basic:>3}  {'#' * b_bar}{'.' * (bar_w - b_bar)}")
    print(f"  Sparse  (<=3 fields): {sparse:>3}  {'#' * s_bar}{'.' * (bar_w - s_bar)}")
    print()
    if sparse > 0:
        print("Skills needing frontmatter completion:")
        for name, pop, is_sparse in sorted(details):
            if is_sparse:
                print(f"  {name} ({pop}/{len(HEALTH_FIELDS)} fields)")
    print()


# ---------------------------------------------------------------------------
#  Main
# ---------------------------------------------------------------------------


def main():
    if len(sys.argv) < 2:
        print(__doc__.strip())
        sys.exit(1)

    command = sys.argv[1]

    if command == "--scan":
        scan()
    elif command == "--list":
        cmd_list()
    elif command == "--find":
        if len(sys.argv) < 3:
            print("Usage: python3 scan.py --find <keyword>")
            sys.exit(1)
        cmd_find(sys.argv[2])
    elif command == "--diagnose":
        cmd_diagnose()
    else:
        print(f"Unknown command: {command}")
        print("Available: --scan, --list, --find <keyword>, --diagnose")
        sys.exit(1)


if __name__ == "__main__":
    main()
