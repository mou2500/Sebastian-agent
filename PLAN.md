# Sebastian-agent 开发计划

## 依赖关系图

```
Phase 1: 基础设施
  config.json schema  ← 扫描路径配置
  scan.py             ← 读取 config → 扫描 SKILL.md → 输出 index.json
                         依赖: config.json schema

Phase 2: 核心 Skill
  SKILL.md            ← /sebastian 入口，任务编排逻辑
                         依赖: index.json format, scan.py

Phase 3: 部署集成
  install.sh          ← 部署到 ~/.claude/skills/ + ~/.sebastian/

Phase 4: 初始化
  运行 install.sh
  第一次扫描（scan.py）
  补充已有 skills 的 frontmatter
```

---

## Phase 1 — 基础设施

### 1.1 config.json schema

`~/.sebastian/config.json`

```json
{
  "skill_paths": [
    "~/.claude/skills",
    "~/.agents/skills"
  ],
  "index_path": "~/.sebastian/index.json",
  "last_scan": null
}
```

- 只有两个关键字段：扫描路径、索引路径
- 由 install.sh 创建初始版本

### 1.2 scan.py

`scripts/scan.py` → 部署到 `~/.sebastian/scan.py`

**功能：**

| 子功能 | 说明 |
|--------|------|
| 读取 config | 从 `~/.sebastian/config.json` 加载扫描路径 |
| 扫描目录 | 遍历所有路径，寻找 `**/SKILL.md` 文件 |
| 解析 frontmatter | 用 Python `yaml` 库解析 YAML frontmatter |
| 正文提取 | 无 frontmatter 时从正文提取：首段作为 description |
| 合并旧索引 | 保留已有的 `usage_count`（不被扫描覆盖） |
| 写入 index.json | 输出标准格式 |
| CLI 参数 | `--scan` 全量扫描，`--list` 打印摘要，`--find <kw>` 搜索 |

**关键逻辑：**

```
scan.py --scan
  → 读取 config.json
  → 遍历每个 skill_path 下的所有 SKILL.md
  → 对每个文件:
     读取文件
     if 有 YAML frontmatter:
        提取 name/description/version/tags/...
     else:
        将文件名作为 name
        取正文第一行作为 description
        其他字段留空
     → 从旧 index.json 读取 usage_count（如有）
     → 组装成完整记录
  → 写入 index.json

scan.py --list
  → 读取 index.json
  → 打印表格

scan.py --find <keyword>
  → 读取 index.json
  → 按 name/tags/capabilities/scenarios 匹配
  → 打印结果
```

**需注意：**
- usage_count 在扫描中不被重置——只从旧索引继承
- 路径统一用 os.path.expanduser() 展开
- 首次运行时 config.json 不存在 → 自动创建默认配置

---

## Phase 2 — 核心 Skill

### 2.1 SKILL.md

`sk/sebastian/SKILL.md` → 部署到 `~/.claude/skills/sebastian/SKILL.md`

**结构：**

```yaml
---
name: sebastian
description: 工程管家 — 分析任务、编排 skills 工作流、管理工具索引
version: 0.1.0
tags: [orchestration, management, meta]
capabilities: 任务分析与拆解、skills 工作流编排、工具索引管理与搜索
scenarios: 复杂多步骤任务、技能发现与管理、工作流规划
paired_with: [find-skill, darwin-skill, skill-creator]
source: internal
---
```

**指令逻辑（SKILL.md 正文）：**

SKILL.md 本质上是给 Claude 的指令。正文需要指导 Claude 实现 4 个命令的行为：

1. **`/sebastian <任务描述>`** — 核心编排流程：
   - 读取 `~/.sebastian/index.json`
   - 根据任务描述，在索引中搜索匹配的 skills
   - 规划工作流（步骤序列）
   - 展示方案给用户确认
   - 分步执行，每步完成后展示结果

2. **`/sebastian update index`** — 触发扫描：
   - 运行 `python3 ~/.sebastian/scan.py --scan`
   - 展示扫描结果摘要

3. **`/sebastian list`** — 列出索引：
   - 运行 `python3 ~/.sebastian/scan.py --list`
   - 展示技能表格

4. **`/sebastian find <关键词>`** — 搜索：
   - 运行 `python3 ~/.sebastian/scan.py --find <keyword>`
   - 展示匹配结果

**重要设计：**

SKILL.md 不能直接"调用"其他 skill。它通过以下方式编排工作流：

```
Step 1: 输出 "现在请调用 /bifeng 写 3 条文案"
         → 用户确认
         → Claude 按指令调用 /bifeng

Step 2: 输出 "文案已生成，现在请调用 /guizang-social-card-skill 生成卡片"
         → 用户确认
         → Claude 按指令调用对应 skill
```

即：**Sebastian 的工作流编排 = 为 Claude 生成下一步指令，Claude 去执行**。

---

## Phase 3 — 部署集成

### 3.1 install.sh

`install.sh` — 安装脚本

```bash
# 1. 创建 ~/.claude/skills/sebastian/
mkdir -p ~/.claude/skills/sebastian

# 2. 复制 SKILL.md
cp sk/sebastian/SKILL.md ~/.claude/skills/sebastian/SKILL.md

# 3. 创建 ~/.sebastian/
mkdir -p ~/.sebastian

# 4. 复制 scan.py
cp scripts/scan.py ~/.sebastian/scan.py

# 5. 创建初始 config.json（如果不存在）
if [ ! -f ~/.sebastian/config.json ]; then
    cat > ~/.sebastian/config.json << 'CONFIG'
{
  "skill_paths": [
    "~/.claude/skills",
    "~/.agents/skills"
  ],
  "index_path": "~/.sebastian/index.json",
  "last_scan": null
}
CONFIG
fi

# 6. 首次扫描（可选）
echo "Sebastian 已安装。运行以下命令完成首次扫描："
echo "  python3 ~/.sebastian/scan.py --scan"
```

---

## Phase 4 — 初始化与补全

4.1 运行 install.sh
4.2 执行首次扫描 `python3 ~/.sebastian/scan.py --scan`
4.3 查看扫描结果，发现缺失字段的 skills
4.4 手动补全关键 skills 的 frontmatter
4.5 重新扫描确保完整
4.6 验证：在 Claude Code 中调用 `/sebastian list`

---

## 执行顺序总结

| 步骤 | 产出 | 估算 |
|------|------|------|
| 1 | 写 config.json schema (已定) | - |
| 2 | 写 scan.py (扫描 + 解析 frontmatter + list + find) | 最大块 |
| 3 | 写 SKILL.md (核心编排指令) | 第二大块 |
| 4 | 写 install.sh | 小块 |
| 5 | 运行 install.sh + 首次扫描 + 补全 frontmatter | 一次性 |
| 6 | 验证 | 一次性 |
