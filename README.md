# Sebastian — 工程管家 v2

<p align="center">
  <img src="assets/Sebastian_logo.svg" alt="Sebastian Logo" width="400"/>
</p>

> 版本 2.5.0 | 作者：[何牟](https://github.com/mou2500)

Sebastian 是一个**元技能（meta-skill）**，负责编排多步骤工作流。它是调度员，不是执行者。

## 结构

```
Sebastian-agent/
├── assets/
│   └── Sebastian_logo.svg   ← Logo（矢量）
├── sk/sebastian/
│   ├── SKILL.md          ← 技能本体
│   └── CHANGELOG.md      ← 更新日志
├── external-tools/       ← 外部工具/插件描述文件
│   ├── career-ops.json   ← 求职自动化工具
│   └── webnovel-writer.json ← 网文创作插件
├── scripts/
│   ├── scan.py           ← 技能/工具/插件扫描索引
│   └── enrich_frontmatter.py  ← 元数据增强
├── install.sh            ← 部署脚本
├── CONTEXT.md            ← 项目上下文
└── PLAN.md               ← 开发规划
```

## 快速使用

安装后通过 `/sebastian` 命令调用：

```
/sebastian <任务描述>        # 核心编排
/sebastian update index      # 更新索引
/sebastian list              # 列出索引
/sebastian find <关键词>      # 搜索技能
/sebastian diagnose index    # 索引健康诊断
/sebastian review            # 审查学习日志
```

## 安装

```bash
git clone https://github.com/mou2500/Sebastian-agent.git
cd Sebastian-agent
bash install.sh
```

## 核心能力

- **Phase 0 意图理解** — 预过滤 → 6 维分解 → 澄清门
- **Skills 加权匹配** — 三级定级（EXACT / INDIRECT / NOMATCH）
- **阈值熔断** — 匹配度不足时自动反问澄清
- **Scope Guard** — 内容 vs 格式对齐检查
- **冲突消解** — 上游优先 / 垂直分离 / 早退出规则
- **外部工具路由** — 关键词触发独立项目脚本（career-ops 求职工具）
- **Plugin 路由** — 关键词触发 Claude Code 插件技能（webnovel-writer 网文创作）
- **工具索引管理** — 统一索引 skill / external_tool / plugin 三种类型
- **8 种工作流模板** — 灵活编排多步骤任务
- **双轨记录** — Lessons 复盘 + rpg-loop XP 经验值
- **索引健康诊断** — 技能索引质量检查与修复

## 许可

MIT
