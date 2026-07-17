# Changelog

## 2.5.1 (2026-07-17)

- **修复** scan.py 沙箱路径兼容性 — 新增 `_real_home()` 自动检测真实用户目录，避开 Claude Code 临时 HOME
- **修复** SKILL.md 全部 `~/.sebastian/` 引用替换为绝对路径，避免沙箱解析错误
- **修复** install.sh 新增 `SEBASTIAN_HOME` 环境变量支持和真实目录自动检测
- **修复** SKILL.md/install.sh 中命令路径改为直接使用 `/c/Users/mou25/.sebastian/`（沙箱内外一致）

## 2.5.0 (2026-07-15)

- 新增「外部工具 (external_tool)」类型 — 独立项目脚本/工具集索引与路由
- 新增「Plugin (plugin)」类型 — Claude Code 插件索引与路由
- 外部工具/插件关键词触发：exact_keywords 直接 EXACT，indirect_keywords 反问确认
- scan.py 扩展：支持 plugin 类型记录、自动发现已安装插件缓存
- 新增模板 H（求职工作流 career-ops）、模板 I（网文创作工作流 webnovel-writer）
- 新增 `--scan-plugins` 命令查看已安装插件
- 新增 `external-tools/` 目录，统一存放外部工具和插件描述文件

## 2.4.0 (2026-07-03)

- 新增自建技能 rpg-loop 即时记录机制
- 执行规则中增加每步自建技能记录要求
- Lessons 章节升级为双轨记录（Lessons + rpg-loop）
- 集成指南中 rpg-loop 升级为双向集成

## 2.3.0 (2026-07-02)

- Phase 0 意图理解流水线（预过滤 / 6 维分解 / 澄清门）
- Scope Guard 内容-格式对齐检查
- 冲突消解规则（上游优先 / 垂直分离 / 早退出）
- 新增模板 G（内容→格式两步流水线）
- 输出格式增加"技术路径"和"依赖"标注

## 2.2.0 (2026-06-28)

- 三级匹配 + 阈值熔断机制
- Scope Guard 请求粒度 vs 产出粒度
- 工作流模板 A-G
- 反向机制与无匹配报告
- lessons 记录系统

## 2.1.0 (2026-06-22)

- 意图分解
- 澄清门

## 2.0.0 (2026-06-15)

- 完整重写：Phase 0 → Phase 9 流水线
- 加权匹配策略

## 1.0.0

- 初始版本
