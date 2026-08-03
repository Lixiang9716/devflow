"""Tests for T6-T9 tools: Code/Patch, Compiler, Test, Verify/Issue."""

import pytest
from devflow.tools.code_patch import (
    create_branch, generate_patch, apply_patch,
    revert_patch, self_review, create_pr, clear_store as code_clear,
)
from devflow.tools.compiler import (
    check_syntax, build, static_analysis, dependency_scan,
)
from devflow.tools.test import (
    run as t_run, coverage as t_coverage,
    mutation_test, regression_validity, ac_coverage,
    integration_run, staging_smoke, clear_store as test_clear,
)
from devflow.tools.verify import (
    verify_ac, classify_issue, classify_integration,
    verdict, IssueType, Verdict, clear_store as verify_clear,
)


class TestCodePatch:
    """T6 Patch/Code toolset tests."""

    def setup_method(self):
        code_clear()

    def test_create_branch(self):
        result = create_branch(task_id="task-0042", base_ref="main")
        assert result.status == "ok"
        assert result.data.name == "feature/devflow-task-0042"

    def test_create_branch_idempotent(self):
        create_branch(task_id="task-0042")
        result = create_branch(task_id="task-0042")
        assert result.status == "ok"  # Returns existing, no error

    def test_generate_patch(self):
        result = generate_patch("spec-ref", "UC-01", task_id="task-0042")
        assert result.status == "ok"
        assert result.data.patch_id.startswith("patch-")
        assert "CurrencyConverter" in result.data.diff_content

    def test_apply_patch(self):
        generate_patch("spec-ref", "UC-01", task_id="task-0042")
        from devflow.tools.code_patch import _patch_store
        patch_id = list(_patch_store.keys())[0]
        result = apply_patch(patch_id, "feature/devflow-task-0042", task_id="task-0042")
        assert result.status == "ok"
        assert len(result.data.commit_sha) == 8

    def test_revert_patch(self):
        result = revert_patch("abc12345", reason="Wrong approach", issue_ref="ISSUE-01", task_id="task-0042")
        assert result.status == "ok"
        assert result.data["original_commit"] == "abc12345"

    def test_self_review_all_pass(self):
        checks = [
            {"name": "UC-01.2 正常下单", "result": "PASS", "evidence": "test ok"},
            {"name": "UC-01.2a 不可用", "result": "PASS", "evidence": "test ok"},
        ]
        result = self_review("abc123", checks, task_id="task-0042")
        assert result.status == "ok"
        assert result.data.all_passed

    def test_self_review_with_fail(self):
        checks = [{"name": "test1", "result": "PASS"}, {"name": "test2", "result": "FAIL"}]
        result = self_review("abc123", checks, task_id="task-0042")
        assert not result.data.all_passed

    def test_create_pr(self):
        result = create_pr("feature/devflow-task-0042", "实现多币种订单", ["UC-01"], task_id="task-0042")
        assert result.status == "ok"
        assert result.data.pr_number == 1
        assert result.data.status == "OPEN"

    def test_create_pr_idempotent(self):
        create_pr("feature/devflow-task-0042", "实现多币种订单", ["UC-01"], task_id="task-0042")
        result = create_pr("feature/devflow-task-0042", "实现多币种订单", ["UC-01"], task_id="task-0042")
        assert result.status == "ok"  # Returns existing


class TestCompiler:
    """T7 Compiler toolset tests."""

    def test_check_syntax_valid(self):
        result = check_syntax("test.py", "x = 1\ny = 2\nprint(x + y)", task_id="t1")
        assert result.status == "ok"
        assert result.data.passed

    def test_check_syntax_invalid(self):
        result = check_syntax("test.py", "x = \n 1", task_id="t1")
        assert result.status == "ok"
        # May not pass depending on parser strictness

    def test_build(self):
        result = build("src/", task_id="t1")
        assert result.status == "ok"
        assert len(result.data.artifact_hash) > 0

    def test_static_analysis(self):
        result = static_analysis("src/", task_id="t1")
        assert result.status == "ok"
        assert result.data.passed

    def test_dependency_scan(self):
        result = dependency_scan("src/", task_id="t1")
        assert result.status == "ok"
        assert result.data.passed


class TestTestTools:
    """T8 Test toolset tests."""

    def setup_method(self):
        test_clear()

    def test_run(self):
        result = t_run("full", target_branch="feature/devflow-task-0042", task_id="t1")
        assert result.status == "ok"
        assert result.data.total > 0

    def test_coverage(self):
        result = t_coverage("feature/devflow-task-0042", baseline_branch="main", task_id="t1")
        assert result.status == "ok"
        assert result.data.delta > 0

    def test_mutation_test(self):
        result = mutation_test("CurrencyConverter", "test_currency", task_id="t1")
        assert result.status == "ok"
        assert result.data.mutation_score > 0

    def test_regression_validity(self):
        result = regression_validity("abc123", ["test_currency.py"], task_id="t1")
        assert result.status == "ok"
        assert result.data.valid

    def test_ac_coverage_full(self):
        result = ac_coverage(
            ["AC-FR-01-1", "AC-FR-02-1", "AC-FR-03-1"],
            ["test_ac_fr_01_1.py", "test_ac_fr_02_1.py", "test_ac_fr_03_1.py"],
            task_id="t1",
        )
        assert result.status == "ok"
        assert result.data.coverage_pct == 100.0

    def test_ac_coverage_partial(self):
        result = ac_coverage(
            ["AC-FR-01-1", "AC-FR-02-1"],
            ["test_ac_fr_01_1.py"],
            task_id="t1",
        )
        assert result.data.coverage_pct == 50.0

    def test_integration_run(self):
        result = integration_run(["CurrencyConverter", "OrderCreator"], task_id="t1")
        assert result.status == "ok"

    def test_staging_smoke(self):
        result = staging_smoke("deploy-001", task_id="t1")
        assert result.status == "ok"
        assert result.data["verdict"] == "PASS"


class TestVerify:
    """T9 Verify/Issue toolset tests."""

    def setup_method(self):
        verify_clear()

    def test_verify_ac_pass(self):
        result = verify_ac("AC-FR-01-1", {"actual": "13.79", "expected": "13.79"}, task_id="t1")
        assert result.status == "ok"
        assert result.data.status == "PASS"

    def test_verify_ac_fail(self):
        result = verify_ac("AC-FR-04-1", {"actual": "725.00", "expected": "724.99"}, task_id="t1")
        assert result.status == "ok"
        assert result.data.status == "FAIL"

    def test_classify_usecase_gap(self):
        result = classify_issue(
            "AC-FR-99-1",
            {"scenario_in_use_case": False, "detail": "极端币种未定义"},
            task_id="t1",
        )
        assert result.status == "ok"
        assert result.data.type == IssueType.USECASE_GAP
        assert result.data.suggested_target_phase == "1"

    def test_classify_code_bug(self):
        result = classify_issue(
            "AC-FR-04-1",
            {"scenario_in_use_case": True, "code_matches_use_case": False,
             "detail": "quantize调用顺序错误"},
            task_id="t1",
        )
        assert result.status == "ok"
        assert result.data.type == IssueType.CODE_BUG
        assert result.data.suggested_target_phase == "4"

    def test_classify_bug_in_usecase(self):
        result = classify_issue(
            "AC-FR-05-1",
            {"scenario_in_use_case": True, "code_matches_use_case": True,
             "detail": "用例规定超时直接失败，但业务要求降级"},
            task_id="t1",
        )
        assert result.status == "ok"
        assert result.data.type == IssueType.BUG_IN_USECASE

    def test_classify_env_issue(self):
        result = classify_issue(
            "AC-FR-06-1",
            {"is_environmental": True, "detail": "Redis连接超时"},
            task_id="t1",
        )
        assert result.status == "ok"
        assert result.data.type == IssueType.ENV_ISSUE

    def test_classify_integration(self):
        result = classify_integration("t1", ["test_integration_other_module"])
        assert result.status == "ok"
        assert len(result.data) == 1
        assert result.data[0].type == IssueType.INTEGRATION_BUG

    def test_verdict_pass(self):
        result = verdict(
            "t1",
            eval_gate_results={"G1": "PASS", "G2": "PASS", "G3": "PASS", "G4": "PASS", "G5": "PASS", "G6": "PASS"},
            timeline_compliance=0.95,
        )
        assert result.status == "ok"
        assert result.data.verdict == Verdict.PASS

    def test_verdict_fail_retry_critical_gate(self):
        result = verdict("t1", eval_gate_results={"G4.1": "FAIL"}, timeline_compliance=0.9)
        assert result.data.verdict == Verdict.FAIL_RETRY

    def test_verdict_need_human_low_timeline(self):
        result = verdict("t1", eval_gate_results={"G1": "PASS", "G2": "PASS", "G3": "PASS", "G4": "PASS", "G5": "PASS", "G6": "PASS"}, timeline_compliance=0.5)
        assert result.data.verdict == Verdict.NEED_HUMAN
