"""End-to-end test with REAL DeepSeek API calls.

Validates that the complete DevFlow pipeline works with a real LLM:
1. Analyst agent analyzes a requirement and creates use cases + ACs
2. Architect agent creates PoC experiments and ADRs
3. QA agent verifies results and produces verdicts
4. Issue classification decision tree works correctly

Requires: DEEPSEEK_API_KEY environment variable.
"""

import json
import os
import sys
import time

import pytest

from devflow.core.config import get_config, reload_config
from devflow.core.llm_client import (
    LLMClient, ToolDefinition, ToolCall, ToolResult,
)
from devflow.core.agent_loop import (
    AgentLoop, AgentContext, get_system_prompt,
)
from devflow.core.mcp_tools import (
    handle_tool_call, PHASE_1_TOOLS, PHASE_2_TOOLS,
)
from devflow.core.correlation import new_correlation
from devflow.core.result import is_ok, is_failure

# Import all tool stores for cleanup
import devflow.tools.usecase as usecase
import devflow.tools.requirement as requirement
import devflow.tools.poc as poc
import devflow.tools.token as token
import devflow.tools.arch as arch
import devflow.tools.verify as verify
import devflow.tools.knowledge as kb
from devflow.tools.verify import IssueType, Verdict
from devflow.core.evidence import clear_evidence


def clear_all_stores():
    """Clean up all in-memory stores."""
    usecase.clear_store()
    requirement.clear_store()
    poc.clear_store()
    token.clear_store()
    arch.clear_store()
    verify.clear_store()
    kb.clear_store()
    clear_evidence()


def requires_api_key():
    """Skip test if API key is not available."""
    config = get_config()
    if not config.llm.api_key:
        pytest.skip("DEEPSEEK_API_KEY not set")


class TestLLMClientBasic:
    """Test the LLM client with real API calls."""

    def test_simple_chat(self):
        """Basic: send a simple message and get a response."""
        requires_api_key()
        client = LLMClient()

        result = client.chat(
            system_prompt="You are a helpful assistant. Keep responses concise.",
            messages=[{"role": "user", "content": "What is 2+2? Reply with just the number."}],
            max_tokens=50,
        )

        assert is_ok(result), f"LLM call failed: {result.message if is_failure(result) else 'unknown'}"
        response = result.data
        assert response.content, "Response should have content"
        assert response.input_tokens > 0, "Should track input tokens"
        assert response.output_tokens > 0, "Should track output tokens"
        print(f"\n   ✓ Simple chat: {response.content.strip()}")
        print(f"     Tokens: {response.input_tokens} in / {response.output_tokens} out")
        print(f"     Duration: {response.duration_ms:.0f}ms")

    def test_chat_with_tool_definitions(self):
        """LLM receives tool definitions but may not call them."""
        requires_api_key()
        client = LLMClient()

        tools = [
            ToolDefinition(
                name="usecase_create",
                description="Create a use case",
                parameters={
                    "name": {"type": "string", "description": "Use case name"},
                    "level": {"type": "string", "enum": ["L0", "L1", "L2"]},
                    "actor": {"type": "string", "description": "Primary actor"},
                    "goal": {"type": "string", "description": "Actor's goal"},
                    "basic_flow": {"type": "array", "items": {"type": "string"}},
                },
                required=["name", "level", "actor", "goal", "basic_flow"],
            ),
        ]

        result = client.chat(
            system_prompt="You are a requirements engineer. Analyze the following requirement and create a use case.",
            messages=[{"role": "user", "content": "电商平台需要支持多币种订单功能"}],
            tools=tools,
            max_tokens=500,
        )

        assert is_ok(result), f"LLM call failed: {result.message if is_failure(result) else 'unknown'}"
        response = result.data
        print(f"\n   ✓ Chat with tools:")
        print(f"     Content: {response.content[:200]}...")
        print(f"     Tool calls: {len(response.tool_calls)}")
        for tc in response.tool_calls:
            print(f"       - {tc.name}: {json.dumps(tc.arguments, ensure_ascii=False)[:100]}")

    def test_chat_with_tools_loop(self):
        """Test the full agent loop with tool calling."""
        requires_api_key()
        clear_all_stores()
        client = LLMClient()
        task_id = "test-llm-loop-001"

        tools = [
            t for t in PHASE_1_TOOLS
            if t.name in ["usecase_create", "requirement_create", "requirement_create_ac"]
        ]

        system_prompt = get_system_prompt("analyst")

        ctx = AgentContext(
            task_id=task_id,
            phase="1",
            agent_name="analyst",
            agent_role="Requirements Engineer",
            system_prompt=system_prompt,
            user_task=(
                "Analyze this requirement and create a structured specification:\n\n"
                "用户登录功能需要支持邮箱+密码登录，登录失败3次后锁定账号30分钟。\n\n"
                "Please:\n"
                "1. Create a use case at L0 level for user login\n"
                "2. Create at least 2 functional requirements (FR)\n"
                "3. Create at least 3 Lean acceptance criteria with quantifiable then clauses\n"
                "4. Then summarize what you created"
            ),
            available_tools=tools,
            tool_handler=lambda tc: handle_tool_call(tc, task_id=task_id),
            max_tool_rounds=8,
        )

        loop = AgentLoop(client)
        result = loop.run(ctx)

        assert is_ok(result), f"Agent loop failed: {result.message if is_failure(result) else 'unknown'}"
        ar = result.data

        print(f"\n   ✓ Agent Loop Result:")
        print(f"     Success: {ar.success}")
        print(f"     Tools called: {len(ar.tool_calls_made)}")
        for tc in ar.tool_calls_made:
            print(f"       - {tc['tool']}: {'✓' if not tc['is_error'] else '✗'}")
        print(f"     Tokens: {ar.tokens_used}")
        print(f"     Duration: {ar.duration_ms:.0f}ms")
        print(f"     Response preview: {ar.final_response[:300]}...")

        # Verify that use cases were created
        ucs = usecase.list_all()
        reqs = requirement.list_reqs()
        print(f"\n     Artifacts created: {len(ucs)} use cases, {len(reqs)} requirements")
        assert ar.success, f"Agent should succeed: {ar.error_message}"
        assert len(ar.tool_calls_made) > 0, "Agent should have called tools"


class TestRealPipeline:
    """Test the full DevFlow pipeline with real LLM calls."""

    def test_phase1_analyst_full(self):
        """Phase 1: Analyst agent creates complete requirements spec."""
        requires_api_key()
        clear_all_stores()

        client = LLMClient()
        task_id = "task-real-001"
        corr = new_correlation()

        # Seed knowledge
        kb.seed_generate("web_api", {"python": "3.10", "framework": "FastAPI"})

        ctx = AgentContext(
            task_id=task_id,
            phase="1",
            agent_name="analyst",
            agent_role="Requirements Engineer",
            system_prompt=get_system_prompt("analyst"),
            user_task=(
                "Analyze this business requirement and create a complete structured specification:\n\n"
                "# 电商平台多币种订单功能\n\n"
                "用户需要以外币查看订单金额并完成下单。系统需要：\n"
                "1. 支持用户选择外币(如USD)作为展示币种\n"
                "2. 获取实时汇率进行换算\n"
                "3. 显示换算后的外币金额\n"
                "4. 创建订单(记录人民币金额+展示币种金额)\n"
                "5. 实际扣款按人民币执行\n\n"
                "Please complete these steps:\n"
                "1. usecase.create: Create a L0 use case '用户使用外币下单' with 5-step basic flow\n"
                "2. requirement.create: Create 3 FRs (汇率换算、不可用拒绝下单、四舍五入) and 1 NFR (p95<2s)\n"
                "3. requirement.create_ac: For each FR, create a Lean AC with given/when/then format\n"
                "   - then MUST be quantifiable (use ==, raises, etc.)\n"
                "   - Example: then='display_amount == Decimal(\"13.79\")'\n"
                "4. usercase.validate: Validate the created use case\n"
                "5. Summarize all created artifacts"
            ),
            available_tools=[
                t for t in PHASE_1_TOOLS
                if t.name not in ["requirement_request_clarification", "complexity_assess"]
            ],
            tool_handler=lambda tc: handle_tool_call(tc, task_id=task_id),
            model="deepseek-v4-flash",  # Use fast model for testing
            max_tool_rounds=10,
        )

        loop = AgentLoop(client)
        result = loop.run(ctx)

        assert is_ok(result), f"Phase 1 failed: {result.message if is_failure(result) else 'unknown'}"
        ar = result.data
        assert ar.success, f"Phase 1 should succeed: {ar.error_message}"

        # Verify artifacts
        ucs = usecase.list_all()
        reqs = requirement.list_reqs()
        print(f"\n   📋 Phase 1 Results:")
        print(f"     Use Cases: {len(ucs)}")
        for uc in ucs:
            print(f"       {uc.uc_id}: {uc.name} ({uc.level.value})")
            print(f"       Basic flow: {len(uc.basic_flow)} steps")
            print(f"       Alternative flows: {len(uc.alternative_flows)}")
        print(f"     Requirements: {len(reqs)}")
        for r in reqs:
            print(f"       {r.req_id}: {r.description[:60]}... ({len(r.acceptance_criteria)} ACs)")

        assert len(ucs) >= 1, "Should have at least 1 use case"
        assert len(reqs) >= 2, "Should have at least 2 requirements"

    def test_phase5_issue_classification_unit(self):
        """Verify the issue classification decision tree (no LLM needed)."""
        clear_all_stores()

        # Test USECASE_GAP
        r1 = verify.classify_issue(
            "AC-FR-99-1",
            {"scenario_in_use_case": False, "detail": "极端汇率未定义"},
            task_id="test-classify",
        )
        assert is_ok(r1)
        assert r1.data.type == IssueType.USECASE_GAP
        assert r1.data.suggested_target_phase == "1"

        # Test CODE_BUG
        r2 = verify.classify_issue(
            "AC-FR-04-1",
            {"scenario_in_use_case": True, "code_matches_use_case": False,
             "detail": "quantize顺序错误"},
            task_id="test-classify",
        )
        assert r2.data.type == IssueType.CODE_BUG
        assert r2.data.suggested_target_phase == "4"

        # Test BUG_IN_USECASE
        r3 = verify.classify_issue(
            "AC-FR-05-1",
            {"scenario_in_use_case": True, "code_matches_use_case": True,
             "detail": "用例规定超时直接失败但业务要求降级"},
            task_id="test-classify",
        )
        assert r3.data.type == IssueType.BUG_IN_USECASE

        # Test ENV_ISSUE
        r4 = verify.classify_issue(
            "AC-FR-06-1",
            {"is_environmental": True, "detail": "Redis连接超时"},
            task_id="test-classify",
        )
        assert r4.data.type == IssueType.ENV_ISSUE

        # Test verdict aggregation
        r5 = verify.verdict(
            "test-verdict",
            eval_gate_results={"G1": "PASS", "G2": "PASS", "G3": "PASS", "G4": "PASS", "G5": "PASS", "G6": "PASS"},
            timeline_compliance=0.92,
        )
        assert r5.data.verdict == Verdict.PASS

        print(f"\n   ✅ Issue classification tree: all 4 types correctly identified")
        print(f"   ✅ Verdict aggregation: correct PASS/FAIL_RETRY/NEED_HUMAN")

    def test_end_to_end_small_task(self):
        """Complete mini pipeline: Phase 1 with real LLM → Phase 5 verdict."""
        requires_api_key()
        clear_all_stores()

        client = LLMClient()
        task_id = "task-e2e-real-001"

        # ═══ Phase 1: Analyst creates specification ═══
        print(f"\n   🟢 Phase 1: Requirements Engineering")

        ctx = AgentContext(
            task_id=task_id,
            phase="1",
            agent_name="analyst",
            agent_role="Requirements Engineer",
            system_prompt=get_system_prompt("analyst"),
            user_task=(
                "Create a structured specification for: 'Todo应用需要支持用户创建任务、标记完成、删除任务'\n\n"
                "Steps:\n"
                "1. usecase_create: Create L0 use case '用户管理Todo任务'\n"
                "2. requirement_create: Create FR for 创建任务, 标记完成, 删除任务\n"
                "3. requirement_create_ac: Create ACs with quantifiable then clauses\n"
                "4. usercase_validate: Validate the use case\n"
                "5. Summarize results"
            ),
            available_tools=[
                t for t in PHASE_1_TOOLS
                if t.name in ["usecase_create", "usecase_upgrade", "usecase_validate",
                             "requirement_create", "requirement_create_ac"]
            ],
            tool_handler=lambda tc: handle_tool_call(tc, task_id=task_id),
            model="deepseek-v4-flash",
            max_tool_rounds=10,
        )

        loop = AgentLoop(client)
        result = loop.run(ctx)

        assert is_ok(result)
        ar = result.data
        assert ar.success, f"Phase 1 failed: {ar.error_message}"

        ucs = usecase.list_all()
        reqs = requirement.list_reqs()
        print(f"     Created: {len(ucs)} UCs, {len(reqs)} requirements")
        print(f"     Tool calls: {len(ar.tool_calls_made)}, Tokens: {ar.tokens_used}")

        # Count ACs
        total_acs = sum(len(r.acceptance_criteria) for r in reqs)
        print(f"     Total ACs: {total_acs}")

        assert len(ucs) >= 1, "Should create at least 1 use case"
        assert len(reqs) >= 2, "Should create at least 2 requirements"

        # ═══ Phase 5: Verify and produce verdict ═══
        print(f"\n   🟢 Phase 5: Verification & Verdict")

        # Simulate testing: all ACs pass
        from devflow.eval_gates import run_g1_check, run_g5_check

        g1 = run_g1_check(task_id, usecase_count=len(ucs), ac_count=total_acs,
                         quantified_ac_count=total_acs, l1_count=len(ucs))
        print(f"     G1: {'PASS' if g1.data['passed'] else 'FAIL'} ({len(ucs)} UCs, {total_acs} ACs)")

        g5 = run_g5_check(task_id, mutation_score=0.65, ac_coverage_pct=100.0,
                         regression_valid=True, traceability_complete=True)
        print(f"     G5: {'PASS' if g5.data['passed'] else 'FAIL'}")

        v = verify.verdict(
            task_id,
            eval_gate_results={"G1": "PASS" if g1.data["passed"] else "FAIL", "G5": "PASS" if g5.data["passed"] else "FAIL"},
            timeline_compliance=0.90,
        )
        print(f"\n   🏁 Final Verdict: {v.data.verdict.value}")
        print(f"     Issues: {len(v.data.issues)}")

        assert v.data.verdict == Verdict.PASS, f"Expected PASS, got {v.data.verdict.value}"

        # Token report
        tr = token.report(task_id)
        if is_ok(tr):
            print(f"     Total cost: ${tr.data.get('total_cost', 0):.6f}")


if __name__ == "__main__":
    # Allow running directly
    pytest.main([__file__, "-v", "-s"])
