"""Agent role definitions — 7 agents across 5 phases.

Each agent has phase-specific responsibilities, runtime, and tool access.
Agents communicate through MinIO files, Matrix rooms, and Knowledge indices — not direct conversation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Callable
import time

from devflow.core.result import Result, ok, permanent
from devflow.core.correlation import CorrelationId, new_correlation


class AgentRuntime(str, Enum):
    """Agent runtime environment."""

    OPEN_CLAW = "OpenClaw"  # Full LLM reasoning
    HERMES = "Hermes"       # Terminal sandbox, autonomous coding
    QWEN_PAW = "QwenPaw"    # Lightweight, high determinism


@dataclass
class AgentConfig:
    """Configuration for a single agent."""

    name: str
    role: str
    runtime: AgentRuntime
    phases: list[str]
    tools: list[str]
    permissions: list[str] = field(default_factory=list)
    crd_file: str = ""


# ── Agent Pipeline Orchestrator ────────────────────────────────────


class PipelinePhase(str, Enum):
    """Five-phase gated pipeline."""

    PHASE_1 = "1"  # Requirements engineering
    PHASE_2 = "2"  # Feasibility study
    PHASE_3 = "3"  # Architecture design
    PHASE_4 = "4"  # Implementation
    PHASE_5 = "5"  # Verification


@dataclass
class Task:
    """A task flowing through the 5-phase pipeline."""

    task_id: str
    title: str
    description: str
    correlation: CorrelationId
    complexity: str = "L"  # S | M | L | XL
    created_at: float = field(default_factory=time.time)
    current_phase: str = "1"
    status: str = "PENDING"  # PENDING | RUNNING | PASS | FAIL_RETRY | NEED_HUMAN | CLOSED

    # Phase outputs
    usecases: list = field(default_factory=list)
    requirements: list = field(default_factory=list)
    acceptance_criteria: list = field(default_factory=list)
    poc_experiments: list = field(default_factory=list)
    architecture: dict = field(default_factory=dict)
    adrs: list = field(default_factory=list)
    patches: list = field(default_factory=list)
    test_results: list = field(default_factory=list)
    issues: list = field(default_factory=list)
    verdict: dict = field(default_factory=dict)


# Predefined agent configurations per the plan
AGENT_DEFINITIONS = {
    "analyst": AgentConfig(
        name="devflow-analyst",
        role="Requirements Engineer / Business Analyst",
        runtime=AgentRuntime.OPEN_CLAW,
        phases=["1", "5"],
        tools=["T1", "T2", "T9"],
        permissions=["github(read)"],
        crd_file="devflow-analyst.yaml",
    ),
    "architect": AgentConfig(
        name="devflow-architect",
        role="Software Architect",
        runtime=AgentRuntime.OPEN_CLAW,
        phases=["2", "3"],
        tools=["T3", "T5"],
        permissions=["github(read)"],
        crd_file="devflow-architect.yaml",
    ),
    "developer": AgentConfig(
        name="devflow-developer",
        role="Software Developer",
        runtime=AgentRuntime.HERMES,
        phases=["4", "5"],
        tools=["T6", "T7"],
        permissions=["github(write)", "feature_branch_only"],
        crd_file="devflow-developer.yaml",
    ),
    "qa": AgentConfig(
        name="devflow-qa",
        role="Test Engineer / QA Auditor",
        runtime=AgentRuntime.QWEN_PAW,
        phases=["4", "5"],
        tools=["T8", "T9"],
        permissions=["github(read)", "github(pr_comment)", "cicd(read)"],
        crd_file="devflow-qa.yaml",
    ),
    "devops": AgentConfig(
        name="devflow-ops",
        role="DevOps Engineer / SRE",
        runtime=AgentRuntime.QWEN_PAW,
        phases=["2", "3", "4", "5"],
        tools=["T7", "T8"],
        permissions=["cicd(write)", "monitor(read)"],
        crd_file="devflow-ops.yaml",
    ),
    "knowledge": AgentConfig(
        name="devflow-librarian",
        role="Knowledge Manager / Process Engineer",
        runtime=AgentRuntime.OPEN_CLAW,
        phases=["1", "2", "3", "4", "5"],
        tools=["T11"],
        permissions=["github(write, docs_only)", "qdrant(write)"],
        crd_file="devflow-librarian.yaml",
    ),
    "attacker": AgentConfig(
        name="devflow-attacker",
        role="Adversarial Tester",
        runtime=AgentRuntime.OPEN_CLAW,
        phases=["1", "3"],
        tools=["T1(read)", "T2(read)"],
        permissions=["read_only"],
        crd_file="devflow-attacker.yaml",
    ),
}


def get_agent(agent_id: str) -> Optional[AgentConfig]:
    """Get agent configuration by ID."""
    return AGENT_DEFINITIONS.get(agent_id)


def get_phase_agents(phase: str) -> list[AgentConfig]:
    """Get all agents active in a given phase."""
    return [a for a in AGENT_DEFINITIONS.values() if phase in a.phases]


def get_agent_phase_responsibilities() -> dict:
    """Get the agent-phase responsibility matrix from the plan."""
    return {
        "Analyst":   {"1": "需求分析、用例设计、AC定义", "2": "经济可行性(成本模型)", "5": "Issue分类(用例缺口)"},
        "Architect": {"2": "技术调研、PoC、风险评估", "3": "自顶向下架构设计、接口契约、ADR"},
        "Developer": {"4": "按接口实现代码、自审查", "5": "修复CODE_BUG"},
        "QA":        {"4": "独立代码审查", "5": "AC验证、测试质量、Issue分类"},
        "DevOps":    {"2": "PoC环境搭建", "3": "基础设施设计", "4": "CI管道配置", "5": "部署、健康检查、Eval-G6"},
        "Knowledge": {"1": "检索正向/反向提示", "2": "检索技术调研历史", "3": "检索架构模式",
                      "4": "检索代码模式、已知错误", "5": "提取经验入库"},
        "Attacker":  {"1": "对抗性用例验证", "3": "架构攻击(XL任务)"},
        "Human":     {"1": "澄清需求歧义", "2": "Go/No-Go决策", "3": "架构评审", "5": "裁决模糊Issue"},
    }
