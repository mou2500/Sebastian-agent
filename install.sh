#!/bin/bash
#
# install.sh — Sebastian 部署脚本
#
# 用法:
#   ./install.sh              # 完整安装
#   ./install.sh --no-scan    # 安装但不执行首次扫描
#

set -euo pipefail

SKILL_SRC="sk/sebastian/SKILL.md"
SKILL_BUNDLE_SRC="sk/sebastian"
SCAN_SRC="scripts/scan.py"
BENCH_SRC="scripts/bench.py"
COMPACT_SRC="scripts/compact_lessons.py"
BENCH_SEED_SRC="sk/sebastian/bench-cases.json"
EXT_DIR_SRC="external-tools"

# 检测真实用户目录（避开 Claude Code 沙箱的临时 HOME）
if [ -n "${SEBASTIAN_HOME:-}" ]; then
  REAL_HOME="$SEBASTIAN_HOME"
elif [ -d "$HOME/.sebastian" ]; then
  REAL_HOME="$HOME"
elif [ -n "${USERNAME:-}" ] && [ -d "/c/Users/$USERNAME/.sebastian" ]; then
  REAL_HOME="/c/Users/$USERNAME"
else
  REAL_HOME="$HOME"
fi

SKILL_DST_DIR="$REAL_HOME/.claude/skills/sebastian"
SKILL_DST="$SKILL_DST_DIR/SKILL.md"
SEBASTIAN_DIR="$REAL_HOME/.sebastian"
SCAN_DST="$SEBASTIAN_DIR/scan.py"
BENCH_DST="$SEBASTIAN_DIR/bench.py"
COMPACT_DST="$SEBASTIAN_DIR/compact_lessons.py"
BENCH_DST_JSON="$SEBASTIAN_DIR/bench.json"
CONFIG_DST="$SEBASTIAN_DIR/config.json"
EXT_DIR_DST="$SEBASTIAN_DIR/external-tools"

echo "=== Sebastian 安装 ==="

# ------------------------------------------------------------------
# 1. 创建目标目录
# ------------------------------------------------------------------
echo "[1/6] 创建目录..."
mkdir -p "$(dirname "$SKILL_DST")"
mkdir -p "$SEBASTIAN_DIR"
mkdir -p "$EXT_DIR_DST"

# ------------------------------------------------------------------
# 2. 复制 SKILL.md + 技能目录文档（CHANGELOG/README）
# ------------------------------------------------------------------
if [ -f "$SKILL_SRC" ]; then
    mkdir -p "$SKILL_DST_DIR"
    cp "$SKILL_SRC" "$SKILL_DST"
    echo "[2/6] SKILL.md → $SKILL_DST"
    for doc in CHANGELOG.md README.md bench-cases.json; do
        if [ -f "$SKILL_BUNDLE_SRC/$doc" ]; then
            cp "$SKILL_BUNDLE_SRC/$doc" "$SKILL_DST_DIR/$doc"
            echo "[2/6] $doc → $SKILL_DST_DIR/$doc"
        fi
    done
else
    echo "[2/6] 错误: 未找到 $SKILL_SRC" >&2
    exit 1
fi

# ------------------------------------------------------------------
# 3. 复制脚本（scan / bench / compact）
# ------------------------------------------------------------------
for src_dst in "$SCAN_SRC:$SCAN_DST" "$BENCH_SRC:$BENCH_DST" "$COMPACT_SRC:$COMPACT_DST"; do
    src="${src_dst%%:*}"
    dst="${src_dst#*:}"
    if [ -f "$src" ]; then
        cp "$src" "$dst"
        chmod +x "$dst"
        echo "[3/6] $(basename "$src") → $dst"
    else
        echo "[3/6] 错误: 未找到 $src" >&2
        exit 1
    fi
done

# ------------------------------------------------------------------
# 4. 部署外部工具描述文件 + 路由评测种子
# ------------------------------------------------------------------
if [ -d "$EXT_DIR_SRC" ]; then
    mkdir -p "$EXT_DIR_DST"
    for f in "$EXT_DIR_SRC"/*.json; do
        if [ -f "$f" ]; then
            cp "$f" "$EXT_DIR_DST/"
            echo "[4/6] 外部工具: $(basename "$f") → $EXT_DIR_DST/"
        fi
    done
else
    echo "[4/6] 无外部工具描述文件，跳过"
fi
if [ ! -f "$BENCH_DST_JSON" ] && [ -f "$BENCH_SEED_SRC" ]; then
    cp "$BENCH_SEED_SRC" "$BENCH_DST_JSON"
    echo "[4/6] bench 种子 → $BENCH_DST_JSON (首次部署)"
else
    echo "[4/6] bench.json 已存在，跳过种子部署"
fi

# ------------------------------------------------------------------
# 5. 创建初始 config.json（如果不存在）
# ------------------------------------------------------------------
if [ ! -f "$CONFIG_DST" ]; then
    cat > "$CONFIG_DST" << 'CONFIG'
{
  "skill_paths": [
    "~/.claude/skills",
    "~/.agents/skills"
  ],
  "external_tools_dir": "~/.sebastian/external-tools",
  "index_path": "~/.sebastian/index.json",
  "last_scan": null
}
CONFIG
    echo "[5/6] config.json → $CONFIG_DST"
else
    echo "[5/6] config.json 已存在，跳过"
fi

# ------------------------------------------------------------------
# 5. 首次扫描（可选）
# ------------------------------------------------------------------
if [ "${1:-}" != "--no-scan" ]; then
    echo "[6/6] 执行首次扫描..."
    python3 "$SCAN_DST" --scan
else
    echo "[6/6] 跳过首次扫描（--no-scan）"
fi

echo ""
echo "=== Sebastian 安装完成 ==="
echo ""
echo "可用命令:"
echo "  /sebastian <任务描述>    — 编排工作流（含外部工具路由）"
echo "  /sebastian update index  — 更新工具索引（技能 + 外部工具）"
echo "  /sebastian list          — 列出所有工具"
echo "  /sebastian find <关键词>  — 搜索工具"
echo "  /sebastian diagnose index— 索引健康诊断"
echo "  /sebastian bench         — 路由评测基准"
echo "  /sebastian compact lessons — 学习日志压缩归档"
