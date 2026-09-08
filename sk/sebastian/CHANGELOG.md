# Changelog

## 2.7.1 (2026-09-08)

能力校验修复(隔离测试 + 突变测试驱动)

- **修复 bench 自证偏差缺陷**: 新增 `bench.py exam` 子命令, 生成剥离标准答案的 `bench.exam.json`(只留 id+prompt)
  - 此前模型预测时直接读含 expected_* 的 bench.json = "对答案", 100% 命中不能反映真实路由能力
  - SKILL.md bench 流程改为: validate → **exam** → 只读 exam 版批量预测 → score
- 隔离环境验证(SEBASTIAN_HOME 沙箱): compact cut/merge 全路径 12 项测试通过
  (超限识别/保留 50/分桶 4 技能/二次 merge 增量扩展/stats 累加/低水位拒绝/全错预测 exit=1 告警)
- 突变测试确认: 删除索引技能后 bench 能检出 miss(回归检测有效, 修复答案可见性后完整成立)

## 2.7.0 (2026-09-08)

P1+P2 进化(借鉴 ACE: 失败定级 / novelty 去重 / 增量契约 / 保护锚点)

- **新增「升级治理」章节** — 升级不再由使用计数单独驱动:
  - 失败→修复定级表: skill(技能内容) / template(模板) / harness(自身规则) 三层, 在最低可表达层修复
  - Novelty 门: 新增 `upgrade-attempts.json` 升级尝试档案(append-only), 推荐升级前查重, 被拒条目带证据永不删除
  - 升级产出契约: itemized delta(增量清单 + 逐条批准), 禁止整体重写技能全文; Empirical acceptance 凭实测证据验收
- **Lessons 记录扩展**: 可选 `rung` 与 `signature`(失败三元签名: 现象/责任/机制) 字段; 归档摘要 failures 条目同步带 rung
- `/sebastian review` 重写: 先查 upgrade-attempts 去重 → 按 rung 推荐(替代纯 XP 计数)
- **保护锚点与人工决策点**: 冲突消解规则 / Scope Guard / 阈值熔断 / 授权条款 / 回退链等列为不可压缩、不可被进化流程改写; 扫描器、bench 规则、压缩阈值改动须人工
- **步骤成功判定约定** (Success Predicate): 按技术路径定义可验收产出断言, 长流程关键步骤在方案中显式写明
- **修复技能名错位**: 模板 A / 集成指南 / 示例中 diagnosing-bugs→systematic-debugging、tdd→test-driven-development; 模板 B/D 引用未入索引技能处加回退注(不中断流程)
- 与 darwin-skill 集成契约更新: 升级产物须为 itemized delta, 被拒方案记入档案

## 2.6.0 (2026-09-07)

P0 进化(借鉴 ACE: 路由可评测 + 记录压缩治理)

- **新增 `/sebastian bench` 路由评测基准** — 固定用例集量化匹配质量:
  - 新增 `scripts/bench.py`: 确定性校验(validate, 先于模型判断) + 批量打分(score) + 回归对比(histories)
  - 用例格式: layer/scenario/prompt/expected_skills/expected_template/expected_level(EXACT|NOMATCH)
  - 模型单次批量推理输出预测 JSON, 脚本算 hit@1/hit@3/分层报告/模板命中率
  - 回归告警: 相比上次基线下降 ≥3pt 或 10%; 绝对阈值 <80%
  - 预测与历史存档于 `~/.sebastian/bench-runs/` 与 `bench-history.json`
  - 新增种子数据集 `sk/sebastian/bench-cases.json` (28 例, 覆盖模板 A/E/G/H/I/J、关键词触发、NOMATCH、技能名边界)
- **新增 `/sebastian compact lessons` 锚定摘要归档** — 解决 lessons.json 无界增长:
  - 新增 `scripts/compact_lessons.py`: status(阈值 40 警告 / 50 上限) / cut(超限记录按主技能分桶) / merge(增量并入归档)
  - 归档文件 `lessons-archive.json`: 固定章节摘要(decisions/failures/stats), 技能名与路径逐字保留
  - 同 skill+period 摘要只做增量扩展, 绝不整体重写(锚定迭代原则)
- `/sebastian review` 更新: 先跑 `--status`, 统计叠加归档摘要
- SKILL.md 文档: 新增命令 7/8, lessons 章节加入成长治理说明

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
