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
    python3 scan.py --scan-plugins  # List installed plugins from cache
"""

import json
import os
import re
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
#  Sandbox-aware path resolution
#  Claude Code sandbox overrides HOME/USERPROFILE to a temp shadow directory.
#  We detect this and fall back to the real user home so ~/.sebastian/ data
#  survives across sessions.
# ---------------------------------------------------------------------------


def _real_home():
    """Resolve the real user home directory, accounting for sandbox shadow dirs.

    Priority:
    1. SEBASTIAN_HOME env var (explicit override)
    2. Current HOME if ~/.sebastian/ exists there (normal case)
    3. Windows: construct from USERNAME (sandbox fallback)
    4. Fall back to HOME
    """
    # 1. Explicit override
    env_home = os.environ.get("SEBASTIAN_HOME")
    if env_home:
        return os.path.abspath(env_home)

    home = os.path.expanduser("~")

    # 2. Current HOME already has .sebastian → use it
    if os.path.isdir(os.path.join(home, ".sebastian")):
        return home

    # 3. Windows sandbox: USERNAME is not overridden by sandbox
    if sys.platform == "win32" or os.name == "nt":
        username = os.environ.get("USERNAME")
        if username:
            real_home = f"C:\\Users\\{username}"
            if os.path.isdir(os.path.join(real_home, ".sebastian")):
                return real_home

    # 4. Fall back
    return home


def _sebastian_dir():
    return os.path.join(_real_home(), ".sebastian")


# ---------------------------------------------------------------------------
#  Default paths (resolved lazily so sandbox detection runs at call time)
# ---------------------------------------------------------------------------

DEFAULT_SKILL_PATHS = [
    "~/.claude/skills",
    "~/.agents/skills",
]
PLUGIN_CACHE_DIR = "~/.claude/plugins/cache"

DEFAULT_CONFIG = {
    "skill_paths": ["~/.claude/skills", "~/.agents/skills"],
    "external_tools_dir": "~/.sebastian/external-tools",
    "index_path": "~/.sebastian/index.json",
    "last_scan": None,
}


def _default_config_path():
    return os.path.join(_sebastian_dir(), "config.json")


def _default_index_path():
    return os.path.join(_sebastian_dir(), "index.json")


def _default_external_tools_dir():
    return os.path.join(_sebastian_dir(), "external-tools")


def _resolve_expanduser(path):
    """Like os.path.expanduser but accounts for sandbox shadow dirs."""
    if path.startswith("~/"):
        return path.replace("~/", _real_home() + "/", 1)
    if path.startswith("~"):
        return path.replace("~", _real_home(), 1)
    return os.path.expanduser(path)


def _ensure_sebastian_dir():
    """Create ~/.sebastian/ in the real home if it does not exist."""
    Path(_sebastian_dir()).mkdir(parents=True, exist_ok=True)


def load_config(config_path=None):
    """Load config from disk or create default."""
    if config_path:
        expanded = _resolve_expanduser(config_path)
    else:
        expanded = os.path.join(_sebastian_dir(), "config.json")

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
    p = path or _default_config_path()
    _ensure_sebastian_dir()
    with open(p, "w", encoding="utf-8") as f:
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
    "type": "skill",
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

EMPTY_EXTERNAL_TOOL_RECORD = {
    "name": "",
    "type": "external_tool",
    "path": "",
    "description": "",
    "version": "",
    "tags": [],
    "capabilities": "",
    "scenarios": "",
    "keywords": [],
    "invoke_type": "command",
    "invoke_cwd": "",
    "invoke_template": "{{script}}",
    "subcommands": {},
    "trigger_confidence": {},
    "source": "external",
    "external_url": "",
    "update_method": "",
    "usage_count": 0,
}

EMPTY_PLUGIN_RECORD = {
    "name": "",
    "type": "plugin",
    "path": "",
    "description": "",
    "version": "",
    "tags": [],
    "capabilities": "",
    "scenarios": "",
    "keywords": [],
    "invoke_type": "plugin_command",
    "invoke_prefix": "",
    "subcommands": {},
    "trigger_confidence": {},
    "source": "plugin",
    "external_url": "",
    "update_method": "plugin_update",
    "usage_count": 0,
}


def record_from_frontmatter(fm, filepath):
    """Build an index record from parsed frontmatter dict."""
    rec = dict(EMPTY_RECORD)
    rec["path"] = filepath
    rec["type"] = "skill"
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
    rec["type"] = "skill"
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
        expanded = _resolve_expanduser(sp)
        if not os.path.isdir(expanded):
            continue
        for root, _dirs, fnames in os.walk(expanded):
            if "SKILL.md" in fnames:
                files.append(os.path.normpath(os.path.join(root, "SKILL.md")))
    return sorted(files)


# ---------------------------------------------------------------------------
#  External tool discovery
# ---------------------------------------------------------------------------


def discover_external_tools(external_tools_dir):
    """Find all external tool JSON descriptors under the given directory."""
    expanded = _resolve_expanduser(external_tools_dir)
    if not os.path.isdir(expanded):
        return []
    files = sorted(
        os.path.join(expanded, f)
        for f in os.listdir(expanded)
        if f.endswith(".json")
    )
    return files


def load_tool_descriptor(filepath):
    """Load and validate a tool descriptor JSON file (external_tool or plugin)."""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        print(f"  [error] Failed to load {filepath}: {e}", file=sys.stderr)
        return None

    tool_type = data.get("type", "external_tool")

    if tool_type == "plugin":
        rec = dict(EMPTY_PLUGIN_RECORD)
    else:
        rec = dict(EMPTY_EXTERNAL_TOOL_RECORD)

    rec["path"] = os.path.normpath(filepath)

    template = EMPTY_PLUGIN_RECORD if tool_type == "plugin" else EMPTY_EXTERNAL_TOOL_RECORD
    for field in template:
        if field in data:
            rec[field] = data[field]

    # Ensure name is set
    if not rec["name"]:
        rec["name"] = os.path.splitext(os.path.basename(filepath))[0]

    # Auto-detect version from plugin cache if available
    if tool_type == "plugin" and not rec.get("version"):
        cache_path = get_plugin_cache_path(rec["name"])
        if cache_path:
            rec["path"] = cache_path

    return rec


def get_plugin_cache_path(plugin_name):
    """Find the latest version cache path for a given plugin by scanning cache."""
    cache_dir = _resolve_expanduser(PLUGIN_CACHE_DIR)
    if not os.path.isdir(cache_dir):
        return None

    # Scan: ~/.claude/plugins/cache/<marketplace>/<plugin>/<version>/
    for marketplace in os.listdir(cache_dir):
        mp_dir = os.path.join(cache_dir, marketplace)
        if not os.path.isdir(mp_dir):
            continue
        for plugin_dir in os.listdir(mp_dir):
            if plugin_dir == plugin_name:
                pdir = os.path.join(mp_dir, plugin_dir)
                if not os.path.isdir(pdir):
                    continue
                versions = sorted(
                    v for v in os.listdir(pdir)
                    if os.path.isdir(os.path.join(pdir, v))
                )
                if versions:
                    return os.path.normpath(os.path.join(pdir, versions[-1]))
    return None


def discover_installed_plugins():
    """Auto-discover installed plugins from Claude Code cache directory."""
    cache_dir = _resolve_expanduser(PLUGIN_CACHE_DIR)
    if not os.path.isdir(cache_dir):
        return []

    plugins = []
    for marketplace in sorted(os.listdir(cache_dir)):
        mp_dir = os.path.join(cache_dir, marketplace)
        if not os.path.isdir(mp_dir):
            continue
        for plugin_dir in sorted(os.listdir(mp_dir)):
            pdir = os.path.join(mp_dir, plugin_dir)
            if not os.path.isdir(pdir):
                continue
            versions = sorted(
                v for v in os.listdir(pdir)
                if os.path.isdir(os.path.join(pdir, v))
            )
            if versions:
                latest = versions[-1]
                skill_dir = os.path.join(pdir, latest, "skills")
                plugin_info = {
                    "name": plugin_dir,
                    "marketplace": marketplace,
                    "version": latest,
                    "path": os.path.normpath(os.path.join(pdir, latest)),
                    "has_skills": os.path.isdir(skill_dir),
                    "skill_names": sorted(os.listdir(skill_dir)) if os.path.isdir(skill_dir) else [],
                }
                plugins.append(plugin_info)
    return plugins


def scan(config_path=None):
    """Full scan: discover skills + external tools, parse, merge, write index."""
    cfg = load_config(config_path)
    skill_paths = [_resolve_expanduser(p) for p in cfg.get("skill_paths", [])]
    ext_dir = _resolve_expanduser(cfg.get("external_tools_dir", "~/.sebastian/external-tools"))
    index_path = _resolve_expanduser(cfg.get("index_path", "~/.sebastian/index.json"))

    print(f"[scan] Skills paths: {skill_paths}", file=sys.stderr)
    print(f"[scan] External tools: {ext_dir}", file=sys.stderr)
    print(f"[scan] Index: {index_path}", file=sys.stderr)

    # Load old index to preserve usage_count
    old_index = load_old_index(index_path)

    # --- Discover skills ---
    files = discover_skill_files(skill_paths)
    print(f"[scan] Found {len(files)} SKILL.md file(s)", file=sys.stderr)

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

        # Set type
        rec["type"] = "skill"

        # Merge usage_count from old index
        old_rec = old_index.get(rec["name"])
        if old_rec:
            rec["usage_count"] = old_rec.get("usage_count", 0)

        records.append(rec)
        src = "frontmatter" if fm_text else "body"
        print(f"  [skill] {rec['name']}", file=sys.stderr)

    # --- Discover external tools ---
    ext_files = discover_external_tools(ext_dir)
    print(f"[scan] Found {len(ext_files)} external tool descriptor(s)", file=sys.stderr)

    for fp in ext_files:
        rec = load_tool_descriptor(fp)
        if rec is None:
            continue

        # Merge usage_count from old index
        old_rec = old_index.get(rec["name"])
        if old_rec:
            rec["usage_count"] = old_rec.get("usage_count", 0)

        records.append(rec)
        rtype = rec.get("type", "tool")
        print(f"  [{rtype}] {rec['name']}", file=sys.stderr)

    # Write index
    _ensure_sebastian_dir()
    with open(index_path, "w", encoding="utf-8") as f:
        json.dump(records, f, indent=2, ensure_ascii=False)
        f.write("\n")

    # Update last_scan
    from datetime import datetime, timezone

    cfg["last_scan"] = datetime.now(timezone.utc).isoformat()
    save_config(cfg, config_path or _default_config_path())

    skills = sum(1 for r in records if r.get('type') == 'skill')
    ext_tools = sum(1 for r in records if r.get('type') == 'external_tool')
    plugins = sum(1 for r in records if r.get('type') == 'plugin')
    print(f"\n[scan] Done. {len(records)} tool(s) indexed ({skills} skills, {ext_tools} external tools, {plugins} plugins).", file=sys.stderr)
    return records


def load_old_index(index_path):
    """Load existing index by name for merging usage_count.
    Handles both array (scan.py format) and dict (manual/legacy format)."""
    if not os.path.exists(index_path):
        return {}
    try:
        with open(index_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            # Legacy dict format: {name: record}
            return data
        # Array format: [{name: ...}, ...]
        return {r["name"]: r for r in data if r.get("name")}
    except (json.JSONDecodeError, KeyError, TypeError):
        return {}


# ---------------------------------------------------------------------------
#  CLI: --list
# ---------------------------------------------------------------------------


def cmd_list(index_path=None):
    """Print a summary table of all indexed skills."""
    path = index_path or _default_index_path()
    expanded = _resolve_expanduser(path)
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
    type_w = max(len(r.get("type", "") or "") for r in records)
    type_w = max(type_w, 12) + 2
    ver_w = max(len(r.get("version", "") or "") for r in records)
    ver_w = max(ver_w, 7) + 2
    src_w = max(len(r.get("source", "") or "") for r in records)
    src_w = max(src_w, 6) + 2
    cnt_w = 6

    sep = "+" + "-" * (name_w + 2) + "+" + "-" * (type_w + 2) + "+" + "-" * (ver_w + 2) + "+" + "-" * (src_w + 2) + "+" + "-" * cnt_w + "+"

    # Header
    print(sep)
    print(f"| {'Name'.ljust(name_w - 1)}| {'Type'.ljust(type_w - 1)}| {'Version'.ljust(ver_w - 1)}| {'Source'.ljust(src_w - 1)}| {'Uses'.ljust(cnt_w - 1)}|")
    print(sep.replace("-", "="))

    for r in records:
        name = r.get("name", "")[:name_w]
        rtype = (r.get("type") or "")[: type_w]
        ver = (r.get("version") or "")[: ver_w]
        src = (r.get("source") or "")[: src_w]
        cnt = str(r.get("usage_count", 0))
        print(f"| {name.ljust(name_w - 1)}| {rtype.ljust(type_w - 1)}| {ver.ljust(ver_w - 1)}| {src.ljust(src_w - 1)}| {cnt.rjust(cnt_w - 2)} |")

    print(sep)
    skills = sum(1 for r in records if r.get("type") == "skill")
    ext = sum(1 for r in records if r.get("type") == "external_tool")
    plugins = sum(1 for r in records if r.get("type") == "plugin")
    print(f"{len(records)} tool(s) ({skills} skills, {ext} external tools, {plugins} plugins)")


# ---------------------------------------------------------------------------
#  CLI: --find
# ---------------------------------------------------------------------------


def cmd_find(keyword, index_path=None):
    """Search index by name/tags/capabilities/scenarios."""
    path = _resolve_expanduser(index_path or _default_index_path())
    if not os.path.exists(path):
        print("Index not found. Run --scan first.", file=sys.stderr)
        return

    with open(path, "r", encoding="utf-8") as f:
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

    print(f"Found {len(matches)} tool(s) matching '{keyword}':\n")
    for r in matches:
        name = r.get("name", "?")
        rtype = r.get("type", "skill")
        desc = (r.get("description") or "(no description)")[:120]
        tags = r.get("tags") or []
        tag_str = f"  tags: [{', '.join(tags)}]" if tags else ""
        extra = ""
        if rtype == "plugin":
            cmds = list(r.get("subcommands", {}).keys())
            extra = f"  commands: {', '.join(cmds[:4])}{'...' if len(cmds) > 4 else ''}"
        elif rtype == "external_tool":
            cmds = list(r.get("subcommands", {}).keys())
            extra = f"  commands: {', '.join(cmds[:4])}{'...' if len(cmds) > 4 else ''}"
        print(f"  [{rtype}] {name}")
        print(f"    {desc}")
        if tag_str:
            print(tag_str)
        if extra:
            print(extra)
        print()


def cmd_diagnose(index_path=None):
    """Print index health report."""
    path = _resolve_expanduser(index_path or _default_index_path())
    if not os.path.exists(path):
        print("Index not found. Run --scan first.", file=sys.stderr)
        return

    with open(path, "r", encoding="utf-8") as f:
        records = json.load(f)

    records = [r for r in records if r.get("type") == "skill"]
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


def scan_external(config_path=None):
    """Scan only external tools and update index (merge with existing skills)."""
    cfg = load_config(config_path)
    ext_dir = _resolve_expanduser(cfg.get("external_tools_dir", "~/.sebastian/external-tools"))
    index_path = _resolve_expanduser(cfg.get("index_path", "~/.sebastian/index.json"))

    print(f"[scan-external] External tools dir: {ext_dir}", file=sys.stderr)
    print(f"[scan-external] Index: {index_path}", file=sys.stderr)

    # Load old index
    old_index = load_old_index(index_path)

    # Keep existing skills, replace external tools and plugins
    existing_skills = []
    for r in old_index.values():
        if r.get("type") not in ("external_tool", "plugin"):
            existing_skills.append(r)

    # Discover external tools and plugins from descriptors
    ext_files = discover_external_tools(ext_dir)
    ext_records = []
    for fp in ext_files:
        rec = load_tool_descriptor(fp)
        if rec is None:
            continue
        old_rec = old_index.get(rec["name"])
        if old_rec:
            rec["usage_count"] = old_rec.get("usage_count", 0)
        ext_records.append(rec)
        rtype = rec.get("type", "tool")
        print(f"  [{rtype}] {rec['name']}", file=sys.stderr)

    records = existing_skills + ext_records

    # Write index
    _ensure_sebastian_dir()
    with open(index_path, "w", encoding="utf-8") as f:
        json.dump(records, f, indent=2, ensure_ascii=False)
        f.write("\n")

    skills = sum(1 for r in existing_skills if r.get("type") == "skill")
    ext_tools = sum(1 for r in ext_records if r.get("type") == "external_tool")
    plugins = sum(1 for r in ext_records if r.get("type") == "plugin")
    print(f"\n[scan-external] Done. {len(records)} tool(s) in index ({skills} skills, {ext_tools} external tools, {plugins} plugins).", file=sys.stderr)
    return records


def main():
    if len(sys.argv) < 2:
        print(__doc__.strip())
        sys.exit(1)

    command = sys.argv[1]

    if command == "--scan":
        scan()
    elif command == "--scan-external":
        scan_external()
    elif command == "--scan-plugins":
        print("[scan-plugins] Discovering installed plugins from cache...", file=sys.stderr)
        plugins = discover_installed_plugins()
        if not plugins:
            print("  No plugins found in cache.", file=sys.stderr)
        for p in plugins:
            print(f"  [plugin] {p['name']} v{p['version']} ({p['marketplace']})", file=sys.stderr)
            if p['has_skills']:
                for s in p['skill_names']:
                    print(f"    skill: {s}", file=sys.stderr)
        print(f"\n[scan-plugins] Done. {len(plugins)} plugin(s) found.", file=sys.stderr)
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
        print("Available: --scan, --scan-external, --scan-plugins, --list, --find <keyword>, --diagnose")
        sys.exit(1)


if __name__ == "__main__":
    main()
