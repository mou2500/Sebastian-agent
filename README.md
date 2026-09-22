# Sebastian — 工程管家 v3

<p align="center">
  <img src="assets/Sebastian_logo.svg" alt="Sebastian Logo" width="400"/>
</p>

> 版本 3.0.0 | 作者：[何牟](https://github.com/mou2500)

Sebastian 是一个**元技能（meta-skill）**，负责编排多步骤工作流。它是调度员，不是执行者。

## 结构

```
Sebastian-agent/
├── assets/
│   └── Sebastian_logo.svg   ← Logo（矢量）
├── sk/sebastian/
│   ├── SKILL.md              ← 技能本体
│   ├── CHANGELOG.md          ← 更新日志
│   ├── RESEARCH-matching.md  ← 双层匹配架构研究文档
│   └── bench-cases.json      ← 路由评测种子用例集
├── external-tools/           ← 外部工具/插件描述文件
│   ├── career-ops.json       ← 求职自动化工具
│   └── webnovel-writer.json  ← 网文创作插件
├── scripts/
│   ├── scan.py               ← 技能/工具/插件扫描索引
│   ├── match_cache.py        ← TF-IDF 召回 + 匹配缓存（v3.0.0 双层架构 Layer 1）
│   ├── bench.py              ← 路由评测: 校验/打分/回归告警/TF-IDF 召回率
│   ├── compact_lessons.py    ← 学习日志锚定压缩归档
│   └── enrich_frontmatter.py ← 元数据增强
├── install.sh                ← 部署脚本
├── CONTEXT.md                ← 项目上下文
└── PLAN.md                   ← 开发规划
```

## 快速使用

安装后通过 `/sebastian` 命令调用：

```
/sebastian <任务描述>          # 核心编排（双层匹配）
/sebastian update index        # 更新索引
/sebastian list                # 列出索引
/sebastian find <关键词>       # 搜索技能
/sebastian diagnose index      # 索引健康诊断
/sebastian review              # 审查学习日志 + 升级推荐
/sebastian bench               # 路由评测基准（量化匹配质量）
/sebastian compact lessons     # 压缩学习日志（锚定摘要归档）
/sebastian revisions           # 查看/回滚技能修订历史
/sebastian health              # 技能健康度面板
/sebastian recommend <任务>    # 双层技能推荐（TF-IDF 召回 + 模型精排）
```

## 安装

```bash
git clone https://github.com/mou2500/Sebastian-agent.git
cd Sebastian-agent
bash install.sh
```

## 核心能力

- **Phase 0 意图理解** — 预过滤 → 6 维分解 → 澄清门
- **双层匹配架构** — TF-IDF 确定性召回（Layer 1）+ 模型语义精排（Layer 2），固定 0-4 rubric，fallback 链，5min 匹配缓存（v3.0.0）
- **三级定级** — EXACT（score=4）/ INDIRECT（score=3）/ NOMATCH（score≤2 或无候选）
- **阈值熔断** — 匹配度不足时自动反问澄清
- **Scope Guard** — 请求粒度 vs 产出粒度、内容 vs 格式对齐检查
- **冲突消解** — 上游优先 / 垂直分离 / 早退出 / 不重复 规则
- **外部工具路由** — 关键词触发独立项目脚本（career-ops 求职工具）
- **Plugin 路由** — 关键词触发 Claude Code 插件技能（webnovel-writer 网文创作）
- **工具索引管理** — 统一索引 skill / external_tool / plugin 三种类型
- **路由评测基准** — 固定用例集量化匹配质量（hit@1/hit@3/分层报告/TF-IDF 召回率/回归告警）
- **12 种工作流模板** — 灵活编排多步骤任务（含步骤成功判定约定；A–I 通用/视觉/文档/求职/网文 + K 内容质检 + L 自维护 + M 金融研究）
- **双轨记录** — Lessons 复盘 + rpg-loop XP 经验值
- **记录锚定压缩** — lessons 超阈值后按技能分桶归档，固定章节增量摘要
- **轻量版本化** — 每次扫描为内容变更的 SKILL.md 存修订快照，支持回滚
- **回退显式化** — lessons 记录标注走了哪条回退链、为什么
- **技能健康度面板** — 聚合 ok/modified/failed/fallback 次数、回退率、失败 rung 分布
- **升级治理** — 失败定级（skill/template/harness）+ novelty 去重档案 + itemized delta 升级契约 + 保护锚点
- **索引健康诊断** — 技能索引质量检查与修复

## 双层匹配架构（v3.0.0）

```
用户任务
  │
  ▼
[Layer 1 — TF-IDF 确定性召回]  纯 Python，<10ms，永远可用
  │  召回 top-20 候选，score 归一化 0-4
  ▼
[Layer 2 — 模型精排]  Claude 按固定 0-4 rubric 评分
  │  ≥3 分纳入推荐；=4 EXACT；=3 INDIRECT；≤2 NOMATCH
  │  缓存：相同任务 + index hash → 5min 内直接取结果
  ▼
推荐列表
  │
  ▼ fallback（模型不可用时）
  纯 TF-IDF 结果，标注 method="tfidf" + fallback_reason
```

研究文档见 `sk/sebastian/RESEARCH-matching.md`（对照 `kitze/skillbox` 推荐引擎，取核心模式，遵守冲突消解规则 4：不引入数据库/外部服务）。

## 许可

MIT
