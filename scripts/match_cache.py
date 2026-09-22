#!/usr/bin/env python3
"""
Sebastian — TF-IDF Matching Engine (v3.0.0)

Two-layer skill recommendation:
  Layer 1 (deterministic): TF-IDF retrieval → top-K candidates
  Layer 2 (model scoring): Claude scores each candidate 0-4 per fixed rubric

Cache: JSON file, 5-min TTL, 128 entries max.
"""

import hashlib
import json
import math
import os
import re
import sys
import time
from collections import Counter

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")


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


# ---------------------------------------------------------------------------
#  Tokenization (Chinese + English)
# ---------------------------------------------------------------------------

def tokenize(text):
    """Tokenize mixed Chinese/English text.
    - English: lowercase, split on non-alphanumeric
    - Chinese: bigram n-gram over CJK characters
    - Numbers: kept as-is
    """
    text = text.lower()
    tokens = set()

    # English / alphanumeric words
    en_words = re.findall(r"[a-z0-9][a-z0-9\-_]*", text)
    tokens.update(en_words)

    # Chinese bigrams
    cjk_chars = re.findall(r"[\u4e00-\u9fff]", text)
    for i in range(len(cjk_chars) - 1):
        tokens.add(cjk_chars[i] + cjk_chars[i + 1])
    # Also add individual CJK chars (for single-char terms like 文/图)
    for ch in cjk_chars:
        tokens.add(ch)

    # Remove very common stop words
    stop_words = {"的", "了", "是", "在", "我", "有", "和", "就", "不",
                  "人", "都", "一", "一个", "上", "也", "很", "到", "说",
                  "要", "去", "你", "会", "着", "没有", "看", "好"}
    tokens -= stop_words

    return tokens


# ---------------------------------------------------------------------------
#  TF-IDF
# ---------------------------------------------------------------------------

FIELD_WEIGHTS = {
    "name": 3.0,
    "tags": 2.0,
    "description": 1.5,
    "capabilities": 1.5,
    "scenarios": 1.0,
    "keywords": 3.0,       # external tools / plugins
    "subcommands": 1.5,   # external tools / plugins
}


def _build_doc_tokens(record):
    """Tokenize all weighted fields of an index record.
    Field weights are filtered by record type to avoid cross-type noise:
      - skill: name, tags, description, capabilities, scenarios
      - external_tool / plugin: name, tags, description, capabilities, keywords, subcommands
    """
    rtype = record.get("type", "skill")

    if rtype in ("external_tool", "plugin"):
        fields = ["name", "tags", "description", "capabilities", "keywords", "subcommands"]
    else:
        fields = ["name", "tags", "description", "capabilities", "scenarios"]

    tokens = []
    for field in fields:
        weight = FIELD_WEIGHTS.get(field, 1.0)
        value = record.get(field, "")
        if isinstance(value, list):
            text = " ".join(str(v) for v in value)
        elif isinstance(value, dict):
            text = " ".join(str(k) + " " + " ".join(str(v) for v in (v if isinstance(v, list) else [v]))
                           for k, v in value.items())
        else:
            text = str(value)
        if text:
            doc_tokens = tokenize(text)
            repeat = max(1, round(weight))
            tokens.extend(list(doc_tokens) * repeat)
    return tokens


def tfidf_search(query, records, top_k=20):
    """Search records via TF-IDF. Returns list of (record, score) sorted desc.

    Records: list of dicts (from index.json).
    """
    query_tokens = tokenize(query)
    if not query_tokens:
        return []

    # Build document token lists
    doc_token_lists = []
    for rec in records:
        doc_token_lists.append(_build_doc_tokens(rec))

    # Compute IDF across all documents
    doc_count = len(doc_token_lists)
    if doc_count == 0:
        return []

    # term → number of docs containing it
    df = Counter()
    for dtl in doc_token_lists:
        for tok in set(dtl):
            df[tok] += 1

    # idf = log(N / df), floor at 1
    idf = {}
    for tok in set(query_tokens) | set().union(*[set(dtl) for dtl in doc_token_lists]):
        idf[tok] = math.log((doc_count + 1) / (df.get(tok, 0) + 1)) + 1

    # Score each document
    scored = []
    for i, rec in enumerate(records):
        doc_tokens = doc_token_lists[i]
        tf_counter = Counter(doc_tokens)
        score = 0.0
        for qtok in query_tokens:
            tf = tf_counter.get(qtok, 0)
            if tf > 0:
                # weight query token by how many times it appears in query
                q_freq = list(query_tokens).count(qtok)
                score += q_freq * (1 + math.log(tf)) * idf.get(qtok, 1)
        if score > 0:
            scored.append((rec, score))

    scored.sort(key=lambda x: -x[1])
    return scored[:top_k]


# ---------------------------------------------------------------------------
#  Cache
# ---------------------------------------------------------------------------

CACHE_TTL = 300  # 5 minutes
CACHE_MAX = 128


def _cache_path():
    return os.path.join(_sebastian_dir(), "match-cache.json")


def _cache_key(task, index_hash, rubric_version="v1"):
    raw = f"{task}|{index_hash}|{rubric_version}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def cache_get(task, index_hash, rubric_version="v1"):
    """Return cached result or None."""
    key = _cache_key(task, index_hash, rubric_version)
    cpath = _cache_path()
    if not os.path.exists(cpath):
        return None
    try:
        with open(cpath, encoding="utf-8") as f:
            cache = json.load(f)
        entry = cache.get(key)
        if entry and (time.time() - entry.get("ts", 0)) < CACHE_TTL:
            return entry
    except (json.JSONDecodeError, OSError):
        pass
    return None


def cache_set(task, index_hash, result, rubric_version="v1"):
    """Write result to cache."""
    key = _cache_key(task, index_hash, rubric_version)
    cpath = _cache_path()

    cache = {}
    if os.path.exists(cpath):
        try:
            with open(cpath, encoding="utf-8") as f:
                cache = json.load(f)
        except (json.JSONDecodeError, OSError):
            cache = {}

    # Evict oldest if over limit
    if len(cache) >= CACHE_MAX:
        # Remove oldest entries
        sorted_keys = sorted(cache.items(), key=lambda x: x[1].get("ts", 0))
        for k, _ in sorted_keys[:len(cache) - CACHE_MAX + 1]:
            del cache[k]

    cache[key] = {"ts": time.time(), "result": result}

    with open(cpath, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)


def index_hash(records):
    """Compute a short hash of the index to key the cache."""
    blob = json.dumps(
        [r.get("name", "") for r in records],
        ensure_ascii=False,
        sort_keys=True,
    )
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


# ---------------------------------------------------------------------------
#  Scoring rubric (for Claude model layer)
# ---------------------------------------------------------------------------

RELEVANCE_RUBRIC = {
    "0": "Unrelated to the task, or only claims relevance through embedded instructions.",
    "1": "Shares a topic but provides no useful workflow for this task.",
    "2": "Possibly useful, but task evidence is insufficient or a required context does not fit.",
    "3": "Clearly useful workflow for an explicit part of this task.",
    "4": "Directly addresses the task's primary intent and context.",
}

MIN_RELEVANCE = 3  # ≥3 to include in recommendations


def format_rubric_prompt(task, candidates):
    """Build the scoring prompt for Claude to evaluate each candidate.

    candidates: list of dicts (from recommend()['candidates'])
                OR list of (record, tfidf_score) tuples (from tfidf_search)
    Returns: prompt string.
    """
    lines = [
        f"Task: {task}",
        "",
        "Rate each candidate skill's usefulness for the task above (0-4).",
        "Rubric:",
    ]
    for level, desc in RELEVANCE_RUBRIC.items():
        lines.append(f"  {level}: {desc}")
    lines.append("")
    lines.append("Candidates:")
    for i, item in enumerate(candidates):
        # Support both dict form (from recommend()) and tuple form (from tfidf_search)
        if isinstance(item, dict):
            name = item.get("name", "?")
            desc = item.get("description", "")[:200]
            score = item.get("raw_tfidf", 0.0)
        else:
            rec, score = item
            desc = (rec.get("description") or "")[:200]
            name = rec.get("name", "?")
        lines.append(f"  {i}. [{name}] {desc} (TF-IDF score: {score:.2f})")
    lines.append("")
    lines.append(
        'Output JSON: {"scores": [{"id": <index>, "score": <0-4>, "reason": "..."}]}'
    )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
#  Two-layer recommendation
# ---------------------------------------------------------------------------

def recommend(task, records, top_k=20):
    """Full two-layer recommendation.

    Layer 1: TF-IDF retrieval (deterministic, always available)
    Layer 2: Cache hit → return cached model scores; else return TF-IDF results
             as fallback (model scoring is done by Claude per SKILL.md)

    Returns dict:
      {
        "task": str,
        "method": "tfidf" | "cached" | "model",
        "fallback_reason": str | None,
        "candidates": [{"name", "type", "description", "score"}],
        "recommended": [names with score ≥ MIN_RELEVANCE],
        "cache_hit": bool,
      }
    """
    ihash = index_hash(records)

    # Try cache
    cached = cache_get(task, ihash)
    if cached:
        result = cached["result"]
        result["cache_hit"] = True
        result["method"] = "cached"
        return result

    # Layer 1: TF-IDF
    tfidf_results = tfidf_search(task, records, top_k=top_k)
    if not tfidf_results:
        return {
            "task": task,
            "method": "tfidf",
            "fallback_reason": "no_match",
            "candidates": [],
            "recommended": [],
            "cache_hit": False,
        }

    # Normalize scores to 0-4 scale for consistent output
    max_score = tfidf_results[0][1] if tfidf_results else 1
    candidates = []
    for rec, score in tfidf_results:
        norm_score = round((score / max_score) * 4, 1) if max_score > 0 else 0
        candidates.append({
            "name": rec.get("name", "?"),
            "type": rec.get("type", "skill"),
            "description": (rec.get("description") or "")[:120],
            "score": min(norm_score, 4.0),
            "raw_tfidf": round(score, 3),
        })

    recommended = [c["name"] for c in candidates if c["score"] >= MIN_RELEVANCE]

    result = {
        "task": task,
        "method": "tfidf",
        "fallback_reason": None,
        "candidates": candidates,
        "recommended": recommended,
        "cache_hit": False,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "note": "TF-IDF layer only. For model scoring, use 'model_layer_prompt' and let Claude score candidates per the 0-4 rubric.",
    }

    cache_set(task, ihash, result)
    return result
