# DevFlow Agent 角色定义

## 角色总览

| Agent | Runtime | 核心职责 | 关键工具 |
|-------|---------|---------|---------|
| Analyst | OpenClaw | 需求分析、用例设计、AC 定义、Issue 分类 | T1, T2, T9 |
| Architect | OpenClaw | 技术调研、PoC、架构设计、ADR | T3, T5 |
| Developer | Hermes | 代码生成、自审查 | T6, T7 |
| QA | QwenPaw | 独立审查、测试验证 | T8, T9 |
| DevOps | QwenPaw | CI/CD、部署、监控、回滚 | T7, T8 |
| Knowledge | OpenClaw | 知识索引、双通道反馈 | T11 |
| Attacker | OpenClaw | 对抗性用例与架构验证 | T1(read), T2(read) |

## 各 Agent 详细定义

### Analyst Agent (devflow-analyst)

```
软件工程角色: Requirements Engineer / Business Analyst

Phase 1:
  AN-1: 需求分析 — 提取实体、识别干系人、发现歧义
  AN-2: 用例设计 — usecase.create(L0) → 澄清 → usecase.upgrade(L1)
  AN-3: 需求规约 — requirement.create(FR/NFR) → requirement.create_ac
  AN-4: 追溯 — requirement.traceability_matrix

Phase 2:
  AN-5: 经济可行性 — token.estimate (与 Architect 协作)

Phase 5:
  AN-6: Issue 分类 (用例维度) — verify.classify_issue (USECASE_GAP/BUG_IN_USECASE)

运行时: OpenClaw
权限: github(read)
```

### Architect Agent (devflow-architect)

```
软件工程角色: Software Architect

Phase 2:
  AR-1: 技术调研 — 技术选型对比
  AR-2: PoC 实验 — poc.create → poc.run → poc.record_result
  AR-3: 风险评估 — 识别技术风险 + 缓解方案

Phase 3:
  AR-4: 架构设计 — arch.define_context_map → arch.define_aggregate
  AR-5: 接口契约 — arch.define_interface
  AR-6: 架构决策 — arch.create_adr
  AR-7: 扩展点声明 — arch.declare_extension_point (关联 Known Unknowns)

运行时: OpenClaw
权限: github(read)
```

### Developer Agent (devflow-developer)

```
软件工程角色: Software Developer

Phase 4:
  DV-1: 分支管理 — code.create_branch
  DV-2: 代码生成 — code.generate_patch (接口优先, 异常路径先行)
  DV-3: 编译验证 — compiler.check_syntax → compiler.static_analysis
  DV-4: 自审查 — code.self_review
  DV-5: PR 管理 — code.apply_patch → code.create_pr

Phase 5:
  DV-6: CODE_BUG 修复 — code.revert_patch → code.generate_patch

运行时: Hermes (终端沙箱, 自主编程)
安全边界:
  - 终端沙箱隔离
  - 禁止 push main
  - 禁止读取真实凭证
  - 仅 feature branch 写入
```

### QA Agent (devflow-qa)

```
软件工程角色: Test Engineer + QA Auditor

关键设计: QA Agent 独立于 Developer Agent (runtime 不同, 权限不同)

Phase 4:
  QA-1: 独立代码审查 — 对照 AC + SolutionSpec + 编码规范

Phase 5:
  QA-2: 测试生成 — test.generate (基于 CodeChange + AC)
  QA-3: 测试执行 — test.run → test.coverage
  QA-4: 测试质量 — test.mutation_test → test.regression_validity
  QA-5: AC 验证 — verify.ac (逐个)
  QA-6: Issue 分类 (代码维度) — verify.classify_issue (CODE_BUG/INTEGRATION_BUG)
  QA-7: 集成回归 — test.integration_run

运行时: QwenPaw (轻量, 确定性强)
权限: github(read + PR comment), cicd(read)
```

### DevOps Agent (devflow-ops)

```
软件工程角色: DevOps Engineer / SRE

Phase 2:
  OP-1: PoC 环境搭建

Phase 3:
  OP-2: 基础设施设计 (Redis, PostgreSQL, CI 管道配置)

Phase 4:
  OP-3: CI 管道配置 (compiler.build 触发)

Phase 5:
  OP-4: 构建 — compiler.build
  OP-5: 部署 — staging(自动) → human /approve-prod → production
  OP-6: 健康检查 — SLO 指标采集 + 判定 (Eval-G6)
  OP-7: 金丝雀渐进 — 1%→5%→...→100%
  OP-8: 自动回滚 — SLO 违约检测 + rollback (Eval-G6)
  OP-9: 生产镜像验证 — test.staging_smoke (Eval-G6)

运行时: QwenPaw (轻量, 操作确定性高)
权限: cicd(write), monitor(read)
```

### Knowledge Agent (devflow-librarian)

```
软件工程角色: Knowledge Manager / Process Engineer

跨阶段:
  KN-1: 知识检索 — kb.retrieve (正向 + 反向双通道)
  KN-2: 经验提取 — kb.index (Task 关闭时提取模式)
      + kb.extract_integration_test (Task 关闭时自动生成集成测试)
  KN-3: 种子生成 — seed.generate (Phase 0)
  KN-4: 知识卫生 — kb.mark_stale → kb.detect_contradiction
  KN-5: 反馈审计 — feedback.audit (每 Sprint Retro)
  KN-6: 因果分析 — 缺陷根因分类 (Pareto 分析) + 过程改进建议

运行时: OpenClaw
权限: github(write, docs repo only), qdrant(write)
```

### Attacker Agent (devflow-attacker)

```
软件工程角色: 对抗性测试者 (没有人类对应角色)

Phase 1 (用例冻结前):
  AT-1: 边界攻击 — attacker.probe_use_case (极端输入)
  AT-2: 顺序攻击 — attacker.probe_use_case (步骤重排)
  AT-3: 依赖攻击 — attacker.probe_use_case (外部异常)
  AT-4: 逻辑矛盾 — attacker.probe_use_case_pair (用例间一致性)
  AT-5: 角色混淆 — attacker.probe_use_case (权限越界)

Phase 3 (仅 XL complexity 任务):
  AT-6: 架构攻击 — attacker.probe_architecture (对架构假设的对抗性测试)

输出: ProbeReport → Human 聚焦审查 (只审 HIGH/MEDIUM 疑点)

运行时: OpenClaw (独立 Agent, 不与任何其他 Agent 共享上下文)
权限: 只读 (T1 read, T2 read)

注意: AT-6 仅在架构复杂度过高时触发(complexity.assess → XL)。
      标准流程中 Attacker 在 Phase 1 关闭后即完成工作,
      Phase 3 必须等 Attacker Phase 1 结果出来才能冻结架构。
```
```

---

## Human 角色

```
Phase 1: 澄清需求歧义 (requirement.request_clarification 的响应方)
         用例疑点裁决 (Level D — Accept/Dismiss/Defer)

Phase 2: Go/No-Go 决策 (declare_feasibility_verdict 的最终审批)

Phase 3: 架构评审 (XL complexity 任务)

Phase 5: 模糊 Issue 裁决 (NEED_HUMAN verdict)
         Sprint Review 验收

Matrix 房间命令:
  /approve-prod  — 批准生产部署
  /reject        — 驳回 (带评论)
  /rollback      — 立即回滚
  /clarify       — 主动提供信息
  /pause         — 暂停 Task
```

---

## Agent 间通信模型

Agent 不直接"对话"。它们通过以下方式交互:

1. **MinIO 文件**: Agent A 产出 → 工具写入 → Agent B 通过工具读取
2. **Matrix 房间**: Human 可见的状态更新和决策请求
3. **Knowledge 索引**: 异步的跨 Sprint 知识传递
4. **Event Store**: 时间线事件的产生和消费

每个 Agent 是独立的 Worker (AgentTeams CRD)，有自己的 runtime、权限和 MCP 配置。
