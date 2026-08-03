# Skill: qa-phase5 — Verification & Issue Classification

## Name
qa-phase5

## Purpose
Verify code against all acceptance criteria using test execution, mutation testing, and regression validity. Classify failures using the issue classification decision tree.

## Input
- Phase 4 output (code patches, PR)
- Phase 1 output (use cases, ACs)
- Test execution results
- Coverage reports

## Output
- Test execution report (passed/failed/flaky/skipped)
- Code coverage delta (before/after)
- Mutation testing score
- Regression validity report
- AC verification results (one per AC)
- Issue classifications (USECASE_GAP / CODE_BUG / BUG_IN_USECASE / ENV_ISSUE)
- Final task verdict (PASS / FAIL_RETRY / NEED_HUMAN)

## Issue Classification Decision Tree
```
验证失败
    │
    ▼
场景在用例中有描述吗？
    ├── 否 → USECASE_GAP → 回到 Phase 1
    └── 是 → 代码符合用例吗？
              ├── 是 → BUG_IN_USECASE → 回到 Phase 1
              └── 否 → CODE_BUG → 回到 Phase 4
环境问题？ → ENV_ISSUE
系统级冲突？ → INTEGRATION_BUG / PRE_EXISTING
```

## Test Quality Gates
- Mutation score ≥ 0.5 (G5.1)
- AC coverage = 100% (G5.2)
- Regression validity: all new tests detect revert (G5.3)
- Traceability complete (G5.4, CRITICAL)

## Tools Used
| Tool | Purpose |
|------|---------|
| test.run | Execute test suite |
| test.coverage | Before/after coverage delta |
| test.mutation_test | cosmic-ray/mutmut mutation score |
| test.regression_validity | git revert → tests MUST fail |
| test.ac_coverage | AC→test coverage matrix |
| test.integration_run | All affected module integration tests |
| verify.ac | Single AC verification |
| verify.classify_issue | Decision tree classification |
| verify.verdict | Aggregate → PASS/FAIL_RETRY/NEED_HUMAN |

## Key Design: Independent from Developer
- Different runtime (QwenPaw vs Hermes)
- Different permissions (read+comment vs write)
- Independent verification, not trust-based
