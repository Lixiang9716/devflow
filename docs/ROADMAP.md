# DevFlow 实现路线图

## 总体策略

单人开发，16 天到初赛 (PPT)，34 天到复赛 (代码+Demo)。
采用**增量式交付**：每个增量产出可独立演示的功能。

---

## Phase 0: 基础设施 (8/1-8/2)

**目标**: 搭好台子，验证核心假设

```
Day 1:
  [ ] AgentTeams 部署 (Docker 一行命令)
  [ ] LLM API 配置 (Higress 网关)
  [ ] GitHub PAT 配置
  [ ] 创建 demo-app 仓库 (FastAPI + pytest + CI)

Day 2:
  [ ] Capability Baseline 脚本
      - 5 个带标注的 Issue → 手动测试 Analyst Agent
      - 3 个已知根因 → 手动测试 Architect Agent
      - 记录 baseline 数据
  [ ] 决策: 基于 baseline 结果调整 Agent prompt/工具配置
  [ ] MinIO + Qdrant + Loki + Tempo + Grafana 部署
```

---

## Increment 1: Phase 1 — 需求工程 (8/3-8/5)

**目标**: 用户提需求 → 产出 L1 用例 + Lean AC

```
工具实现 (P0):
  [ ] T1: usecase.create, usecase.upgrade, usecase.validate
  [ ] T2: requirement.create, requirement.create_ac, 
         requirement.traceability_matrix, requirement.request_clarification
  [ ] T10: evidence.write (Phase 1 部分)

Agent Skill:
  [ ] Analyst Agent Phase 1 SKILL.md
  [ ] AgentTeams CRD: devflow-analyst

验证:
  [ ] 5 个测试 Issue → 每个产出完整的 L1 用例 + AC
  [ ] G1 Eval-Gate 自动化
  [ ] 时间线模板 phase1_standard 定义

Demo (Increment 1):
  输入: "电商需要多币种订单功能"
  输出: UC-01(L1) + 6 个 FR + 8 个 Lean AC
```

---

## Increment 2: Phase 2 — 可行性研究 (8/6-8/7)

**目标**: 基于用例做技术验证和成本预估

```
工具实现 (P1):
  [ ] T3: poc.create, poc.run, poc.record_result
  [ ] T4: token.estimate, token.record_call
  [ ] T10: evidence.write (Phase 2 集成)

Agent Skill:
  [ ] Architect Agent Phase 2 SKILL.md
  [ ] AgentTeams CRD: devflow-architect

验证:
  [ ] 对 Phase 1 的 UC-01 跑 PoC 实验
  [ ] 输出 Token 成本模型
  [ ] G2 Eval-Gate 自动化
```

---

## Increment 3: Phase 3 — 架构设计 (8/8-8/9)

**目标**: 自顶向下架构设计 + ADR

```
工具实现 (P1):
  [ ] T5: arch.define_context_map, arch.define_interface,
         arch.create_adr, arch.generate_class_diagram
  [ ] T10: evidence.write (Phase 3 集成)

Agent Skill:
  [ ] Architect Agent Phase 3 SKILL.md

验证:
  [ ] 基于 UC-01 产出: Context Map + 聚合定义 + 接口契约 + ADR
  [ ] G3 Eval-Gate 自动化
```

---

## Increment 4: Phase 4 — 实现 (8/10-8/11)

**目标**: 从架构生成代码 patch

```
工具实现 (P0):
  [ ] T6: code.create_branch, code.generate_patch, 
         code.apply_patch, code.self_review, code.create_pr
  [ ] T7: compiler.check_syntax, compiler.build,
         compiler.static_analysis
  [ ] T10: evidence.write (Phase 4 集成)

Agent Skill:
  [ ] Developer Agent Phase 4 SKILL.md
  [ ] AgentTeams CRD: devflow-developer

验证:
  [ ] 基于 UC-01 + 架构 → 生成代码 patch
  [ ] 自动编译 + SAST + 自审查
  [ ] G4 Eval-Gate 自动化
  [ ] 时间线模板 phase4_standard 定义
```

---

## Increment 5: Phase 5 — 验证 (8/12-8/14)

**目标**: 测试 + AC 验证 + Issue 分类

```
工具实现 (P1):
  [ ] T8: test.run, test.coverage, test.mutation_test,
         test.regression_validity
  [ ] T9: verify.ac, verify.classify_issue, verify.verdict
  [ ] T10: evidence.write (Phase 5 集成)

Agent Skill:
  [ ] QA Agent Phase 5 SKILL.md
  [ ] DevOps Agent SKILL.md
  [ ] AgentTeams CRD: devflow-qa, devflow-ops

验证:
  [ ] 测试执行 + 覆盖率 + 变异测试
  [ ] Issue 分类 (模拟 USECASE_GAP 和 CODE_BUG)
  [ ] G5/G6 Eval-Gate 自动化
  [ ] 端到端流程: Issue → PASS (至少 1 个 golden path)
```

---

## Increment 6: 高级质量机制 (8/15-8/18)

**目标**: 四级验证 + 时间线 + 系统回归

```
工具实现 (P2):
  [ ] T1: usecase.add_alternative, usecase.declare_known_unknown
  [ ] T11: kb.index, kb.retrieve, seed.generate
  [ ] T12: timeline.verify, complexity.assess, trust.calculate,
         conflict.detect
  [ ] Attacker Agent SKILL.md + CRD
  [ ] Knowledge Agent SKILL.md + CRD

验证:
  [ ] 四级验证完整链路 (Level A→B→C→D)
  [ ] 时间线验证: 检测跳过/乱序/异常延迟
  [ ] 系统级回归: 跨任务冲突 + 集成测试套件
  [ ] 反馈审计: feedback.audit 输出
  [ ] 信任累积: trust 上升/下降/重置
```

---

## 复赛准备 (8/19-9/3)

```
Week 1 (8/19-8/25):
  [ ] 端到端 Demo 打磨 (连跑 3 次不炸)
  [ ] 录制 18 分钟 Demo 视频
  [ ] MCP Server 单测补全
  [ ] 双语 README + 架构图

Week 2 (8/26-9/3):
  [ ] 边界用例覆盖 (重试、flaky、回滚、timeout)
  [ ] 尝试向小型开源仓库提交修复 (开源贡献分)
  [ ] PPT 定稿 (基于 PoC 数据, 非理论设计)
  [ ] Grafana 仪表盘打磨
  [ ] 提交复赛
```

---

## 决赛准备 (9/4-9/22)

```
[ ] 扩展到双项目并行 (展示编排规模化)
[ ] Token 成本优化对比 (before vs after, 展示可观测收益)
[ ] 安全加固 (凭证、注入防御)
[ ] 答辩逐字稿 + QA 预演
```

---

## 关键风险 & 降级策略

| 风险 | 降级策略 |
|------|---------|
| LLM 能力不足 (baseline < 阈值) | 缩小使用场景到"简单缺陷修复"；增加 Human 审查频率 |
| 时间不够 | P2 工具推迟到复赛；初赛只演示 golden path |
| AgentTeams 兼容性问题 | 回退到直接 LLM + MCP 调用 (不做 AgentTeams 集成, 在方案中说明) |
| Demo 翻车 | 预录关键步骤 + 现场只走已验证剧本 |
