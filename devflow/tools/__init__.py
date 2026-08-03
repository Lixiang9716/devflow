"""DevFlow tool groups T1-T12."""

# T1: UseCase
from devflow.tools.usecase import (
    create as usecase_create,
    upgrade as usecase_upgrade,
    add_alternative as usecase_add_alternative,
    declare_known_unknown as usecase_declare_known_unknown,
    link_to_requirement as usecase_link_to_requirement,
    link_to_code as usecase_link_to_code,
    trace as usecase_trace,
    validate as usecase_validate,
    get as get_usecase,
    UseCase, UseCaseLevel,
)

# T2: Requirement
from devflow.tools.requirement import (
    create as requirement_create,
    create_ac as requirement_create_ac,
    traceability_matrix as requirement_traceability_matrix,
    request_clarification as requirement_request_clarification,
    Requirement, AcceptanceCriterion, ReqType, AcMethod,
)

# T3: PoC
from devflow.tools.poc import (
    create as poc_create,
    run as poc_run,
    record_result as poc_record_result,
    list_experiments as poc_list,
    compare as poc_compare,
    PoCExperiment, PoCConclusion,
)

# T4: Token
from devflow.tools.token import (
    record_call as token_record_call,
    estimate as token_estimate,
    report as token_report,
    budget_check as token_budget_check,
    budget_enforce as token_budget_enforce,
    anomaly_detect as token_anomaly_detect,
    trend as token_trend,
    TokenCall, TokenBudget,
)

# T5: Architecture
from devflow.tools.arch import (
    define_context_map as arch_define_context_map,
    define_aggregate as arch_define_aggregate,
    generate_class_diagram as arch_generate_class_diagram,
    generate_sequence_diagram as arch_generate_sequence_diagram,
    define_interface as arch_define_interface,
    create_adr as arch_create_adr,
    supersede_adr as arch_supersede_adr,
    declare_extension_point as arch_declare_extension_point,
    validate_architecture as arch_validate_architecture,
    ADR, InterfaceContract, ExtensionPoint,
)

# T6: Code/Patch
from devflow.tools.code_patch import (
    create_branch as code_create_branch,
    generate_patch as code_generate_patch,
    apply_patch as code_apply_patch,
    revert_patch as code_revert_patch,
    self_review as code_self_review,
    create_pr as code_create_pr,
    PatchResult, SelfReviewResult, PR,
)

# T7: Compiler
from devflow.tools.compiler import (
    check_syntax as compiler_check_syntax,
    type_check as compiler_type_check,
    build as compiler_build,
    static_analysis as compiler_static_analysis,
    dependency_scan as compiler_dependency_scan,
)

# T8: Test
from devflow.tools.test import (
    generate as test_generate,
    run as test_run,
    coverage as test_coverage,
    mutation_test as test_mutation_test,
    regression_validity as test_regression_validity,
    ac_coverage as test_ac_coverage,
    integration_run as test_integration_run,
    staging_smoke as test_staging_smoke,
)

# T9: Verify
from devflow.tools.verify import (
    verify_ac,
    classify_issue as verify_classify_issue,
    classify_integration as verify_classify_integration,
    verdict as verify_verdict,
    IssueType, Verdict, IssueClassification, TaskVerdict,
)

# T11: Knowledge
from devflow.tools.knowledge import (
    index as kb_index,
    retrieve as kb_retrieve,
    mark_stale as kb_mark_stale,
    detect_contradiction as kb_detect_contradiction,
    health_report as kb_health_report,
    extract_integration_test as kb_extract_integration_test,
    seed_generate as kb_seed_generate,
    KnowledgeChannel, KnowledgeEntry, ContextPack,
)

# T12: Crosscutting
from devflow.tools.crosscut import (
    verify_timeline,
    detect_skip,
    compare_tasks,
    assess_complexity,
    calculate_trust,
    decay_trust,
    detect_conflict,
    audit_feedback,
    system_regression_test,
    system_consistency_check,
    system_health_trend,
    ComplexityLevel, TimelineReport,
)

__all__ = [
    # T1
    "usecase_create", "usecase_upgrade", "usecase_add_alternative",
    "usecase_declare_known_unknown", "usecase_link_to_requirement",
    "usecase_link_to_code", "usecase_trace", "usecase_validate", "get_usecase",
    "UseCase", "UseCaseLevel",
    # T2
    "requirement_create", "requirement_create_ac", "requirement_traceability_matrix",
    "requirement_request_clarification", "Requirement", "AcceptanceCriterion", "ReqType", "AcMethod",
    # T3
    "poc_create", "poc_run", "poc_record_result", "poc_list", "poc_compare",
    "PoCExperiment", "PoCConclusion",
    # T4
    "token_record_call", "token_estimate", "token_report", "token_budget_check",
    "token_budget_enforce", "token_anomaly_detect", "token_trend",
    "TokenCall", "TokenBudget",
    # T5
    "arch_define_context_map", "arch_define_aggregate", "arch_generate_class_diagram",
    "arch_generate_sequence_diagram", "arch_define_interface", "arch_create_adr",
    "arch_supersede_adr", "arch_declare_extension_point", "arch_validate_architecture",
    "ADR", "InterfaceContract", "ExtensionPoint",
    # T6
    "code_create_branch", "code_generate_patch", "code_apply_patch",
    "code_revert_patch", "code_self_review", "code_create_pr",
    "PatchResult", "SelfReviewResult", "PR",
    # T7
    "compiler_check_syntax", "compiler_type_check", "compiler_build",
    "compiler_static_analysis", "compiler_dependency_scan",
    # T8
    "test_generate", "test_run", "test_coverage", "test_mutation_test",
    "test_regression_validity", "test_ac_coverage", "test_integration_run",
    "test_staging_smoke",
    # T9
    "verify_ac", "verify_classify_issue", "verify_classify_integration",
    "verify_verdict", "IssueType", "Verdict", "IssueClassification", "TaskVerdict",
    # T11
    "kb_index", "kb_retrieve", "kb_mark_stale", "kb_detect_contradiction",
    "kb_health_report", "kb_extract_integration_test", "kb_seed_generate",
    "KnowledgeChannel", "KnowledgeEntry", "ContextPack",
    # T12
    "verify_timeline", "detect_skip", "compare_tasks", "assess_complexity",
    "calculate_trust", "decay_trust", "detect_conflict", "audit_feedback",
    "system_regression_test", "system_consistency_check", "system_health_trend",
    "ComplexityLevel", "TimelineReport",
]
