---
name: sebastian
description: 工程管家 v2 — 分析任务、加权匹配 skills、编排多步骤工作流、管理工具索引
version: 2.4.0
tags: [orchestration, management, meta, workflow]
capabilities: 意图理解（Phase 0 流水线）、任务分析与拆解、skills 加权匹配与三级定级、多步骤工作流编排、工具索引管理与健康诊断、工作流复盘与学习日志
scenarios: 复杂多步骤任务、技能发现与管理、工作流规划、索引健康诊断、学习复盘
paired_with: [find-skill, darwin-skill, skill-creator, skill-rpg-loop]
source: internal
---

# Sebastian — 工程管家

## 概述

Sebastian 是一个元技能（meta-skill），负责：
1. 根据用户的任务描述，**加权匹配**已安装的 skills 索引，选拔最合适的工具
2. 编排多步骤工作流，处理步骤依赖
3. 管理 skills 索引（更新、列出、搜索、健康诊断）
4. **识别与同类型技能的边界**，做出正确的路由决策

**核心理念：** Sebastian **不直接调用**其他 skills，也不自行完成任务。它生成工作流方案，由 Claude 按步骤执行。它是调度员，不是执行者。

---

## 命令参考

> **⚠️ 沙箱路径兼容性**
> 在 Claude Code 等沙箱环境中，`~` 可能解析为临时影子目录而非真实用户目录。
> `scan.py` 已内置自动探测逻辑（按 `SEBASTIAN_BASE_DIR` 环境变量 → `USERPROFILE`
> → `HOME` 转换 → 实际含 `.claude/skills` 的目录 顺序回退），
> 可直接运行无需手动指定路径。如果仍失败，可显式设置：
> ```bash
> SEBASTIAN_BASE_DIR=/path/to/your/skills python3 scan.py --scan
> ```

### 1. `/sebastian <任务描述>` — 核心编排

**流程：**

### Phase 0：意图理解（新增，在匹配任何 skill 之前执行）
0a. **请求预过滤** — 根据输入的结构特征（句数、动词数量、受众线索、行业线索）判断：
    - 单句 + 明确动作 + 已知对象 → 快速通道（跳过 0b/0c）
    - 多句 + 模糊需求 → 进入 0b 分解
    - 矛盾信号 / 信息不足 → 进入 0b + 标记"需澄清"
0b. **意图分解** — 提取 6 维度：核心产出类型（coreType）、交付格式（deliveryFormat）、受众（audience）、动作（action）、粒度（granularity）、置信度（confidence），生成结构化 Intent 对象 + 概率多解释候选项
0c. **澄清门** — 置信度非 high 或 top-1 概率 < 80% 时，生成最多 2 个澄清问题，用户回答后更新概率

### Phase 1-9：技能匹配与编排（改进）
1. **读取索引** — 读取 `~/.sebastian/index.json`
2. **加权匹配** — 以用户请求原文 + Intent.coreType + Intent.deliveryFormat + Intent.audience 为输入，按 name/tags/description/capabilities/scenarios 多字段权重搜索
3. **三级定级** — 将匹配结果标记为 EXACT / INDIRECT / NOMATCH
4. **阈值熔断** — 根据置信度决定行为：
   - **EXACT (≥70%)** → 继续到步骤 5
   - **INDIRECT (30%~69%)** → 触发反问机制，询问用户是否继续
   - **NOMATCH (<30%)** → 出无匹配报告，不走后续步骤
5. **Scope Guard** — 检查：
   - 用户请求粒度 vs 工具产出粒度是否一致
   - Intent.coreType vs 工具 coreType 是否对齐
   - Intent.deliveryFormat vs 工具的 deliveryFormats → 是否需要额外步骤
6. **冲突消解** — 应用上游优先 / 垂直分离 / 早退出 规则
7. **识别工作流模板** — 任务类型是否匹配预定义的集成工作流
8. **规划工作流** — 生成步骤序列，标注步骤依赖关系，每步注明技术路径类型（skill / 通用工具 / python 脚本等）
9. **展示方案** — 用以下格式向用户展示（每步必须包含"技术路径"和"依赖"）：

   ```
   ┌─────────────────────────────────────────────┐
   │  Sebastian v2 工作流方案                     │
   ├─────────────────────────────────────────────┤
   │  任务: <用户任务描述>                         │
   │  意图: <Intent.coreType> / <Intent.deliveryFormat> │
   │  匹配模式: <模板类别>                        │
   │  匹配技能: <N> 个                           │
   │  步骤依赖: <DAG 简述>                       │
   ├─────────────────────────────────────────────┤
   │  步骤 1: <skill 名称或技术方案>              │
   │          — <做什么>                          │
   │          技术路径: <skill 名 / python / 通用工具>  │
   │  步骤 2: <skill 名称或技术方案> (依赖步骤 1) │
   │          — <做什么>                          │
   │          技术路径: <skill 名 / python / 通用工具>  │
   │  ...                                       │
   └─────────────────────────────────────────────┘
   ```

   方案末尾自动追加路径处理规则：

   ```
   路径处理规则：本方案涉及的每个文件路径，执行者仅检查其存在性。
   存在则继续，不存在则返回用户报告错误。
   不搜索、不猜测、不试替代写法。
   ```

10. **等待确认** — 用户确认后，逐步执行

**执行规则：**
- 每步完成后，展示该步的产出摘要
- 如果某步失败：
  - **停止执行**
  - **向用户报告失败原因和可用的替代方案（如有）**
  - **获得用户授权后再继续**
  - **不得擅自执行计划外的技术方案（如换工具链、安装新依赖等）**
- 所有步骤完成后，给出最终摘要，包括产出的文件/变更
- **工作流完成后，自动追加一条 lessons 记录到 `~/.sebastian/lessons.json`**
- **自建技能记录要求：**
  - 凡是在工作流中用到的**自建技能**（包括管家自己 sebastian），每步执行完毕后立即调用 `/skill-rpg-loop` 记录使用
  - 自建技能列表：`sebastian`、`bifeng`、`novel-learner`、`panel-of-experts`、`shuixian`、`text2img`、`img2img`、`image-recognition`、`skill-rpg-loop`
  - 记录时机：每步执行完成后（而不是等整个工作流结束），调用 `/skill-rpg-loop` 记录该步的 XP
  - 如果某步自建技能执行失败，同样调用 `/skill-rpg-loop` 记录为 `failed`，以便积累经验教训驱动后续升级

### Phase 0 — 意图理解详解

在匹配任何 skill 之前执行。输出一个结构化 Intent 对象，作为后续所有阶段的输入源。

#### 0a. 请求预过滤

基于输入的结构特征（而非关键词）判断：

| 特征 | 判定 | 行为 |
|------|------|------|
| 单句 + 明确动作动词 + 已知对象 | 明确请求 | 快速通道：直接进入 Phase 1，跳过 0b/0c |
| 多句 + 模糊需求 / 行业线索 + 受众线索 | 复杂请求 | 进入 0b 分解 |
| 矛盾信号（如 docx 出现在文件名但描述是营销）或信息不足 | 需澄清 | 进入 0b + 标记"需澄清" |

#### 0b. 意图分解

提取 6 维度：

| 维度 | 示例值 | 说明 |
|------|--------|------|
| `coreType` | `copywriting` / `design` / `data` / `code` / `process` | 核心产出类型 |
| `deliveryFormat` | `docx` / `xlsx` / `html` / `image` / `none` | 交付格式（从文件扩展名或显式指定提取） |
| `audience` | `bank-executive` / `tech-team` / `general` / `unknown` | 受众（从行业线索推断） |
| `action` | `create` / `modify` / `analyze` / `review` / `plan` | 动作（从动词提取） |
| `granularity` | `single-output` / `composite` / `multi-step` | 粒度（输出数量 + 步骤数） |
| `confidence` | `high` / `medium` / `low` | 置信度（信号一致性评估） |

输出示例：

```
Intent {
  coreType: "copywriting",
  deliveryFormat: "docx",
  audience: "bank-executive",
  action: "modify",
  granularity: "single-output",
  confidence: "medium",
  interpretations: [
    { desc: "对公营销文案改写", prob: 0.70 },
    { desc: "docx 格式编辑", prob: 0.25 }
  ]
}
```

#### 0c. 澄清门

触发条件：`confidence != "high"` 或 `interpretations[0].prob < 0.8`

- 生成最多 2 个澄清问题，针对 top-2 解释之间的矛盾点
- 用户回答后更新概率：
  - 被确认的解释：prob × 1.5
  - 被反驳的解释：prob × 0.3
  - 重新归一化
- **一轮澄清后无论清晰与否，都进入 Phase 1**

#### 意图输出如何影响后续阶段

- **加权匹配**：Intent.coreType / Intent.deliveryFormat / Intent.audience 作为额外匹配字段输入
- **Scope Guard**：若 Intent.coreType ≠ Intent.deliveryFormat 的偏好 skill，自动拆分为两步骤（内容层 + 形式层）
- **模板匹配**：coreType ≠ deliveryFormat 时触发模板 G（内容→格式流水线）

---

### 2. `/sebastian update index` — 更新索引

**流程：**

1. 运行 `python3 ~/.sebastian/scan.py --scan`
2. 展示扫描结果摘要（新增/更新/总数 + 索引健康度报告）
3. 如果用户有疑问，可使用 `--list` 或 `--find` 进一步查看

---

### 3. `/sebastian list` — 列出索引

**流程：**

1. 运行 `python3 ~/.sebastian/scan.py --list`
2. 以表格展示所有已索引技能

---

### 4. `/sebastian find <关键词>` — 搜索

**流程：**

1. 运行 `python3 ~/.sebastian/scan.py --find <keyword>`
2. 展示匹配结果及描述

---

### 5. `/sebastian diagnose index` — 索引健康诊断

**流程：**

1. 运行 `python3 ~/.sebastian/scan.py --diagnose`
2. 输出索引健康度报告：总计 / 完整 / 基本 / 稀疏 各多少
3. 列出字段缺失最严重的技能

---

### 6. `/sebastian review` — 审查学习日志

**流程：**

1. 读取 `~/.sebastian/lessons.json`
2. 汇总统计：总执行次数、各 skill 使用次数、XP 排名
3. 推荐 XP ≥ 5 的 skill 走 `/skill-rpg-loop` 升级
4. 展示近期 lessons 摘要

---

## 加权匹配策略（三级匹配 + 阈值熔断）

### 匹配度分级

| 级别 | 标记 | 判定标准 | 行为 |
|------|------|----------|------|
| **精确匹配** | `EXACT` | 工具的核心产出 = 用户需求 | 直接产出方案，推荐该工具 |
| **间接匹配** | `INDIRECT` | 工具包含用户需求作为子功能，但核心产出不同 | 提示 scope 差异，触发反问机制 |
| **无匹配** | `NOMATCH` | 置信度低于阈值（< 30%） | 不出方案，出"无匹配报告" |

### 匹配字段及权重

| 字段 | 权重 | 说明 |
|------|------|------|
| `name` | 高 | 直接名称匹配（最高优先级） |
| `tags` | 高 | 标签分类匹配 |
| `description` | 中 | 描述中的关键词匹配 |
| `capabilities` | 中 | 能力清单匹配 |
| `scenarios` | 低 | 使用场景匹配 |
| `paired_with` | 辅助 | 已知的关联工具链 |
| `Intent.coreType` | **极高** | Phase 0 输出的核心产出类型（优先于原文关键词） |
| `Intent.deliveryFormat` | 高 | Phase 0 输出的交付格式 |
| `Intent.audience` | 中 | Phase 0 输出的受众维度 |

### 匹配流程

0. **意图理解输出** — Phase 0 的结构化 Intent 对象作为额外输入源，`Intent.coreType` / `Intent.deliveryFormat` / `Intent.audience` 加入匹配维度
1. **精确名称匹配**：任务关键词是否直接对应某个 skill 名称
2. **标签聚类**：任务属于哪个领域（design / engineering / productivity / misc）
3. **描述关键词扫描**：在 description / capabilities 中搜索任务关键动名词
4. **场景拟合**：检查 scenarios 是否有与任务相似的预设场景
5. **组合推断**：如果任务覆盖多个领域，自动匹配多个 skills 并识别依赖关系
6. **三级定级**：综合以上结果，将匹配结果标记为 EXACT / INDIRECT / NOMATCH

### 阈值熔断规则

- 综合置信度 **≥ 70%**：EXACT，直接出方案
- 综合置信度 **30% ~ 69%**：INDIRECT，触发反问机制
- 综合置信度 **< 30%**：NOMATCH，出"无匹配报告"

### 无匹配报告模板

```
┌─────────────────────────────────────────────┐
│  无匹配报告                                  │
├─────────────────────────────────────────────┤
│  任务: <用户任务描述>                         │
│  最接近的工具: <技能名> (置信度: X%)          │
│  能力差距: <为什么不完全匹配>                 │
├─────────────────────────────────────────────┤
│  建议替代方案:                               │
│  1. 用 Claude 通用能力直接完成                │
│  2. 用 /find-skill 搜索新技能                │
│  3. 用 /skill-creator 创建专用技能           │
└─────────────────────────────────────────────┘
```

### 反问机制

当匹配度为 `INDIRECT` 时，**不直接产出方案**。先向用户提问澄清：

> **反问模板：**
> "当前没有专门做 <用户需求> 的工具。<候选工具名> 能做 <候选工具的核心功能>（含 <子功能>），但产出是 <实际产出类型> 而非 <用户期望产出类型>。你要用这个，还是换其他方式？"

### 任务范围守卫（Scope Guard）

在编排前检查两个维度：

**维度一：请求粒度 vs 产出粒度（原逻辑）**

| 用户请求粒度 | 工具产出粒度 | 判定 |
|-------------|-------------|------|
| 单一产出（如"设计 logo"） | 单一产出（如专门的 logo 工具） | 匹配 |
| 单一产出（如"设计 logo"） | 复合产出（如 9 面板品牌套件） | 粒度不匹配 → 标记 INDIRECT，触发反问 |
| 复合产出（如"整套品牌视觉"） | 复合产出（品牌套件板） | 匹配 |
| 复合产出（如"整套品牌视觉"） | 单一产出 | 粒度不匹配 → 提示用户需要多个工具组合 |

**维度二：内容 vs 形式对齐（新增）**

当 Phase 0 的意图分解结果可用时，额外检查：

| Intent.coreType | Intent.deliveryFormat | Skill 类型 | 判定 |
|----------------|----------------------|-----------|------|
| `copywriting` | `none` | copywriting skill | 对齐 → 单步骤 |
| `copywriting` | `docx` | copywriting skill | 不对齐 → 触发模板 G，拆分为两步 |
| `document-formatting` | `docx` | docx skill | 对齐 → 单步骤 |
| `design` | `html` | design skill | 对齐 → 单步骤 |

当 `coreType ≠ deliveryFormat` 的偏好 skill 时，Scope Guard 自动识别为两步骤任务：

```
步骤 1: <coreType 对应的 skill> — 产出内容（content layer）
步骤 2: <deliveryFormat 对应的 skill> — 包装为指定格式（presentation layer）
```

### 冲突消解规则

在 Scope Guard 之后、工作流模板匹配之前执行，确保各阶段不打架。

#### 规则 1：上游优先
Phase 0 的意图分析结果，Phase 1 的匹配不能推翻——只能细化。如果 Intent 说 `coreType=copywriting`，即使 "docx" 关键词出现 10 次，也不会把 docx 作为主技能匹配。

#### 规则 2：垂直分离
`coreType` 和 `deliveryFormat` 是两个独立维度，竞争不同技能池。bifeng 和 docx 不在同一个赛道上竞争——bifeng 竞争 coreType，docx 竞争 deliveryFormat。消除直接冲突。

#### 规则 3：早退出
符合 `single + 明确 + high-confidence` 的请求，直接走快速通道进入 Phase 1 的原有流程，Phase 0 不做多解释、不做概率分析、不生成澄清问题。

#### 规则 4：不重复
不复制外部技能的完整复杂公式，只取其核心模式。不引入完整的贝叶斯公式、15 条路由表或 27 个命令映射。

### 不匹配时的回退链

```
1. 重新表述用户任务描述（可能语义不清晰）
2. 用更宽泛的关键词再次搜索索引
3. 建议使用 `/find-skill` 搜索可安装的新技能
4. 建议直接用 Claude 的通用能力完成
5. 如果涉及原创技能需求，建议使用 `/skill-creator` 创建新技能
```

---

## 工作流模板

### 模板 A：Bug 调试流程

适用于"系统出 bug 了 / 哪里报错了 / 性能回退了"

```
步骤 1: /diagnosing-bugs — 结构化调试循环
步骤 2: /tdd (可选) — 修复 + 回归测试
步骤 3: /domain-modeling (可选) — 如果 bug 暴露了领域模型模糊，更新 CONTEXT.md
```

### 模板 B：项目启动流程

适用于"我们要做一个新功能 / 我有个想法"

```
步骤 1: /panel-of-experts (可选) — 需求不明确时多角色讨论
步骤 2: /to-prd — 转化为 PRD 文档
步骤 3: /to-issues — 拆解为垂直切片
步骤 4: /triage — 打标签分类形成 backlog
```

### 模板 C：架构改进流程

适用于"代码需要重构 / 架构需要优化"

```
步骤 1: /grill-with-docs — 领域模型质询
步骤 2: /domain-modeling — 精炼领域模型
步骤 3: /redesign-existing-projects (可选) — UI/前端视觉审计
```

### 模板 D：跨 Session 交接

适用于"先做一部分，下次继续 / 换 agent 接手"

```
步骤 1: /to-prd — 将已完成+剩余计划落地文档
步骤 2: /handoff — 生成交接文档
```

### 模板 E：视觉产出流程

适用于"需要设计/图片/品牌物料"

```
步骤 1: /shuixian (可选) — 美术总监审查方向
步骤 2: 根据产出类型选择:
  - 品牌套件 → /brandkit
  - 网页设计 → /design-taste-frontend
  - 社交卡片 → /guizang-social-card-skill
  - 网页 PPT → /guizang-ppt-skill
  - 文生图 → /text2img
  - 图生图 → /img2img
步骤 3: /stitch-design-taste (可选) — 生成设计规范文档
```

### 模板 F：文档/数据处理流程

适用于"生成报告 / 处理文档 / 处理表格"

```
步骤 1: 根据产出类型选择:
  - Word 文档 → /docx
  - 电子表格 → /xlsx
  - 演示文稿 → /pptx
步骤 2: /handoff (可选) — 长任务需要存档
```

### 模板 G：内容→格式两步流水线（新增）

适用于 Intent.coreType ≠ Intent.deliveryFormat 的场景——核心产出和交付格式不在同一个 skill 中。

触发条件：Phase 0 的 Scope Guard 检测到 coreType 与 deliveryFormat 不对齐。

```
步骤 1: <coreType 对应的 skill> — 产出内容（content layer）
步骤 2: <deliveryFormat 对应的 skill> — 包装为指定格式（presentation layer）
```

示例：对公营销文案→输出 .docx 文件

```
Intent.coreType = copywriting → /bifeng（写文案）
Intent.deliveryFormat = docx  → /docx（输出 .docx）
```

---

## 与同类型技能的冲突边界

### Sebastian vs. 直接调用 skill

| 场景 | 用哪个 |
|------|--------|
| 用户说"我想做 X"（X 是一个技能名或非常具体的操作） | 直接调用 skill，无需 Sebastian |
| 用户说"帮我做 X，需要 Y 和 Z 配合" | **Sebastian** |
| 用户说"我不知道该用什么来做 X" | `/find-skill` |
| 用户说"我有一个包含多步骤的复杂任务" | **Sebastian** |
| 用户只说了模糊的需求，需要先判断属于哪个领域 | **Sebastian（Phase 0 意图理解）** |

### Sebastian 的判断原则

1. **单步骤 → 不经过 Sebastian**：如果任务明确对应一个技能的直接能力，直接调用
2. **多步骤 → 经过 Sebastian**：需要 2 个以上技能协作，或步骤有前后依赖关系
3. **订阅/定时 → 经过 loop 技能**：定期执行的任务用 `/loop`
4. **纯咨询 → 经过 panel-of-experts**：需要多角色讨论的战略决策

---

## 集成指南

### 与 `diagnosing-bugs` 的集成

识别现象关键词（"报错"、"失败"、"异常"、"崩溃"、"性能回退"），优先编排 `/diagnosing-bugs` 作为第一步。

### 与 `find-skill` 的集成

当匹配结果为 NOMATCH 时，自动建议使用 `/find-skill` 搜索可安装的外部技能。

### 与 `skill-rpg-loop` 的集成

**双向集成，不只是升级推荐：**

1. **即时记录（正向）** — 工作流每步执行自建技能后，立即调用 `/skill-rpg-loop` 记录该步使用，让 rpg-loop 实时积累 XP
2. **升级推荐（反向）** — `/sebastian review` 识别 XP ≥ 5 的技能后，推荐用户执行 `/skill-rpg-loop` 升级对应技能

具体规则见上方「Lessons 与 rpg-loop 记录」章节。

### 与 `darwin-skill` 的集成

当 lessons 中某技能连续 modified/failed 超过 3 次，推荐使用 `/darwin-skill` 做结构性优化。

### 与 `handoff` 的集成

在长周期工作流的末尾自动推荐。

### Skill coreType 映射表

Phase 0 加权匹配和 Scope Guard 依赖以下 coreType 映射关系。执行 `/sebastian update index` 后自动加载：

| Skill | coreType | deliveryFormats |
|-------|----------|----------------|
| bifeng | `copywriting` | none（无文件输出） |
| docx | `document-formatting` | docx |
| xlsx | `data-analysis` | xlsx |
| pptx | `presentation` | pptx |
| design-taste-frontend | `design` | html |
| brandkit | `design` | png |
| guizang-social-card-skill | `design` | png |
| guizang-ppt-skill | `design` | html |
| text2img | `image-generation` | image |
| img2img | `image-generation` | image |
| imagegen-frontend-web | `design` | image |
| imagegen-frontend-mobile | `design` | image |
| kami | `typesetting` | html |
| sebastian | `meta` | none |

---

## Lessons 与 rpg-loop 记录

### 双轨记录机制

每次工作流执行时，Sebastian 需要做两件事：

1. **Lessons 记录（内部复盘用）** → 写入 `~/.sebastian/lessons.json`
2. **rpg-loop 记录（XP 经验值用）** → 调用 `/skill-rpg-loop` 记录每步使用

两者分工：Lessons 记录整个工作流的复盘信息，rpg-loop 记录每个自建技能的 XP 用于升级。

### Lessons 记录格式

工作流执行完毕后（所有步骤完成或用户终止），Sebastian 自动追加一条记录到 `~/.sebastian/lessons.json`：

```json
{
  "timestamp": "2026-07-02T12:00:00Z",
  "task": "用户原始任务描述",
  "workflow": ["skill-A", "skill-B"],
  "result": "ok | modified | failed",
  "lesson": "学到的东西或发现的不足",
  "recommendation": "建议升级/创建哪个 skill"
}
```

- `result=ok` → 参与 skill 的 usage_count +1
- `result=modified` → usage_count +3
- `result=failed` → usage_count +5
- XP ≥ 5 的 skill 在 `/sebastian review` 时推荐走 `/skill-rpg-loop` 升级

### rpg-loop 记录调用时机

每步自建技能执行完成后，主动调用 `/skill-rpg-loop` 记录该步的使用结果。具体：

| 步骤结果 | rpg-loop 调用方式 |
|---------|-----------------|
| 执行成功，用户无修正 | 记录 `ok`，XP +1 |
| 执行成功但经用户修改 | 记录 `modified`，XP +3 |
| 执行失败或放弃 | 记录 `failed`，XP +5 |

调用示例：
```
/skill-rpg-loop 记录 sebastian 使用: 编排工作流，结果=ok
/skill-rpg-loop 记录 bifeng 使用: 撰写营销文案，结果=modified
/skill-rpg-loop 记录 text2img 使用: 生成产品配图，结果=ok
```

每步独立记录，不应等到整个工作流结束才统一调用。

---

## 编排示例

### 示例 1：产品发布会 landing page + 社交卡片

```
┌─────────────────────────────────────────────┐
│  Sebastian v2 工作流方案                     │
├─────────────────────────────────────────────┤
│  任务: 产品发布会 landing page + 社交卡片    │
│  匹配模式: 视觉产出流程                      │
│  匹配技能: 3 个                             │
├─────────────────────────────────────────────┤
│  步骤 1: /guizang-ppt-skill                 │
│          — 生成发布会风格的网页 PPT/展示页   │
│  步骤 2: /guizang-social-card-skill         │
│          — 生成社交媒体分享卡片              │
│  步骤 3: /brandkit                          │
│          — 补充品牌套件保持视觉一致性        │
└─────────────────────────────────────────────┘
```

### 示例 2：系统出现了一个奇怪的 bug

```
┌─────────────────────────────────────────────┐
│  Sebastian v2 工作流方案                     │
├─────────────────────────────────────────────┤
│  任务: 排查线上 bug                          │
│  匹配模式: Bug 调试流程                      │
│  匹配技能: 2 个                             │
│  步骤依赖: 步骤 2 依赖步骤 1                │
├─────────────────────────────────────────────┤
│  步骤 1: /diagnosing-bugs                   │
│          — 结构化调试                        │
│  步骤 2: /tdd                              │
│          — TDD 增加回归测试                  │
└─────────────────────────────────────────────┘
```

### 示例 3：对公营销文案 → 输出 .docx（内容→格式流水线）

```
┌─────────────────────────────────────────────┐
│  Sebastian v2 工作流方案                     │
├─────────────────────────────────────────────┤
│  任务: 修改 docx 格式的银行合作建议书        │
│  意图: copywriting / docx                   │
│  匹配模式: 模板 G（内容→格式流水线）         │
│  匹配技能: 2 个                             │
│  步骤依赖: 步骤 2 依赖步骤 1                │
├─────────────────────────────────────────────┤
│  步骤 1: /bifeng                            │
│          — 对公营销文案改写（content layer）  │
│  步骤 2: /docx                              │
│          — 包装为 .docx 格式（presentation）  │
└─────────────────────────────────────────────┘
```

## 维护者

- 作者：何牟
- 来源：内部自建
- 版本：2.4.0
- 最后更新：2026-07-03
