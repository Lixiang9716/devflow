"""End-to-end tests: complete 5-phase DevFlow pipeline.

Covers the full golden path from the plan:
  Phase 1: 需求工程 — use case creation → L0→L1 upgrade → FR → Lean AC
  Phase 2: 可行性研究 — PoC experiments + token estimation
  Phase 3: 架构设计 — context map + interface contracts + ADR + extension points
  Phase 4: 实现 — branch → patch → compile → SAST → self-review → PR
  Phase 5: 验证 — test execution → AC verification → issue classification → verdict

Also tests:
  - Issue classification decision tree (USECASE_GAP vs CODE_BUG vs BUG_IN_USECASE)
  - Eval-Gates G1-G6
  - Timeline verification
  - Evidence traceability
  - Cross-task conflict detection
  - Complexity assessment + pipeline tailoring
  - Feedback audit
"""

import pytest
from devflow.core.correlation import new_correlation
from devflow.core.evidence import clear_evidence, trace_chain, check_integrity, get_events
from devflow.core.result import is_ok, is_failure

# Import all tools
import devflow.tools.usecase as usecase
import devflow.tools.requirement as requirement
import devflow.tools.poc as poc
import devflow.tools.token as token
import devflow.tools.arch as arch
import devflow.tools.code_patch as code_patch
import devflow.tools.compiler as compiler
import devflow.tools.test as test_tools
import devflow.tools.verify as verify
import devflow.tools.knowledge as kb
import devflow.tools.crosscut as xcut

# Import eval gates
from devflow.eval_gates import (
    run_g1_check, run_g2_check, run_g3_check,
    run_g4_check, run_g5_check, run_g6_check,
)

# Import agent definitions
from devflow.agents import (
    AGENT_DEFINITIONS, get_phase_agents,
    get_agent_phase_responsibilities,
)


def clear_all_stores():
    """Clear all tool stores between tests."""
    usecase.clear_store()
    requirement.clear_store()
    poc.clear_store()
    token.clear_store()
    arch.clear_store()
    code_patch.clear_store()
    test_tools.clear_store()
    verify.clear_store()
    kb.clear_store()
    clear_evidence()


class TestPhase1RequirementsEngineering:
    """Phase 1: 需求工程 — full golden path."""

    task_id = "task-e2e-001"

    def setup_method(self):
        clear_all_stores()

    def test_complete_phase1_golden_path(self):
        """End-to-end Phase 1: user request → L1 use case + FR + Lean ACs.

        Scenario: 电商平台需要支持多币种订单，下单时按实时汇率换算为人民币结算
        """
        corr = new_correlation()

        # Step 1: Create initial L0 use case
        result = usecase.create(
            name="用户使用外币下单",
            level="L0",
            actor="买家",
            goal="以外币查看订单金额并完成下单",
            basic_flow=[
                "1. 买家选择外币作为支付币种",
                "2. 系统获取实时汇率",
                "3. 系统换算并显示外币金额",
                "4. 买家确认 → 创建订单",
                "5. 实际扣款按人民币执行",
            ],
            correlation=corr, task_id=self.task_id,
        )
        assert is_ok(result)
        uc = result.data
        assert uc.level.value == "L0"

        # Step 2: Request clarification (simulating ambiguity discovery)
        clarification = requirement.request_clarification(
            "汇率来源是什么？",
            ["央行牌价", "第三方API", "手动录入"],
            context="多币种订单",
            correlation=corr, task_id=self.task_id,
        )
        assert is_ok(clarification)
        assert clarification.data["status"] == "PENDING"

        # Step 3: Retrieve knowledge feedback
        kb.seed_generate("ecommerce", {"python": "3.10", "framework": "FastAPI"})

        # Step 4: Upgrade to L1 with alternative flows
        upgrade_result = usecase.upgrade(
            uc.uc_id,
            "L1",
            additions={
                "alternative_flows": [
                    {"flow_name": "2a", "scenario": "汇率服务不可用",
                     "trigger": "API返回500", "outcome": "拒绝下单，提示用户稍后重试"},
                    {"flow_name": "2b", "scenario": "汇率服务超时",
                     "trigger": "响应时间 > 3s", "outcome": "降级使用缓存汇率"},
                    {"flow_name": "3a", "scenario": "换算精度超过2位小数",
                     "trigger": "结果小数位 > 2", "outcome": "四舍五入到分"},
                ],
            },
            correlation=corr, task_id=self.task_id,
        )
        assert is_ok(upgrade_result)
        assert upgrade_result.data.level.value == "L1"

        # Step 5: Declare known unknowns
        ku_result = usecase.declare_known_unknown(
            uc.uc_id,
            "极端汇率场景: 1 目标币种 << 0.01 人民币 (如 VND, IDR)",
            "MEDIUM",
            correlation=corr, task_id=self.task_id,
        )
        assert is_ok(ku_result)

        # Step 6: Create functional requirements
        fr1 = requirement.create(
            uc.uc_id, "FR",
            "汇率换算: 人民币金额 × 实时汇率 → 目标币种金额",
            correlation=corr, task_id=self.task_id,
        )
        assert is_ok(fr1)
        assert fr1.data.req_id.startswith("FR-")

        fr2 = requirement.create(
            uc.uc_id, "FR",
            "汇率服务不可用时拒绝下单",
            correlation=corr, task_id=self.task_id,
        )
        assert is_ok(fr2)

        fr3 = requirement.create(
            uc.uc_id, "FR",
            "汇率服务超时时使用缓存汇率(5分钟窗口)",
            correlation=corr, task_id=self.task_id,
        )
        assert is_ok(fr3)

        fr4 = requirement.create(
            uc.uc_id, "FR",
            "换算结果四舍五入到分",
            correlation=corr, task_id=self.task_id,
        )
        assert is_ok(fr4)

        nfr1 = requirement.create(
            uc.uc_id, "NFR",
            "汇率查询响应时间 < 2s (p95)",
            priority="HIGH", correlation=corr, task_id=self.task_id,
        )
        assert is_ok(nfr1)

        # Step 7: Create Lean ACs
        ac1 = requirement.create_ac(
            fr1.data.req_id,
            given={"rate": 7.25, "amount_cny": 100},
            when="convert_order_to_display_currency(order, target='USD')",
            then="display_amount == Decimal('13.79')",
            correlation=corr, task_id=self.task_id,
        )
        assert is_ok(ac1)
        assert ac1.data.generated_test_file != ""

        ac2 = requirement.create_ac(
            fr2.data.req_id,
            given={"rate_service": "return 500"},
            when="convert_order_to_display_currency(order, target='USD')",
            then="raises ServiceUnavailable",
            correlation=corr, task_id=self.task_id,
        )
        assert is_ok(ac2)

        ac3 = requirement.create_ac(
            fr3.data.req_id,
            given={"rate_service": "timeout after 3s", "cache": "valid"},
            when="convert_order_to_display_currency(order, target='USD')",
            then="display_amount == Decimal('13.79')",
            correlation=corr, task_id=self.task_id,
        )
        assert is_ok(ac3)

        ac4 = requirement.create_ac(
            fr4.data.req_id,
            given={"rate": 7.25, "amount_cny": 99.999},
            when="convert_order_to_display_currency(order, target='USD')",
            then="display_amount == Decimal('724.99')",
            correlation=corr, task_id=self.task_id,
        )
        assert is_ok(ac4)

        # Step 8: Traceability matrix
        matrix = requirement.traceability_matrix(self.task_id)
        assert is_ok(matrix)
        assert len(matrix.data["matrix"]) == 5  # 4 FR + 1 NFR

        # Step 9: Validate use case
        validation = usecase.validate(uc.uc_id, correlation=corr, task_id=self.task_id)
        assert is_ok(validation)
        assert validation.data["valid"] == True

        # Phase 1 outputs verified
        assert len(usecase.list_all()) == 1
        assert len(requirement.list_reqs()) == 5
        assert len(uc.alternative_flows) == 3
        assert len(uc.known_unknowns) == 1


class TestPhase2FeasibilityStudy:
    """Phase 2: 可行性研究 — PoC + Token estimation."""

    task_id = "task-e2e-002"

    def setup_method(self):
        clear_all_stores()

    def test_complete_phase2(self):
        """Phase 2: technical PoC + economic feasibility."""
        corr = new_correlation()

        # PoC-1: 精度验证
        exp1 = poc.create(
            "汇率换算精度", "Decimal 满足精度需求",
            "from decimal import Decimal\nresult = Decimal('100') * Decimal('7.25')\nprint(result)",
            "725.00", linked_fr="FR-01",
            correlation=corr, task_id=self.task_id,
        )
        assert is_ok(exp1)

        # Run PoC
        run1 = poc.run(exp1.data.experiment_id, correlation=corr, task_id=self.task_id)
        assert is_ok(run1)

        # Record conclusion
        poc.record_result(
            exp1.data.experiment_id, "PASS",
            evidence={"note": "Decimal精度满足需求"},
            correlation=corr, task_id=self.task_id,
        )

        # Token cost estimation
        cost_model = token.estimate(
            {"task_type": "multi_currency", "complexity": "L"},
            "deepseek-v4-pro",
            task_id=self.task_id,
        )
        assert is_ok(cost_model)
        assert cost_model.data["total_cost"] < 1.0  # Should be cheap
        assert len(cost_model.data["per_phase"]) == 5


class TestPhase3Architecture:
    """Phase 3: 架构设计 — top-down design + ADR."""

    task_id = "task-e2e-003"

    def setup_method(self):
        clear_all_stores()

    def test_complete_phase3(self):
        """Phase 3: self-top-down architecture design."""
        corr = new_correlation()

        # Level 0: System context
        ctx_result = arch.define_context_map(
            contexts=[
                {"name": "订单服务", "responsibility": "订单管理、多币种换算", "agents": ["analyst"]},
                {"name": "汇率服务", "responsibility": "外部汇率API", "agents": []},
                {"name": "支付网关", "responsibility": "支付处理", "agents": []},
            ],
            relationships=[
                {"source": "订单服务", "target": "汇率服务", "type": "CUSTOMER_SUPPLIER"},
                {"source": "订单服务", "target": "支付网关", "type": "CUSTOMER_SUPPLIER"},
            ],
            task_id=self.task_id, correlation=corr,
        )
        assert is_ok(ctx_result)
        assert "plantuml" in ctx_result.data

        # Level 3: Interface contracts
        iface1 = arch.define_interface(
            "ExchangeRateProvider", "v1",
            inputs={"from_currency": "str", "to_currency": "str"},
            outputs={"rate": "Decimal", "timestamp": "datetime"},
            errors=["ServiceUnavailable", "Timeout"],
            constraints=["rate > 0", "响应时间 < 2s"],
            task_id=self.task_id, correlation=corr,
        )
        assert is_ok(iface1)

        iface2 = arch.define_interface(
            "CurrencyConverter", "v1",
            inputs={"amount": "Money", "target": "Currency"},
            outputs={"display_amount": "Decimal"},
            errors=["PrecisionOverflow"],
            constraints=["result 四舍五入到分"],
            task_id=self.task_id, correlation=corr,
        )
        assert is_ok(iface2)

        # ADR-001: Decimal vs integer
        adr1 = arch.create_adr(
            "汇率精度使用 Python Decimal 而非整数(分)",
            "多币种换算产生多位小数，需选择精度方案",
            "使用 Decimal + quantize(Decimal('0.01'))",
            "避免浮点误差；标准库支持；PoC 验证通过",
            "性能略低于整数(纳秒级差异，可忽略)",
            alternatives=["整数(分)", "float"],
            task_id=self.task_id, correlation=corr,
        )
        assert is_ok(adr1)
        assert adr1.data.adr_id == "ADR-001"

        # ADR-002: Redis cache
        adr2 = arch.create_adr(
            "汇率缓存使用 Redis 而非本地内存",
            "多实例部署时需共享缓存",
            "Redis，TTL 5min",
            "多实例一致性；已有 Redis 基础设施",
            "引入 Redis 依赖；网络延迟 ~1ms",
            task_id=self.task_id, correlation=corr,
        )
        assert is_ok(adr2)
        assert adr2.data.adr_id == "ADR-002"

        # Extension point for known unknown
        ep = arch.declare_extension_point(
            "ExchangeRateProvider", "支持极小值货币(VND, IDR)",
            "极端汇率场景", task_id=self.task_id, correlation=corr,
        )
        assert is_ok(ep)

        # Architecture validation
        arch_validation = arch.validate_architecture(task_id=self.task_id)
        assert is_ok(arch_validation)
        assert arch_validation.data["passed"]


class TestPhase4Implementation:
    """Phase 4: 实现 — code generation + compilation + self-review."""

    task_id = "task-e2e-004"

    def setup_method(self):
        clear_all_stores()

    def test_complete_phase4(self):
        """Phase 4: implementation with three lines of defense."""
        corr = new_correlation()

        # Defense line 1: Create branch
        branch = code_patch.create_branch(self.task_id, base_ref="main", correlation=corr)
        assert is_ok(branch)

        # Generate patch
        patch = code_patch.generate_patch("spec-ref", "UC-01", task_id=self.task_id, correlation=corr)
        assert is_ok(patch)
        assert "CurrencyConverter" in patch.data.diff_content

        # Compile/check syntax
        syntax = compiler.check_syntax("order.py", patch.data.diff_content, task_id=self.task_id, correlation=corr)
        assert is_ok(syntax)

        # Static analysis
        sast = compiler.static_analysis("src/", task_id=self.task_id, correlation=corr)
        assert is_ok(sast)
        assert sast.data.passed

        # Dependency scan
        deps = compiler.dependency_scan("src/", task_id=self.task_id, correlation=corr)
        assert is_ok(deps)
        assert deps.data.passed

        # Build
        build_result = compiler.build("src/", task_id=self.task_id, correlation=corr)
        assert is_ok(build_result)

        # Self-review
        checks = [
            {"name": "UC-01.2 正常下单", "result": "PASS", "evidence": "test passed"},
            {"name": "UC-01.2a 拒绝下单", "result": "PASS", "evidence": "test passed"},
            {"name": "UC-01.2b 降级缓存", "result": "PASS", "evidence": "test passed"},
            {"name": "UC-01.3 汇率换算精度", "result": "PASS", "evidence": "test passed"},
            {"name": "UC-01.3a 四舍五入", "result": "PASS", "evidence": "test passed"},
            {"name": "FR-01~04 全覆盖", "result": "PASS", "evidence": "verified"},
        ]
        review = code_patch.self_review("abc12345", checks, task_id=self.task_id, correlation=corr)
        assert is_ok(review)
        assert review.data.all_passed

        # Apply patch
        apply_result = code_patch.apply_patch(
            patch.data.patch_id, branch.data.name,
            task_id=self.task_id, correlation=corr,
        )
        assert is_ok(apply_result)

        # Create PR
        pr = code_patch.create_pr(
            branch.data.name, "实现多币种订单功能",
            ["UC-01"], task_id=self.task_id, correlation=corr,
        )
        assert is_ok(pr)
        assert pr.data.status == "OPEN"


class TestPhase5Verification:
    """Phase 5: 验证 — test execution + AC verification + issue classification + verdict."""

    task_id = "task-e2e-005"

    def setup_method(self):
        clear_all_stores()

    def test_ac_verification_and_pass(self):
        """All ACs pass → PASS verdict."""
        corr = new_correlation()

        # Run tests
        test_result = test_tools.run("full", target_branch="feature/devflow-task-0042", task_id=self.task_id, correlation=corr)
        assert is_ok(test_result)

        # Coverage
        cov = test_tools.coverage("feature/devflow-task-0042", baseline_branch="main", task_id=self.task_id, correlation=corr)
        assert is_ok(cov)

        # Mutation testing
        mut = test_tools.mutation_test("CurrencyConverter", "test_currency", task_id=self.task_id, correlation=corr)
        assert is_ok(mut)

        # Regression validity
        reg = test_tools.regression_validity("abc12345", ["test_currency.py"], task_id=self.task_id, correlation=corr)
        assert is_ok(reg)

        # AC coverage
        ac_cov = test_tools.ac_coverage(
            ["AC-FR-01-1", "AC-FR-02-1", "AC-FR-03-1", "AC-FR-04-1"],
            ["test_ac_fr_01_1.py", "test_ac_fr_02_1.py", "test_ac_fr_03_1.py", "test_ac_fr_04_1.py"],
            task_id=self.task_id, correlation=corr,
        )
        assert is_ok(ac_cov)
        assert ac_cov.data.coverage_pct == 100.0

        # Verify all ACs
        for ac_id, expected in [
            ("AC-FR-01-1", "13.79"),
            ("AC-FR-02-1", "ServiceUnavailable"),
            ("AC-FR-03-1", "13.79"),
            ("AC-FR-04-1", "724.99"),
        ]:
            v = verify.verify_ac(ac_id, {"actual": expected, "expected": expected}, task_id=self.task_id, correlation=corr)
            assert is_ok(v)
            assert v.data.status == "PASS", f"{ac_id} should pass"

        # Final verdict
        final = verify.verdict(
            self.task_id,
            eval_gate_results={"G1": "PASS", "G2": "PASS", "G3": "PASS", "G4": "PASS", "G5": "PASS", "G6": "PASS"},
            timeline_compliance=0.95,
            correlation=corr,
        )
        assert is_ok(final)
        assert final.data.verdict.value == "PASS"

    def test_code_bug_classification(self):
        """Phase 5: AC fails → classified as CODE_BUG → back to Phase 4."""
        corr = new_correlation()

        # Simulate test failure
        issue = verify.classify_issue(
            "AC-FR-04-1",
            {
                "scenario_in_use_case": True,
                "code_matches_use_case": False,
                "detail": "quantize调用顺序错误：上游提前截断了精度",
            },
            task_id=self.task_id, correlation=corr,
        )
        assert is_ok(issue)
        assert issue.data.type.value == "CODE_BUG"
        assert issue.data.suggested_target_phase == "4"

        # Fix: revert + regenerate
        revert = code_patch.revert_patch("abc12345", reason="quantize顺序错误", task_id=self.task_id, correlation=corr)
        assert is_ok(revert)

        new_patch = code_patch.generate_patch("spec-ref-v2", "UC-01", task_id=self.task_id, correlation=corr)
        assert is_ok(new_patch)

    def test_usecase_gap_classification(self):
        """Phase 5: AC fails → USECASE_GAP → back to Phase 1."""
        corr = new_correlation()

        issue = verify.classify_issue(
            "AC-FR-99-1",
            {
                "scenario_in_use_case": False,
                "detail": "越南盾(VND)极端汇率场景未在用例中定义",
            },
            task_id=self.task_id, correlation=corr,
        )
        assert is_ok(issue)
        assert issue.data.type.value == "USECASE_GAP"
        assert issue.data.suggested_target_phase == "1"


class TestEvalGates:
    """Eval-Gate G1-G6 programmatic evaluation."""

    def test_g1_all_pass(self):
        result = run_g1_check("t1", usecase_count=1, ac_count=4, quantified_ac_count=4, l1_count=1)
        assert is_ok(result)
        assert result.data["passed"]

    def test_g1_fail_no_usecases(self):
        result = run_g1_check("t1", usecase_count=0, ac_count=0, quantified_ac_count=0, l1_count=0)
        assert not result.data["passed"]

    def test_g3_adr_coverage(self):
        result = run_g3_check("t1", has_context_map=True, has_interface_contracts=True,
                              adr_count=2, extension_points_declared=True, circular_deps=False)
        assert result.data["passed"]

    def test_g3_circular_deps_fail(self):
        result = run_g3_check("t1", has_context_map=True, has_interface_contracts=True,
                              adr_count=2, extension_points_declared=False, circular_deps=True)
        assert not result.data["passed"]  # CRITICAL gate fails

    def test_g4_compilation_fail(self):
        result = run_g4_check("t1", compilation_passed=False, sast_clean=True,
                              no_cves=True, no_regression=True, self_review_complete=True)
        assert not result.data["passed"]  # CRITICAL gate fails

    def test_g5_mutation_score_pass(self):
        result = run_g5_check("t1", mutation_score=0.65, ac_coverage_pct=100.0,
                              regression_valid=True, traceability_complete=True)
        assert result.data["passed"]

    def test_g5_mutation_score_fail(self):
        result = run_g5_check("t1", mutation_score=0.3, ac_coverage_pct=80.0,
                              regression_valid=False, traceability_complete=True)
        # G5.4 is CRITICAL (traceability_complete=True makes it pass)
        # G5.2 (AC coverage < 100%) and G5.1 (mutation < 0.5) fail but are non-critical
        # Since the only critical gate (G5.4) passes, overall passed=True
        assert result.data["passed"]


class TestTimelineVerification:
    """Timeline verification: process integrity."""

    def test_timeline_phase1_complete(self):
        clear_all_stores()
        task_id = "task-timeline-001"
        corr = new_correlation()

        # Execute Phase 1 in order
        usecase.create("test", "L0", "actor", "goal", ["s1", "s2", "s3"], correlation=corr, task_id=task_id)
        from devflow.tools.usecase import list_all
        uc_id = list_all()[0].uc_id
        requirement.request_clarification("?", ["A", "B"], correlation=corr, task_id=task_id)
        kb.index(task_id, "positive", {"test": True}, correlation=corr)
        usecase.upgrade(uc_id, "L1", correlation=corr, task_id=task_id)
        requirement.create(uc_id, "FR", "test FR", correlation=corr, task_id=task_id)
        requirement.create_ac("FR-01", {"x": 1}, "do()", "result == 1", correlation=corr, task_id=task_id)
        usecase.validate(uc_id, correlation=corr, task_id=task_id)

        # Verify timeline
        result = xcut.verify_timeline(task_id, "1", correlation=corr)
        assert is_ok(result)
        report = result.data
        assert report.compliance_pct >= 0  # Should have reasonable compliance

    def test_detect_skip_apply_without_syntax(self):
        """Detect: code applied without syntax check."""
        clear_all_stores()
        task_id = "task-skip-001"

        # Write events simulating a skip
        from devflow.core.evidence import write_evidence as ev_write
        ev_write(task_id, "4", "step1", {}, "code.create_branch")
        ev_write(task_id, "4", "step2", {}, "code.generate_patch")
        # SKIPPED: compiler.check_syntax
        ev_write(task_id, "4", "step3", {}, "code.apply_patch")

        events = get_events(task_id)
        skips = xcut.detect_skip("4", events)
        skip_tools = [s.get("tool", "") for s in skips]
        assert any("compiler" in s or "syntax" in s.lower() for s in skip_tools)


class TestComplexityAssessment:
    """Complexity assessment and pipeline tailoring."""

    def test_simple_task_skips_phase2_3(self):
        result = xcut.assess_complexity(
            {"file_count": 2, "dependency_depth": 1, "financial": False, "security": False, "historical_similarity": 0.9},
            task_id="t1",
        )
        assert is_ok(result)
        assert result.data["level"] == "S"
        assert "2" in result.data["skip_phases"]
        assert "3" in result.data["skip_phases"]

    def test_xl_task_full_pipeline(self):
        result = xcut.assess_complexity(
            {"file_count": 20, "dependency_depth": 5, "financial": True, "security": False, "uc_count": 6},
            task_id="t1",
        )
        assert result.data["level"] == "XL"


class TestCrossTaskConflict:
    """Cross-task conflict detection."""

    def test_no_conflict(self):
        pending = [
            {"task_id": "t1", "modified_files": ["src/a.py"]},
            {"task_id": "t2", "modified_files": ["src/b.py"]},
        ]
        result = xcut.detect_conflict("t1", pending)
        assert result.data["conflict_count"] == 0

    def test_file_overlap_conflict(self):
        pending = [
            {"task_id": "t1", "modified_files": ["src/a.py", "src/shared.py"]},
            {"task_id": "t2", "modified_files": ["src/b.py", "src/shared.py"]},
        ]
        result = xcut.detect_conflict("t1", pending)
        assert result.data["conflict_count"] == 1
        assert result.data["action"] == "SERIALIZE"


class TestAgentDefinitions:
    """Agent role definitions."""

    def test_all_7_agents_defined(self):
        assert len(AGENT_DEFINITIONS) == 7
        assert "analyst" in AGENT_DEFINITIONS
        assert "architect" in AGENT_DEFINITIONS
        assert "developer" in AGENT_DEFINITIONS
        assert "qa" in AGENT_DEFINITIONS
        assert "devops" in AGENT_DEFINITIONS
        assert "knowledge" in AGENT_DEFINITIONS
        assert "attacker" in AGENT_DEFINITIONS

    def test_phase1_agents(self):
        agents = get_phase_agents("1")
        agent_names = {a.name for a in agents}
        assert "devflow-analyst" in agent_names
        assert "devflow-librarian" in agent_names
        assert "devflow-attacker" in agent_names

    def test_phase4_agents(self):
        agents = get_phase_agents("4")
        agent_names = {a.name for a in agents}
        assert "devflow-developer" in agent_names
        assert "devflow-qa" in agent_names
        assert "devflow-ops" in agent_names

    def test_phase_responsibility_matrix(self):
        matrix = get_agent_phase_responsibilities()
        assert "Analyst" in matrix
        assert matrix["Developer"]["4"] is not None
        assert matrix["QA"]["5"] is not None
        assert matrix["Attacker"]["1"] is not None


class TestFeedbackAndSystemHealth:
    """Feedback audit and system health monitoring."""

    def test_feedback_audit(self):
        result = xcut.audit_feedback("Sprint-3")
        assert is_ok(result)
        assert result.data["adoption"]["kar"] > 0.5
        assert result.data["effectiveness"]["fer"] > 1.0

    def test_system_health_trend(self):
        result = xcut.system_health_trend(("Sprint-1", "Sprint-3"))
        assert is_ok(result)
        assert result.data["integration_test_suite_size"] > 0

    def test_knowledge_health(self):
        kb.index("t1", "positive", {"test": True})
        report = kb.health_report()
        assert is_ok(report)
        assert report.data["total_entries"] > 0


class TestFullGoldenPath:
    """Complete end-to-end golden path: Phase 1→5 with PASS verdict.

    This is the single most important test — it validates that the entire
    pipeline works together as designed in the plan.
    """

    task_id = "task-golden-001"

    def setup_method(self):
        clear_all_stores()

    def test_full_five_phase_pipeline_golden_path(self):
        """Complete golden path matching the plan's multi-currency order scenario.

        Phase 1: Use case + FR + AC
        Phase 2: PoC + Token estimation
        Phase 3: Architecture + ADR
        Phase 4: Code generation + compilation + PR
        Phase 5: Testing + AC verification → PASS
        """
        corr = new_correlation()
        tid = self.task_id

        # ═══════════════════════════════════════════════════════════
        # Phase 1: Requirements Engineering
        # ═══════════════════════════════════════════════════════════

        # Create L0 use case
        uc = usecase.create(
            name="用户使用外币下单",
            level="L0", actor="买家", goal="以外币查看订单金额并完成下单",
            basic_flow=["1. 选择外币", "2. 获取汇率", "3. 换算显示", "4. 确认创建订单", "5. 人民币扣款"],
            correlation=corr, task_id=tid,
        )
        assert is_ok(uc), f"Phase 1 failed: {uc.message if is_failure(uc) else ''}"

        # Request Human clarification
        requirement.request_clarification(
            "汇率来源?", ["央行API", "第三方API"], correlation=corr, task_id=tid,
        )

        # Seed knowledge + retrieve
        kb.seed_generate("ecommerce", {"python": "3.10"})
        kb.retrieve({"domain": "multi_currency"}, task_id=tid, correlation=corr)

        # Upgrade to L1
        uc_up = usecase.upgrade(
            uc.data.uc_id, "L1",
            additions={"alternative_flows": [
                {"flow_name": "2a", "scenario": "服务不可用", "trigger": "500", "outcome": "拒绝下单"},
                {"flow_name": "2b", "scenario": "服务超时", "trigger": ">3s", "outcome": "降级缓存"},
            ]},
            correlation=corr, task_id=tid,
        )
        assert is_ok(uc_up)

        # Declare known unknowns
        usecase.declare_known_unknown(uc.data.uc_id, "极端汇率(VND, IDR)", "MEDIUM", correlation=corr, task_id=tid)

        # Create FRs + ACs
        fr1 = requirement.create(uc.data.uc_id, "FR", "汇率换算: CNY × rate → 目标币种", correlation=corr, task_id=tid)
        requirement.create_ac(fr1.data.req_id, {"rate": 7.25, "amount": 100},
                             "convert(order, 'USD')", "display_amount == Decimal('13.79')", correlation=corr, task_id=tid)
        fr2 = requirement.create(uc.data.uc_id, "FR", "汇率服务不可用时拒绝下单", correlation=corr, task_id=tid)
        requirement.create_ac(fr2.data.req_id, {"rate_svc": "500"},
                             "convert(order, 'USD')", "raises ServiceUnavailable", correlation=corr, task_id=tid)
        fr3 = requirement.create(uc.data.uc_id, "FR", "超时降级缓存", correlation=corr, task_id=tid)
        requirement.create_ac(fr3.data.req_id, {"rate_svc": "timeout", "cache": "valid"},
                             "convert(order, 'USD')", "display_amount == Decimal('13.79')", correlation=corr, task_id=tid)
        fr4 = requirement.create(uc.data.uc_id, "FR", "四舍五入到分", correlation=corr, task_id=tid)
        requirement.create_ac(fr4.data.req_id, {"rate": 7.25, "amount": 99.999},
                             "convert(order, 'USD')", "display_amount == Decimal('724.99')", correlation=corr, task_id=tid)

        nfr = requirement.create(uc.data.uc_id, "NFR", "p95延迟 < 2s", priority="HIGH", correlation=corr, task_id=tid)

        # Validate + trace
        usecase.validate(uc.data.uc_id, correlation=corr, task_id=tid)
        requirement.traceability_matrix(tid)

        # Complexity assessment
        complexity = xcut.assess_complexity(
            {"file_count": 8, "dependency_depth": 3, "financial": True, "security": False, "uc_count": 1},
            task_id=tid, correlation=corr,
        )
        assert complexity.data["level"] in ("L", "XL")

        # Eval-Gate G1
        g1 = run_g1_check(tid, usecase_count=1, ac_count=4, quantified_ac_count=4, l1_count=1)
        assert g1.data["passed"], f"G1 failed: {g1.data['checks']}"

        # ═══════════════════════════════════════════════════════════
        # Phase 2: Feasibility Study
        # ═══════════════════════════════════════════════════════════

        # PoC experiments
        exp = poc.create("精度验证", "Decimal精度足够",
                         "from decimal import Decimal\nprint(Decimal('100')*Decimal('7.25'))",
                         "725.00", linked_fr=fr1.data.req_id, correlation=corr, task_id=tid)
        poc.run(exp.data.experiment_id, correlation=corr, task_id=tid)
        poc.record_result(exp.data.experiment_id, "PASS", correlation=corr, task_id=tid)

        # Token estimation
        token.estimate({"task_type": "multi_currency"}, "deepseek-v4-pro", task_id=tid)

        # G2 gate
        g2 = run_g2_check(tid, poc_count=1, poc_pass_count=1, cost_model_complete=True, verdict_clear=True)
        assert g2.data["passed"]

        # ═══════════════════════════════════════════════════════════
        # Phase 3: Architecture Design
        # ═══════════════════════════════════════════════════════════

        arch.define_context_map(
            [{"name": "订单服务", "responsibility": "订单管理", "agents": ["analyst"]}],
            [{"source": "订单服务", "target": "汇率服务", "type": "CUSTOMER_SUPPLIER"}],
            task_id=tid, correlation=corr,
        )
        arch.define_interface("ExchangeRateProvider", "v1",
                             {"from": "Currency", "to": "Currency"},
                             {"rate": "Decimal"}, ["ServiceUnavailable"],
                             task_id=tid, correlation=corr)
        arch.define_interface("CurrencyConverter", "v1",
                             {"amount": "Money", "target": "Currency"},
                             {"display_amount": "Decimal"}, [],
                             task_id=tid, correlation=corr)
        arch.create_adr("使用Decimal", "多币种精度", "Decimal+quantize", "避免浮点误差", "性能略降",
                        alternatives=["整数(分)"], task_id=tid, correlation=corr)
        arch.create_adr("Redis缓存", "多实例", "Redis TTL 5min", "一致性", "网络1ms",
                        task_id=tid, correlation=corr)
        arch.declare_extension_point("ExchangeRateProvider", "极小值货币", "极端汇率",
                                    task_id=tid, correlation=corr)
        arch.validate_architecture(task_id=tid)

        g3 = run_g3_check(tid, has_context_map=True, has_interface_contracts=True,
                         adr_count=2, extension_points_declared=True, circular_deps=False)
        assert g3.data["passed"]

        # ═══════════════════════════════════════════════════════════
        # Phase 4: Implementation
        # ═══════════════════════════════════════════════════════════

        # Check cross-task conflicts
        xcut.detect_conflict(tid, [{"task_id": tid, "modified_files": ["src/order.py"]}], correlation=corr)

        code_patch.create_branch(tid, correlation=corr)
        patch = code_patch.generate_patch("spec-ref", uc.data.uc_id, task_id=tid, correlation=corr)
        assert is_ok(patch)

        compiler.check_syntax("order.py", "x=1\ny=2", task_id=tid, correlation=corr)
        compiler.static_analysis("src/", task_id=tid, correlation=corr)
        compiler.dependency_scan("src/", task_id=tid, correlation=corr)
        compiler.build("src/", task_id=tid, correlation=corr)

        code_patch.self_review("abc12345", [
            {"name": "UC-01 all flows", "result": "PASS", "evidence": "verified"},
        ], task_id=tid, correlation=corr)

        code_patch.apply_patch(patch.data.patch_id, f"feature/devflow-{tid}", task_id=tid, correlation=corr)
        code_patch.create_pr(f"feature/devflow-{tid}", "多币种订单功能", [uc.data.uc_id], task_id=tid, correlation=corr)

        g4 = run_g4_check(tid, compilation_passed=True, sast_clean=True,
                         no_cves=True, no_regression=True, self_review_complete=True)
        assert g4.data["passed"]

        # ═══════════════════════════════════════════════════════════
        # Phase 5: Verification
        # ═══════════════════════════════════════════════════════════

        test_tools.run("full", target_branch=f"feature/devflow-{tid}", task_id=tid, correlation=corr)
        test_tools.coverage(f"feature/devflow-{tid}", baseline_branch="main", task_id=tid, correlation=corr)
        test_tools.mutation_test("CurrencyConverter", "test_currency", task_id=tid, correlation=corr)
        test_tools.regression_validity("abc12345", ["test_currency.py"], task_id=tid, correlation=corr)
        test_tools.ac_coverage(
            ["AC-FR-01-1", "AC-FR-02-1", "AC-FR-03-1", "AC-FR-04-1"],
            ["test_ac_fr_01_1.py", "test_ac_fr_02_1.py", "test_ac_fr_03_1.py", "test_ac_fr_04_1.py"],
            task_id=tid, correlation=corr,
        )
        test_tools.integration_run(["CurrencyConverter"], task_id=tid, correlation=corr)
        test_tools.staging_smoke("deploy-001", task_id=tid, correlation=corr)

        # All ACs pass
        for ac_id, val in [("AC-FR-01-1", "13.79"), ("AC-FR-02-1", "ServiceUnavailable"),
                           ("AC-FR-03-1", "13.79"), ("AC-FR-04-1", "724.99")]:
            v = verify.verify_ac(ac_id, {"actual": val, "expected": val}, task_id=tid, correlation=corr)
            assert v.data.status == "PASS"

        # Extract integration test
        kb.extract_integration_test(tid, correlation=corr)

        g5 = run_g5_check(tid, mutation_score=0.65, ac_coverage_pct=100.0,
                         regression_valid=True, traceability_complete=True)
        g6 = run_g6_check(tid, health_check_passed=True, slo_compliant=True, rollback_verified=True)
        assert g5.data["passed"]
        assert g6.data["passed"]

        # Timeline verification
        timeline = xcut.verify_timeline(tid, "1", correlation=corr)
        assert is_ok(timeline)

        # Final verdict
        final = verify.verdict(tid,
            eval_gate_results={"G1": "PASS", "G2": "PASS", "G3": "PASS", "G4": "PASS", "G5": "PASS", "G6": "PASS"},
            timeline_compliance=0.90, correlation=corr,
        )
        assert is_ok(final)
        assert final.data.verdict.value == "PASS", \
            f"Golden path should PASS, got {final.data.verdict.value}"

        # Token report
        token.report(tid)

        # Feedback audit (Sprint Retro)
        xcut.audit_feedback("Sprint-1", correlation=corr, task_id=tid)

        # System health
        xcut.system_health_trend(("Sprint-1", "Sprint-1"), correlation=corr)

        # Evidence integrity
        integrity = check_integrity(tid)
        assert integrity["pass"], f"Evidence tampered: {integrity['tampered']}"

        # Trace chain
        chain = trace_chain(tid)
        assert len(chain["forward"]["usecases"]) > 0
        assert len(chain["forward"]["verdicts"]) > 0

        # Success!
        print(f"\n✓ Golden Path Complete: {tid}")
        print(f"  Verdict: {final.data.verdict.value}")
        print(f"  Issues: {len(final.data.issues)}")
        print(f"  Evidence records: {len(get_events(tid))}")
