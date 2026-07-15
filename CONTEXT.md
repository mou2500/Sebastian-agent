# Sebastian-agent

## 项目定位

一个"工程管家"角色 AI agent，灵感来自《黑执事》中的管家 Sebastian。

## 核心理念

所有可调用的能力单元（Skills / 外部工具 / MCP / 插件 / CLI / Agent）统一视为 **工具 (Tool)**，由 Sebastian 统一发现、管理和编排。

## 核心职责

- **工具管理 (Tool Management)**: 检索、更新、管理本机所有工具，包括 Skills、MCP 工具、插件、CLI 工具、其他 Agent
- **任务编排 (Task Orchestration)**: 分析任务、规划方案、指派合适的工具构建工作流

### 第一版范围

管理 Skills + **外部工具（External Tools）**，后续版本再叠加 MCP / Agent / CLI 工具。

## 跨平台兼容

遵循 [Agent Skills 标准](https://agentskills.io/specification)，三大平台已统一：

| 平台 | 支持 |
|------|------|
| Claude Code | 原生 |
| OpenAI Codex CLI | 原生 |
| Gemini CLI | 支持 |
| Cursor / Copilot / Junie | 支持 |

技能存放路径符合标准：
- `~/.claude/skills/` — Claude Code 用户级技能
- `~/.agents/skills/` — Agent Skills 标准的 USER 作用域

## 交互模式

- **手动调用**: 用户通过 `/sebastian <任务>` 按需触发，小任务无需经过 Sebastian
- **工作流模式**: 规划 + 分步执行 — Sebastian 输出方案 → 用户确认 → 分步执行（每步完成后展示结果，用户确认再继续下一步）

## 支持的命令

| 命令 | 说明 |
|------|------|
| `/sebastian <任务描述>` | 核心命令 — 分析任务，从索引中找到匹配的 skills，规划工作流，分步执行 |
| `/sebastian update index` | 更新索引 — 重新扫描全部路径，重建 index.json |
| `/sebastian list` | 查看索引 — 列出索引中所有 skills 摘要表 |
| `/sebastian find <关键词>` | 搜索技能 — 按名称/标签/场景搜索技能 |
| `/sebastian diagnose index` | 索引健康度诊断 — 检查各技能的 frontmatter 字段完整性，输出缺失统计 |
| `/sebastian review` | 审查学习日志 — 查看 lessons.json，推荐需要升级的技能（联动 skill-rpg-loop） |

## 项目结构

```
D:\Projects\Sebastian-agent\     ← 项目源码根目录
├── CONTEXT.md                    ← 项目文档（本文件）
├── sk/
│   └── sebastian/
│       └── SKILL.md              ← Sebastian 的 Skill 源码
├── external-tools/               ← 外部工具/插件描述文件（源码）
│   ├── career-ops.json           ← career-ops 外部工具描述
│   └── webnovel-writer.json      ← webnovel-writer 插件描述
├── scripts/
│   └── scan.py                   ← 索引扫描脚本（开发版）
└── install.sh                    ← 安装脚本（部署到 ~/.claude/skills/ + ~/.sebastian/）
```

### 运行时路径

| 路径 | 说明 |
|------|------|
| `~/.claude/skills/sebastian/SKILL.md` | Skill 入口，`/sebastian` 调用 |
| `~/.sebastian/scan.py` | 扫描脚本（install 时部署） |
| `~/.sebastian/index.json` | 工具元数据索引 |
| `~/.sebastian/config.json` | 路径配置 |
| `~/.sebastian/external-tools/` | 外部工具/插件描述文件 |

### 扫描路径

- `~/.claude/skills/`
- `~/.agents/skills/`
- `~/.sebastian/external-tools/` — 外部工具/插件描述文件（JSON 格式）
- `~/.claude/plugins/cache/` — 已安装的插件缓存（`--scan-plugins` 自动发现）

### 扫描方式

手动触发，通过 `/sebastian update index` 调用。

## SKILL.md Frontmatter 标准

遵循 Agent Skills 标准并扩展 Sebastian 元数据字段。技能作者在 SKILL.md 头部写入 YAML frontmatter：

```yaml
---
name: grill-with-docs
description: 方案质询与文档打磨
version: 1.0.0
tags: [planning, documentation]
capabilities: 分析用户方案，通过质询打磨术语精度，同步更新文档
scenarios: 方案评审、需求澄清、术语统一
paired_with: [skill-creator, darwin-skill]
source: internal
external_url:
update_method:
---
```

扫描策略：**优先读 frontmatter → 正文提取 → 手动补全**。

## 工具索引 (Index Schema)

工具索引存储在 `~/.sebastian/index.json`，由扫描脚本生成。

### Skill 索引字段

```json
{
  "name": "grill-with-docs",
  "path": "~/.claude/skills/grill-with-docs/SKILL.md",
  "description": "方案质询与文档打磨",
  "version": "1.0.0",
  "tags": ["planning", "documentation"],
  "capabilities": "分析用户方案，通过质询打磨术语精度，同步更新文档",
  "scenarios": "方案评审、需求澄清、术语统一",
  "paired_with": ["skill-creator", "darwin-skill"],
  "source": "internal",
  "external_url": "",
  "update_method": "",
  "usage_count": 0
}
```

| 字段 | 说明 |
|------|------|
| `name` | 技能调用名称 |
| `path` | 文件路径（支持多路径来源） |
| `description` | 简短描述 |
| `version` | 版本号 |
| `tags` | 标签，用于搜索匹配 |
| `capabilities` | 它能做什么 |
| `scenarios` | 适合什么场景 |
| `paired_with` | 常和哪个技能搭配 |
| `source` | `internal`（自建）或 `external`（外部下载） |
| `external_url` | 外部来源地址 |
| `update_method` | 外部库的更新方法 |
| `usage_count` | 被管家调用的次数，每次调用 +1，由 Sebastian 自动维护 |

### 外部工具索引字段

外部工具是独立项目中的脚本/工具集，不以 SKILL.md 形式存在。描述文件存放在 `~/.sebastian/external-tools/{name}.json`，由 `scan.py --scan` 自动发现并加入索引。

```json
{
  "name": "career-ops",
  "type": "external_tool",
  "path": "D:/Projects/career-ops",
  "description": "AI 求职自动化工具集",
  "version": "1.20.0",
  "tags": ["job-search", "career"],
  "capabilities": "职位搜索、评估、简历生成、追踪",
  "scenarios": "找工作、求职、面试准备",
  "keywords": ["找工作", "求职", "job", "career"],
  "invoke_type": "command",
  "invoke_cwd": "D:/Projects/career-ops",
  "invoke_template": "node {{script}}",
  "subcommands": {
    "scan": "搜索职位 — node scan.mjs",
    "pdf": "生成简历 PDF — node generate-pdf.mjs"
  },
  "trigger_confidence": {
    "exact_keywords": ["找工作", "求职"],
    "indirect_keywords": ["跳槽", "招聘"]
  },
  "source": "external",
  "usage_count": 0
}
```

| 字段 | 说明 |
|------|------|
| `type` | `external_tool` 标记外部工具 |
| `keywords` | 触发关键词列表，用于路由匹配 |
| `invoke_cwd` | 执行命令的工作目录 |
| `invoke_template` | 命令模板（`{{script}}` 会被替换） |
| `subcommands` | 子命令列表：名称 → 描述/调用方式 |
| `trigger_confidence` | 两级关键词：`exact_keywords` 直接触发，`indirect_keywords` 反问确认 |

### Plugin 索引字段

Plugin 是通过 Claude Code 插件市场安装的插件，描述文件存放在 `~/.sebastian/external-tools/{name}.json`，`type` 设为 `"plugin"`。

```json
{
  "name": "webnovel-writer",
  "type": "plugin",
  "version": "6.2.1",
  "path": "~/.claude/plugins/cache/.../6.2.1",
  "description": "长篇网文创作系统",
  "tags": ["webnovel", "writing", "网文"],
  "capabilities": "初始化、规划、写作、审查、查询、学习、健康检查、仪表盘",
  "scenarios": "写小说、网文创作、故事规划",
  "keywords": ["写小说", "网文", "创作"],
  "invoke_type": "plugin_command",
  "invoke_prefix": "/webnovel-",
  "subcommands": {
    "webnovel-init": "初始化小说项目",
    "webnovel-write": "写作章节"
  },
  "trigger_confidence": {
    "exact_keywords": ["写小说", "网文"],
    "indirect_keywords": ["写作", "创作"]
  },
  "source": "plugin",
  "usage_count": 0
}
```

| 字段 | 说明 |
|------|------|
| `type` | `plugin` 标记为 Claude Code 插件 |
| `invoke_type` | `plugin_command` 表示通过 `/` 斜杠命令调用 |
| `invoke_prefix` | 斜杠命令前缀（如 `/webnovel-`） |
| `keywords` | 触发关键词列表，用于路由匹配 |
| `subcommands` | 子命令列表：名称 → 描述 |
| `trigger_confidence` | 两级关键词：`exact_keywords` 直接触发，`indirect_keywords` 反问确认 |
| `source` | `plugin` 标记为插件市场来源 |

## 进化层次模型

Sebastian 的自我进化分为三个层次，按依赖顺序推进：

| 层次 | 名称 | 能力 | 关键指标 |
|------|------|------|---------|
| **L1 感知层** | 索引感知 | 知道自己有哪些技能、每个技能的信息是否完整 | 索引健康度（完整字段的技能占比） |
| **L2 推理层** | 动态编排 | 不依赖硬编码模板，能根据 tags/paired_with 动态推断组合 | 非模板工作流的占比 |
| **L3 学习层** | 复盘进化 | 每次任务后记录教训，周期性触发 skill-rpg-loop 修剪升级 | lessons 积累量、技能升级频率 |

### 当前状态

- L1：部分就绪 — index.json Schema已定义，scan.py已写，但 `~/.sebastian/` 尚未部署，40个技能中27个 frontmatter 稀疏（≤3字段）
- L2：基础 — 5个硬编码工作流模板，尚未引入动态推断
- L3：空白 — 无 lessons 学习机制

## 索引健康度

scan.py 在扫描时输出健康度报告，格式如下：

```
索引健康度报告
━━━━━━━━━━━━━━━━━━━━━━━━━━━
总计: N skills
完整 (≥6字段):  N skills
基本 (4-5字段): N skills
稀疏 (≤3字段):  N skills  ← 需要补全
━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

字段完整性定义为 frontmatter 中以下字段的覆盖数：
`name + description + tags + capabilities + scenarios + paired_with + version + source`

通过 `/sebastian diagnose index` 触发。

## 学习日志 (Lessons)

每次工作流执行完毕后，Sebastian 自动追加一条记录到 `~/.sebastian/lessons.json`：

```json
{
  "timestamp": "2026-07-02T12:00:00Z",
  "task": "用户原始任务描述",
  "workflow": ["skill-A", "skill-B"],
  "result": "ok | modified | failed",
  "lesson": "学到的东西或发现的不足",
  "recommendation": "可选：建议升级哪个 skill、创建新 skill、调整模板"
}
```

- `result=ok` → 对应 skill 的 usage_count +1
- `result=modified` → usage_count +3
- `result=failed` → usage_count +5
- 累积到 XP ≥ 5 的 skill，`/sebastian review` 时推荐走 skill-rpg-loop 升级

## 术语表

| 术语 | 定义 |
|------|------|
| **Tool (工具)** | 可被 Sebastian 调用的能力单元，是 Skills / MCP / 插件 / CLI / Agent 的统一抽象 |
| **Skill** | 一种 Tool，对应一个 SKILL.md 文件及其配套实现 |
| **MCP Tool** | 通过 Model Context Protocol 注册的工具 |
| **Plugin** | 插件形式的扩展能力 |
| **CLI Tool** | 命令行工具 |
| **Agent (子 Agent)** | 可独立运行的子 Agent，也可作为一种 Tool 被 Sebastian 编排 |
| **Sebastian** | 本 agent 的代称，工程管家角色 |
| **任务编排** | 将用户输入的任务拆解、规划，并指派合适的 Tools 组合执行 |
| **L1 感知层** | Sebastian 进化层次的第一层：索引完整性和自我诊断 |
| **L2 推理层** | Sebastian 进化层次的第二层：基于索引动态推断工作流组合 |
| **L3 学习层** | Sebastian 进化层次的第三层：任务后复盘记录 lessons，周期性触发 skill-rpg-loop |
| **索引健康度** | 衡量索引质量的指标 — 各技能 frontmatter 字段覆盖率的统计 |
| **Lessons (学习日志)** | 工作流执行结果记录，存储在 `~/.sebastian/lessons.json`，用于触发 skill-rpg-loop |
| **XP (经验值)** | 技能的 usage_count 值，result=ok +1, modified +3, failed +5。XP ≥ 5 触发 skill-rpg-loop 升级 |
