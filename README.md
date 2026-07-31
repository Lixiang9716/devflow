# DevFlow — AI 驱动的结构化软件工程系统

## 一句话

DevFlow 不是"AI 写代码的工具"。DevFlow 是一个**用软件工程方法论驱动的多 Agent 协同系统**——用户提需求，系统按五阶段门禁（需求工程→可行性研究→架构设计→实现→验证）推进，12 组确定性工具产生产物，LLM 只负责推理和决策。

## 核心理念

```
LLM 的职责:  推理 + 决定调用哪把工具 + 组装参数
工具的职责:  执行 + 校验 + 持久化 + 证据 + 关联 ID + 幂等

Agent 不"写"任何东西。Agent 调用工具，工具产生产物。
```

## 架构速览

```
Phase 1         Phase 2         Phase 3         Phase 4         Phase 5
需求工程    →   可行性研究   →   架构设计    →   实现       →   验证
─────────────────────────────────────────────────────────────────────────
用例+需求        技术调研         自顶向下         代码生成         AC验证
渐进式披露       PoC实验          ADR             三道防线         Issue分类
四级验证         Token成本       接口契约         编译+SAST        时间线验证
                Go/No-Go        扩展点                           系统回归

反馈回路:
  验证失败 → Issue 分类 (5 类):
    USECASE_GAP      → 回到 Phase 1 (补充用例)
    BUG_IN_USECASE   → 回到 Phase 1 (修正用例)
    CODE_BUG         → 回到 Phase 4 (修复代码)
    ENV_ISSUE        → DevOps Agent 处理
    INTEGRATION_BUG  → 创建子 Task (系统级冲突, 发现的) or 已有问题 (PRE_EXISTING)
```

## 项目结构

```
devflow/
├── README.md              # 本文件
├── docs/
│   ├── ARCHITECTURE.md    # 完整架构说明
│   ├── TOOLS.md           # 12 组工具完整规格
│   ├── QUALITY.md         # 质量验证框架
│   ├── AGENTS.md          # Agent 角色定义
│   └── ROADMAP.md         # 实现路线图
├── tools/                  # 工具实现 (T1-T12)
├── skills/                 # Agent Skill 定义 (SKILL.md)
├── agents/                 # AgentTeams CRD 配置
├── eval_gates/             # Eval-G1~G6 评估配置
├── templates/              # 时间线模板、质量报告模板
└── tests/                  # DevFlow 自身的测试
```

## 关键技术决策

| 决策 | 理由 |
|------|------|
| 结构化门禁而非 Scrum | Agent 在模糊上下文中产生幻觉，需要阶段性收敛 |
| 一切产物由工具生成 | LLM 文本不可靠，工具保证 schema + 幂等 + 证据 |
| 用例渐进式披露 (L0/L1/L2) | 不追求 Phase 1 穷尽，L2 是预期演进 |
| Attacker Agent 对抗性验证 | 减少 Human 审查量从 100% 到 15% |
| 事件时间线验证 | 产物正确 ≠ 过程正确，时间线检测跳跃和捷径 |
| 反馈有效性度量 | 学习系统需要验证自己真的在学习 |

## 快速开始

```bash
# 1. 安装 AgentTeams (一行命令)
bash <(curl -sSL https://higress.ai/hiclaw/install.sh)

# 2. 部署 DevFlow Agent 团队
hiclaw apply -f agents/

# 3. 运行 Capability Baseline (Phase 0)
devflow baseline run

# 4. 提交第一个需求
devflow task create "电商平台需要支持多币种订单"
```
