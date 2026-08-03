# Skill: architect-phase3 — Top-Down Architecture Design

## Name
architect-phase3

## Purpose
Design system architecture top-down from context map to data model, with interface contracts and Architecture Decision Records for every non-trivial decision.

## Input
- Phase 1 output (use cases, requirements, acceptance criteria)
- Phase 2 output (PoC results, feasibility report, token cost model)
- Known unknowns from Phase 1
- Knowledge context (architecture patterns, known pitfalls)

## Output
- Context map (PlantUML source + relationships)
- Component decomposition (aggregates, entities, value objects)
- Interface contracts (JSON Schema validated, versioned)
- Architecture Decision Records (ADR-001, ADR-002, ...)
- Extension points mapped to known unknowns
- Architecture validation report (no circular deps, etc.)

## Design Levels
```
Level 0: System Context (external systems + system boundary)
Level 1: Containers/Services (service decomposition + dependencies)
Level 2: Components (internal component breakdown per service)
Level 3: Interface Contracts (I/O + errors per interface)
Level 4: Data Model (entities + relationships)
```

## Tools Used
| Tool | Purpose |
|------|---------|
| arch.define_context_map | Bounded contexts + DDD relationships |
| arch.define_aggregate | Aggregate root + entities + invariants |
| arch.generate_class_diagram | AST→PlantUML class diagram |
| arch.generate_sequence_diagram | UseCase→sequence diagram |
| arch.define_interface | Versioned interface contract (I/O/errors/constraints) |
| arch.create_adr | Architecture Decision Record (auto-numbered) |
| arch.declare_extension_point | Map known unknowns to extension points |
| arch.validate_architecture | Check circular deps, cross-layer calls, SPOF |

## ADR Format
Each ADR MUST include: Title, Context, Decision, Rationale, Consequences, Alternatives.
Auto-numbered (ADR-001). Supersedes chain maintained.

## Failure Handling
- Circular dependency detected → redesign before proceeding
- Interface version conflict → supersede and update dependents
- Extension point not mapped → flag as gap, return to Phase 1

## Reuse Value
Architecture patterns are domain-agnostic. Context maps and interface contracts
are reusable across projects with similar bounded context structures.
