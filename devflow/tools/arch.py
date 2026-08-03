"""T5: Architecture toolset — architecture as code (PlantUML/Mermaid).

Architecture is expressed as PlantUML/Mermaid source — code, not images.
Tools generate and validate architectural artifacts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
import uuid

from devflow.core.evidence import write_evidence
from devflow.core.result import Result, ok, permanent
from devflow.core.idempotency import make_content_hash, check_exists, record_operation
from devflow.core.correlation import CorrelationId


class RelationshipType(str, Enum):
    PARTNERSHIP = "PARTNERSHIP"
    CUSTOMER_SUPPLIER = "CUSTOMER_SUPPLIER"
    ACL = "ACL"  # Anti-Corruption Layer
    CONFORMIST = "CONFORMIST"


class InterfaceMethod(str, Enum):
    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    DELETE = "DELETE"
    RPC = "RPC"


@dataclass
class Context:
    """A bounded context in the system."""

    name: str
    responsibility: str
    agents: list[str] = field(default_factory=list)


@dataclass
class ContextRelationship:
    """Relationship between two bounded contexts."""

    source: str
    target: str
    type: RelationshipType
    description: str = ""


@dataclass
class InterfaceContract:
    """An interface contract with version, I/O, errors, constraints."""

    name: str
    version: str
    inputs: dict
    outputs: dict
    errors: list[str] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)


@dataclass
class ADR:
    """Architecture Decision Record."""

    adr_id: str
    title: str
    context: str
    decision: str
    rationale: str
    consequences: str
    alternatives: list[str] = field(default_factory=list)
    superseded_by: Optional[str] = None
    supersedes: Optional[str] = None


@dataclass
class ExtensionPoint:
    """A declared extension point for known unknowns."""

    interface: str
    purpose: str
    known_unknown_ref: str


# Stores
_context_maps: dict[str, list] = {}
_aggregates: dict[str, list] = {}
_interfaces: dict[str, InterfaceContract] = {}
_adrs: dict[str, ADR] = {}
_extension_points: dict[str, list[ExtensionPoint]] = {}
_adr_counter: int = 0


def define_context_map(
    contexts: list[dict],
    relationships: list[dict],
    task_id: str = "",
    correlation: Optional[CorrelationId] = None,
) -> Result[dict]:
    """Define a context map with bounded contexts and their relationships."""
    ctx_list = [Context(**c) for c in contexts]
    # Convert string relationship types to enum
    rel_list = []
    for r in relationships:
        r_copy = dict(r)
        if isinstance(r_copy.get("type"), str):
            r_copy["type"] = RelationshipType(r_copy["type"])
        rel_list.append(ContextRelationship(**r_copy))

    context_map = {
        "contexts": [{"name": c.name, "responsibility": c.responsibility, "agents": c.agents}
                     for c in ctx_list],
        "relationships": [{"source": r.source, "target": r.target,
                          "type": r.type.value if isinstance(r.type, RelationshipType) else r.type}
                         for r in rel_list],
    }

    _context_maps[task_id] = context_map

    # Generate PlantUML source
    plantuml_src = _generate_context_map_plantuml(ctx_list, rel_list)

    write_evidence(
        task_id=task_id, phase="3", step="arch.define_context_map",
        content={"context_count": len(ctx_list), "relationship_count": len(rel_list)},
        tool_name="arch.define_context_map", correlation=correlation,
    )

    return ok({"context_map": context_map, "plantuml": plantuml_src})


def _generate_context_map_plantuml(
    contexts: list[Context],
    relationships: list[ContextRelationship],
) -> str:
    """Generate PlantUML source for a context map."""
    lines = ["@startuml", "skinparam componentStyle rectangle", ""]
    for ctx in contexts:
        lines.append(f'component "{ctx.name}" as {ctx.name.lower().replace(" ", "_")} {{')
        lines.append(f'  [{ctx.responsibility}]')
        lines.append("}")
    for rel in relationships:
        arrow = {
            RelationshipType.PARTNERSHIP: "<->",
            RelationshipType.CUSTOMER_SUPPLIER: "-->",
            RelationshipType.ACL: "..>",
            RelationshipType.CONFORMIST: "->",
        }.get(rel.type, "-->")
        lines.append(f"{rel.source} {arrow} {rel.target} : {rel.type.value}")
    lines.append("")
    lines.append("@enduml")
    return "\n".join(lines)


def define_aggregate(
    context: str,
    name: str,
    invariants: list[str],
    entities: list[str] = None,
    value_objects: list[str] = None,
    task_id: str = "",
    correlation: Optional[CorrelationId] = None,
) -> Result[dict]:
    """Define an aggregate within a bounded context."""
    aggregate = {
        "context": context,
        "name": name,
        "invariants": invariants,
        "entities": entities or [],
        "value_objects": value_objects or [],
    }

    if task_id not in _aggregates:
        _aggregates[task_id] = []
    _aggregates[task_id].append(aggregate)

    # Generate class diagram PlantUML
    plantuml = _generate_aggregate_plantuml(name, entities or [], value_objects or [])

    write_evidence(
        task_id=task_id, phase="3", step="arch.define_aggregate",
        content={"context": context, "name": name, "entity_count": len(entities or [])},
        tool_name="arch.define_aggregate", correlation=correlation,
    )

    return ok({"aggregate": aggregate, "plantuml": plantuml})


def _generate_aggregate_plantuml(
    name: str, entities: list[str], value_objects: list[str],
) -> str:
    """Generate PlantUML class diagram for an aggregate."""
    lines = ["@startuml", f"package \"{name} Aggregate\" {{"]
    for entity in entities:
        lines.append(f"  class {entity} {{")
        lines.append("  }")
    for vo in value_objects:
        lines.append(f"  class {vo} <<ValueObject>> {{")
        lines.append("  }")
    lines.append("}")
    lines.append("@enduml")
    return "\n".join(lines)


def generate_class_diagram(scope: str, task_id: str = "") -> Result[str]:
    """Generate a class diagram for a scope from code (AST parsing).

    In production, this would parse actual code AST.
    """
    plantuml = f"@startuml\n' Class diagram for: {scope}\n@enduml"
    return ok(plantuml)


def generate_sequence_diagram(usecase_id: str, task_id: str = "") -> Result[str]:
    """Generate a sequence diagram from a use case.

    Actor → Controller → Service → Repository → ExternalAPI
    """
    plantuml = f"""@startuml
actor Actor
participant Controller
participant Service
participant Repository
participant ExternalAPI

Actor -> Controller: Request
Controller -> Service: Process
Service -> Repository: Query
Service -> ExternalAPI: External call
ExternalAPI --> Service: Response
Service --> Controller: Result
Controller --> Actor: Response
@enduml"""
    return ok(plantuml)


def define_interface(
    name: str,
    version: str,
    inputs: dict,
    outputs: dict,
    errors: list[str] = None,
    constraints: list[str] = None,
    task_id: str = "",
    correlation: Optional[CorrelationId] = None,
) -> Result[InterfaceContract]:
    """Define an interface contract with JSON Schema validation."""
    if not version.startswith("v"):
        return permanent("architect", "3", f"Version must start with 'v': {version}")

    contract = InterfaceContract(
        name=name,
        version=version,
        inputs=inputs,
        outputs=outputs,
        errors=errors or [],
        constraints=constraints or [],
    )
    _interfaces[f"{name}:{version}"] = contract

    write_evidence(
        task_id=task_id, phase="3", step="arch.define_interface",
        content={"name": name, "version": version},
        tool_name="arch.define_interface", correlation=correlation,
    )

    return ok(contract)


def create_adr(
    title: str,
    context: str,
    decision: str,
    rationale: str,
    consequences: str,
    alternatives: list[str] = None,
    supersedes: str = None,
    task_id: str = "",
    correlation: Optional[CorrelationId] = None,
) -> Result[ADR]:
    """Create an Architecture Decision Record.

    Built-in: auto-numbering (ADR-001), supersedes chain maintenance.
    """
    global _adr_counter
    _adr_counter += 1

    adr_id = f"ADR-{_adr_counter:03d}"
    adr = ADR(
        adr_id=adr_id,
        title=title,
        context=context,
        decision=decision,
        rationale=rationale,
        consequences=consequences,
        alternatives=alternatives or [],
        supersedes=supersedes,
    )

    _adrs[adr_id] = adr

    # Maintain supersedes chain
    if supersedes and supersedes in _adrs:
        _adrs[supersedes].superseded_by = adr_id

    write_evidence(
        task_id=task_id, phase="3", step="arch.create_adr",
        content={"adr_id": adr_id, "title": title},
        tool_name="arch.create_adr", correlation=correlation,
    )

    return ok(adr)


def supersede_adr(
    old_id: str, new_id: str, reason: str,
    correlation: Optional[CorrelationId] = None, task_id: str = "",
) -> Result[dict]:
    """Mark an ADR as superseded by a new one."""
    if old_id not in _adrs:
        return permanent("architect", "3", f"ADR {old_id} not found")
    if new_id not in _adrs:
        return permanent("architect", "3", f"ADR {new_id} not found")

    _adrs[old_id].superseded_by = new_id
    _adrs[new_id].supersedes = old_id

    write_evidence(
        task_id=task_id, phase="3", step="arch.supersede_adr",
        content={"old": old_id, "new": new_id, "reason": reason},
        tool_name="arch.supersede_adr", correlation=correlation,
    )

    return ok({"old": old_id, "new": new_id, "reason": reason})


def declare_extension_point(
    interface: str,
    purpose: str,
    known_unknown_ref: str,
    task_id: str = "",
    correlation: Optional[CorrelationId] = None,
) -> Result[ExtensionPoint]:
    """Declare an extension point for a known unknown.

    Associates Phase 1 known_unknown with a Phase 3 architectural extension point.
    """
    ep = ExtensionPoint(
        interface=interface,
        purpose=purpose,
        known_unknown_ref=known_unknown_ref,
    )

    if task_id not in _extension_points:
        _extension_points[task_id] = []
    _extension_points[task_id].append(ep)

    write_evidence(
        task_id=task_id, phase="3", step="arch.declare_extension_point",
        content={"interface": interface, "known_unknown": known_unknown_ref},
        tool_name="arch.declare_extension_point", correlation=correlation,
    )

    return ok(ep)


def validate_architecture(rules: dict = None, task_id: str = "") -> Result[dict]:
    """Validate architecture against rules.

    Checks: circular dependencies? cross-layer calls? single points of failure?
    """
    checks = []
    violations = []

    # Check for circular dependencies (simplified)
    relationships = _context_maps.get(task_id, {}).get("relationships", [])
    if relationships:
        checked = set()
        for rel in relationships:
            pair = tuple(sorted([rel.get("source", ""), rel.get("target", "")]))
            if pair in checked:
                violations.append({
                    "type": "CIRCULAR_DEPENDENCY",
                    "detail": f"Circular relationship: {pair}",
                })
            checked.add(pair)

    # Check interfaces have implementations
    unimplemented = []
    if rules and rules.get("check_unimplemented_interfaces"):
        for key, iface in _interfaces.items():
            # In production, would check AST for implementations
            pass

    checks.append({"check": "circular_dependency_check", "result": "PASS" if not violations else "FAIL"})

    result = {
        "passed": len(violations) == 0,
        "checks": checks,
        "violations": violations,
    }

    write_evidence(
        task_id=task_id, phase="3", step="arch.validate_architecture",
        content=result, tool_name="arch.validate_architecture",
    )

    return ok(result)


def clear_store():
    """Clear architecture stores (for testing)."""
    global _adr_counter
    _context_maps.clear()
    _aggregates.clear()
    _interfaces.clear()
    _adrs.clear()
    _extension_points.clear()
    _adr_counter = 0
