"""Agent Execution Loop — the runtime that powers each DevFlow agent.

Each agent runs: receive task context → call LLM with tool definitions →
parse tool calls → execute tools → feed results back → iterate → produce Result.

This is the core "Agent reasons, tools execute" loop from the plan.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Optional, Callable, Any

from devflow.core.config import get_config
from devflow.core.llm_client import (
    LLMClient, get_llm_client, ToolDefinition, ToolCall, ToolResult, LLMResponse,
)
from devflow.core.result import Result, ok, retryable, permanent, need_human, is_ok
from devflow.core.correlation import CorrelationId, new_correlation
from devflow.core.evidence import write_evidence
from devflow.tools.token import record_call as token_record


@dataclass
class AgentContext:
    """Context passed to an agent for execution."""

    task_id: str
    phase: str
    agent_name: str
    agent_role: str
    system_prompt: str
    user_task: str
    available_tools: list[ToolDefinition] = field(default_factory=list)
    tool_handler: Optional[Callable[[ToolCall], ToolResult]] = None
    correlation: Optional[CorrelationId] = None
    max_tool_rounds: int = 5
    model: Optional[str] = None

    # Knowledge context (from T11)
    positive_context: list[dict] = field(default_factory=list)
    negative_context: list[dict] = field(default_factory=list)


@dataclass
class AgentRunResult:
    """Result of an agent execution run."""

    agent_name: str
    phase: str
    task_id: str
    final_response: str
    tool_calls_made: list[dict] = field(default_factory=list)
    tokens_used: int = 0
    duration_ms: float = 0.0
    success: bool = True
    error_message: str = ""


class AgentLoop:
    """Executes a single agent run: LLM reasoning + tool calling loop.

    Usage:
        loop = AgentLoop()
        result = loop.run(AgentContext(
            task_id="task-001", phase="1", agent_name="analyst",
            agent_role="Requirements Engineer",
            system_prompt=ANALYST_SYSTEM_PROMPT,
            user_task="Analyze: 电商需要多币种订单功能",
            available_tools=[usecase_create_tool, requirement_create_tool, ...],
            tool_handler=my_tool_handler,
        ))
    """

    def __init__(self, client: Optional[LLMClient] = None):
        self.client = client or get_llm_client()

    def run(self, ctx: AgentContext) -> Result[AgentRunResult]:
        """Execute the agent loop.

        1. Build enriched system prompt with knowledge context
        2. Enter chat_with_tools_loop
        3. LLM reasons → may call tools → tool results fed back
        4. LLM produces final answer
        5. Record evidence + tokens
        """
        start_time = time.time()
        tool_calls_log = []
        corr = ctx.correlation or new_correlation()

        # Enrich system prompt with knowledge context
        enriched_prompt = self._build_enriched_prompt(ctx)

        # Define the tool handler wrapper that logs calls
        def wrapped_tool_handler(tc: ToolCall) -> ToolResult:
            if ctx.tool_handler:
                result = ctx.tool_handler(tc)
            else:
                result = ToolResult(
                    tool_call_id=tc.id,
                    name=tc.name,
                    content=json.dumps({"error": "No tool handler configured"}),
                    is_error=True,
                )
            tool_calls_log.append({
                "tool": tc.name,
                "arguments": tc.arguments,
                "result": result.content[:500],
                "is_error": result.is_error,
            })
            return result

        # Execute the LLM + tools loop
        llm_result = self.client.chat_with_tools_loop(
            system_prompt=enriched_prompt,
            user_message=ctx.user_task,
            tools=ctx.available_tools,
            tool_handler=wrapped_tool_handler,
            model=ctx.model,
            correlation=corr,
            max_tool_rounds=ctx.max_tool_rounds,
        )

        duration_ms = (time.time() - start_time) * 1000

        if not is_ok(llm_result):
            # Track failed token usage if available
            agent_result = AgentRunResult(
                agent_name=ctx.agent_name,
                phase=ctx.phase,
                task_id=ctx.task_id,
                final_response=llm_result.message if hasattr(llm_result, 'message') else str(llm_result),
                tool_calls_made=tool_calls_log,
                duration_ms=duration_ms,
                success=False,
                error_message=llm_result.message if hasattr(llm_result, 'message') else "LLM call failed",
            )
            write_evidence(
                task_id=ctx.task_id, phase=ctx.phase,
                step=f"{ctx.agent_name}.run",
                content={"success": False, "tool_calls": len(tool_calls_log)},
                tool_name=f"agent.{ctx.agent_name}", correlation=corr,
            )
            return ok(agent_result)  # Return the result even on LLM failure

        response = llm_result.data

        # Record token usage
        if response.input_tokens > 0 or response.output_tokens > 0:
            token_record(
                agent=ctx.agent_name,
                phase=ctx.phase,
                model=response.model,
                input_tokens=response.input_tokens,
                output_tokens=response.output_tokens,
                correlation=corr,
                task_id=ctx.task_id,
            )

        agent_result = AgentRunResult(
            agent_name=ctx.agent_name,
            phase=ctx.phase,
            task_id=ctx.task_id,
            final_response=response.content,
            tool_calls_made=tool_calls_log,
            tokens_used=response.input_tokens + response.output_tokens,
            duration_ms=duration_ms,
            success=True,
        )

        # Write evidence
        write_evidence(
            task_id=ctx.task_id, phase=ctx.phase,
            step=f"{ctx.agent_name}.run",
            content={
                "success": True,
                "tool_calls": len(tool_calls_log),
                "tokens": agent_result.tokens_used,
                "duration_ms": duration_ms,
            },
            tool_name=f"agent.{ctx.agent_name}", correlation=corr,
        )

        return ok(agent_result)

    def _build_enriched_prompt(self, ctx: AgentContext) -> str:
        """Enrich the system prompt with knowledge context."""
        parts = [ctx.system_prompt]

        if ctx.positive_context:
            parts.append("\n## Positive Knowledge (successful patterns from history)")
            for item in ctx.positive_context:
                content = item.get("content", item)
                parts.append(f"- {json.dumps(content, ensure_ascii=False, default=str)}")

        if ctx.negative_context:
            parts.append("\n## Negative Knowledge (known mistakes to avoid)")
            for item in ctx.negative_context:
                content = item.get("content", item)
                parts.append(f"- ⚠️ {json.dumps(content, ensure_ascii=False, default=str)}")

        return "\n".join(parts)


# ── Pre-defined Agent System Prompts ────────────────────────────

ANALYST_SYSTEM_PROMPT = """You are a Requirements Engineer / Business Analyst for a structured software engineering system called DevFlow.

Your job in Phase 1 is to:
1. Analyze the user's natural language requirement
2. Create use cases (L0 → L1 format) using the usecase.create tool
3. If there are ambiguities, use requirement.request_clarification to ask the human
4. Create functional requirements (FR) and non-functional requirements (NFR) using requirement.create
5. For each FR, create Lean acceptance criteria using requirement.create_ac
   - AC format: {given: {...}, when: "action", then: "quantifiable assertion"}
   - then MUST be quantifiable (contain ==, <, >, in, matches, raises, etc.)
   - NO fuzzy words: 正常, 正确, 合理, should, maybe
6. Upgrade use cases to L1 when you have enough information
7. Validate use cases with usecase.validate
8. Generate the traceability matrix

Always follow Lean AC rules: one assertion per AC, quantifiable then clause, test code auto-generated by tool.

When you're done, summarize what you've created and the key design decisions."""

ARCHITECT_SYSTEM_PROMPT = """You are a Software Architect for DevFlow.

In Phase 2 (Feasibility):
1. Create PoC experiments to validate key technical risks using poc.create
2. Run PoC experiments with poc.run
3. Record conclusions (PASS/FAIL/INCONCLUSIVE)
4. Estimate token costs with token.estimate

In Phase 3 (Architecture Design):
1. Define the system context map with bounded contexts and relationships
2. Define interface contracts with inputs, outputs, and error types
3. Create Architecture Decision Records (ADR) for every non-trivial decision
4. Declare extension points for known unknowns
5. Validate the architecture (no circular dependencies, etc.)

Follow the top-down design approach: Context → Containers → Components → Interfaces → Data Model."""

DEVELOPER_SYSTEM_PROMPT = """You are a Software Developer for DevFlow.

In Phase 4 (Implementation):
1. Create a feature branch with code.create_branch
2. Generate code patches with code.generate_patch
3. BEFORE applying, check syntax with compiler.check_syntax
4. Run static analysis with compiler.static_analysis
5. Self-review your changes with code.self_review
6. Apply the patch with code.apply_patch
7. Create a PR with code.create_pr

In Phase 5 (Bug Fixes):
1. When QA finds a CODE_BUG, revert the patch with code.revert_patch
2. Generate a new corrected patch
3. Follow the same compilation and review process

Always implement exception paths first, then the happy path.
Each component is one commit. Link each commit to its use case."""

QA_SYSTEM_PROMPT = """You are a QA Engineer / Test Auditor for DevFlow.

In Phase 4:
1. Review code independently against acceptance criteria

In Phase 5 (Verification):
1. Run the test suite with test.run
2. Measure coverage with test.coverage
3. Run mutation testing with test.mutation_test
4. Verify regression test validity with test.regression_validity
5. Check AC coverage with test.ac_coverage
6. Verify each AC one by one with verify.ac
7. For any FAIL, classify the issue with verify.classify_issue
8. Run integration tests with test.integration_run
9. Produce the final verdict with verify.verdict

Key principle: you are INDEPENDENT from the Developer agent.
You verify their work, not trust it."""

KNOWLEDGE_SYSTEM_PROMPT = """You are a Knowledge Manager for DevFlow.

Your job spans all phases:
1. Retrieve relevant knowledge before each phase starts with kb.retrieve
2. Index new knowledge after task completion with kb.index
3. Mark stale entries with kb.mark_stale
4. Detect contradictions between positive and negative indices
5. Extract integration tests from completed tasks with kb.extract_integration_test
6. Generate seed knowledge for cold-start scenarios
7. Run periodic health reports with kb.health_report

Dual-channel approach:
- Positive index: patterns that WORKED (successful patterns, templates)
- Negative index: patterns that FAILED (known mistakes, anti-patterns)

Always provide context to agents before they start work."""

ATTACKER_SYSTEM_PROMPT = """You are an Adversarial Tester for DevFlow.

Your ONLY job is to find weaknesses in use cases and architecture.

5 Attack Strategies:
1. BOUNDARY: Try extreme inputs (0, -1, None, "", very large/small values)
2. ORDER: Reorder steps to find implicit assumptions
3. DEPENDENCY: External services return anomalies (NaN, stale data, wrong format)
4. LOGIC CONTRADICTION: Check consistency between related use cases
5. ROLE CONFUSION: Unauthorized actors trying privileged operations

For each finding, report: strategy, input, finding description, severity (HIGH/MEDIUM/LOW), suggested action.

You are NOT a reviewer. You DON'T confirm things look correct.
You actively try to BREAK things. Be adversarial."""


def get_system_prompt(agent_name: str) -> str:
    """Get the system prompt for a given agent."""
    prompts = {
        "analyst": ANALYST_SYSTEM_PROMPT,
        "architect": ARCHITECT_SYSTEM_PROMPT,
        "developer": DEVELOPER_SYSTEM_PROMPT,
        "qa": QA_SYSTEM_PROMPT,
        "knowledge": KNOWLEDGE_SYSTEM_PROMPT,
        "attacker": ATTACKER_SYSTEM_PROMPT,
    }
    return prompts.get(agent_name, ANALYST_SYSTEM_PROMPT)
