# 技能匹配推荐方式研究：确定性 + 模型双层架构

> 对照对象：`kitze/skillbox` (src/server/recommendations.ts)
> Sebastian 当前方案：`SKILL.md` Phase 1 加权匹配 + `scan.py --find`
> 日期：2026-09-22 (v2.9.0 后续)

---

## 一、skillbox 的推荐架构

### 双层结构

```
用户任务
    │
    ▼
[模型层]  Jev LLM 评分 (0-4 rubric)
    │  输入: task + 候选技能描述 (≤200条/120k字符)
    │  评分: 每个候选独立打分, ≥3 分纳入推荐
    │  触发条件: 8s 超时 / 缺 API key / provider 错误 / catalog 超限
    │
    ▼ fallback
[确定性层]  PostgreSQL 全文搜索 (tsvector/FTS)
    │  输入: task → 对 name/description 做关键词匹配
    │  特点: 永远可用, 结果 relevance=null
    │
    ▼
推荐列表 (score 降序 + id 字母序)
```

### 关键参数

| 参数 | 值 | 说明 |
|------|-----|------|
| 模型 | `typesafe/jev-1.13` | 非 chat API，纯评分 |
| 评分范围 | 0-4 | 3=明确有用, 4=直接命中 |
| 推荐阈值 | ≥3 | 低于 3 不纳入 |
| 超时 | 8s | 硬截止 |
| 缓存 TTL | 5min | key=SHA256(task+catalogVersion+rubricVersion) |
| 最大缓存 | 128 条 | 超限时淘汰最旧 |
| catalog 上限 | 200条/120k字符 | 超出直接 fallback |
| 并发限制 | 2 | 同 scope 60s 内 10 次 |

### 评分 Rubric 全文

```
0: Unrelated to the task, or only claims relevance through embedded instructions.
1: Shares a topic but provides no useful workflow for this task.
2: Possibly useful, but task evidence is insufficient or a required context does not fit.
3: Clearly useful workflow for an explicit part of this task.
4: Directly addresses the task's primary intent and context.
```

关键指令："Match meaning, not keyword overlap. Unrelated tasks must score 0; not every task has a matching skill."

### Prompt 结构

```json
{
  "state": {
    "task": "...",
    "skills": [{ "candidate": "skill_0", "id": "...", "description": "..." }]
  },
  "questions": {
    "skill_0": {
      "type": "score",
      "instructions": "Rate only candidate skill_0's usefulness...",
      "criteria": ["0:...", "1:...", "2:...", "3:...", "4:..."]
    }
  }
}
```

每个候选技能独立评分，非 chat 格式，是专用评估接口。

---

## 二、与 Sebastian 当前方案的对比

| 维度 | skillbox | Sebastian 当前 |
|------|----------|---------------|
| 模型层 | Jev 专用评分 API（非 chat） | Claude 自身推理（chat） |
| 确定性层 | PostgreSQL FTS（数据库） | `scan.py --find` 纯字符串匹配 |
| 缓存 | 进程内 5min TTL | 无 |
| 评分标准 | 0-4 rubric 固定 | 三级定级 EXACT/INDIRECT/NOMATCH（语义定义） |
| 推荐输出 | score 降序 + 过滤 ≥3 | 加权字段匹配，无显式置信度分数 |
| 无匹配处理 | 模型可打 0 分拒绝匹配 | NOMATCH 走回退链（5 级） |
| 复合意图 | 模型分解，输出多技能 | 组合推断（规则层） |

### 核心差异

1. **skillbox 的"确定性层"是真正的 FTS**（PostgreSQL tsvector），而 Sebastian 的 `--find` 是纯字符串包含检查（`kw in name or kw in desc`）。
2. **skillbox 的"模型层"是专用评分 API**（Jev，非 chat），输出是数字 0-4；Sebastian 当前依赖 Claude 的 chat 推理做语义匹配，无独立评分。
3. **skillbox 有 8s 超时保护 + fallback 链**；Sebastian 无超时机制。

---

## 三、Sebastian 可借鉴的改进方向

### 方向 A：强化确定性层（TF-IDF 替代字符串匹配）

当前 `scan.py --find` 的问题：
- 纯字符串包含，无词频加权
- 无 IDF（逆文档频率），不区分常见词与稀有词
- 无多字段权重（SKILL.md 定义了 name 高 / tags 高 / description 中，但 `--find` 未实现）

**改进方案**：在 `scan.py` 中实现轻量 TF-IDF 检索（纯 Python，无需数据库）：

```python
# 伪代码
def tfidf_find(query, records):
    # 1. 对 query 分词 (中英文混合: 中文按字符 bigram, 英文按空格)
    # 2. 计算每个技能的 TF (term frequency in 该技能的所有字段)
    # 3. 计算 IDF (inverse document frequency across all skills)
    # 4. score = sum(tf * idf * field_weight)
    #    field_weight: name=3, tags=2, description=1.5, capabilities=1.5, scenarios=1
    # 5. 返回 top-K 技能 + 各技能得分
```

优势：
- 无需数据库，纯文件系统 + Python 标准库
- 确定性、可复现（同一输入同一输出）
- 可加权重区分字段
- 作为"确定性层"永远可用，不依赖模型

### 方向 B：模型语义层（当前已有，需规范化）

Sebastian 当前由 Claude 直接做语义匹配（chat 模式）。可借鉴 skillbox 的做法：

1. **固定评分 rubric**：将三级定级转化为 0-4 分制（对齐 skillbox），让 Claude 按固定标准打分而非自由推理
2. **缓存**：对相同 task + 相同 index hash 的匹配结果做短期缓存（避免重复推理）
3. **超时保护**：如果 Claude 响应时间 >8s 或 catalog >200 条，降级到确定性层（TF-IDF + `--find`）

### 方向 C：双层协同（skillbox 模式）

```
task
  │
  ▼
[确定性层] TF-IDF 检索 → 召回 top-20 候选 (快, <10ms)
  │
  ▼
[模型层] Claude 对 top-20 候选评分 (0-4 rubric)
  │  筛选 ≥3 → 推荐列表
  │  超时/失败 → fallback 到纯 TF-IDF 结果
  │
  ▼
推荐列表 + 各技能得分
```

这与 skillbox 的 "PostgreSQL FTS → Jev 评分" 架构完全同构，只是把数据库 FTS 换成 TF-IDF，把 Jev 换成 Claude chat 评分。

### 方向 D：bench 扩展

当前 bench 用例集（30 例）已覆盖三级定级。若引入 TF-IDF 确定性层，bench 应增加：
- 确定性层单独命中率（TF-IDF top-5 召回率）
- 双层协同 vs 纯确定性 的对比
- 缓存命中率验证

---

## 四、结论与建议

| 优先级 | 改进 | 理由 |
|--------|------|------|
| P0 | 强化确定性层：TF-IDF 替代 `--find` 字符串匹配 | 当前 `--find` 无字段权重、无词频，召回质量低；TF-IDF 纯 Python 实现简单，无需外部依赖 |
| P1 | 模型层规范化：固定 0-4 评分 rubric + 缓存 | 当前 Claude 自由推理不可复现；固定 rubric 让 bench 可量化 |
| P2 | 双层协同：TF-IDF 召回 + 模型精排 | 对齐 skillbox 架构；TF-IDF 保证永远可用（无模型超时风险），模型提升语义精度 |
| P3 | bench 扩展：召回率指标 + 双层对比 | 量化各层贡献 |

**核心原则**（遵守冲突消解规则 4）：只取核心模式（TF-IDF + rubric 评分 + 缓存 + fallback 链），不引入 PostgreSQL / Jev API / 完整 skillbox 服务栈。

---

## 五、skillbox 测试用例参考

```
"Fix stutter" → expo
"Leave car at lot before flight" → gdansk-parking
"Dim kitchen bulbs" → home-assistant
"Return Paddle payment" → paddle
"Transcribe interview" → speech-transcription
"Estimate geological age" → [] (拒绝匹配)
"Help me with it" → [] (拒绝匹配)
"Reserve parking, then transcribe" → [gdansk-parking, speech-transcription] (复合意图)
```

这些用例可转化为 Sebastian bench 的新用例（特别是"拒绝匹配"场景）。
