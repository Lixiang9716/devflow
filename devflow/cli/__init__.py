"""DevFlow CLI — command-line entry point for the structured SE system.

Usage:
    devflow task create "电商平台需要支持多币种订单"
    devflow task run <task_id> [--phase 1-5] [--agent analyst]
    devflow task status <task_id>
    devflow task report <task_id>
    devflow baseline run
    devflow config show
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import os

from devflow.core.config import get_config, reload_config
from devflow.core.correlation import new_correlation
from devflow.core.llm_client import LLMClient, ToolDefinition, ToolCall, ToolResult
from devflow.core.agent_loop import (
    AgentLoop, AgentContext, get_system_prompt,
)
from devflow.core.mcp_tools import (
    AGENT_TOOLS, PHASE_TOOLS, handle_tool_call,
)
from devflow.tools.usecase import clear_store as uc_clear
from devflow.tools.requirement import clear_store as req_clear
from devflow.tools.verify import IssueType, Verdict
from devflow.tools.crosscut import assess_complexity
from devflow.eval_gates import run_all_gates
from devflow.agents import AGENT_DEFINITIONS, get_phase_agents


def create_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser."""
    parser = argparse.ArgumentParser(
        prog="devflow",
        description="DevFlow — AI-driven structured software engineering system",
    )
    sub = parser.add_subparsers(dest="command", help="Available commands")

    # task create
    task_create = sub.add_parser("task", help="Task management")
    task_sub = task_create.add_subparsers(dest="task_command")

    tc = task_sub.add_parser("create", help="Create a new task")
    tc.add_argument("description", help="Natural language task description")
    tc.add_argument("--complexity", choices=["S", "M", "L", "XL"], default=None,
                    help="Override auto-detected complexity")

    # task run
    tr = task_sub.add_parser("run", help="Run a task or phase")
    tr.add_argument("task_id", help="Task identifier")
    tr.add_argument("--phase", choices=["1", "2", "3", "4", "5"], help="Run specific phase")
    tr.add_argument("--agent", help="Run specific agent")
    tr.add_argument("--model", help="Override LLM model")

    # task status
    ts = task_sub.add_parser("status", help="Check task status")
    ts.add_argument("task_id", help="Task identifier")

    # task report
    trep = task_sub.add_parser("report", help="Generate task report")
    trep.add_argument("task_id", help="Task identifier")

    # baseline
    bl = sub.add_parser("baseline", help="Capability baseline")
    bl_sub = bl.add_subparsers(dest="baseline_command")
    bl_sub.add_parser("run", help="Run capability baseline for all agents")

    # config
    cfg = sub.add_parser("config", help="Configuration management")
    cfg_sub = cfg.add_subparsers(dest="config_command")
    cfg_sub.add_parser("show", help="Show current configuration")

    return parser


def cmd_task_create(args):
    """Create a new task with complexity assessment."""
    description = args.description
    corr = new_correlation()

    print(f"\n📋 Creating task: {description}")
    print(f"   Task ID: {corr.task_id}")

    # Assess complexity
    spec = {"description": description}
    if args.complexity:
        spec["complexity"] = args.complexity
    else:
        # Auto-detect: simple heuristic
        word_count = len(description)
        spec["file_count"] = min(word_count // 10, 20)
        spec["dependency_depth"] = 2

    result = assess_complexity(spec, task_id=corr.task_id)
    if hasattr(result, 'data'):
        complexity = result.data.get("level", "L")
        pipeline = result.data.get("pipeline", "")
    else:
        complexity = "L"
        pipeline = "Full pipeline"

    print(f"   Complexity: {complexity}")
    print(f"   Pipeline: {pipeline}")
    print(f"\n✅ Task created. Run: devflow task run {corr.task_id}")

    return corr.task_id


def cmd_task_run(args):
    """Run a task phase with the appropriate agent."""
    task_id = args.task_id
    phase = args.phase or "1"
    agent_name = args.agent

    config = get_config()
    if not config.llm.api_key:
        print("❌ Error: DEEPSEEK_API_KEY not set. Please set it in your environment.")
        print("   export DEEPSEEK_API_KEY=sk-...")
        return 1

    client = LLMClient()
    loop = AgentLoop(client)

    # Determine which agents to run
    if agent_name:
        agents_to_run = [agent_name]
    else:
        phase_agents = get_phase_agents(phase)
        agents_to_run = [a.name.replace("devflow-", "") for a in phase_agents]

    print(f"\n🚀 Running Phase {phase} for {task_id}")
    print(f"   Agents: {', '.join(agents_to_run)}")
    print(f"   Model: {args.model or config.llm.default_model}")

    all_results = {}

    for agent in agents_to_run:
        if agent == "ops":
            continue  # DevOps is infrastructure-only
        if agent == "attacker" and phase not in ("1", "3"):
            continue

        print(f"\n   🤖 Running {agent} agent...")
        tools = AGENT_TOOLS.get(agent, PHASE_TOOLS.get(phase, []))

        ctx = AgentContext(
            task_id=task_id,
            phase=phase,
            agent_name=agent,
            agent_role=AGENT_DEFINITIONS.get(agent, {}).role if agent in AGENT_DEFINITIONS else agent,
            system_prompt=get_system_prompt(agent),
            user_task=f"Task {task_id}: Execute Phase {phase} responsibilities as the {agent} agent.",
            available_tools=tools,
            tool_handler=lambda tc: handle_tool_call(tc, task_id=task_id),
            model=args.model,
        )

        result = loop.run(ctx)
        if hasattr(result, 'data'):
            ar = result.data
            status = "✅" if ar.success else "❌"
            print(f"   {status} {agent}: {ar.tokens_used} tokens, {ar.duration_ms:.0f}ms")
            if ar.tool_calls_made:
                print(f"      Tools called: {len(ar.tool_calls_made)}")
                for tc in ar.tool_calls_made[:3]:
                    print(f"        - {tc['tool']}: {'✓' if not tc['is_error'] else '✗'}")
            all_results[agent] = ar
        else:
            print(f"   ❌ {agent}: Failed to run")

    return all_results


def cmd_task_status(args):
    """Check task status."""
    task_id = args.task_id
    from devflow.core.evidence import get_events, trace_chain

    events = get_events(task_id)
    chain = trace_chain(task_id)

    print(f"\n📊 Task Status: {task_id}")
    print(f"   Events recorded: {len(events)}")

    if events:
        phases = set(e.phase for e in events)
        print(f"   Phases touched: {sorted(phases)}")

        by_phase = {}
        for e in events:
            by_phase[e.phase] = by_phase.get(e.phase, 0) + 1
        for p, count in sorted(by_phase.items()):
            print(f"     Phase {p}: {count} events")

        if chain.get("forward"):
            fwd = chain["forward"]
            print(f"   Trace chain: {sum(len(v) for v in fwd.values())} nodes")
    else:
        print(f"   No events recorded yet. Run: devflow task run {task_id}")


def cmd_task_report(args):
    """Generate a comprehensive task report."""
    task_id = args.task_id
    from devflow.core.evidence import get_events, trace_chain, check_integrity
    from devflow.tools.token import report as token_report

    events = get_events(task_id)
    chain = trace_chain(task_id)
    integrity = check_integrity(task_id)

    print(f"\n{'='*60}")
    print(f"  DevFlow Task Report: {task_id}")
    print(f"{'='*60}")

    print(f"\n📋 Summary")
    print(f"   Total events: {len(events)}")
    print(f"   Evidence integrity: {'✅' if integrity['pass'] else '❌ TAMPERED'}")

    # Token report
    token_result = token_report(task_id)
    if hasattr(token_result, 'data'):
        tr = token_result.data
        print(f"\n💰 Token Usage")
        print(f"   Total cost: ${tr.get('total_cost', 0):.4f}")
        print(f"   Total calls: {tr.get('total_calls', 0)}")
        for phase_key, data in tr.get("by_phase", {}).items():
            print(f"   {phase_key}: {data['input']:,} in / {data['output']:,} out, ${data['cost']:.4f}")

    # Trace chain
    if chain.get("forward"):
        fwd = chain["forward"]
        print(f"\n🔗 Traceability Chain")
        for key, items in fwd.items():
            if items:
                print(f"   {key}: {len(items)}")

    if chain.get("broken_links"):
        print(f"\n⚠️  Broken Links: {len(chain['broken_links'])}")

    # Timeline
    if events:
        print(f"\n⏱️  Event Timeline")
        for e in events[-10:]:  # Last 10
            print(f"   [{e.phase}] {e.tool_name}: {e.step} @ {time.strftime('%H:%M:%S', time.gmtime(e.timestamp))}")


def main():
    """Main CLI entry point."""
    parser = create_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    if args.command == "task":
        if args.task_command == "create":
            cmd_task_create(args)
        elif args.task_command == "run":
            cmd_task_run(args)
        elif args.task_command == "status":
            cmd_task_status(args)
        elif args.task_command == "report":
            cmd_task_report(args)
        else:
            print("Usage: devflow task {create|run|status|report} ...")
    elif args.command == "baseline":
        print("🔬 Capability Baseline — not yet implemented")
        print("   This will run benchmark tests for all 7 agents.")
    elif args.command == "config":
        if args.config_command == "show":
            config = get_config()
            print(f"\n⚙️  DevFlow Configuration")
            print(f"   LLM Model: {config.llm.default_model}")
            print(f"   LLM Endpoint: {config.llm.base_url}")
            print(f"   API Key: {'✓ set' if config.llm.api_key else '❌ not set'}")
            print(f"   Project: {config.project_name}")
            print(f"   Log Level: {config.log_level}")
        else:
            print("Usage: devflow config show")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
