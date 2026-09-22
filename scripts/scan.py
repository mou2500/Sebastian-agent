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
    python3 scan.py --recommend <task>  # Two-layer TF-IDF + model recommendation (v3.0.0)
"""

import hashlib
import json
import os
import re
import shutil
import sys
from pathlib import Path
from datetime import datetime, timezone

# v3.0.0: TF-IDF matching engine
try:
    import match_cache
except ImportError:
    match_cache = None

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

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
    "author": "",
    "external_url": "",
    "update_method": "",
    "usage_count": 0,
    "content_hash": "",
    "last_revision": "",
    "revision_count": 0,
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
              "source", "author", "external_url", "update_method"):
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
#  Revision snapshots (lightweight versioning)
# ---------------------------------------------------------------------------

REVISIONS_DIR = "~/.sebastian/skill-revisions"
MAX_REVISIONS_PER_SKILL = 20


def _revisions_dir():
    return _resolve_expanduser(REVISIONS_DIR)


# Names that have >1 source path (e.g. a .system built-in + a user copy).
# Populated by scan() before it saves revisions; used to disambiguate dirs.
_COLLIDING_NAMES = set()


def _skill_revision_dir(skill_name, path=""):
    """Revision dir per skill. Same-named skills (e.g. .system vs. user)
    get a path-keyed subdirectory so their histories don't mix."""
    base = skill_name
    if path and skill_name in _COLLIDING_NAMES:
        base = f"{skill_name}__{hashlib.sha1(path.encode('utf-8')).hexdigest()[:6]}"
    return os.path.join(_revisions_dir(), base)


def _file_hash(text):
    """SHA-256 hash of file content (bytes-safe via UTF-8)."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _stamp():
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def save_revision(skill_name, content, path=""):
    """Save a revision snapshot for a skill. Returns revision filename or None if skipped."""
    rev_dir = _skill_revision_dir(skill_name, path)
    Path(rev_dir).mkdir(parents=True, exist_ok=True)

    content_hash = _file_hash(content)
    short_hash = content_hash[:8]

    # Check if last revision has same hash → skip
    existing = sorted(f for f in os.listdir(rev_dir) if f.endswith(".md"))
    if existing:
        last = existing[-1]
        # Filename format: YYYYMMDDTHHMMSSZ_<hash>.md
        last_hash = last.rsplit("_", 1)[-1].replace(".md", "") if "_" in last else ""
        if last_hash == short_hash:
            return None  # unchanged

    fname = f"{_stamp()}_{short_hash}.md"
    fpath = os.path.join(rev_dir, fname)
    with open(fpath, "w", encoding="utf-8") as f:
        f.write(content)

    # Trim old revisions if over limit
    all_revs = sorted(f for f in os.listdir(rev_dir) if f.endswith(".md"))
    if len(all_revs) > MAX_REVISIONS_PER_SKILL:
        for old in all_revs[: len(all_revs) - MAX_REVISIONS_PER_SKILL]:
            try:
                os.remove(os.path.join(rev_dir, old))
            except OSError:
                pass

    return fname


def _find_revision_dirs(skill_name):
    """Find all revision directories for a skill (handles path-keyed dirs
    for same-named skills). Returns a list of dir paths."""
    rev_dir = _skill_revision_dir(skill_name)
    if os.path.isdir(rev_dir):
        return [rev_dir]
    # No plain dir — try path-keyed variants: <name>__<hash6>
    base_dir = _revisions_dir()
    if not os.path.isdir(base_dir):
        return []
    import glob
    found = glob.glob(os.path.join(base_dir, f"{skill_name}__*"))
    return [d for d in found if os.path.isdir(d)]


def list_revisions(skill_name):
    """List all saved revisions for a skill, newest first.
    For same-named skills, merges results from all path-keyed dirs."""
    dirs = _find_revision_dirs(skill_name)
    results = []
    for d in dirs:
        files = sorted(
            (f for f in os.listdir(d) if f.endswith(".md")),
            reverse=True,
        )
        for f in files:
            fpath = os.path.join(d, f)
            parts = f.replace(".md", "").split("_", 1)
            ts = parts[0] if parts else "?"
            h = parts[1] if len(parts) > 1 else ""
            size = os.path.getsize(fpath)
            results.append({"filename": f, "timestamp": ts, "hash": h,
                           "size": size, "dir": os.path.basename(d)})
    results.sort(key=lambda r: r["timestamp"], reverse=True)
    return results


def revert_revision(skill_name, revision_name, target_path=None):
    """Restore a skill's SKILL.md from a revision snapshot.
    Returns (success: bool, target_path: str)."""
    # Find the revision file across all candidate dirs
    rev_path = None
    for d in _find_revision_dirs(skill_name):
        candidate = os.path.join(d, revision_name)
        if os.path.exists(candidate):
            rev_path = candidate
            break
    if rev_path is None:
        return False, f"Revision not found: {revision_name}"

    # Find current SKILL.md path from index if not provided
    if target_path is None:
        index_path = _default_index_path()
        old_index = load_old_index(index_path)
        rec = old_index.get(skill_name)
        if not rec or not rec.get("path"):
            return False, f"Skill '{skill_name}' not found in index, can't determine target path"
        target_path = rec["path"]

    if not os.path.exists(target_path):
        return False, f"Target file missing: {target_path}"

    # First, snapshot current state as a revision too (so revert itself is undoable)
    with open(target_path, "r", encoding="utf-8") as f:
        current = f.read()
    save_revision(skill_name, current, path=target_path)

    # Copy revision content over
    shutil.copy2(rev_path, target_path)
    return True, target_path


def revisions_status():
    """Print summary of all skill revisions."""
    rev_dir = _revisions_dir()
    if not os.path.isdir(rev_dir):
        print("(no revisions yet — run --scan to create first snapshots)")
        return

    skills = sorted(d for d in os.listdir(rev_dir)
                    if os.path.isdir(os.path.join(rev_dir, d)))
    if not skills:
        print("(no revisions yet)")
        return

    total = 0
    total_size = 0
    print(f"{'Skill':<30} {'Revisions':>10}  {'Latest':<18}  {'Size':>8}")
    print("-" * 72)
    for s in skills:
        revs = list_revisions(s)
        n = len(revs)
        total += n
        latest = revs[0]["timestamp"] if revs else "-"
        size = sum(r["size"] for r in revs)
        total_size += size
        size_str = f"{size/1024:.1f}K" if size < 1024*1024 else f"{size/1024/1024:.1f}M"
        print(f"{s:<30} {n:>10}  {latest:<18}  {size_str:>8}")
    print("-" * 72)
    total_str = f"{total_size/1024:.1f}K" if total_size < 1024*1024 else f"{total_size/1024/1024:.1f}M"
    print(f"{'TOTAL':<30} {total:>10}  {'':<18}  {total_str:>8}")
    print(f"\n(per-skill cap: {MAX_REVISIONS_PER_SKILL} revisions)")


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
    old_by_key = load_old_index_by_key(index_path)

    # --- Discover skills ---
    files = discover_skill_files(skill_paths)
    print(f"[scan] Found {len(files)} SKILL.md file(s)", file=sys.stderr)

    # Detect same-named skills with different source paths so their
    # revision histories don't mix (e.g. a .system built-in + a user copy).
    global _COLLIDING_NAMES
    _COLLIDING_NAMES = set()
    _name_paths = {}
    for fp in files:
        name = os.path.basename(os.path.dirname(fp)) or os.path.splitext(os.path.basename(fp))[0]
        _name_paths.setdefault(name, set()).add(fp)
    _COLLIDING_NAMES = {n for n, ps in _name_paths.items() if len(ps) > 1}

    records = []
    new_revisions = 0
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

        # Content hash & revision snapshot
        content_hash = _file_hash(text)
        rec["content_hash"] = content_hash
        old_rec = _find_old_rec(rec["name"], fp, old_index, old_by_key)

        # Save revision if content changed (or first scan)
        if not old_rec or old_rec.get("content_hash") != content_hash:
            rev_name = save_revision(rec["name"], text, path=fp)
            if rev_name:
                rec["last_revision"] = rev_name
                old_count = old_rec.get("revision_count", 0) if old_rec else 0
                rec["revision_count"] = old_count + 1
                new_revisions += 1
            else:
                # Hash matches last revision (shouldn't happen often but handle it)
                rec["last_revision"] = old_rec.get("last_revision", "") if old_rec else ""
                rec["revision_count"] = old_rec.get("revision_count", 0) if old_rec else 0
        else:
            rec["last_revision"] = old_rec.get("last_revision", "")
            rec["revision_count"] = old_rec.get("revision_count", 0)

        # Merge usage_count from old index
        if old_rec:
            rec["usage_count"] = old_rec.get("usage_count", 0)

        records.append(rec)
        src = "frontmatter" if fm_text else "body"
        changed = " [changed]" if (not old_rec or old_rec.get("content_hash") != content_hash) else ""
        print(f"  [skill] {rec['name']}{changed}", file=sys.stderr)

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
    if new_revisions:
        print(f"[scan] {new_revisions} skill(s) changed → revision snapshot saved.", file=sys.stderr)
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


def load_old_index_by_key(index_path):
    """Load index keyed by (name, path) for skills that share a name.

    Returns a dict: {name: [record, ...]}  where each record has its original
    path.  Used by scan() to match the *same physical file* even when two
    SKILL.md files happen to have the same skill name (e.g. .system vs user)."""
    if not os.path.exists(index_path):
        return {}
    try:
        with open(index_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        result = {}
        if isinstance(data, dict):
            # Legacy: {name: record}  → wrap in list
            for name, rec in data.items():
                result.setdefault(name, []).append(rec)
        else:
            for rec in data:
                name = rec.get("name")
                if name:
                    result.setdefault(name, []).append(rec)
        return result
    except (json.JSONDecodeError, KeyError, TypeError):
        return {}


def _find_old_rec(name, path, old_index, old_by_key):
    """Find the old record matching a specific (name, path) or fall back to name only."""
    # Try exact (name, path) match first
    candidates = old_by_key.get(name, [])
    if candidates:
        for c in candidates:
            if c.get("path") == path:
                return c
        # name match but path differs → still better than nothing
        return candidates[0]
    # Fall back to legacy name-only
    return old_index.get(name)


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
    rev_w = 5

    sep = "+" + "-" * (name_w + 2) + "+" + "-" * (type_w + 2) + "+" + "-" * (ver_w + 2) + "+" + "-" * (src_w + 2) + "+" + "-" * cnt_w + "+" + "-" * rev_w + "+"

    # Header
    print(sep)
    print(f"| {'Name'.ljust(name_w - 1)}| {'Type'.ljust(type_w - 1)}| {'Version'.ljust(ver_w - 1)}| {'Source'.ljust(src_w - 1)}| {'Uses'.ljust(cnt_w - 1)}| {'Rev'.ljust(rev_w - 1)}|")
    print(sep.replace("-", "="))

    for r in records:
        name = r.get("name", "")[:name_w]
        rtype = (r.get("type") or "")[: type_w]
        ver = (r.get("version") or "")[: ver_w]
        src = (r.get("source") or "")[: src_w]
        cnt = str(r.get("usage_count", 0))
        rev = str(r.get("revision_count", 0) or "-")
        print(f"| {name.ljust(name_w - 1)}| {rtype.ljust(type_w - 1)}| {ver.ljust(ver_w - 1)}| {src.ljust(src_w - 1)}| {cnt.rjust(cnt_w - 2)} | {rev.rjust(rev_w - 2)} |")

    print(sep)
    skills = sum(1 for r in records if r.get("type") == "skill")
    ext = sum(1 for r in records if r.get("type") == "external_tool")
    plugins = sum(1 for r in records if r.get("type") == "plugin")
    total_rev = sum(r.get("revision_count", 0) for r in records if r.get("type") == "skill")
    print(f"{len(records)} tool(s) ({skills} skills, {ext} external tools, {plugins} plugins)")
    print(f"Total skill revisions: {total_rev} (see --revisions or --history <skill>)")


# ---------------------------------------------------------------------------
#  CLI: --recommend (v3.0.0 two-layer matching)
# ---------------------------------------------------------------------------


def cmd_recommend(task, index_path=None):
    """Two-layer skill recommendation.

    Layer 1: TF-IDF deterministic retrieval (always available)
    Layer 2: Cache hit OR model scoring prompt (Claude executes per SKILL.md)

    Output: JSON to stdout.
    """
    path = _resolve_expanduser(index_path or _default_index_path())
    if not os.path.exists(path):
        print("Index not found. Run --scan first.", file=sys.stderr)
        sys.exit(1)

    with open(path, "r", encoding="utf-8") as f:
        records = json.load(f)

    if match_cache is None:
        print("ERROR: match_cache module not found in scripts/", file=sys.stderr)
        sys.exit(1)

    result = match_cache.recommend(task, records)

    # If TF-IDF layer found candidates, build the model-layer prompt
    # so Claude can score them (SKILL.md step 11 instructs Claude to do this)
    if result["method"] == "tfidf" and result["candidates"]:
        prompt = match_cache.format_rubric_prompt(task, result["candidates"])
        result["model_layer_prompt"] = prompt

    print(json.dumps(result, ensure_ascii=False, indent=2))


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


def _load_lessons_stats():
    """Aggregate skill statistics from lessons.json (both flat and archive).

    Returns dict: {skill_name: {ok, modified, failed, total, last_used,
                                fallback_count, rung_failures: {skill, template, harness}}}
    """
    lessons_path = os.path.join(_sebastian_dir(), "lessons.json")
    archive_path = os.path.join(_sebastian_dir(), "lessons-archive.json")
    stats = {}

    def _record_skill(skill, result, timestamp, has_fallback=False, rung=None):
        if skill not in stats:
            stats[skill] = {"ok": 0, "modified": 0, "failed": 0, "total": 0,
                            "last_used": "", "fallback_count": 0,
                            "rung_failures": {"skill": 0, "template": 0, "harness": 0}}
        s = stats[skill]
        s["total"] += 1
        if result in s:
            s[result] += 1
        if timestamp and (not s["last_used"] or timestamp > s["last_used"]):
            s["last_used"] = timestamp
        if has_fallback:
            s["fallback_count"] += 1
        if rung and rung in s["rung_failures"]:
            s["rung_failures"][rung] += 1

    # Flat lessons
    if os.path.exists(lessons_path):
        try:
            with open(lessons_path, "r", encoding="utf-8") as f:
                lessons = json.load(f)
            if isinstance(lessons, list):
                for r in lessons:
                    result = r.get("result", "ok")
                    ts = r.get("timestamp", "")
                    wf = r.get("workflow") or []
                    has_fb = bool(r.get("fallback") or r.get("fallback_reason")
                                  or r.get("fallback_chain"))
                    rung = r.get("rung") if result == "failed" else None
                    for skill in wf:
                        _record_skill(skill, result, ts, has_fb, rung)
        except (json.JSONDecodeError, OSError):
            pass

    # Archive digests (stats only, not individual records)
    if os.path.exists(archive_path):
        try:
            with open(archive_path, "r", encoding="utf-8") as f:
                archive = json.load(f)
            digests = archive.get("digests", []) if isinstance(archive, dict) else []
            for d in digests:
                skill = d.get("skill", "unknown")
                st = d.get("stats", {})
                period = d.get("period", "")
                # Extract end date from period "YYYY-MM-DD ~ YYYY-MM-DD"
                end_date = period.split("~")[-1].strip() if "~" in period else period
                ts = end_date + "T23:59:59Z" if end_date else ""
                fb_count = sum(item.get("count", 0) for item in d.get("fallback_top", []))
                for result in ("ok", "modified", "failed"):
                    count = st.get(result, 0)
                    for _ in range(count):
                        _record_skill(skill, result, ts, fb_count > 0)
        except (json.JSONDecodeError, OSError, TypeError):
            pass

    return stats


def _days_since(iso_timestamp):
    """Approximate days since an ISO timestamp string. Returns None if invalid."""
    if not iso_timestamp:
        return None
    try:
        # Handle various formats
        ts_str = iso_timestamp.replace("Z", "+00:00")
        if "T" not in ts_str:
            ts_str = ts_str + "T00:00:00+00:00"
        then = datetime.fromisoformat(ts_str)
        now = datetime.now(timezone.utc)
        delta = now - then
        return delta.days
    except (ValueError, TypeError):
        return None


def cmd_health(index_path=None):
    """Skill health dashboard: usage, success rate, activity, failures."""
    path = _resolve_expanduser(index_path or _default_index_path())
    if not os.path.exists(path):
        print("Index not found. Run --scan first.", file=sys.stderr)
        return

    with open(path, "r", encoding="utf-8") as f:
        records = json.load(f)

    stats = _load_lessons_stats()
    skills = [r for r in records if r.get("type") == "skill"]
    ext_tools = [r for r in records if r.get("type") in ("external_tool", "plugin")]

    if not skills:
        print("(no skills in index)")
        return

    # Merge index usage_count with lessons stats
    for s in skills:
        name = s["name"]
        if name in stats:
            s["_health"] = stats[name]
        else:
            s["_health"] = {"ok": 0, "modified": 0, "failed": 0, "total": 0,
                            "last_used": "", "fallback_count": 0,
                            "rung_failures": {"skill": 0, "template": 0, "harness": 0}}

    total_lessons = sum(s["_health"]["total"] for s in skills)
    total_ok = sum(s["_health"]["ok"] for s in skills)
    total_modified = sum(s["_health"]["modified"] for s in skills)
    total_failed = sum(s["_health"]["failed"] for s in skills)
    total_fallback = sum(s["_health"]["fallback_count"] for s in skills)

    print()
    print("Sebastian Skill Health Dashboard")
    print("=" * 60)
    print(f"  Skills indexed:  {len(skills)}")
    print(f"  External tools:  {len(ext_tools)}")
    print(f"  Total lesson records: {total_lessons}")
    if total_lessons > 0:
        ok_pct = total_ok * 100 // total_lessons
        mod_pct = total_modified * 100 // total_lessons
        fail_pct = total_failed * 100 // total_lessons
        fb_pct = total_fallback * 100 // total_lessons
        print(f"    ok={total_ok} ({ok_pct}%)  modified={total_modified} ({mod_pct}%)  "
              f"failed={total_failed} ({fail_pct}%)  fallback={total_fallback} ({fb_pct}%)")

    # --- Most used skills ---
    print()
    print("📊  Most Used (by lesson records)")
    print("-" * 60)
    by_usage = sorted(skills, key=lambda s: -s["_health"]["total"])
    rank = 1
    for s in by_usage[:10]:
        h = s["_health"]
        if h["total"] == 0:
            break
        days = _days_since(h["last_used"])
        days_str = f"{days}d ago" if days is not None else "?"
        bar_len = 20
        filled = int(bar_len * h["total"] / max(by_usage[0]["_health"]["total"], 1))
        bar = "█" * filled + "░" * (bar_len - filled)
        print(f"  {rank:>2}. {s['name']:<28} {bar}  {h['total']:>3}  ({days_str})")
        rank += 1
    if rank == 1:
        print("  (no usage data yet)")

    # --- High failure rate ---
    print()
    print("⚠️  High Failure Rate (>=30%, min 2 records)")
    print("-" * 60)
    fail_list = [s for s in skills
                 if s["_health"]["total"] >= 2
                 and s["_health"]["failed"] > 0
                 and s["_health"]["failed"] / s["_health"]["total"] >= 0.3]
    fail_list.sort(key=lambda s: -s["_health"]["failed"] / s["_health"]["total"])
    if fail_list:
        for s in fail_list[:10]:
            h = s["_health"]
            rate = h["failed"] * 100 // h["total"]
            rungs = h["rung_failures"]
            rung_str = ", ".join(f"{k}:{v}" for k, v in rungs.items() if v > 0) or "n/a"
            print(f"  {s['name']:<28}  {h['failed']}/{h['total']} ({rate}%)  rungs: {rung_str}")
    else:
        print("  ✓ No skills with high failure rate (or insufficient data)")

    # --- High modification rate (candidates for upgrade) ---
    print()
    print("🔧  High Modification Rate (>=40%, min 2 records)")
    print("-" * 60)
    mod_list = [s for s in skills
                if s["_health"]["total"] >= 2
                and s["_health"]["modified"] > 0
                and s["_health"]["modified"] / s["_health"]["total"] >= 0.4]
    mod_list.sort(key=lambda s: -s["_health"]["modified"] / s["_health"]["total"])
    if mod_list:
        for s in mod_list[:10]:
            h = s["_health"]
            rate = h["modified"] * 100 // h["total"]
            print(f"  {s['name']:<28}  {h['modified']}/{h['total']} ({rate}%) → 升级候选")
    else:
        print("  (no skills with high modification rate yet)")

    # --- Inactive skills (never used or >90d unused) ---
    print()
    print("💤  Inactive / Never Used (in index but no lesson records)")
    print("-" * 60)
    never_used = [s for s in skills if s["_health"]["total"] == 0]
    # Also count from usage_count field (legacy / index-only metric)
    index_never_used = [s for s in skills if s.get("usage_count", 0) == 0
                        and s["_health"]["total"] == 0]
    print(f"  Never used (no lessons): {len(never_used)}/{len(skills)} skills")
    if never_used:
        # Show first 15
        for s in never_used[:15]:
            print(f"    · {s['name']}")
        if len(never_used) > 15:
            print(f"    …and {len(never_used) - 15} more")

    print()
    print("Tip: 运行 /sebastian review 查看升级推荐 (按失败定级)")


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
    elif command == "--recommend":
        if len(sys.argv) < 3:
            print("Usage: python3 scan.py --recommend <task description>")
            sys.exit(1)
        cmd_recommend(sys.argv[2])
    elif command == "--find":
        if len(sys.argv) < 3:
            print("Usage: python3 scan.py --find <keyword>")
            sys.exit(1)
        cmd_find(sys.argv[2])
    elif command == "--diagnose":
        cmd_diagnose()
    elif command == "--health":
        cmd_health()
    elif command == "--revisions":
        revisions_status()
    elif command == "--history":
        if len(sys.argv) < 3:
            print("Usage: python3 scan.py --history <skill-name>")
            sys.exit(1)
        skill = sys.argv[2]
        revs = list_revisions(skill)
        if not revs:
            print(f"No revisions found for '{skill}' (run --scan first to create snapshots)")
        else:
            print(f"Revisions for '{skill}' ({len(revs)} total, newest first):")
            print()
            print(f"{'#':>3}  {'Timestamp':<18}  {'Hash':<10}  {'Size':>8}  Filename")
            print("-" * 70)
            for i, r in enumerate(revs, 1):
                size_str = f"{r['size']}B" if r['size'] < 1024 else f"{r['size']/1024:.1f}K"
                print(f"{i:>3}  {r['timestamp']:<18}  {r['hash']:<10}  {size_str:>8}  {r['filename']}")
            print()
            print("To revert: python3 scan.py --revert <skill-name> <filename>")
    elif command == "--revert":
        if len(sys.argv) < 4:
            print("Usage: python3 scan.py --revert <skill-name> <revision-filename>")
            print("  (find filename with --history <skill-name>)")
            sys.exit(1)
        skill = sys.argv[2]
        revision = sys.argv[3]
        # Pre-check before asking
        rev_dir = _skill_revision_dir(skill)
        rev_path = os.path.join(rev_dir, revision)
        if not os.path.exists(rev_path):
            print(f"ERROR: revision not found: {revision}")
            print(f"  Path checked: {rev_path}")
            sys.exit(1)

        # Show what's about to happen
        index_path = _default_index_path()
        old_index = load_old_index(index_path)
        rec = old_index.get(skill)
        target = rec.get("path", "?") if rec else "?"
        print(f"About to revert '{skill}':")
        print(f"  Target file: {target}")
        print(f"  Revert to:   {revision}")
        print()
        print("WARNING: This will overwrite the current SKILL.md with the revision content.")
        print("  (current state will be saved as a new revision first, so revert is undoable)")
        print()
        # Require confirmation via --yes flag (non-interactive for safety)
        if len(sys.argv) >= 5 and sys.argv[4] == "--yes":
            ok, msg = revert_revision(skill, revision)
            if ok:
                print(f"Reverted '{skill}' → {msg}")
                print("Run --scan to rebuild the index.")
            else:
                print(f"ERROR: {msg}")
                sys.exit(1)
        else:
            print("To confirm, re-run with --yes at the end:")
            print(f"  python3 scan.py --revert {skill} {revision} --yes")
    else:
        print(f"Unknown command: {command}")
        print("Available: --scan, --scan-external, --scan-plugins, --list, --find <keyword>,")
        print("           --diagnose, --health, --revisions, --history <skill>, --revert <skill> <rev>,")
        print("           --recommend <task>  (v3.0.0 two-layer TF-IDF + model recommendation)")
        sys.exit(1)


if __name__ == "__main__":
    main()
