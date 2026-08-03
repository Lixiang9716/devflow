"""Live demo: run the Phase 1 Analyst agent with real-time process logs.

Unlike `demo.sh` (which prints only the summary after the agent finishes),
this script prints every step as it happens:
  - each LLM reasoning round (what the agent "thought")
  - every tool call the agent requests (name + arguments)
  - the result returned by each tool
  - the final agent response + token usage

Usage:
    python examples/live_demo.py
"""

from __future__ import annotations

import json
import time

from devflow.core.agent_loop import AgentContext, AgentLoop, get_system_prompt
from devflow.core.llm_client import LLMClient, LLMResponse, ToolCall, ToolResult
from devflow.core.mcp_tools import PHASE_1_TOOLS, handle_tool_call
from devflow.core.result import is_ok
from devflow.tools import requirement, usecase


class LiveLLMClient(LLMClient):
    """LLM client that prints each reasoning round in real time."""

    round_no = 0

    def chat(self, *args, **kwargs):
        LiveLLMClient.round_no += 1
        result = super().chat(*args, **kwargs)
        if is_ok(result):
            resp: LLMResponse = result.data
            round_no = LiveLLMClient.round_no
            print(f"\n  {'─' * 62}")
            print(f"  🤖 LLM 推理 第 {round_no} 轮 ({resp.model})  "
                  f"[{resp.input_tokens} in / {resp.output_tokens} out, {resp.duration_ms:.0f}ms]")
            print(f"  {'─' * 62}")
            text = (resp.content or "").strip()
            if text:
                for line in text.splitlines():
                    print(f"    {line}")
            for tc in resp.tool_calls:
                args = json.dumps(tc.arguments, ensure_ascii=False)
                if len(args) > 300:
                    args = args[:300] + "…"
                print(f"  🔧 请求调用工具: {tc.name}")
                print(f"     参数: {args}")
        else:
            print(f"  ❌ LLM 调用失败: {result.message}")
        return result


def live_tool_handler(tc: ToolCall, task_id: str) -> ToolResult:
    """Wrap the real tool handler to log every execution."""
    print(f"  ⚙️  执行工具: {tc.name} …")
    result = handle_tool_call(tc, task_id=task_id)
    content = result.content
    if len(content) > 400:
        content = content[:400] + "…"
    symbol = "✅" if not result.is_error else "❌"
    print(f"  {symbol} 工具返回 ({len(result.content)} bytes): {content}")
    return result


def main() -> None:
    usecase.clear_store()
    requirement.clear_store()

    client = LiveLLMClient()
    task_id = "demo-live-001"

    ctx = AgentContext(
        task_id=task_id,
        phase="1",
        agent_name="analyst",
        agent_role="Requirements Engineer",
        system_prompt=get_system_prompt("analyst"),
        user_task=(
            "Analyze this requirement and create a complete structured specification:\n\n"
            "# 电商平台多币种订单功能\n\n"
            "用户需要以外币查看订单金额并完成下单。系统需要：\n"
            "1. 支持用户选择外币(如USD)作为展示币种\n"
            "2. 获取实时汇率进行换算\n"
            "3. 显示换算后的外币金额\n"
            "4. 创建订单(同时记录人民币金额和展示币种金额)\n"
            "5. 实际扣款按人民币执行\n\n"
            "Steps:\n"
            "1. usecase_create: Create L0 use case\n"
            "2. requirement_create: Create 4 FRs + 1 NFR\n"
            "3. requirement_create_ac: Create Lean ACs (quantifiable then)\n"
            "4. usercase_upgrade: Upgrade to L1 with alternative flows\n"
            "5. Summarize all artifacts"
        ),
        available_tools=[
            t for t in PHASE_1_TOOLS
            if t.name not in ("requirement_request_clarification", "complexity_assess")
        ],
        tool_handler=lambda tc: live_tool_handler(tc, task_id=task_id),
        model="deepseek-v4-flash",
        max_tool_rounds=10,
    )

    print("╔════════════════════════════════════════════════════════════════╗")
    print("║  DevFlow 实时运行演示 — Phase 1 需求工程 (Analyst Agent)        ║")
    print("╚════════════════════════════════════════════════════════════════╝")

    start = time.time()
    result = AgentLoop(client).run(ctx)
    elapsed = time.time() - start

    print(f"\n  {'═' * 62}")
    if is_ok(result):
        ar = result.data
        ucs = usecase.list_all()
        reqs = requirement.list_reqs()
        total_acs = sum(len(r.acceptance_criteria) for r in reqs)
        print(f"  ✅ Phase 1 完成: {len(ucs)} 用例, {len(reqs)} 条 FR/NFR, {total_acs} 条 AC")
        print(f"  📊 Token: {ar.tokens_used} | 工具调用: {len(ar.tool_calls_made)} 次 | 耗时: {elapsed:.1f}s")
        print(f"  {'─' * 62}")
        for uc in ucs:
            print(f"     UC: {uc.name} ({uc.level.value}) — {len(uc.basic_flow)} 主流程步骤, "
                  f"{len(uc.alternative_flows)} 备选流程")
        for r in reqs:
            print(f"     {r.req_id}: {r.description[:58]}… ({len(r.acceptance_criteria)} ACs)")
        print(f"  {'─' * 62}")
        print(f"  🏁 Agent 最终回复:\n")
        for line in ar.final_response.splitlines():
            print(f"    {line}")
    else:
        print(f"  ❌ Phase 1 失败: {result.message}")


if __name__ == "__main__":
    main()
