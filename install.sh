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
SCAN_SRC="scripts/scan.py"

SKILL_DST="$HOME/.claude/skills/sebastian/SKILL.md"
SEBASTIAN_DIR="$HOME/.sebastian"
SCAN_DST="$SEBASTIAN_DIR/scan.py"
CONFIG_DST="$SEBASTIAN_DIR/config.json"

echo "=== Sebastian 安装 ==="

# ------------------------------------------------------------------
# 1. 创建目标目录
# ------------------------------------------------------------------
echo "[1/5] 创建目录..."
mkdir -p "$(dirname "$SKILL_DST")"
mkdir -p "$SEBASTIAN_DIR"

# ------------------------------------------------------------------
# 2. 复制 SKILL.md
# ------------------------------------------------------------------
if [ -f "$SKILL_SRC" ]; then
    cp "$SKILL_SRC" "$SKILL_DST"
    echo "[2/5] SKILL.md → $SKILL_DST"
else
    echo "[2/5] 错误: 未找到 $SKILL_SRC" >&2
    exit 1
fi

# ------------------------------------------------------------------
# 3. 复制 scan.py
# ------------------------------------------------------------------
if [ -f "$SCAN_SRC" ]; then
    cp "$SCAN_SRC" "$SCAN_DST"
    chmod +x "$SCAN_DST"
    echo "[3/5] scan.py → $SCAN_DST"
else
    echo "[3/5] 错误: 未找到 $SCAN_SRC" >&2
    exit 1
fi

# ------------------------------------------------------------------
# 4. 创建初始 config.json（如果不存在）
# ------------------------------------------------------------------
if [ ! -f "$CONFIG_DST" ]; then
    cat > "$CONFIG_DST" << 'CONFIG'
{
  "skill_paths": [
    "~/.claude/skills",
    "~/.agents/skills"
  ],
  "index_path": "~/.sebastian/index.json",
  "last_scan": null
}
CONFIG
    echo "[4/5] config.json → $CONFIG_DST"
else
    echo "[4/5] config.json 已存在，跳过"
fi

# ------------------------------------------------------------------
# 5. 首次扫描（可选）
# ------------------------------------------------------------------
if [ "${1:-}" != "--no-scan" ]; then
    echo "[5/5] 执行首次扫描..."
    python3 "$SCAN_DST" --scan
else
    echo "[5/5] 跳过首次扫描（--no-scan）"
fi

echo ""
echo "=== Sebastian 安装完成 ==="
echo ""
echo "可用命令:"
echo "  /sebastian <任务描述>    — 编排工作流"
echo "  /sebastian update index  — 更新技能索引"
echo "  /sebastian list          — 列出所有技能"
echo "  /sebastian find <关键词>  — 搜索技能"
