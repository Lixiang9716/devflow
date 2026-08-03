# DevFlow — 结构化软件工程驱动的多 Agent 协同系统

## 作品简介（500 字）

**项目名称**: DevFlow：结构化软件工程驱动的多 Agent 协同系统

**问题与场景**: 当前 AI 编码助手（Copilot、Cursor 等）聚焦于单次代码补全，缺乏端到端的软件工程流程覆盖。Agent 在模糊上下文中容易产生幻觉——跳过需求分析直接写代码、遗漏异常路径、无法追溯缺陷根因。企业级软件研发需要从需求到验证的完整闭环，而非孤立的代码生成。

**核心解决方案**: DevFlow 将结构化软件工程方法论映射为五阶段门禁模型（需求工程→可行性研究→架构设计→实现→验证），由 7 个专职 Agent 协同执行。核心理念是"一切皆工具"——Agent 只负责推理和决策，23 个确定性工具负责执行、校验、证据沉淀和关联追溯。当验证阶段发现缺陷时，系统通过决策树自动分类为 USECASE_GAP（用例缺口→回到需求工程）、CODE_BUG（代码缺陷→回到实现），形成自主闭环。

**创新点与差异化优势**: (1) 阶段门禁替代 Scrum 迭代——每个阶段有唯一焦点和明确的出口标准，减少 Agent 幻觉空间；(2) 四级用例质量验证——通过工具自动校验(Level A)、知识模式对比(Level B)、对抗性 Agent 攻击(Level C)三级过滤，将人类审查量压缩至 15%；(3) 事件时间线验证——不仅验证产物正确性，还验证过程合规性，检测 Agent 是否跳过关键步骤；(4) 双通道知识反馈——正向索引成功模式、反向索引已知错误，系统越用越准；(5) 不可变证据链——每个工具调用自动写入 SHA256 哈希时间戳的审计记录，全链路可追溯。

**开放/复用价值**: 五阶段门禁模型领域无关，可应用于电商、金融、SaaS、基础设施等任何软件工程场景。12 组工具通过 MCP 协议标准化，可被任何 Agent 框架调用。所有 Agent 角色定义、Skill 规格、Eval-Gate 配置均开源（MIT 协议）。

**当前进展**: 已完成全部 12 组工具实现（8732 行代码）、7 个 Agent 的 AgentTeams CRD 部署配置、4 个核心 Skill 定义、6 个程序化评估门禁（G1-G6），以及 112 个测试（含真实 DeepSeek API 端到端测试）。AgentTeams 集成已部署，MCP Server 可工作。

---

## 方案 PPT 结构（12 页）

### 页 1: 封面
- DevFlow: 结构化软件工程驱动的多 Agent 协同
- Agent Infra 赛道 · 软件研发全流程协同
- 个人参赛

### 页 2: 核心思想 — 为什么不用 Scrum？
- Agent ≠ 人: 人在模糊中迭代，Agent 在模糊中幻觉
- 结构化门禁: 每个阶段唯一焦点，强制阶段性收敛
- 对比表: Scrum vs 结构化门禁

### 页 3: 五阶段全景
- Phase 1→5 流程图 + Issue 反馈回路
- 每个阶段的输入/输出/门禁
- USECASE_GAP → Phase 1, CODE_BUG → Phase 4

### 页 4: 一切皆工具 — Agent 不产生产物
- LLM 职责 vs 工具职责 对比表
- 12 组工具清单 (T1-T12)
- 工具调用链路示例

### 页 5: Phase 1 需求工程 — 用例驱动的渐进式披露
- L0→L1→L2 三级用例演进
- Lean AC 格式: {given, when, then}
- 四级质量验证 (Level A→B→C→D)

### 页 6: Phase 2-3 可行性与架构
- PoC 代码化管理 (可执行、可复现、可比较)
- Token 成本模型 (精确估算 vs 运行时追踪)
- 自顶向下架构设计 5 层
- ADR 架构决策记录

### 页 7: Phase 4-5 实现与验证
- 三道防线: Developer自审 → CI自动化 → QA独立审查
- 异常路径先行原则
- 测试质量门禁: 变异测试 ≥0.5, AC覆盖 100%, 回归有效性
- Eval-G1~G6 程序化评估

### 页 8: Issue 分类决策树 ⭐核心亮点
- 四种分类: USECASE_GAP / CODE_BUG / BUG_IN_USECASE / ENV_ISSUE
- 决策树可视化
- 具体案例: 精度丢失 → CODE_BUG, 极端币种 → USECASE_GAP
- 反馈回路: 验证失败 → 分类 → 回到正确阶段

### 页 9: 7 Agent 角色矩阵
- Analyst / Architect / Developer / QA / DevOps / Knowledge / Attacker
- 每个 Agent 在 5 个阶段的职责分布
- Agent 间通信: MinIO 文件 + Matrix 房间 + Knowledge 索引
- Attacker 独立设计: 5 种攻击策略，只读权限

### 页 10: 质量验证全景
- 六层渗透防御: 工具层→Eval-Gate→四级验证→时间线→反馈→系统回归
- 事件时间线: 产物正确≠过程正确
- 反馈有效性: 5 个量化指标 (KAR, FER, LV, FFPR, 新鲜度)
- 信任累积: Human审查量自动递减

### 页 11: 工程落地与可观测
- AgentTeams CRD 部署架构
- MCP Server 工具标准化
- 可观测: Trace + Log + Metrics
- 安全: 断路器 + Saga 补偿 + 权限边界

### 页 12: 数据与展望
- 真实 LLM 测试结果: 112 测试通过，完整 E2E 管道
- Token 成本: ~$0.03/task vs 人类 $60-240
- 演进路线: 种子知识→真实经验→自主学习
- 开源计划

---

## 技术实现

### 工具清单（23 个 MCP 工具）

| 组 | 工具 | 用途 |
|----|------|------|
| T1 | usecase_create, usecase_upgrade, usecase_validate, usecase_add_alternative, usecase_declare_known_unknown | 用例全生命周期 |
| T2 | requirement_create, requirement_create_ac, requirement_traceability_matrix, requirement_request_clarification | 需求规约 + Lean AC |
| T3 | poc_create, poc_run, poc_record_result | PoC 可执行实验 |
| T4 | token_record_call, token_estimate, token_report, token_budget_check | 精确 Token 追踪 |
| T5 | arch_define_context_map, arch_define_interface, arch_create_adr, arch_declare_extension_point | 架构即代码 |
| T6 | code_create_branch, code_generate_patch, code_apply_patch, code_revert_patch, code_self_review, code_create_pr | Patch 代码管理 |
| T7 | compiler_check_syntax, compiler_type_check, compiler_build, compiler_static_analysis, compiler_dependency_scan | 确定性编译 |
| T8 | test_run, test_coverage, test_mutation_test, test_regression_validity, test_ac_coverage, test_integration_run, test_staging_smoke | 测试质量评估 |
| T9 | verify_ac, verify_classify_issue, verify_classify_integration, verify_verdict | Issue 分类决策树 |
| T11 | kb_index, kb_retrieve, kb_mark_stale, kb_detect_contradiction, kb_health_report, kb_seed_generate | 双通道知识 |
| T12 | timeline_verify, complexity_assess, trust_calculate, conflict_detect, feedback_audit, system_regression_test | 横切关注点 |

### Agent 角色清单

| Agent | Runtime | 模型 | Phase | 核心职责 |
|-------|---------|------|-------|---------|
| Analyst | OpenClaw | deepseek-v4-pro | 1, 5 | 需求分析、用例设计、AC定义、Issue分类(用例维度) |
| Architect | OpenClaw | deepseek-v4-pro | 2, 3 | 技术调研、PoC、自顶向下架构设计、ADR |
| Developer | Hermes | deepseek-v4-pro | 4, 5 | 代码生成(Patch)、自审查、CODE_BUG修复 |
| QA | CoPaw | deepseek-v4-flash | 4, 5 | 独立审查、测试验证、Issue分类(代码维度) |
| DevOps | CoPaw | deepseek-v4-flash | 2-5 | CI/CD、部署、健康检查、自动回滚 |
| Knowledge | OpenClaw | deepseek-v4-pro | 1-5 | 双通道知识索引、上下文检索、反馈审计 |
| Attacker | OpenClaw | deepseek-v4-pro | 1, 3 | 对抗性验证(5种攻击策略)、架构攻击(XL) |

### Skill 清单

| Skill | Agent | 用途 | I/O |
|-------|-------|------|-----|
| analyst-phase1 | Analyst | 需求分析与规格化 | 自然语言需求 → UC/FR/AC |
| architect-phase3 | Architect | 自顶向下架构设计 | 需求+可行性 → 架构+ADR+接口契约 |
| developer-phase4 | Developer | 接口优先代码生成 | 架构+UC → Patch+PR |
| qa-phase5 | QA | 验证与Issue分类 | 代码+AC → 测试报告+Issue分类+判决 |
| lean-ac-format | Analyst | Lean AC格式规则 | FR → {given,when,then} |
| issue-classification-tree | QA | 缺陷分类决策树 | FAIL AC → USECASE_GAP/CODE_BUG/... |
| adr-template | Architect | 架构决策记录模板 | 决策场景 → ADR-XXX |
| five-strategies | Attacker | 5种对抗性攻击策略 | UC → ProbeReport |

---

## 快速开始

### 1. 安装 DevFlow

```bash
git clone https://github.com/devflow/devflow
cd devflow
pip install -e ".[dev]"
```

### 2. 配置 LLM

```bash
export DEEPSEEK_API_KEY=sk-...
```

### 3. 安装 AgentTeams (一行命令)

```bash
bash <(curl -sSL https://higress.ai/hiclaw/install.sh)
```

### 4. 部署 DevFlow Agent 团队

```bash
# Deploy all 7 agents + team configuration
bash deploy/agentteams/deploy.sh
```

### 5. 运行测试

```bash
python -m pytest tests/ -v  # 112 tests
```

### 6. 提交任务

打开 Element Web UI (http://127.0.0.1:18088)，向 devflow-analyst 发送：
```
电商平台需要支持多币种订单功能，下单时按实时汇率换算为人民币结算
```

观察 5 阶段 Pipeline 自动执行。

---

## Demo 脚本

### 场景: 电商多币种订单功能

1. **Phase 1 (Analyst)**: 创建 UC-01(L0→L1) + 4 FR + 8 Lean AC
2. **Phase 2 (Architect)**: PoC 精度实验 → Token 成本预估 $0.03
3. **Phase 3 (Architect)**: Context Map + 2 接口契约 + 2 ADR
4. **Phase 4 (Developer)**: Feature Branch → Patch → 编译 → Self-Review → PR
5. **Phase 5 (QA)**: 测试执行 → 变异测试 → AC 验证 → 判决: PASS

### 异常演示: Issue 分类

1. 构造精度丢失场景: ¥99.999 × 7.25 = $724.99 实际输出 $725.00
2. QA 调用 verify_classify_issue
3. 决策树分析: UC 中有四舍五入规则 → 代码中 quantize 顺序错误 → CODE_BUG
4. 自动回流 Phase 4 → Developer 修复 → 重新验证

---

## 技术栈

- **Agent 框架**: AgentTeams (Hiclaw)
- **LLM**: DeepSeek V4 Pro (via Anthropic-compatible API)
- **语言**: Python 3.12+
- **存储**: MinIO (证据), Qdrant (知识向量), PostgreSQL (持久化)
- **可观测**: OpenTelemetry → Loki (Log) + Tempo (Trace) + Grafana
- **协议**: MCP (Model Context Protocol) — 23 个标准化工具
- **基础设施**: Docker, Nacos, Higress AI Gateway

## 开源协议

MIT License
