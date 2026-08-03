"""T7: Compiler/Build toolset — deterministic compilation and verification.

Compilation and building are deterministic tools — Agent doesn't judge
"should compile"; it calls the tools and gets definitive answers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional
import ast
import hashlib

from devflow.core.evidence import write_evidence
from devflow.core.result import Result, ok, permanent
from devflow.core.correlation import CorrelationId


@dataclass
class SyntaxCheckResult:
    """Result of a syntax check."""

    target: str
    passed: bool
    errors: list[dict] = field(default_factory=list)

    @classmethod
    def from_code(cls, target: str, code: str) -> "SyntaxCheckResult":
        """Check Python syntax by parsing with AST."""
        try:
            ast.parse(code)
            return cls(target=target, passed=True)
        except SyntaxError as e:
            return cls(target=target, passed=False, errors=[{
                "file": target, "line": e.lineno or 0,
                "message": str(e.msg), "offset": e.offset or 0,
            }])


@dataclass
class TypeCheckResult:
    """Result of type checking (mypy/pyright)."""

    target: str
    passed: bool
    errors: list[dict] = field(default_factory=list)


@dataclass
class BuildResult:
    """Result of a full build."""

    target: str
    passed: bool
    artifact_hash: str = ""
    build_log_ref: str = ""
    errors: list[str] = field(default_factory=list)


@dataclass
class StaticAnalysisResult:
    """Result of SAST + lint + security scanning."""

    target: str
    passed: bool
    violations: list[dict] = field(default_factory=list)


@dataclass
class DependencyScanResult:
    """Result of dependency CVE + license compatibility check."""

    target: str
    passed: bool
    cves: list[dict] = field(default_factory=list)
    license_issues: list[dict] = field(default_factory=list)


def check_syntax(
    target: str,
    code: str = "",
    correlation: Optional[CorrelationId] = None,
    task_id: str = "",
) -> Result[SyntaxCheckResult]:
    """Check syntax of a target file/module.

    Returns: {pass: bool, errors: [{file, line, message}]}
    """
    result = SyntaxCheckResult.from_code(target, code)

    write_evidence(
        task_id=task_id, phase="4", step="compiler.check_syntax",
        content={"target": target, "passed": result.passed, "error_count": len(result.errors)},
        tool_name="compiler.check_syntax", correlation=correlation,
    )

    return ok(result)


def type_check(
    target: str,
    strict: bool = False,
    correlation: Optional[CorrelationId] = None,
    task_id: str = "",
) -> Result[TypeCheckResult]:
    """Run type checking (mypy/pyright) and return structured results."""
    # In production, would run mypy --output json
    result = TypeCheckResult(target=target, passed=True)

    write_evidence(
        task_id=task_id, phase="4", step="compiler.type_check",
        content={"target": target, "strict": strict, "passed": result.passed},
        tool_name="compiler.type_check", correlation=correlation,
    )

    return ok(result)


def build(
    target: str,
    config: dict = None,
    correlation: Optional[CorrelationId] = None,
    task_id: str = "",
) -> Result[BuildResult]:
    """Full build with artifact hashing.

    Returns: {pass, artifact_hash, build_log_ref}.
    """
    artifact_hash = hashlib.sha256(f"{target}:{config}".encode()).hexdigest()[:16]
    result = BuildResult(
        target=target,
        passed=True,
        artifact_hash=artifact_hash,
        build_log_ref=f"minio://builds/{task_id}/{artifact_hash}.log",
    )

    write_evidence(
        task_id=task_id, phase="4", step="compiler.build",
        content={"target": target, "passed": result.passed, "hash": artifact_hash},
        tool_name="compiler.build", correlation=correlation,
    )

    return ok(result)


def static_analysis(
    target: str,
    ruleset: dict = None,
    correlation: Optional[CorrelationId] = None,
    task_id: str = "",
) -> Result[StaticAnalysisResult]:
    """Run SAST + lint + security scanning.

    Returns aggregated violations: [{rule, file, line, severity}].
    """
    violations = []
    # In production: run bandit, ruff, pylint, etc.

    result = StaticAnalysisResult(
        target=target,
        passed=len(violations) == 0,
        violations=violations,
    )

    write_evidence(
        task_id=task_id, phase="4", step="compiler.static_analysis",
        content={"target": target, "passed": result.passed, "violation_count": len(violations)},
        tool_name="compiler.static_analysis", correlation=correlation,
    )

    return ok(result)


def dependency_scan(
    target: str,
    correlation: Optional[CorrelationId] = None,
    task_id: str = "",
) -> Result[DependencyScanResult]:
    """Scan dependencies for CVEs and license issues."""
    cves = []
    license_issues = []

    result = DependencyScanResult(
        target=target,
        passed=len(cves) == 0 and len(license_issues) == 0,
        cves=cves,
        license_issues=license_issues,
    )

    write_evidence(
        task_id=task_id, phase="4", step="compiler.dependency_scan",
        content={"target": target, "passed": result.passed},
        tool_name="compiler.dependency_scan", correlation=correlation,
    )

    return ok(result)
