"""MCP Tool Wrappers — expose all DevFlow tools as LLM-callable functions.

Each tool is wrapped with a JSON Schema definition (ToolDefinition)
and a handler function that maps ToolCall → ToolResult.

This is the "一切皆工具" (everything is a tool) principle in action.
"""

from __future__ import annotations

import json
from typing import Optional, Callable

from devflow.core.llm_client import ToolDefinition, ToolCall, ToolResult
from devflow.core.correlation import CorrelationId

# Import all tool functions
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


# ═══════════════════════════════════════════════════════════════════
# Phase 1: Requirements Engineering Tools
# ═══════════════════════════════════════════════════════════════════

USECASE_CREATE = ToolDefinition(
    name="usecase_create",
    description="Create a new use case at L0/L1/L2 level. L0=summary skeleton, L1=with alternative flows, L2=with discovered edge cases.",
    parameters={
        "name": {"type": "string", "description": "Use case name (descriptive)"},
        "level": {"type": "string", "enum": ["L0", "L1", "L2"], "description": "Detail level"},
        "actor": {"type": "string", "description": "Primary actor"},
        "goal": {"type": "string", "description": "Actor's goal"},
        "basic_flow": {"type": "array", "items": {"type": "string"}, "description": "Main success scenario steps (min 3)"},
        "task_id": {"type": "string", "description": "Task identifier"},
    },
    required=["name", "level", "actor", "goal", "basic_flow"],
)

USECASE_UPGRADE = ToolDefinition(
    name="usecase_upgrade",
    description="Upgrade a use case to a higher level (L0→L1, L1→L2). Cannot downgrade.",
    parameters={
        "uc_id": {"type": "string", "description": "Use case ID"},
        "new_level": {"type": "string", "enum": ["L1", "L2"], "description": "Target level"},
        "additions": {"type": "object", "description": "New content: alternative_flows, preconditions, postconditions"},
        "task_id": {"type": "string", "description": "Task identifier"},
    },
    required=["uc_id", "new_level"],
)

USECASE_VALIDATE = ToolDefinition(
    name="usecase_validate",
    description="Validate a use case against quality rules: level≥L1, flow≥3 steps, known unknowns declared.",
    parameters={
        "uc_id": {"type": "string", "description": "Use case ID to validate"},
        "task_id": {"type": "string", "description": "Task identifier"},
    },
    required=["uc_id"],
)

REQUIREMENT_CREATE = ToolDefinition(
    name="requirement_create",
    description="Create a functional (FR) or non-functional (NFR) requirement linked to a use case.",
    parameters={
        "uc_ref": {"type": "string", "description": "Reference use case ID"},
        "type": {"type": "string", "enum": ["FR", "NFR"], "description": "FR or NFR"},
        "description": {"type": "string", "description": "Requirement description"},
        "priority": {"type": "string", "enum": ["HIGH", "MEDIUM", "LOW"], "description": "Priority level"},
        "task_id": {"type": "string", "description": "Task identifier"},
    },
    required=["uc_ref", "type", "description"],
)

REQUIREMENT_CREATE_AC = ToolDefinition(
    name="requirement_create_ac",
    description="Create a Lean acceptance criterion: {given, when, then}. then MUST be quantifiable (==, <, >, in, matches, raises). NO fuzzy words.",
    parameters={
        "fr_ref": {"type": "string", "description": "Reference FR ID (e.g., FR-01)"},
        "given": {"type": "object", "description": "Preconditions as key-value pairs"},
        "when": {"type": "string", "description": "Action under test (function call)"},
        "then": {"type": "string", "description": "Quantifiable assertion (must contain ==, <, >, in, matches, or raises)"},
        "task_id": {"type": "string", "description": "Task identifier"},
    },
    required=["fr_ref", "given", "when", "then"],
)

REQUIREMENT_CLARIFY = ToolDefinition(
    name="requirement_request_clarification",
    description="Request clarification from the human when requirements are ambiguous.",
    parameters={
        "question": {"type": "string", "description": "The clarification question"},
        "options": {"type": "array", "items": {"type": "string"}, "description": "Possible answers"},
        "context": {"type": "string", "description": "Why this clarification is needed"},
        "task_id": {"type": "string", "description": "Task identifier"},
    },
    required=["question"],
)

# ═══════════════════════════════════════════════════════════════════
# Phase 2: Feasibility Study Tools
# ═══════════════════════════════════════════════════════════════════

POC_CREATE = ToolDefinition(
    name="poc_create",
    description="Create a proof-of-concept experiment with executable code.",
    parameters={
        "name": {"type": "string", "description": "Experiment name"},
        "hypothesis": {"type": "string", "description": "What we're testing"},
        "code": {"type": "string", "description": "Python code to execute"},
        "expected_result": {"type": "string", "description": "Expected output"},
        "linked_fr": {"type": "string", "description": "Related FR ID"},
        "task_id": {"type": "string", "description": "Task identifier"},
    },
    required=["name", "hypothesis", "code", "expected_result"],
)

POC_RUN = ToolDefinition(
    name="poc_run",
    description="Execute a PoC experiment and compare actual vs expected output.",
    parameters={
        "experiment_id": {"type": "string", "description": "Experiment ID to run"},
        "task_id": {"type": "string", "description": "Task identifier"},
    },
    required=["experiment_id"],
)

TOKEN_ESTIMATE = ToolDefinition(
    name="token_estimate",
    description="Estimate token consumption and cost for a task across all phases.",
    parameters={
        "task_spec": {"type": "object", "description": "Task specification"},
        "model": {"type": "string", "description": "LLM model to estimate for"},
        "task_id": {"type": "string", "description": "Task identifier"},
    },
    required=["task_spec", "model"],
)

# ═══════════════════════════════════════════════════════════════════
# Phase 3: Architecture Design Tools
# ═══════════════════════════════════════════════════════════════════

ARCH_CONTEXT_MAP = ToolDefinition(
    name="arch_define_context_map",
    description="Define a system context map with bounded contexts and their relationships.",
    parameters={
        "contexts": {"type": "array", "items": {"type": "object"}, "description": "List of bounded contexts"},
        "relationships": {"type": "array", "items": {"type": "object"}, "description": "Context relationships"},
        "task_id": {"type": "string", "description": "Task identifier"},
    },
    required=["contexts", "relationships"],
)

ARCH_INTERFACE = ToolDefinition(
    name="arch_define_interface",
    description="Define an interface contract with version, inputs, outputs, errors, and constraints.",
    parameters={
        "name": {"type": "string", "description": "Interface name"},
        "version": {"type": "string", "description": "Version (must start with 'v')"},
        "inputs": {"type": "object", "description": "Input parameters schema"},
        "outputs": {"type": "object", "description": "Output schema"},
        "errors": {"type": "array", "items": {"type": "string"}, "description": "Possible error types"},
        "constraints": {"type": "array", "items": {"type": "string"}, "description": "Business constraints"},
        "task_id": {"type": "string", "description": "Task identifier"},
    },
    required=["name", "version", "inputs", "outputs"],
)

ARCH_CREATE_ADR = ToolDefinition(
    name="arch_create_adr",
    description="Create an Architecture Decision Record for every non-trivial decision.",
    parameters={
        "title": {"type": "string", "description": "ADR title"},
        "context": {"type": "string", "description": "Background and problem"},
        "decision": {"type": "string", "description": "What we decided"},
        "rationale": {"type": "string", "description": "Why we decided this"},
        "consequences": {"type": "string", "description": "Resulting consequences"},
        "alternatives": {"type": "array", "items": {"type": "string"}, "description": "Rejected alternatives"},
        "task_id": {"type": "string", "description": "Task identifier"},
    },
    required=["title", "context", "decision", "rationale", "consequences"],
)

# ═══════════════════════════════════════════════════════════════════
# Phase 4: Implementation Tools
# ═══════════════════════════════════════════════════════════════════

CODE_CREATE_BRANCH = ToolDefinition(
    name="code_create_branch",
    description="Create a feature branch for the task.",
    parameters={
        "task_id": {"type": "string", "description": "Task identifier"},
        "base_ref": {"type": "string", "description": "Base reference (default: main)"},
    },
    required=["task_id"],
)

CODE_GENERATE_PATCH = ToolDefinition(
    name="code_generate_patch",
    description="Generate a unified diff patch from spec + use cases. Agent reasons what to change, tool produces the diff.",
    parameters={
        "spec_ref": {"type": "string", "description": "Reference to architecture spec"},
        "uc_ref": {"type": "string", "description": "Reference use case ID"},
        "task_id": {"type": "string", "description": "Task identifier"},
    },
    required=["spec_ref", "uc_ref"],
)

COMPILER_CHECK_SYNTAX = ToolDefinition(
    name="compiler_check_syntax",
    description="Check Python syntax of generated code before applying.",
    parameters={
        "target": {"type": "string", "description": "Target file name"},
        "code": {"type": "string", "description": "Code content to check"},
        "task_id": {"type": "string", "description": "Task identifier"},
    },
    required=["target", "code"],
)

CODE_SELF_REVIEW = ToolDefinition(
    name="code_self_review",
    description="Developer self-review: check implementation against all use case flows.",
    parameters={
        "commit_sha": {"type": "string", "description": "Commit to review"},
        "checks": {"type": "array", "items": {"type": "object"}, "description": "List of {name, result: PASS|FAIL|SKIP, evidence}"},
        "task_id": {"type": "string", "description": "Task identifier"},
    },
    required=["commit_sha", "checks"],
)

# ═══════════════════════════════════════════════════════════════════
# Phase 5: Verification Tools
# ═══════════════════════════════════════════════════════════════════

TEST_RUN = ToolDefinition(
    name="test_run",
    description="Execute a test suite and return results.",
    parameters={
        "suite": {"type": "string", "description": "Test suite name"},
        "target_branch": {"type": "string", "description": "Branch being tested"},
        "task_id": {"type": "string", "description": "Task identifier"},
    },
    required=["suite"],
)

VERIFY_AC = ToolDefinition(
    name="verify_ac",
    description="Verify a single acceptance criterion against actual test output.",
    parameters={
        "ac_id": {"type": "string", "description": "AC identifier"},
        "actual": {"type": "string", "description": "Actual output"},
        "expected": {"type": "string", "description": "Expected output"},
        "task_id": {"type": "string", "description": "Task identifier"},
    },
    required=["ac_id", "actual", "expected"],
)

VERIFY_CLASSIFY = ToolDefinition(
    name="verify_classify_issue",
    description="Classify a test failure: USECASE_GAP→Phase1, CODE_BUG→Phase4, BUG_IN_USECASE→Phase1, ENV_ISSUE→DevOps.",
    parameters={
        "ac_id": {"type": "string", "description": "Failed AC identifier"},
        "scenario_in_use_case": {"type": "boolean", "description": "Is this scenario described in the use case?"},
        "code_matches_use_case": {"type": "boolean", "description": "Does code behavior match the use case?"},
        "is_environmental": {"type": "boolean", "description": "Is this an environment/infrastructure issue?"},
        "detail": {"type": "string", "description": "Detailed failure analysis"},
        "task_id": {"type": "string", "description": "Task identifier"},
    },
    required=["ac_id", "detail"],
)

VERIFY_VERDICT = ToolDefinition(
    name="verify_verdict",
    description="Produce final task verdict: PASS, FAIL_RETRY, or NEED_HUMAN.",
    parameters={
        "task_id": {"type": "string", "description": "Task identifier"},
        "eval_gate_results": {"type": "object", "description": "G1-G6 gate results"},
        "timeline_compliance": {"type": "number", "description": "Timeline compliance percentage (0-100)"},
    },
    required=["task_id"],
)

# ═══════════════════════════════════════════════════════════════════
# Cross-phase: Knowledge & Crosscutting Tools
# ═══════════════════════════════════════════════════════════════════

KB_RETRIEVE = ToolDefinition(
    name="kb_retrieve",
    description="Retrieve relevant knowledge (positive + negative) for the current task context.",
    parameters={
        "task_context": {"type": "object", "description": "Current task context for similarity matching"},
        "channels": {"type": "array", "items": {"type": "string"}, "description": "Channels: positive, negative, both"},
        "task_id": {"type": "string", "description": "Task identifier"},
    },
    required=["task_context"],
)

KB_INDEX = ToolDefinition(
    name="kb_index",
    description="Index new knowledge into the positive or negative channel.",
    parameters={
        "task_id": {"type": "string", "description": "Task identifier"},
        "channel": {"type": "string", "enum": ["positive", "negative", "cost_optimization"], "description": "Knowledge channel"},
        "content": {"type": "object", "description": "Knowledge content to index"},
    },
    required=["task_id", "channel", "content"],
)

COMPLEXITY_ASSESS = ToolDefinition(
    name="complexity_assess",
    description="Assess task complexity (S/M/L/XL) and determine which phases to skip.",
    parameters={
        "task_spec": {"type": "object", "description": "Task specification with file_count, dependency_depth, financial, security flags"},
        "task_id": {"type": "string", "description": "Task identifier"},
    },
    required=["task_spec"],
)

TIMELINE_VERIFY = ToolDefinition(
    name="timeline_verify",
    description="Verify actual event timeline against expected phase template.",
    parameters={
        "task_id": {"type": "string", "description": "Task identifier"},
        "phase": {"type": "string", "description": "Phase number (1-5)"},
    },
    required=["task_id", "phase"],
)


# ═══════════════════════════════════════════════════════════════════
# Tool Collections by Phase and Agent
# ═══════════════════════════════════════════════════════════════════

PHASE_1_TOOLS = [
    USECASE_CREATE, USECASE_UPGRADE, USECASE_VALIDATE,
    REQUIREMENT_CREATE, REQUIREMENT_CREATE_AC, REQUIREMENT_CLARIFY,
    KB_RETRIEVE, COMPLEXITY_ASSESS,
]

PHASE_2_TOOLS = [
    POC_CREATE, POC_RUN, TOKEN_ESTIMATE, KB_RETRIEVE,
]

PHASE_3_TOOLS = [
    ARCH_CONTEXT_MAP, ARCH_INTERFACE, ARCH_CREATE_ADR, KB_RETRIEVE,
]

PHASE_4_TOOLS = [
    CODE_CREATE_BRANCH, CODE_GENERATE_PATCH, COMPILER_CHECK_SYNTAX,
    CODE_SELF_REVIEW, KB_RETRIEVE,
]

PHASE_5_TOOLS = [
    TEST_RUN, VERIFY_AC, VERIFY_CLASSIFY, VERIFY_VERDICT,
    KB_RETRIEVE, KB_INDEX, TIMELINE_VERIFY,
]

AGENT_TOOLS = {
    "analyst": PHASE_1_TOOLS,
    "architect": PHASE_2_TOOLS + PHASE_3_TOOLS,
    "developer": PHASE_4_TOOLS,
    "qa": PHASE_5_TOOLS,
    "knowledge": [KB_RETRIEVE, KB_INDEX],
    "attacker": PHASE_1_TOOLS,  # Read-only tool access for probing
}

PHASE_TOOLS = {
    "1": PHASE_1_TOOLS,
    "2": PHASE_2_TOOLS,
    "3": PHASE_3_TOOLS,
    "4": PHASE_4_TOOLS,
    "5": PHASE_5_TOOLS,
}


# ═══════════════════════════════════════════════════════════════════
# Universal Tool Handler
# ═══════════════════════════════════════════════════════════════════

def handle_tool_call(tc: ToolCall, task_id: str = "") -> ToolResult:
    """Universal tool handler: maps tool call name → function call → result.

    This is THE single dispatch point for all tool calls from any agent.
    Agent reasons about what to do → calls tool by name → this handler executes.
    """
    name = tc.name
    args = dict(tc.arguments)
    args.setdefault("task_id", task_id)

    handlers: dict[str, Callable] = {
        # Phase 1
        "usecase_create": lambda a: usecase.create(
            a["name"], a["level"], a["actor"], a["goal"],
            a.get("basic_flow", []), task_id=a.get("task_id", "")),
        "usecase_upgrade": lambda a: usecase.upgrade(
            a["uc_id"], a["new_level"],
            additions=a.get("additions"), task_id=a.get("task_id", "")),
        "usecase_validate": lambda a: usecase.validate(
            a["uc_id"], task_id=a.get("task_id", "")),
        "requirement_create": lambda a: requirement.create(
            a["uc_ref"], a["type"], a["description"],
            priority=a.get("priority", "MEDIUM"), task_id=a.get("task_id", "")),
        "requirement_create_ac": lambda a: requirement.create_ac(
            a["fr_ref"], a["given"], a["when"], a["then"],
            task_id=a.get("task_id", "")),
        "requirement_request_clarification": lambda a: requirement.request_clarification(
            a["question"], options=a.get("options", []),
            context=a.get("context", ""), task_id=a.get("task_id", "")),
        # Phase 2
        "poc_create": lambda a: poc.create(
            a["name"], a["hypothesis"], a["code"], a["expected_result"],
            linked_fr=a.get("linked_fr", ""), task_id=a.get("task_id", "")),
        "poc_run": lambda a: poc.run(
            a["experiment_id"], task_id=a.get("task_id", "")),
        "token_estimate": lambda a: token.estimate(
            a["task_spec"], a["model"], task_id=a.get("task_id", "")),
        # Phase 3
        "arch_define_context_map": lambda a: arch.define_context_map(
            a["contexts"], a["relationships"], task_id=a.get("task_id", "")),
        "arch_define_interface": lambda a: arch.define_interface(
            a["name"], a["version"], a["inputs"], a["outputs"],
            errors=a.get("errors", []), constraints=a.get("constraints", []),
            task_id=a.get("task_id", "")),
        "arch_create_adr": lambda a: arch.create_adr(
            a["title"], a["context"], a["decision"], a["rationale"],
            a["consequences"], alternatives=a.get("alternatives", []),
            task_id=a.get("task_id", "")),
        # Phase 4
        "code_create_branch": lambda a: code_patch.create_branch(
            task_id=a.get("task_id", ""), base_ref=a.get("base_ref", "main")),
        "code_generate_patch": lambda a: code_patch.generate_patch(
            a["spec_ref"], a["uc_ref"], task_id=a.get("task_id", "")),
        "compiler_check_syntax": lambda a: compiler.check_syntax(
            a["target"], a.get("code", ""), task_id=a.get("task_id", "")),
        "code_self_review": lambda a: code_patch.self_review(
            a["commit_sha"], a["checks"], task_id=a.get("task_id", "")),
        # Phase 5
        "test_run": lambda a: test_tools.run(
            a["suite"], target_branch=a.get("target_branch", ""),
            task_id=a.get("task_id", "")),
        "verify_ac": lambda a: verify.verify_ac(
            a["ac_id"], {"actual": a["actual"], "expected": a["expected"]},
            task_id=a.get("task_id", "")),
        "verify_classify_issue": lambda a: verify.classify_issue(
            a["ac_id"],
            {"scenario_in_use_case": a.get("scenario_in_use_case"),
             "code_matches_use_case": a.get("code_matches_use_case"),
             "is_environmental": a.get("is_environmental", False),
             "detail": a["detail"]},
            task_id=a.get("task_id", "")),
        "verify_verdict": lambda a: verify.verdict(
            a["task_id"],
            eval_gate_results=a.get("eval_gate_results", {}),
            timeline_compliance=a.get("timeline_compliance", 100.0)),
        # Cross-phase
        "kb_retrieve": lambda a: kb.retrieve(
            a["task_context"], channels=a.get("channels", ["positive", "negative"]),
            task_id=a.get("task_id", "")),
        "kb_index": lambda a: kb.index(
            a["task_id"], a["channel"], a["content"]),
        "complexity_assess": lambda a: xcut.assess_complexity(
            a["task_spec"], task_id=a.get("task_id", "")),
        "timeline_verify": lambda a: xcut.verify_timeline(
            a["task_id"], a["phase"]),
    }

    handler = handlers.get(name)
    if not handler:
        return ToolResult(
            tool_call_id=tc.id, name=name,
            content=json.dumps({"error": f"Unknown tool: {name}"}, ensure_ascii=False),
            is_error=True,
        )

    try:
        result = handler(args)
        result_dict = result.data if hasattr(result, 'data') else result
        # Convert to JSON-serializable form
        if hasattr(result_dict, 'to_dict'):
            result_dict = result_dict.to_dict()
        elif hasattr(result_dict, '__dataclass_fields__'):
            from dataclasses import asdict
            result_dict = asdict(result_dict)
        elif isinstance(result_dict, str):
            result_dict = {"result": result_dict}

        return ToolResult(
            tool_call_id=tc.id, name=name,
            content=json.dumps(result_dict, ensure_ascii=False, default=str),
            is_error=False,
        )
    except Exception as e:
        return ToolResult(
            tool_call_id=tc.id, name=name,
            content=json.dumps({"error": str(e)}, ensure_ascii=False),
            is_error=True,
        )
