# DevFlow 工具规格 (T1-T12)

## 设计原则

所有工具共享以下行为:
- **Schema 校验**: 在入口做, 不在出口做 (fail fast)
- **幂等检查**: 相同参数的重复调用 → 返回已有结果
- **证据自动写入**: 每次调用自动调用 `evidence.write`
- **关联 ID 自动注入**: correlation_id 由工具层保证, Agent 无感
- **结构化日志**: 每次调用自动写 `log.structured`

---

## T1. UseCase 工具集

管理用例的完整生命周期: 创建 → 演进 → 追溯。

```
usecase.create(name, level, actor, goal, basic_flow)
  → level ∈ {L0, L1, L2}
  → 内置: name 唯一性检查, basic_flow ≥ 3 步, 版本号初始化
  → 产物: minio://usecases/{name}.yaml

usecase.upgrade(uc_id, new_level, additions)
  → 内置: 禁止降级(L2→L1), 版本号递增, 演进日志追加

usecase.add_alternative(uc_id, flow_name, scenario, trigger, outcome)
  → 内置: 关联 USECASE_GAP issue, 标记来源(Phase)

usecase.declare_known_unknown(uc_id, description, risk_level)
  → 关联到 UC, 供 Phase 3 arch.declare_extension_point 引用

usecase.link_to_requirement(uc_id, req_id)
usecase.link_to_code(uc_id, commit_sha, file_path)
usecase.trace(uc_id)
  → 返回完整追溯链: UC→FR→AC→Code→Test→Verdict

usecase.validate(uc_id)
  → 检查: level≥L1? basic_flow≥3步? 每个FR至少1个AC?
          known_unknowns 已声明?
          (如果是 financial/security 领域: 审计日志 AF 是否存在?)
```

---

## T2. Requirement 工具集

需求规约的结构化管理。

```
requirement.create(uc_ref, type, description, priority)
  → type ∈ {FR, NFR}
  → 内置: 自动编号(FR-01), UC 引用校验

requirement.create_ac(fr_ref, given, when, then, method?)
  → Lean AC 格式: {given: {var: val}, when: "action", then: "assertion"}
  → method ∈ {TEST, MANUAL, OBSERVE} (默认 TEST)
  → 内置: then 必须可量化(含 ==, <, >, in, matches)
  → 自动生成测试代码: 写入 test_{ac_id}.py
  → 自动调用 compiler.check_syntax 验证测试代码语法
  → method=MANUAL: 标记为技术债 (不可自动验证)
  → method=OBSERVE: then 改为 PromQL/Loki 查询
  → 拒绝: then 含有模糊词("正常"/"正确"/"合理")

requirement.traceability_matrix(task_id)
  → 输出: UC→FR→AC 矩阵
  → 自动检测: 孤儿 FR, 未验证 AC

requirement.request_clarification(question, options, context)
  → 写入 Matrix 房间, 记录等待状态, timeout 告警
```

---

## T3. PoC 工具集

可行性验证的代码化管理——PoC 可执行、可复现、可比较。

```
poc.create(name, hypothesis, code, expected_result, linked_fr)
  → code 存入 MinIO, 关联 FR

poc.run(experiment_id)
  → 在沙箱执行, 捕获 stdout/stderr/exit_code
  → 对比 actual vs expected

poc.list(task_id)
  → 返回该 Task 的所有 PoC 实验及结论

poc.record_result(experiment_id, conclusion, evidence)
  → conclusion ∈ {PASS, FAIL, INCONCLUSIVE}

poc.compare(expected, actual)
  → 调用 diff 工具 → 返回差异(文本 diff)
```

---

## T4. Token 追踪工具集

LLM 消耗的精确追踪——运行时 instrumentation, 不是事后估算。

```
token.record_call(agent, phase, model, input_tokens, output_tokens)
  → 每次 LLM 调用后立即调用
  → 内置: 自动计算 cost(按 model 价格表), 注入 correlation_id

token.estimate(task_spec, model, phases)
  → 基于历史数据 + 任务复杂度预估
  → 返回: {per_phase: {...}, total: N, confidence: float}

token.report(task_id)
  → 完整 token 消耗明细: {phase: {agent, input, output, cost}}

token.budget_check(task_id, budget_limit)
  → 返回: {status: OK|WARNING|EXCEEDED, remaining: $X}

token.anomaly_detect(task_id)
  → 检测: 单 Phase token > 历史 p95 × 1.5?
          总 token > 历史 p95 × 1.3?
          LLM retry 次数 > 历史 p95 × 2?
  → 异常 → 告警, 建议原因

token.trend(agent?, phase?, date_range?)
  → 返回 token 消耗趋势(用于成本优化 + 模型漂移检测)

token.budget_enforce(task_id, per_phase_budget)
  → 每 Phase 执行前检查, 超出 → 暂停 + 通知 Human
```

---

## T5. UML / 架构工具集

架构以 PlantUML/Mermaid 源码表达——代码, 不是图片。

```
arch.define_context_map(contexts, relationships)
  → contexts: [{name, responsibility, agents}]
  → relationships: [{from, to, type: PARTNERSHIP|CUSTOMER_SUPPLIER|ACL|CONFORMIST}]
  → 产物: PlantUML 源码 + 渲染图

arch.define_aggregate(context, name, invariants, entities, value_objects)
  → 产物: 聚合类图 PlantUML 源码

arch.generate_class_diagram(scope)
  → 从代码 AST 反向生成 → PlantUML 源码

arch.generate_sequence_diagram(usecase_id)
  → 从用例生成时序图: Actor→Controller→Service→Repository→ExternalAPI

arch.define_interface(name, version, inputs, outputs, errors, constraints)
  → JSON Schema 校验, 版本递增

arch.create_adr(title, context, decision, rationale, consequences, alternatives)
  → 自动编号(ADR-001), supersedes 链维护

arch.supersede_adr(old_id, new_id, reason)
  → 检查新旧 ADR 引用完整性

arch.declare_extension_point(interface, purpose, known_unknown_ref)
  → 关联 Phase 1 的 known_unknown

arch.validate_architecture(rules)
  → 检查: 循环依赖? 跨层调用? 单点故障? 接口未实现?
  → 如果定义了 PlantUML: 检查图与代码的一致性
```

---

## T6. Patch / 代码工具集

代码变更通过 patch 管理——不是 LLM 自由文本。

```
code.create_branch(task_id, base_ref)
  → 命名规范: feature/devflow-{task_id}
  → 内置: 检查分支不存在

code.generate_patch(spec_ref, uc_ref, context)
  → LLM 密集调用: Agent 推理"改什么", 工具执行"怎么改"
  → 输入: SolutionSpec + UseCase + 架构约束
  → 输出: unified diff patch (git format-patch)
  → 内置: diff 语法校验, 行号范围校验

code.apply_patch(patch, branch)
  → git apply → commit
  → 内置: commit message 自动关联 UC, 签名(agent_id + timestamp)

code.revert_patch(commit_sha)
  → git revert → commit
  → 记录回滚原因, 关联 Issue

code.self_review(commit_sha, checks)
  → checks: [{name, result: PASS|FAIL|SKIP, evidence}]

code.create_pr(branch, title, linked_ucs)
  → 内置: 幂等(同名 PR → 返回已有), 自动关联 UC
```

---

## T7. Compiler / 构建工具集

编译和构建是确定性工具——Agent 不判断"应该能编译通过"。

```
compiler.check_syntax(target)
  → 返回: {pass: bool, errors: [{file, line, message}]}

compiler.type_check(target, strict?)
  → mypy/pyright/tsc 结构化输出

compiler.build(target, config?)
  → {pass, artifact_hash, build_log_ref}

compiler.static_analysis(target, ruleset?)
  → SAST + lint + 安全的聚合
  → {pass, violations: [{rule, file, line, severity}]}

compiler.dependency_scan(target)
  → CVE + 许可证兼容
  → {pass, cves: [...], license_issues: [...]}
```

---

## T8. Test 工具集

测试执行和质量评估——不是"Agent 觉得测试够了"。

```
test.generate(code_change, acs, style)
  → 为代码变更和 AC 生成测试用例(LLM 密集)
  → 产物: test_*.py 文件

test.run(suite, target_branch)
  → {total, passed, failed, skipped, flaky}
  → 内置: flaky 检测(跑 3 次, 结果不一致 → 标记)

test.coverage(target_branch, baseline_branch?)
  → {before_pct, after_pct, delta, uncovered_lines}

test.mutation_test(target, test_suite)
  → cosmic-ray / mutmut → mutation_score

test.regression_validity(fix_commit, test_files)
  → revert fix → run tests → 必须 FAIL
  → 如果 PASS: 测试无效 (没有真正测到修复)

test.ac_coverage(ac_list, test_files)
  → 每个 AC 是否至少有一个测试? → {ac_id: bool}
  → 输出覆盖率矩阵

test.integration_run(changed_modules)
  → 跑所有受影响模块的集成测试 (系统级)
```

---

## T9. Verify / Issue 工具集

验证和分类的核心逻辑。

```
verify.ac(ac_id, test_run_result)
  → 对比 AC.then 与 test_run_result
  → {status: PASS|FAIL, actual, expected, evidence_ref}

verify.classify_issue(ac_id, failure_detail)
  → 决策树:
    usecase.trace → 场景在用例中? 
      → 否: USECASE_GAP
      → 是: 代码符合用例? 
        → 是: BUG_IN_USECASE
        → 否: CODE_BUG
    → 环境问题: ENV_ISSUE
  → 返回: {type, detail, suggested_target_phase}

verify.verdict(task_id)
  → 聚合 Eval-Gate + 时间线 + 系统回归 → PASS|FAIL_RETRY|NEED_HUMAN

verify.integration_classify(task_id, failing_tests)
  → INTEGRATION_BUG: Task 的正确修改破坏了其他模块的假设
  → PRE_EXISTING: 已有问题被新测试发现 (好!)
```

---

## T10. Evidence / 证据工具集

不可变证据的唯一写入入口。所有其他工具内部调用它。

```
evidence.write(task_id, phase, step, content, tool_name)
  → 内置: SHA256 + timestamp + correlation_id
  → 不可变: 写入后只能 append, 不能 update
  → 产物: MinIO evidence/{task_id}/{phase}/{step}_{ts}.json

evidence.trace_chain(task_id)
  → 正向: UC→FR→AC→Code→Test→Verdict→Deploy
  → 反向: Deploy→...→UC
  → 检测: 断链? 孤儿?

evidence.integrity_check(task_id)
  → SHA256 校验 → {pass, tampered: [...]}
```

---

## T11. Knowledge / 知识工具集

双通道知识索引的读写。

```
kb.index(task_id, channel, content)
  → channel ∈ {positive, negative, cost_optimization}
  → 自动提取: task_type, module, keywords, embedding
  → 写入 Qdrant 对应索引

kb.extract_integration_test(task_id)
  → Task 关闭时自动生成: 基于当前 Task 的修改影响面 → 生成集成回归测试
  → 产物: 测试文件进入集成测试套件, 下次任何 Task 修改相关模块时自动运行

kb.retrieve(task_context, channels, top_k)
  → channels: [positive] | [negative] | [both]
  → 返回: {positive: [...], negative: [...]} (结构化的 ContextPack)

kb.mark_stale(entry_id, reason)
  → 降低权重, 写操作日志, 不删除

kb.detect_contradiction()
  → 对比 positive_index 和 negative_index
  → 返回矛盾条目对

kb.health_report()
  → {total, stale, contradictions, index_freshness}

seed.generate(project_type, tech_stack)
  → 三级种子: 通用(~200条) + 模板(~50条/类型) + LLM合成(20-30条, 即时)
  → 每条: {content, confidence, source}
  → confidence: PREDEFINED=0.8, TEMPLATE=0.7, SYNTHESIZED=0.5
```

---

## T12. 横切工具

```
log.structured(level, action, message, metrics)
  → 自动注入: correlation_id, agent_id, phase, timestamp
  → 写入: Loki

cache.semantic_get(input_text)
cache.semantic_set(input_text, result, ttl)

circuit_breaker.state(service_name)
circuit_breaker.record(service_name, success: bool)

timeline.verify(task_id, phase, template?)
  → 对比实际事件流 vs 预期模板
  → 返回: {compliance_pct, gaps, order_violations, unexpected, timing_anomalies}

timeline.detect_skip(phase, events)
  → 检测常见跳过模式

complexity.assess(task_spec, usecases)
  → 返回: {level: S|M|L|XL, dimensions: {...}}
  → 驱动流程裁剪

trust.calculate(agent_id, task_type, recent_n)
  → 返回: {score, level, review_frequency}

trust.decay(agent_id)
  → 强制衰减: 模型变更 → 重置 0.5
  → 自然衰减: 每 5 个 Task 无审查 → -0.05

conflict.detect(task_id, pending_tasks)
  → 跨任务文件/接口/ADR 冲突检测

feedback.audit(sprint_id)
  → 5 个指标: KAR, FER, LV, 新鲜度-效果关联, FFPR

timeline.compare_tasks(task_ids)
  → 对比多个同类 Task 的时间线, 发现异常模式

system.regression_test(scope)
  → scope: {module, all_affected, full_system}
  → 输出: {total, passed, failed, new_failures, flaky}

system.consistency_check(task_ids)
  → 检查多个 Task 间的接口/数据模型/ADR 兼容性

system.health_trend(sprint_range)
  → 追踪: 集成测试规模、staging_smoke 失败率、生产事故率、回滚率

test.staging_smoke(deployment_id)
  → 健康检查 + 生产日志回放 + 金丝雀渐进 (1%→5%→25%→50%→100%)

attacker.probe_use_case(uc_id, strategies)
  → 5 种攻击: 边界、顺序、依赖、逻辑矛盾、角色混淆
  → 输出: ProbeReport {findings, summary}

attacker.probe_use_case_pair(uc_id_a, uc_id_b)
  → 检查两个用例间的一致性 (逻辑矛盾攻击)

attacker.probe_architecture(arch_spec)
  → 对架构假设的对抗性测试 (仅在 Phase 3 对 XL 任务运行)

quality.report(uc_id)
  → 聚合 Level A(工具) + B(Knowledge) + C(Attacker) 的结果
  → 输出: QualityReport (Human 只读 Level C 疑点)

quality.accept_fix(finding_id)
quality.dismiss_finding(finding_id, reason)
quality.defer_finding(finding_id, target_phase)
  → Human 的三态决策, 记录到用例演进日志

declare_feasibility_verdict(verdict, conditions?, risks?)
  → verdict ∈ {GO, NO_GO, CONDITIONAL_GO}
  → Conditional-Go: 列出前置条件 + 自动验证时机
```

---

## 工具实现优先级

| 优先级 | 工具 | 理由 |
|--------|------|------|
| P0 | T1 UseCase, T2 Requirement | Phase 1 核心, Demo 必需 |
| P0 | T6 Patch, T7 Compiler | Phase 4 核心, Demo 必需 |
| P0 | T10 Evidence | 所有工具依赖它 |
| P1 | T8 Test, T9 Verify | Phase 5 核心 |
| P1 | T3 PoC, T4 Token | Phase 2 核心 |
| P1 | T5 UML/Arch | Phase 3 核心 |
| P2 | T11 Knowledge | 反馈回路, 可先 mock |
| P2 | T12 横切 | 渗透到所有 Phase |
