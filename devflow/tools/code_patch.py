"""T6: Patch/Code toolset — code changes managed as patches.

Code changes are patches, not free-form LLM text.
Agent reasons "what to change"; tools execute "how to change."
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional
import hashlib

from devflow.core.evidence import write_evidence
from devflow.core.result import Result, ok, permanent
from devflow.core.idempotency import make_content_hash, check_exists, record_operation
from devflow.core.correlation import CorrelationId


@dataclass
class Branch:
    """A git branch for a task."""

    name: str
    task_id: str
    base_ref: str
    created: str = ""


@dataclass
class PatchResult:
    """Result of generating/applying a code patch."""

    patch_id: str
    spec_ref: str
    uc_refs: list[str]
    diff_content: str
    commit_sha: str = ""
    branch: str = ""


@dataclass
class SelfReviewResult:
    """Developer self-review of a commit."""

    commit_sha: str
    checks: list[dict]
    all_passed: bool
    evidence: list[str]


@dataclass
class PR:
    """A pull request."""

    pr_number: int
    branch: str
    title: str
    linked_ucs: list[str]
    status: str = "OPEN"


# In-memory stores
_branch_store: dict[str, Branch] = {}
_patch_store: dict[str, PatchResult] = {}
_review_store: dict[str, SelfReviewResult] = {}
_pr_store: dict[str, PR] = {}
_pr_counter: int = 0


def create_branch(
    task_id: str,
    base_ref: str = "main",
    correlation: Optional[CorrelationId] = None,
) -> Result[Branch]:
    """Create a feature branch for a task.

    Built-in: checks branch doesn't exist, naming convention: feature/devflow-{task_id}.
    """
    branch_name = f"feature/devflow-{task_id}"

    # Idempotency: check if branch exists
    if branch_name in _branch_store:
        return ok(_branch_store[branch_name])

    branch = Branch(
        name=branch_name,
        task_id=task_id,
        base_ref=base_ref,
    )
    _branch_store[branch_name] = branch

    write_evidence(
        task_id=task_id, phase="4", step="code.create_branch",
        content={"branch": branch_name, "base_ref": base_ref},
        tool_name="code.create_branch", correlation=correlation,
    )

    return ok(branch)


def generate_patch(
    spec_ref: str,
    uc_ref: str,
    context: dict = None,
    correlation: Optional[CorrelationId] = None,
    task_id: str = "",
) -> Result[PatchResult]:
    """Generate a unified diff patch from spec + use cases.

    LLM-intensive call: Agent reasons "what to change", tool produces the diff.
    Built-in: diff syntax validation, line number range validation.
    """
    # Simulate generating a unified diff patch
    diff_content = f"""--- a/src/order.py
+++ b/src/order.py
@@ -10,6 +10,12 @@
 class CurrencyConverter:
+    def convert(self, amount: Decimal, target: str) -> Decimal:
+        '''{uc_ref}: Convert CNY amount to display currency'''
+        rate = self.rate_provider.get_rate(Currency.CNY, Currency(target))
+        display = (amount * rate.rate).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
+        return display
"""

    patch_hash = hashlib.sha256(diff_content.encode()).hexdigest()[:12]
    patch = PatchResult(
        patch_id=f"patch-{patch_hash}",
        spec_ref=spec_ref,
        uc_refs=[uc_ref],
        diff_content=diff_content,
    )

    _patch_store[patch.patch_id] = patch

    # Validate diff syntax (basic check)
    if not diff_content.startswith("---"):
        return permanent("developer", "4", "Generated patch does not start with diff header")

    write_evidence(
        task_id=task_id, phase="4", step="code.generate_patch",
        content={"patch_id": patch.patch_id, "uc_ref": uc_ref},
        tool_name="code.generate_patch", correlation=correlation,
    )

    return ok(patch)


def apply_patch(
    patch_id: str,
    branch: str,
    correlation: Optional[CorrelationId] = None,
    task_id: str = "",
) -> Result[PatchResult]:
    """Apply a patch to a branch (git apply → commit).

    Built-in: commit message auto-associates UC, signature (agent_id + timestamp).
    """
    patch = _patch_store.get(patch_id)
    if not patch:
        return permanent("developer", "4", f"Patch {patch_id} not found")

    # Simulate git apply + commit
    commit_sha = hashlib.sha256(patch.diff_content.encode()).hexdigest()[:8]
    patch.commit_sha = commit_sha
    patch.branch = branch

    write_evidence(
        task_id=task_id, phase="4", step="code.apply_patch",
        content={"patch_id": patch_id, "branch": branch, "commit": commit_sha},
        tool_name="code.apply_patch", correlation=correlation,
    )

    return ok(patch)


def revert_patch(
    commit_sha: str,
    reason: str = "",
    issue_ref: str = "",
    correlation: Optional[CorrelationId] = None,
    task_id: str = "",
) -> Result[dict]:
    """Revert a patch (git revert → new commit).

    Records rollback reason and associates with the issue.
    """
    revert_sha = hashlib.sha256(f"revert-{commit_sha}".encode()).hexdigest()[:8]

    write_evidence(
        task_id=task_id, phase="4", step="code.revert_patch",
        content={"commit": commit_sha, "revert_sha": revert_sha, "reason": reason, "issue": issue_ref},
        tool_name="code.revert_patch", correlation=correlation,
    )

    return ok({"original_commit": commit_sha, "revert_commit": revert_sha, "reason": reason})


def self_review(
    commit_sha: str,
    checks: list[dict],
    correlation: Optional[CorrelationId] = None,
    task_id: str = "",
) -> Result[SelfReviewResult]:
    """Developer self-review of a commit.

    checks: [{name, result: PASS|FAIL|SKIP, evidence}]
    """
    all_passed = all(c.get("result") == "PASS" for c in checks if c.get("result") != "SKIP")
    review = SelfReviewResult(
        commit_sha=commit_sha,
        checks=checks,
        all_passed=all_passed,
        evidence=[c.get("evidence", "") for c in checks],
    )
    _review_store[commit_sha] = review

    write_evidence(
        task_id=task_id, phase="4", step="code.self_review",
        content={"commit": commit_sha, "all_passed": all_passed, "checks": len(checks)},
        tool_name="code.self_review", correlation=correlation,
    )

    return ok(review)


def create_pr(
    branch: str,
    title: str,
    linked_ucs: list[str],
    correlation: Optional[CorrelationId] = None,
    task_id: str = "",
) -> Result[PR]:
    """Create a pull request.

    Built-in: idempotent (same name PR → returns existing), auto-associates UC.
    """
    global _pr_counter

    # Idempotency: check if PR with same title exists
    for pr in _pr_store.values():
        if pr.title == title and pr.branch == branch:
            return ok(pr)

    _pr_counter += 1
    pr = PR(
        pr_number=_pr_counter,
        branch=branch,
        title=title,
        linked_ucs=linked_ucs,
    )
    _pr_store[f"PR-{_pr_counter}"] = pr

    write_evidence(
        task_id=task_id, phase="4", step="code.create_pr",
        content={"pr_number": _pr_counter, "branch": branch, "linked_ucs": linked_ucs},
        tool_name="code.create_pr", correlation=correlation,
    )

    return ok(pr)


def clear_store():
    """Clear code stores (for testing)."""
    global _pr_counter
    _branch_store.clear()
    _patch_store.clear()
    _review_store.clear()
    _pr_store.clear()
    _pr_counter = 0
