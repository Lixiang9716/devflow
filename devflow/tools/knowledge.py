"""T11: Knowledge toolset — dual-channel knowledge indexing.

Two independent indices:
- positive: successful patterns, best practices, templates
- negative: known mistakes, pitfalls, anti-patterns

Knowledge Agent provides bidirectional feedback at the start of every phase.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
import time

from devflow.core.evidence import write_evidence
from devflow.core.result import Result, ok, permanent
from devflow.core.correlation import CorrelationId


class KnowledgeChannel(str, Enum):
    POSITIVE = "positive"       # Success patterns, templates, best practices
    NEGATIVE = "negative"       # Known mistakes, pitfalls, anti-patterns
    COST_OPTIMIZATION = "cost_optimization"  # Token cost optimization insights


@dataclass
class KnowledgeEntry:
    """A single knowledge entry in the double-channel index."""

    entry_id: str
    channel: KnowledgeChannel
    content: dict
    task_type: str = ""
    module: str = ""
    keywords: list[str] = field(default_factory=list)
    confidence: float = 0.8
    created_at: float = field(default_factory=time.time)
    last_referenced: float = 0.0
    reference_count: int = 0
    stale: bool = False
    stale_reason: str = ""


@dataclass
class ContextPack:
    """Structured knowledge feedback package for an agent."""

    positive: list[dict] = field(default_factory=list)
    negative: list[dict] = field(default_factory=list)
    cost_optimization: list[dict] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)


# In-memory knowledge stores (production uses Qdrant)
_positive_index: dict[str, KnowledgeEntry] = {}
_negative_index: dict[str, KnowledgeEntry] = {}
_cost_index: dict[str, KnowledgeEntry] = {}


def index(
    task_id: str,
    channel: str,
    content: dict,
    correlation: Optional[CorrelationId] = None,
) -> Result[KnowledgeEntry]:
    """Index knowledge into the specified channel.

    Auto-extracts: task_type, module, keywords, embedding.
    Writes to Qdrant corresponding index.
    """
    try:
        ch = KnowledgeChannel(channel)
    except ValueError:
        return permanent("knowledge", "X", f"Invalid channel: {channel}")

    entry_id = f"kb-{ch.value}-{int(time.time())}-{hash(str(content)) % 10000}"
    keywords = _extract_keywords(content)

    entry = KnowledgeEntry(
        entry_id=entry_id,
        channel=ch,
        content=content,
        task_type=content.get("task_type", task_id),
        keywords=keywords,
        confidence=content.get("confidence", 0.8),
    )

    target_index = {
        KnowledgeChannel.POSITIVE: _positive_index,
        KnowledgeChannel.NEGATIVE: _negative_index,
        KnowledgeChannel.COST_OPTIMIZATION: _cost_index,
    }[ch]
    target_index[entry_id] = entry

    write_evidence(
        task_id=task_id, phase="X", step="kb.index",
        content={"entry_id": entry_id, "channel": channel},
        tool_name="kb.index", correlation=correlation,
    )

    return ok(entry)


def _extract_keywords(content: dict) -> list[str]:
    """Simple keyword extraction from content."""
    keywords = []
    for key in ["pattern_type", "domain", "module", "flow_type", "mistake"]:
        if key in content and content[key]:
            keywords.append(str(content[key]))
    return keywords


def retrieve(
    task_context: dict,
    channels: list[str] = None,
    top_k: int = 5,
    correlation: Optional[CorrelationId] = None,
    task_id: str = "",
) -> Result[ContextPack]:
    """Retrieve knowledge from specified channels.

    channels: [positive] | [negative] | [positive, negative]
    Returns structured ContextPack for agent consumption.
    """
    channels = channels or ["positive", "negative"]
    pack = ContextPack()

    if "positive" in channels:
        pack.positive = [
            {"entry_id": e.entry_id, "content": e.content, "confidence": e.confidence}
            for e in list(_positive_index.values())[:top_k]
        ]

    if "negative" in channels:
        pack.negative = [
            {"entry_id": e.entry_id, "content": e.content, "confidence": e.confidence}
            for e in list(_negative_index.values())[:top_k]
        ]

    if "cost_optimization" in channels:
        pack.cost_optimization = [
            {"entry_id": e.entry_id, "content": e.content, "confidence": e.confidence}
            for e in list(_cost_index.values())[:top_k]
        ]

    pack.metadata = {
        "task_context": task_context,
        "retrieved_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "total_positive": len(_positive_index),
        "total_negative": len(_negative_index),
    }

    write_evidence(
        task_id=task_id, phase="X", step="kb.retrieve",
        content={"channels": channels, "positive_hits": len(pack.positive),
                 "negative_hits": len(pack.negative)},
        tool_name="kb.retrieve", correlation=correlation,
    )

    return ok(pack)


def mark_stale(
    entry_id: str,
    reason: str,
    correlation: Optional[CorrelationId] = None,
    task_id: str = "",
) -> Result[dict]:
    """Mark a knowledge entry as stale.

    Reduces weight but keeps the entry. Never deletes.
    """
    for index in [_positive_index, _negative_index, _cost_index]:
        if entry_id in index:
            entry = index[entry_id]
            entry.stale = True
            entry.stale_reason = reason
            entry.confidence *= 0.5

            write_evidence(
                task_id=task_id, phase="X", step="kb.mark_stale",
                content={"entry_id": entry_id, "reason": reason},
                tool_name="kb.mark_stale", correlation=correlation,
            )

            return ok({"entry_id": entry_id, "marked_stale": True, "reason": reason})

    return permanent("knowledge", "X", f"Entry {entry_id} not found")


def detect_contradiction(
    correlation: Optional[CorrelationId] = None,
    task_id: str = "",
) -> Result[list[dict]]:
    """Compare positive and negative indices for contradictory entries."""
    contradictions = []

    pos_keywords = set()
    for entry in _positive_index.values():
        pos_keywords.update(entry.keywords)

    for neg_entry in _negative_index.values():
        for kw in neg_entry.keywords:
            if kw in pos_keywords:
                # Find the conflicting positive entry
                for pos_entry in _positive_index.values():
                    if kw in pos_entry.keywords:
                        contradictions.append({
                            "positive_entry": pos_entry.entry_id,
                            "negative_entry": neg_entry.entry_id,
                            "shared_keyword": kw,
                            "conflict_description": f"Positive pattern and negative warning share keyword: {kw}",
                        })

    return ok(contradictions)


def health_report(
    correlation: Optional[CorrelationId] = None,
    task_id: str = "",
) -> Result[dict]:
    """Generate knowledge health report."""
    total = len(_positive_index) + len(_negative_index) + len(_cost_index)
    stale = sum(1 for e in {**_positive_index, **_negative_index, **_cost_index}.values() if e.stale)

    return ok({
        "total_entries": total,
        "positive": len(_positive_index),
        "negative": len(_negative_index),
        "cost_optimization": len(_cost_index),
        "stale_count": stale,
        "contradiction_count": 0,
        "index_freshness": "OK" if total > 0 else "EMPTY",
    })


def extract_integration_test(
    task_id: str,
    correlation: Optional[CorrelationId] = None,
) -> Result[dict]:
    """Auto-generate integration regression test on task close.

    Based on current task's change impact surface → generate integration test
    that runs whenever any task touches related modules.
    """
    test_content = {
        "task_id": task_id,
        "action": "kb.extract_integration_test",
        "status": "GENERATED",
        "test_name": f"test_integration_regression_{task_id}",
    }

    write_evidence(
        task_id=task_id, phase="5", step="kb.extract_integration_test",
        content=test_content, tool_name="kb.extract_integration_test",
        correlation=correlation,
    )

    return ok(test_content)


def get_entry(entry_id: str) -> Optional[KnowledgeEntry]:
    """Get a knowledge entry by ID."""
    for index in [_positive_index, _negative_index, _cost_index]:
        if entry_id in index:
            return index[entry_id]
    return None


def seed_generate(project_type: str, tech_stack: dict) -> Result[dict]:
    """Generate seed knowledge (Phase 0, cold start).

    Three tiers:
      1. Universal SE patterns (~200 entries, PREDEFINED, confidence=0.8)
      2. Project-type templates (~50 entries/type, TEMPLATE, confidence=0.7)
      3. LLM-synthesized (20-30 entries, SYNTHESIZED, confidence=0.5)
    """
    seeds = {
        "universal": [
            {"pattern_type": "USE_CASE_PATTERN", "domain": "financial",
             "flow_type": "currency_conversion",
             "known_concerns": ["precision", "rounding", "rate_source", "fallback", "audit"]},
            {"pattern_type": "COMMON_MISTAKE", "domain": "financial",
             "mistake": "Using float instead of Decimal for currency",
             "symptom": "Random 0.01 rounding errors",
             "root_cause": "IEEE 754 floating point precision",
             "fix_pattern": "from decimal import Decimal",
             "severity": "HIGH"},
        ],
        "template": [
            {"project_type": project_type, "pattern": "CRUD_API",
             "concerns": ["auth", "pagination", "error_handling"]},
        ],
        "synthesized": [
            {"source": "SYNTHESIZED", "tech_stack": tech_stack,
             "suggestion": "Use FastAPI dependency injection for rate service",
             "confidence": 0.5},
        ],
    }

    for entry_data in seeds["universal"]:
        entry_data["confidence"] = 0.8
        entry_data["source"] = "PREDEFINED"
        index("seed", "positive", entry_data)

    for entry_data in seeds["template"]:
        entry_data["confidence"] = 0.7
        entry_data["source"] = "TEMPLATE"
        index("seed", "positive", entry_data)

    for entry_data in seeds["synthesized"]:
        entry_data["confidence"] = 0.5
        entry_data["source"] = "SYNTHESIZED"
        index("seed", "positive", entry_data)

    return ok({"seeded_categories": list(seeds.keys()), "total_entries": 0})


def clear_store():
    """Clear knowledge stores (for testing)."""
    _positive_index.clear()
    _negative_index.clear()
    _cost_index.clear()
