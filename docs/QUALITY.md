# DevFlow 质量验证框架

## 验证全景

DevFlow 的质量验证不是事后检查，而是**六层渗透**的防御体系：

```
Layer 1: 工具层校验  → 产物结构对 (工具入口, fail fast)
Layer 2: Eval-Gate    → 产物质量对 (阶段出口, 程序化评估)
Layer 3: 四级验证     → 语义正确性 (Attacker + Human 聚焦审查)
Layer 4: 时间线验证   → 过程对 (Agent 是否按流程走)
Layer 5: 反馈有效性   → 学习对 (知识系统真的在变好吗?)
Layer 6: 系统回归     → 整体对 (单任务通过 ≠ 系统健康)
```

---

## Layer 1: 工具层校验

每个工具在入口做 schema 校验，不等到 Phase 出口。详见 `TOOLS.md`。

关键原则: **Eval-Gate 读取的是工具的确定性输出，不是 LLM 的文本**。

---

## Layer 2: Eval-Gate (程序化评估)

| Gate | 触发时机 | 评估内容 |
|------|---------|---------|
| G1 | Phase 1 出口 | Schema 校验、AC 可测试性(每个 AC.then 可量化)、用例完整性、Lean AC 规则 |
| G2 | Phase 2 出口 | PoC 代码可复现、PoC 结果已归档、成本模型完整、feasibility verdict 明确 |
| G3 | Phase 3 出口 | 架构无循环依赖、接口契约完整、ADR 覆盖所有非平凡决策、扩展点已声明 |
| G4 | Phase 4 出口 | 编译通过、SAST clean、依赖 CVE clean、既有测试无回归、self_review 完整 |
| G5 | Phase 5 出口 | 变异测试 score ≥ 0.5、AC 覆盖率 100%、回归测试有效性(所有新测试 detect revert)、追溯完整性 |
| G6 | Phase 5 出口 | 部署健康、SLO 合规、回滚验证 (G6 由 DevOps Agent 执行) |

Verdict 聚合逻辑:

```
所有 CRITICAL gate FAIL → FAIL_RETRY
  (G1.1 schema, G2.1 PoC代码可复现, G3.1 架构无循环依赖,
   G4.1 编译, G4.2 既有测试无回归, G5.4 追溯完整性)

所有 gate PASS → PASS
部分非 CRITICAL gate FAIL → 对应的 Eval-Gate 标记 WARN, 但整体仍 PASS
```

Verdict 枚举: `PASS | FAIL_RETRY | NEED_HUMAN` (三值, 由 verify.verdict 工具返回)

---

## Layer 3: 用例质量四级验证

不是 Human 审查整个用例，而是四级过滤压缩到 15% 的工作量。

### Level A: 结构正确性 (工具自动)

`usecase.validate()` — schema、格式、AC 可测试性、追溯链完整性。零 LLM 参与。拦截 ~40%。

### Level B: 模式完整性 (Knowledge + 历史)

Knowledge Agent 对比当前用例和历史用例的**结构**:

```
类似历史用例包含的 Alternative Flow 类型:  当前 UC-01:
  依赖服务不可用              ✓ 2a (有)
  依赖服务超时                ✓ 2b (有)
  精度/舍入异常               ✓ 3a (有)
  极端值/边界                ✗ 缺失 → 疑点
  审计/日志                  ✗ 缺失 → HIGH 风险

输出: 差异清单 {must_fix, should_consider, already_covered}
```

拦截 ~30%。

### Level C: 对抗性发现 (Attacker Agent)

专门"找茬"的 Agent，5 种攻击策略:

| 策略 | 攻击方向 |
|------|---------|
| 边界攻击 | 极端输入值: 0, -1, None, "", 极大/极小值 |
| 顺序攻击 | 重新排列步骤, 找到隐含假设 |
| 依赖攻击 | 外部服务返回异常值: NaN, 过期数据, 错误格式 |
| 逻辑矛盾 | 用例间的一致性: UC-A 和 UC-B 对同一场景的冲突处理 |
| 角色混淆 | 非授权 Actor 尝试越权操作 |

输出: 疑点列表 (不是判断, 是问题)。拦截 ~15%。

### Level D: 人类聚焦审查

Human 只审 Attacker 输出的 HIGH/MEDIUM 疑点。每个疑点点 Accept/Dismiss/Defer。
审查时间: 2-5 分钟 vs 30 分钟(全文审查)。压缩比: 12%。

---

## Layer 4: 事件时间线验证

### 原理

每个工具调用 = 不可变事件 (T10 evidence 自动记录)。事件按时间排序 = 时间线。
时间线 vs 预期模板 = 过程合规性。

### 验证内容

- **缺失事件**: Agent 跳过了必要步骤 (如跳过 Attacker 直接出口)
- **顺序违规**: 步骤顺序不对 (如在澄清前就写了 AC)
- **意外事件**: Agent 做了模板中没有的操作
- **时序异常**: 两个事件间延迟异常 (Agent 可能卡住了)

### 与 Eval-Gate 的交叉

```
Eval PASS + timeline OK   → 最可信
Eval PASS + timeline BAD  → 产物对但过程有跳跃 → 标记 NEED_HUMAN
Eval FAIL + timeline OK   → 过程合规但产物不合格 → 正常 FAIL_RETRY
Eval FAIL + timeline BAD  → 两个维度都失败 → 严重告警, 可能系统性退化
```

---

## Layer 5: 反馈有效性度量

验证"学习系统真的在学习"——5 个核心指标:

| 指标 | 公式 | 健康阈值 | 异常动作 |
|------|------|---------|---------|
| KAR 知识采纳率 | 使用反馈的 Task / 总 Task | > 60% | < 30% → 反馈不相关 |
| FER 反馈有效率 | 用反馈后 PASS 率 / 不用时 PASS 率 | > 1.2 | < 0.8 → 反馈有害 |
| LV 学习速率 | Δ(first_pass_rate) / Δ(Sprint) | > 0 | < 0 → 系统性退化 |
| 知识新鲜度 | 旧知识被引后的 Task 成功率 | 稳定 | 随年龄下降 → 知识过期 |
| FFPR 假阳性率 | 反向提示被检查但风险不存在 | < 30% | > 30% → 狼来了效应 |

### 反馈自我审计

`feedback.audit(sprint_id)` 在 Sprint Retro 自动运行，输出:
- 最有效的 3 条新知识
- 需要审查的 misleading 条目
- 各 Agent 的反馈采纳率对比
- 建议的改进动作

---

## Layer 6: 系统级回归验证

单任务验证通过 ≠ 系统健康。

### S1: 跨任务冲突检测

`conflict.detect(task_id, pending_tasks)` 在 Phase 4 创建分支前运行:
- 当前 Task 要修改的文件，是否被其他 pending Task 也在修改？
- 当前 Task 要修改的接口，是否有其他 Task 依赖？
- 当前 Task 的 ADR，是否与 pending Task 的 ADR 冲突？

冲突 → PM Agent 决定: 串行化 or 人工确认。

### S2: 集成测试套件

`test.integration_run(changed_modules)` 在 Phase 5 运行:
- 不是只跑当前 Task 的测试
- 跑所有受影响模块的集成测试
- 每次 Task 关闭 → Knowledge Agent 自动生成一条集成测试加入套件
- 失败 → INTEGRATION_BUG (单模块正确, 组合失败)

### S3: 生产镜像验证

`test.staging_smoke(deployment_id)` 在部署后运行:
- 健康检查
- 从生产日志采样真实请求 → staging 回放 → 对比响应
- 金丝雀渐进: 1%→5%→25%→50%→100%, 任何异常自动回滚

### 系统健康趋势

`system.health_trend(sprint_range)` 追踪:
- 集成测试套件规模 (应线性增长)
- staging_smoke 失败率
- 生产事故率 (incident / Sprint)
- 回滚率 (rollback / deployment)

---

## 验证执行时序

```
Phase 0:  Capability Baseline (Agent 基准)
          - Analyst: UC 完整度 ≥ 80%, AC 可测试率 ≥ 70%
          - Architect: root_cause precision ≥ 60%
          - Developer: 编译通过率 ≥ 80%, 既有测试通过率 ≥ 70%
          - QA: defect_detection_rate ≥ 40%, false_positive_rate ≤ 30%
          低于基线 → Agent 标记 DEGRADED → 强制 NEED_HUMAN
          模型变更 → 自动重跑基线, 指标下降 >10% 告警, >20% 自动回退
Phase 1:  G1 → Level A(工具) → Level B(Knowledge) → Level C(Attacker) → Level D(Human)
           → timeline.verify(phase=1)

Phase 2:  G2 → timeline.verify(phase=2)

Phase 3:  G3 → timeline.verify(phase=3)

Phase 4:  G4 → conflict.detect (跨任务) → timeline.verify(phase=4)

Phase 5:  G5 → G6 → verify.classify_issue → verify.verdict
           → test.integration_run (系统回归)
           → test.staging_smoke (生产镜像)
           → timeline.verify(phase=5)
           → feedback.audit (每 Sprint Retro)

持续:     system.health_trend (每 Sprint)
          token.anomaly_detect (每 Task)
```

---

## 信任累积: Human 审查量自适应

```
trust.calculate(agent_id, task_type, recent_n):
  score = first_pass_rate × 0.4 + (1 - fail_retry_rate) × 0.3 + human_accept_rate × 0.3

  score ≥ 0.85 → Human 每 5 个 Task 抽查 1 个
  score ≥ 0.70 → Human 每 2 个 Task 审 1 个
  score < 0.70 → Human 每个 Task 必审

信任衰减:
  - LLM 模型变更 → 重置为 0.5
  - 每 5 个 Task 无 Human 审查 → -0.05
  - Agent 基线退化 → 重置为 0.5

超时自动放行:
  Phase 2 Go/No-Go 等待 4h → trust ≥ 0.85 → 自动 Go; trust < 0.85 → 自动 No-Go
  Phase 3 架构评审 8h → complexity ≤ M 自动通过;
                        ≥ L 升级备用 reviewer, 无备用 → 自动通过但标记
  Attacker 疑点审查 4h → HIGH 自动 Accept, MEDIUM/LOW 自动 Defer
  Phase 5 低风险裁决 → trust ≥ 0.85 → 自动 PASS
```
