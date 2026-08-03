# Skill: developer-phase4 — Interface-First Code Generation

## Name
developer-phase4

## Purpose
Generate code as patches from architecture specs and use cases. Implement by interface contract, verify by use case. Exception paths first, then happy path.

## Input
- Phase 3 architecture (interface contracts, component decomposition, ADRs)
- Phase 1 use cases (UC basic flow + alternative flows)
- Knowledge context (code patterns, known bugs from negative index)

## Output
- Feature branch (feature/devflow-{task_id})
- Unified diff patch (git format-patch)
- Compilation verification (syntax check, type check, build)
- SAST + dependency CVE scan results
- Self-review report (checked against all UC flows)
- Pull request (linked to UCs)

## Implementation Rules
1. Implement by interface contract, verify by use case
2. Exception paths first (catch, fallback, timeout), then happy path
3. Each component is one commit
4. Each commit message: which interface, which use case
5. Self-review before PR: check against ALL UC flows (basic + alternative)

## Three Lines of Defense
```
Line 1 (Developer): Self-review → each UC flow checked
Line 2 (CI):        Compile + SAST + existing tests no regression
Line 3 (QA):        Independent review, test quality, AC verification
```

## Tools Used
| Tool | Purpose |
|------|---------|
| code.create_branch | Feature branch (idempotent) |
| code.generate_patch | Diffusion patch from spec+UC |
| compiler.check_syntax | AST parse validation |
| compiler.type_check | mypy/pyright |
| compiler.build | Full build + artifact hash |
| compiler.static_analysis | SAST + lint + security |
| compiler.dependency_scan | CVE + license check |
| code.self_review | Check against all UC flows |
| code.apply_patch | git apply → commit (auto-UC linkage) |
| code.create_pr | PR creation (idempotent, auto-UC linkage) |

## Security Boundary
- Terminal sandbox isolation
- No push to main
- No read of real credentials
- Feature branch writes only
