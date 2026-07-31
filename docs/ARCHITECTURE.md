# DevFlow 架构文档

## 1. 过程架构: 五阶段门禁模型

### 为什么结构化门禁而非 Scrum

Scrum 的迭代模型适合**需求不确定**的人类团队——开发者有判断力, 可以在模糊中迭代前进。
AI Agent 在模糊上下文中会产生幻觉: 给它模糊的 Story, 它会补全而不是追问。

五阶段门禁通过**强制阶段性收敛**来减少 Agent 的出错空间。每个阶段有唯一的焦点和明确的出口标准。

### Phase 1: 需求工程

**输入**: 用户自然语言需求
**输出**: 用例文档(L0→L1)、需求规约(FR/NFR)、验收标准(Lean AC)、Known Unknowns

**用例渐进式披露**:

| Level | 时机 | 内容 |
|-------|------|------|
| L0 概要 | Phase 1 初始 | 用例名 + Actor + Goal + 主成功场景骨架 |
| L1 标准 | Human 澄清 + Knowledge 反馈后 | + 可预见的 Alternative Flow + 前置/后置条件 |
| L2 详细 | Phase 4/5 反馈 | + 新发现的边界场景 (USECASE_GAP 补充) |

**Lean AC 格式**: `{ given, when, then }` — AC 即测试定义, 由工具自动生成测试代码。

**四级质量验证**: 见 `QUALITY.md`

### Phase 2: 可行性研究

**输入**: 需求规约 + 用例文档
**输出**: 技术调研、PoC 实验结果、Token 成本模型、Go/No-Go 决策

在写架构设计或代码之前回答: 这个需求在技术上和经济上是否可行？

- 技术可行性: 技术选型 + PoC 微型实验 + 风险评估
- 经济可行性: 完整的 Token 消耗预估 (per Phase, per Agent)
- 决策: Go / No-Go / Conditional-Go (列出前置条件, 满足后自动 Go)

### Phase 3: 架构设计 (自顶向下)

**输入**: 需求规约 + 可行性报告
**输出**: 架构文档 (5 层细化)、ADR、接口契约、扩展点声明

```
Level 0: 系统上下文 (外部系统 + 系统边界)
Level 1: 容器/服务 (服务划分 + 依赖)
Level 2: 组件 (每个服务内部的组件分解)
Level 3: 接口契约 (每个接口的 I/O + 错误)
Level 4: 数据模型 (实体 + 关系)
```

每个非平凡决策必须写 ADR (Architecture Decision Record)。

### Phase 4: 实现

**输入**: 架构文档 + 用例文档
**输出**: 代码 (patch) + PR + 自审报告

关键原则: **按接口契约实现, 按用例验证**。异常路径先行。

三道防线: Developer 自审 → CI 自动化 (编译+SAST+CVE) → QA 独立审查

### Phase 5: 验证与 Issue 分类

**输入**: 代码 + 用例文档
**输出**: 测试报告、AC 验证结果、Issue 分类、最终裁决

Issue 分类决策树:

```
验证失败 → 场景在用例中有描述吗?
  否 → USECASE_GAP → 回到 Phase 1
  是 → 代码符合用例吗?
    是 → BUG_IN_USECASE → 回到 Phase 1
    否 → CODE_BUG → 回到 Phase 4
  环境问题? → ENV_ISSUE
  系统级冲突? → INTEGRATION_BUG
```

---

## 2. 核心原则: 一切皆工具

Agent 不产生产物。Agent 调用工具, 工具产生产物。

```
Agent (LLM)            工具 (确定性代码)          存储
──────────            ────────────────          ──────
推理 "该做什么"  →    Schema 校验             → MinIO
组装参数        →    幂等检查                → Qdrant
决定调用哪把工具 →    版本管理                → Git
                    证据自动生成             → Evidence Store
                    关联 ID 自动注入          → Loki
```

完整工具清单见 `TOOLS.md`。

---

## 3. Agent 角色

| Agent | Phase 1 | Phase 2 | Phase 3 | Phase 4 | Phase 5 |
|-------|---------|---------|---------|---------|---------|
| Analyst | 需求分析、用例设计、AC 定义 | 经济可行性 | — | — | Issue 分类(用例缺口) |
| Architect | — | 技术调研、PoC | 架构设计、ADR | — | — |
| Developer | — | — | — | 代码生成、自审查 | 修复 CODE_BUG |
| QA | — | — | — | 独立代码审查 | AC 验证、测试质量 |
| DevOps | — | PoC 环境 | 基础设施设计 | CI 管道 | 部署、健康检查(Eval-G6) |
| Knowledge | 双向反馈 | 技术调研历史 | 架构模式 | 代码模式、已知错误 | 经验提取入库 |
| Attacker | 对抗性验证 | — | — | — | — |
| Human | 澄清歧义 | Go/No-Go | 架构评审 | — | 疑点裁决 |

详细 Agent 定义见 `AGENTS.md`。

---

## 4. 质量验证全景

| 验证维度 | 机制 | 文档 |
|---------|------|------|
| 产物结构 | 工具层 schema 校验 | TOOLS.md |
| 产物质量 | Eval-G1~G6 程序化评估 | QUALITY.md |
| 过程完整性 | 事件时间线验证 | QUALITY.md |
| 语义正确性 | 四级验证 (Attacker + Human) | QUALITY.md |
| 反馈有效性 | 反馈回路健康度量 | QUALITY.md |
| 系统一致性 | 跨任务冲突 + 集成回归 | QUALITY.md |

---

## 5. 跨切面模式

| 模式 | 用途 |
|------|------|
| Result 类型 | 统一错误处理 (RETRYABLE/PERMANENT/NEED_HUMAN) |
| 幂等性 | 所有写入操作可安全重试 |
| 语义缓存 | 相似需求不重复分析 |
| 关联 ID | 全链路追溯 (task→phase→agent→llm_call) |
| 断路器 | 外部服务容错 |
| Saga | 跨 Phase 补偿事务 |
| 结构化日志 | 统一 JSON 格式, Loki 存储 |
| 读写分离 | Knowledge 检索和索引使用不同 Qdrant 节点 |
| 依赖注入 | Skill 可 mock, 可独立测试 |
| 功能开关 | 新 Agent/Skill/Gate 渐进上线, 可控降级 |
| 信任累积 | Human 审查量随 Agent 表现自动递减 |

---

## 6. 已知风险与修复

| 风险 | 修复机制 |
|------|---------|
| Agent 能力未经验证 | Phase 0 Capability Baseline + 模型漂移检测 |
| 阶段门禁僵化 | complexity.assess → S/M/L/XL 四级动态裁剪 |
| Human 决策瓶颈 | trust 累积 + auto_approve + 超时自动放行 |
| 反馈冷启动 | 三级种子知识库(通用+模板+合成) + cold_start 模式 |
| 无成本实证 | T4 budget_enforce + anomaly_detect |
