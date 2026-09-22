# Changelog

## 2.9.0 (2026-09-22)

借鉴 skillbox 三项轻量改进(版本化 / 回退显式化 / 使用统计健康度)

> 来源: 对比 `kitze/skillbox` 后, 取其"不可变修订 + fallbackReason + 使用量上报"核心模式,
> 以文件系统 + 现有脚本实现, 不引入数据库/服务(遵守冲突消解规则 4: 只取核心模式不复制完整公式)。

- **1. 轻量版本化(修订快照)**
  - `scan.py --scan` 时为内容 hash 变更的 SKILL.md 自动快照到 `~/.sebastian/skill-revisions/<name>/<ts>_<hash8>.md` (每技能上限 20 份, 超出裁剪最旧)
  - 新增 `--revisions` / `--history <skill>` / `--revert <skill> <rev> [--yes]` 命令; revert 先快照当前态保证可逆
  - index.json 每条记录新增 `content_hash` / `last_revision` / `revision_count`; `--list` 表格新增 `Rev` 列
  - Windows GBK 输出修复: scan.py 顶部 `sys.stdout/stderr.reconfigure(encoding="utf-8")`
- **3. 回退显式化(fallbackReason)**
  - lessons 记录新增可选 `fallback` 字段 `{chain, reason}`, 显式标注"哪步走了回退链、为什么"; 向后兼容 `fallback_reason` / `fallback_chain` 旧字段名
  - `compact_lessons.py --status` 新增回退率统计 + Top-3 回退原因; 归档摘要新增 `fallback_top` 聚合; `--merge` 增量合并 fallback_top
- **5. 使用统计与健康度面板**
  - `scan.py --health`: 从 lessons.json + lessons-archive.json 聚合每技能 ok/modified/failed/fallback 次数、最近使用时间、失败 rung 分布
  - 面板含: 总览 / Most Used Top10 / High Failure Rate(≥30%) / High Modification Rate(≥40%) / Never Used 清单
  - `_load_lessons_stats` 兼容 flat 与归档摘要两种来源, 字段缺失向后兼容(视为 0)
- **SKILL.md**: 版本 2.8.0 → 2.9.0; 新增命令 9 (`/sebastian revisions`) 与 10 (`/sebastian health`); 概述第 6/7 条; Lessons 记录格式补 fallback 字段说明; 命令 5 加指向 health/revisions 的指针

**后续(未做):** 技能匹配推荐方式的原理研究(确定性 TF-IDF + 模型语义微调双层架构) — 明日专项。

## 2.8.0 (2026-09-21)

jev-judge 接入(判定层第三维度) + bench 基线纠偏

- **判定层第三维度**: coreType 映射表新增 `jev-judge | judgment | none`, 并注明判定层既不产出内容也不包装格式, 不参与 coreType 竞争, 仅在"内容已存在、需要把关"时作为附加步骤接入
- **新增模板 K (内容质检/把关流水线)**: 内容定稿 → jev-judge 按 preset 下判断(quality/compliance/tone/channel/自定义) → 条件人工复核; 约定"判为不合规则改写回步骤 1"(改写归 bifeng, jev-judge 不生成文本)
- jev-judge frontmatter 补 `paired_with: [bifeng, ecommerce-visual-copywriting]` 与 `maintainer`, 版本 1.0 → 1.1 (索引 8/8 字段)
- bench 用例 +2 共 30 例: id 29 (合规把关 → jev-judge, 模板 K)、id 30 (反例: 润色改写走 bifeng 而非 jev-judge)
- **bench 首轮消除答案可见性后的真实测量**: hit@1 26/30 (86.7%), hit@3 26/30, 模板 6/7
  - 历史 100% 基线(20260908T031129Z)早于 exam 机制(同日 13:00 才修复自证偏差) → 属污染数据; **86.7% 才是可信基线**, 本次"回归告警"为假警报
  - 4 条 miss: #13 简历润色误配 career-ops(应 bifeng)、#24 长文排版误配 bifeng(应 kami)、#4 landing page 误配 design-taste-frontend(应 guizang-ppt-skill)、#28 直接命中 find-skills(用例期望 NOMATCH, 疑似用例设计问题)
  - 模板 miss 1/7 恰为 #17 期望模板 J —— 而 SKILL.md 无模板 J(见遗留项), 即该缺陷已实际造成评分损失
- **遗留项(本次未修, 需人工决策)**: ①模板 J(照片→插画)被 lessons 2026-08-21、CHANGELOG 2.6.0、bench case 17 三处引用, 但 SKILL.md 从未落地; ②bench 用例集与打分规则属人工决策点, #4/#28 疑似用例设计问题需人工复核后再改

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
