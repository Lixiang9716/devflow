#!/usr/bin/env python3
"""DevFlow MCP Server — exposes all DevFlow tools via MCP stdio protocol.

AgentTeams (Hiclaw) agents connect to this server to call DevFlow tools.
Implements the MCP stdio JSON-RPC protocol.

Usage:
    python devflow/mcp_server.py                          # All tools
    python devflow/mcp_server.py --tool-group T1,T2,T11   # Specific groups
    python devflow/mcp_server.py --readonly               # Read-only tools only
"""

from __future__ import annotations

import json
import sys
import argparse
from typing import Any, Callable

# Add project root to path
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from devflow.core.config import get_config
from devflow.core.evidence import write_evidence
from devflow.core.correlation import new_correlation

# Import all tool functions
import devflow.tools.usecase as usecase
import devflow.tools.requirement as requirement
import devflow.tools.poc as poc
import devflow.tools.token as token_tools
import devflow.tools.arch as arch
import devflow.tools.code_patch as code_patch
import devflow.tools.compiler as compiler
import devflow.tools.test as test_tools
import devflow.tools.verify as verify
import devflow.tools.knowledge as kb
import devflow.tools.crosscut as xcut


# ═══════════════════════════════════════════════════════════════════
# MCP Tool Registry — all tools with JSON Schema definitions
# ═══════════════════════════════════════════════════════════════════

MCP_TOOLS = {
    # ── Phase 1: UseCase ──
    "usecase_create": {
        "description": "Create a new use case at L0/L1/L2 level. L0=summary skeleton, L1=with alternative flows, L2=with discovered edge cases. Returns the created UseCase with uc_id.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Use case name (descriptive, e.g., '用户使用外币下单')"},
                "level": {"type": "string", "enum": ["L0", "L1", "L2"], "description": "Detail level: L0=summary, L1=standard with alt flows, L2=with discovered edge cases"},
                "actor": {"type": "string", "description": "Primary actor (e.g., '买家')"},
                "goal": {"type": "string", "description": "Actor's goal in one sentence"},
                "basic_flow": {"type": "array", "items": {"type": "string"}, "description": "Main success scenario steps (minimum 3 steps required)"},
                "task_id": {"type": "string", "description": "Task identifier for traceability"},
            },
            "required": ["name", "level", "actor", "goal", "basic_flow"],
        },
        "handler": lambda args: usecase.create(
            args["name"], args["level"], args["actor"], args["goal"],
            args.get("basic_flow", []), task_id=args.get("task_id", "")),
    },
    "usecase_upgrade": {
        "description": "Upgrade a use case to higher level (L0→L1, L1→L2). Cannot downgrade. Adds alternative flows, pre/post conditions.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "uc_id": {"type": "string", "description": "Use case ID from usecase_create"},
                "new_level": {"type": "string", "enum": ["L1", "L2"], "description": "Target level"},
                "additions": {"type": "object", "description": "New content: {alternative_flows: [...], preconditions: [...], postconditions: [...]}"},
                "task_id": {"type": "string", "description": "Task identifier"},
            },
            "required": ["uc_id", "new_level"],
        },
        "handler": lambda args: usecase.upgrade(
            args["uc_id"], args["new_level"],
            additions=args.get("additions"), task_id=args.get("task_id", "")),
    },
    "usecase_validate": {
        "description": "Validate a use case against quality rules: level≥L1, basic_flow≥3 steps, known_unknowns declared. Returns {valid, checks}.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "uc_id": {"type": "string", "description": "Use case ID to validate"},
                "task_id": {"type": "string", "description": "Task identifier"},
            },
            "required": ["uc_id"],
        },
        "handler": lambda args: usecase.validate(args["uc_id"], task_id=args.get("task_id", "")),
    },

    # ── Phase 1: Requirement ──
    "requirement_create": {
        "description": "Create a functional (FR) or non-functional (NFR) requirement linked to a use case. Returns the created Requirement with req_id (e.g., FR-01).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "uc_ref": {"type": "string", "description": "Reference use case ID"},
                "type": {"type": "string", "enum": ["FR", "NFR"], "description": "FR=functional, NFR=non-functional"},
                "description": {"type": "string", "description": "Requirement description"},
                "priority": {"type": "string", "enum": ["HIGH", "MEDIUM", "LOW"], "description": "Priority level"},
                "task_id": {"type": "string", "description": "Task identifier"},
            },
            "required": ["uc_ref", "type", "description"],
        },
        "handler": lambda args: requirement.create(
            args["uc_ref"], args["type"], args["description"],
            priority=args.get("priority", "MEDIUM"), task_id=args.get("task_id", "")),
    },
    "requirement_create_ac": {
        "description": "Create a Lean acceptance criterion: {given, when, then}. then MUST be quantifiable (==, <, >, in, matches, raises). NO fuzzy words (正常, 正确, should, maybe). Auto-generates test skeleton.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "fr_ref": {"type": "string", "description": "Reference FR ID (e.g., 'FR-01')"},
                "given": {"type": "object", "description": "Preconditions as key-value pairs, e.g., {rate: 7.25, amount_cny: 100}"},
                "when": {"type": "string", "description": "Action under test (function call), e.g., 'convert_order(order, target=\"USD\")'"},
                "then": {"type": "string", "description": "Quantifiable assertion (must contain ==, <, >, in, matches, or raises), e.g., 'display_amount == Decimal(\"13.79\")'"},
                "task_id": {"type": "string", "description": "Task identifier"},
            },
            "required": ["fr_ref", "given", "when", "then"],
        },
        "handler": lambda args: requirement.create_ac(
            args["fr_ref"], args["given"], args["when"], args["then"],
            task_id=args.get("task_id", "")),
    },

    # ── Phase 2: PoC ──
    "poc_create": {
        "description": "Create a proof-of-concept experiment with executable Python code. Returns experiment_id for use with poc_run.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Experiment name"},
                "hypothesis": {"type": "string", "description": "What we're testing"},
                "code": {"type": "string", "description": "Python code to execute in sandbox"},
                "expected_result": {"type": "string", "description": "Expected stdout output"},
                "linked_fr": {"type": "string", "description": "Related FR ID"},
                "task_id": {"type": "string", "description": "Task identifier"},
            },
            "required": ["name", "hypothesis", "code", "expected_result"],
        },
        "handler": lambda args: poc.create(
            args["name"], args["hypothesis"], args["code"], args["expected_result"],
            linked_fr=args.get("linked_fr", ""), task_id=args.get("task_id", "")),
    },
    "poc_run": {
        "description": "Execute a PoC experiment in sandbox. Compares actual vs expected. Returns PASS/FAIL/INCONCLUSIVE.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "experiment_id": {"type": "string", "description": "Experiment ID from poc_create"},
                "task_id": {"type": "string", "description": "Task identifier"},
            },
            "required": ["experiment_id"],
        },
        "handler": lambda args: poc.run(args["experiment_id"], task_id=args.get("task_id", "")),
    },

    # ── Phase 2: Token ──
    "token_estimate": {
        "description": "Estimate LLM token consumption and cost for a task across all 5 phases.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "task_spec": {"type": "object", "description": "Task specification with type and complexity"},
                "model": {"type": "string", "description": "LLM model to estimate for (e.g., 'deepseek-v4-pro')"},
                "task_id": {"type": "string", "description": "Task identifier"},
            },
            "required": ["task_spec", "model"],
        },
        "handler": lambda args: token_tools.estimate(
            args["task_spec"], args["model"], task_id=args.get("task_id", "")),
    },

    # ── Phase 3: Architecture ──
    "arch_define_context_map": {
        "description": "Define a system context map with bounded contexts and DDD relationships (PARTNERSHIP, CUSTOMER_SUPPLIER, ACL, CONFORMIST). Generates PlantUML source.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "contexts": {"type": "array", "items": {"type": "object"}, "description": "List of {name, responsibility, agents}"},
                "relationships": {"type": "array", "items": {"type": "object"}, "description": "List of {source, target, type, description}"},
                "task_id": {"type": "string", "description": "Task identifier"},
            },
            "required": ["contexts", "relationships"],
        },
        "handler": lambda args: arch.define_context_map(
            args["contexts"], args["relationships"], task_id=args.get("task_id", "")),
    },
    "arch_define_interface": {
        "description": "Define a versioned interface contract with JSON Schema validation. Version must start with 'v'.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Interface name (e.g., 'ExchangeRateProvider')"},
                "version": {"type": "string", "description": "Version string starting with 'v' (e.g., 'v1')"},
                "inputs": {"type": "object", "description": "Input parameters schema"},
                "outputs": {"type": "object", "description": "Output schema"},
                "errors": {"type": "array", "items": {"type": "string"}, "description": "Possible error types"},
                "constraints": {"type": "array", "items": {"type": "string"}, "description": "Business constraints"},
                "task_id": {"type": "string", "description": "Task identifier"},
            },
            "required": ["name", "version", "inputs", "outputs"],
        },
        "handler": lambda args: arch.define_interface(
            args["name"], args["version"], args["inputs"], args["outputs"],
            errors=args.get("errors", []), constraints=args.get("constraints", []),
            task_id=args.get("task_id", "")),
    },
    "arch_create_adr": {
        "description": "Create an Architecture Decision Record (auto-numbered ADR-001). Every non-trivial architectural decision MUST have an ADR.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "ADR title (e.g., '使用Decimal而非整数处理汇率精度')"},
                "context": {"type": "string", "description": "Background and problem description"},
                "decision": {"type": "string", "description": "What we decided"},
                "rationale": {"type": "string", "description": "Why we decided this"},
                "consequences": {"type": "string", "description": "Resulting consequences (positive and negative)"},
                "alternatives": {"type": "array", "items": {"type": "string"}, "description": "Rejected alternatives and why"},
                "task_id": {"type": "string", "description": "Task identifier"},
            },
            "required": ["title", "context", "decision", "rationale", "consequences"],
        },
        "handler": lambda args: arch.create_adr(
            args["title"], args["context"], args["decision"], args["rationale"],
            args["consequences"], alternatives=args.get("alternatives", []),
            task_id=args.get("task_id", "")),
    },

    # ── Phase 4: Code ──
    "code_create_branch": {
        "description": "Create a feature branch for the task (naming: feature/devflow-{task_id}). Idempotent.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "Task identifier"},
                "base_ref": {"type": "string", "description": "Base branch (default: main)"},
            },
            "required": ["task_id"],
        },
        "handler": lambda args: code_patch.create_branch(
            task_id=args["task_id"], base_ref=args.get("base_ref", "main")),
    },
    "code_generate_patch": {
        "description": "Generate a unified diff patch from architecture spec + use cases. LLM reasons what to change, tool produces the diff.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "spec_ref": {"type": "string", "description": "Reference to architecture spec"},
                "uc_ref": {"type": "string", "description": "Reference use case ID"},
                "context": {"type": "object", "description": "Additional context for code generation"},
                "task_id": {"type": "string", "description": "Task identifier"},
            },
            "required": ["spec_ref", "uc_ref"],
        },
        "handler": lambda args: code_patch.generate_patch(
            args["spec_ref"], args["uc_ref"], context=args.get("context"),
            task_id=args.get("task_id", "")),
    },
    "compiler_check_syntax": {
        "description": "Check Python syntax of code using AST parsing BEFORE applying. Returns {pass, errors}.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "target": {"type": "string", "description": "Target file name for error reporting"},
                "code": {"type": "string", "description": "Code content to check"},
                "task_id": {"type": "string", "description": "Task identifier"},
            },
            "required": ["target", "code"],
        },
        "handler": lambda args: compiler.check_syntax(
            args["target"], args.get("code", ""), task_id=args.get("task_id", "")),
    },

    # ── Phase 5: Test ──
    "test_run": {
        "description": "Execute a test suite. Returns {total, passed, failed, skipped, flaky}. Built-in flaky detection (run 3x).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "suite": {"type": "string", "description": "Test suite name (e.g., 'full', 'unit', 'integration')"},
                "target_branch": {"type": "string", "description": "Branch being tested"},
                "task_id": {"type": "string", "description": "Task identifier"},
            },
            "required": ["suite"],
        },
        "handler": lambda args: test_tools.run(
            args["suite"], target_branch=args.get("target_branch", ""),
            task_id=args.get("task_id", "")),
    },
    "test_coverage": {
        "description": "Measure test coverage with before/after delta.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "target_branch": {"type": "string", "description": "Branch being tested"},
                "baseline_branch": {"type": "string", "description": "Baseline branch for comparison (e.g., 'main')"},
                "task_id": {"type": "string", "description": "Task identifier"},
            },
            "required": ["target_branch"],
        },
        "handler": lambda args: test_tools.coverage(
            args["target_branch"], baseline_branch=args.get("baseline_branch"),
            task_id=args.get("task_id", "")),
    },

    # ── Phase 5: Verify ──
    "verify_ac": {
        "description": "Verify a single acceptance criterion against actual test output. Returns PASS or FAIL.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "ac_id": {"type": "string", "description": "AC identifier (e.g., 'AC-FR-01-1')"},
                "actual": {"type": "string", "description": "Actual test output"},
                "expected": {"type": "string", "description": "Expected output from AC"},
                "task_id": {"type": "string", "description": "Task identifier"},
            },
            "required": ["ac_id", "actual", "expected"],
        },
        "handler": lambda args: verify.verify_ac(
            args["ac_id"], {"actual": args["actual"], "expected": args["expected"]},
            task_id=args.get("task_id", "")),
    },
    "verify_classify_issue": {
        "description": "Classify a test failure using the decision tree: USECASE_GAP→Phase1, BUG_IN_USECASE→Phase1, CODE_BUG→Phase4, ENV_ISSUE→DevOps.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "ac_id": {"type": "string", "description": "Failed AC identifier"},
                "scenario_in_use_case": {"type": "boolean", "description": "Is this scenario described in the use case?"},
                "code_matches_use_case": {"type": "boolean", "description": "Does the code behavior match the use case description?"},
                "is_environmental": {"type": "boolean", "description": "Is this an environment/infrastructure issue?"},
                "detail": {"type": "string", "description": "Detailed failure analysis description"},
                "task_id": {"type": "string", "description": "Task identifier"},
            },
            "required": ["ac_id", "detail"],
        },
        "handler": lambda args: verify.classify_issue(
            args["ac_id"],
            {"scenario_in_use_case": args.get("scenario_in_use_case"),
             "code_matches_use_case": args.get("code_matches_use_case"),
             "is_environmental": args.get("is_environmental", False),
             "detail": args["detail"]},
            task_id=args.get("task_id", "")),
    },
    "verify_verdict": {
        "description": "Produce final task verdict aggregating all Eval-Gate results: PASS, FAIL_RETRY, or NEED_HUMAN.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "Task identifier"},
                "eval_gate_results": {"type": "object", "description": "G1-G6 gate results as {G1: 'PASS', G2: 'PASS', ...}"},
                "timeline_compliance": {"type": "number", "description": "Timeline compliance percentage (0-100)"},
            },
            "required": ["task_id"],
        },
        "handler": lambda args: verify.verdict(
            args["task_id"],
            eval_gate_results=args.get("eval_gate_results", {}),
            timeline_compliance=args.get("timeline_compliance", 100.0)),
    },

    # ── Knowledge ──
    "kb_retrieve": {
        "description": "Retrieve relevant knowledge (positive + negative channels) for the current task context.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "task_context": {"type": "object", "description": "Current task context for similarity matching"},
                "channels": {"type": "array", "items": {"type": "string"}, "description": "Which channels to query: ['positive'], ['negative'], or ['positive', 'negative']"},
                "task_id": {"type": "string", "description": "Task identifier"},
            },
            "required": ["task_context"],
        },
        "handler": lambda args: kb.retrieve(
            args["task_context"], channels=args.get("channels", ["positive", "negative"]),
            task_id=args.get("task_id", "")),
    },
    "kb_index": {
        "description": "Index new knowledge into the positive or negative channel for future retrieval.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "Task identifier"},
                "channel": {"type": "string", "enum": ["positive", "negative", "cost_optimization"], "description": "Knowledge channel"},
                "content": {"type": "object", "description": "Knowledge content to index"},
            },
            "required": ["task_id", "channel", "content"],
        },
        "handler": lambda args: kb.index(args["task_id"], args["channel"], args["content"]),
    },

    # ── Crosscutting ──
    "complexity_assess": {
        "description": "Assess task complexity (S/M/L/XL) and determine which phases can be skipped. S tasks skip Phase 2+3.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "task_spec": {"type": "object", "description": "Task spec with: file_count, dependency_depth, financial(bool), security(bool), historical_similarity(0-1)"},
                "task_id": {"type": "string", "description": "Task identifier"},
            },
            "required": ["task_spec"],
        },
        "handler": lambda args: xcut.assess_complexity(
            args["task_spec"], task_id=args.get("task_id", "")),
    },
    "timeline_verify": {
        "description": "Verify actual event timeline against expected phase template. Detects missing events, order violations, timing anomalies.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "Task identifier"},
                "phase": {"type": "string", "description": "Phase number (1-5)"},
            },
            "required": ["task_id", "phase"],
        },
        "handler": lambda args: xcut.verify_timeline(args["task_id"], args["phase"]),
    },
}


# ═══════════════════════════════════════════════════════════════════
# MCP stdio Protocol Implementation
# ═══════════════════════════════════════════════════════════════════

def _serialize_result(result: Any) -> dict:
    """Convert DevFlow Result/Success/Failure/dataclass to JSON-serializable dict."""
    from devflow.core.result import Success, Failure

    if isinstance(result, Success):
        data = result.data
    elif isinstance(result, Failure):
        return {"status": "error", "code": result.code.value, "message": result.message, "detail": result.detail}
    else:
        data = result

    # Convert dataclass to dict
    if hasattr(data, 'to_dict'):
        return {"status": "ok", **data.to_dict()}
    elif hasattr(data, '__dataclass_fields__'):
        from dataclasses import asdict
        return {"status": "ok", **asdict(data)}
    elif isinstance(data, dict):
        return {"status": "ok", **data}
    elif isinstance(data, (list, str, int, float, bool)):
        return {"status": "ok", "data": data}
    return {"status": "ok", "data": str(data)}


def handle_request(request: dict) -> dict:
    """Handle a single JSON-RPC request."""
    method = request.get("method", "")
    req_id = request.get("id")

    # ── initialize ──
    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "serverInfo": {
                    "name": "devflow-mcp-server",
                    "version": "0.1.0",
                },
                "capabilities": {
                    "tools": {},
                },
            },
        }

    # ── tools/list ──
    elif method == "tools/list":
        tools_list = []
        for name, spec in MCP_TOOLS.items():
            tools_list.append({
                "name": name,
                "description": spec["description"],
                "inputSchema": spec["inputSchema"],
            })
        return {"jsonrpc": "2.0", "id": req_id, "result": {"tools": tools_list}}

    # ── tools/call ──
    elif method == "tools/call":
        params = request.get("params", {})
        tool_name = params.get("name", "")
        tool_args = params.get("arguments", {})

        tool = MCP_TOOLS.get(tool_name)
        if not tool:
            return {
                "jsonrpc": "2.0", "id": req_id,
                "result": {
                    "content": [{"type": "text", "text": json.dumps({"error": f"Unknown tool: {tool_name}"}, ensure_ascii=False)}],
                    "isError": True,
                },
            }

        try:
            result = tool["handler"](tool_args)
            output = _serialize_result(result)
            return {
                "jsonrpc": "2.0", "id": req_id,
                "result": {
                    "content": [{"type": "text", "text": json.dumps(output, ensure_ascii=False, default=str)}],
                },
            }
        except Exception as e:
            return {
                "jsonrpc": "2.0", "id": req_id,
                "result": {
                    "content": [{"type": "text", "text": json.dumps({"error": str(e), "tool": tool_name}, ensure_ascii=False)}],
                    "isError": True,
                },
            }

    # ── notifications ──
    elif method == "notifications/initialized":
        return None  # No response for notifications

    elif method == "ping":
        return {"jsonrpc": "2.0", "id": req_id, "result": {}}

    else:
        return {
            "jsonrpc": "2.0", "id": req_id,
            "error": {"code": -32601, "message": f"Method not found: {method}"},
        }


def main():
    """Run the MCP server in stdio mode."""
    parser = argparse.ArgumentParser(description="DevFlow MCP Server")
    parser.add_argument("--tool-group", help="Comma-separated tool groups (T1,T2,...)")
    parser.add_argument("--readonly", action="store_true", help="Only expose read-only tools")
    args = parser.parse_args()

    # Filter tools if requested
    if args.tool_group:
        groups = set(args.tool_group.split(","))
        # For now, expose all tools regardless of group filter
        pass

    if args.readonly:
        readonly_tools = {
            "usecase_validate", "kb_retrieve", "token_estimate",
            "verify_ac", "verify_classify_issue", "verify_verdict",
            "timeline_verify", "complexity_assess",
        }
        for name in list(MCP_TOOLS.keys()):
            if name not in readonly_tools:
                del MCP_TOOLS[name]

    # MCP stdio loop
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
            response = handle_request(request)
            if response is not None:
                sys.stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
                sys.stdout.flush()
        except json.JSONDecodeError:
            continue


if __name__ == "__main__":
    main()
