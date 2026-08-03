"""Tests for T1-T5 tools: UseCase, Requirement, PoC, Token, Architecture.

Each test class fully isolates its state.
"""

import pytest
from devflow.tools.usecase import (
    create as uc_create, upgrade as uc_upgrade, add_alternative as uc_add_alt,
    declare_known_unknown as uc_declare_ku, validate as uc_validate,
    clear_store as uc_clear, list_all as uc_list,
)
from devflow.tools.requirement import (
    create as req_create, create_ac as req_create_ac,
    traceability_matrix as req_trace_matrix,
    request_clarification as req_clarify,
    clear_store as req_clear, list_reqs,
)
from devflow.tools.poc import (
    create as poc_create, run as poc_run,
    list_experiments as poc_list, clear_store as poc_clear,
)
from devflow.tools.token import (
    record_call as token_record, estimate as token_estimate,
    report as token_report, budget_check as token_budget,
    clear_store as token_clear,
)
from devflow.tools.arch import (
    define_context_map as arch_ctx_map,
    define_interface as arch_iface,
    create_adr as arch_adr,
    declare_extension_point as arch_ep,
    clear_store as arch_clear,
)


@pytest.fixture(autouse=True)
def clear_all():
    """Clear all stores before each test."""
    uc_clear()
    req_clear()
    poc_clear()
    token_clear()
    arch_clear()


class TestUseCase:
    """T1 UseCase toolset tests."""

    def test_create_l0(self):
        result = uc_create(
            name="用户使用外币下单", level="L0", actor="买家",
            goal="以外币查看订单金额并完成下单",
            basic_flow=["选择外币", "获取汇率", "换算显示", "确认创建", "人民币扣款"],
            task_id="task-test-1",
        )
        assert result.status == "ok"
        uc = result.data
        assert uc.level.value == "L0"
        assert len(uc.basic_flow) == 5

    def test_create_rejects_invalid_level(self):
        result = uc_create("test", "L3", "actor", "goal", ["s1", "s2", "s3"])
        assert result.status == "error"

    def test_create_rejects_short_flow(self):
        result = uc_create("test", "L0", "actor", "goal", ["only"])
        assert result.status == "error"

    def test_upgrade_l0_to_l1(self):
        r = uc_create("test", "L0", "actor", "goal",
                      ["s1", "s2", "s3"], task_id="t1")
        uc_id = r.data.uc_id
        result = uc_upgrade(uc_id, "L1",
                           additions={"alternative_flows": [{"desc": "服务不可用"}]},
                           task_id="t1")
        assert result.status == "ok"
        assert result.data.level.value == "L1"

    def test_prevent_downgrade(self):
        r = uc_create("test", "L1", "actor", "goal",
                      ["s1", "s2", "s3"], task_id="t1")
        uc_id = r.data.uc_id
        result = uc_upgrade(uc_id, "L0", task_id="t1")
        assert result.status == "error"

    def test_add_alternative_flow(self):
        r = uc_create("test", "L1", "actor", "goal",
                      ["s1", "s2", "s3"], task_id="t1")
        uc_id = r.data.uc_id
        result = uc_add_alt(uc_id, "汇率服务不可用", "服务500", "调用失败", "拒绝下单", task_id="t1")
        assert result.status == "ok"
        assert len(result.data.alternative_flows) == 1

    def test_declare_known_unknown(self):
        r = uc_create("test", "L1", "actor", "goal",
                      ["s1", "s2", "s3"], task_id="t1")
        uc_id = r.data.uc_id
        result = uc_declare_ku(uc_id, "极端汇率场景", "MEDIUM", task_id="t1")
        assert result.status == "ok"
        assert len(result.data.known_unknowns) == 1

    def test_validate_l0_warns_level(self):
        r = uc_create("test", "L0", "actor", "goal",
                      ["s1", "s2", "s3"], task_id="t1")
        uc_id = r.data.uc_id
        result = uc_validate(uc_id, task_id="t1")
        assert result.status == "ok"
        has_level_fail = any(
            c["check"] == "level >= L1" and c["result"] == "FAIL"
            for c in result.data["checks"]
        )
        assert has_level_fail


class TestRequirement:
    """T2 Requirement toolset tests."""

    UC_ID = "UC-FAKE-TEST"

    def setup_method(self):
        # Create a fake use case for FRs to reference
        uc_create("fake-use-case", "L1", "actor", "goal",
                  ["s1", "s2", "s3"], task_id="t-setup")
        ucs = uc_list()
        if ucs:
            self.UC_ID = ucs[0].uc_id

    def test_create_fr(self):
        result = req_create(self.UC_ID, "FR", "汇率换算: CNY × rate → 目标币种", task_id="t1")
        assert result.status == "ok"
        assert result.data.req_id.startswith("FR-")

    def test_create_nfr(self):
        result = req_create(self.UC_ID, "NFR", "p95 < 2s", priority="HIGH", task_id="t1")
        assert result.status == "ok"
        assert result.data.req_id.startswith("NFR-")

    def test_create_ac(self):
        r = req_create(self.UC_ID, "FR", "desc", task_id="t1")
        result = req_create_ac(r.data.req_id,
            given={"rate": 7.25, "amount": 100},
            when="convert(order, 'USD')",
            then="display_amount == Decimal('13.79')",
            task_id="t1",
        )
        assert result.status == "ok"

    def test_rejects_fuzzy(self):
        r = req_create(self.UC_ID, "FR", "desc", task_id="t1")
        result = req_create_ac(r.data.req_id, {"x": 1}, "do()", "系统正常", task_id="t1")
        assert result.status == "error"

    def test_manual_method(self):
        r = req_create(self.UC_ID, "FR", "desc", task_id="t1")
        result = req_create_ac(r.data.req_id, {"x": 1}, "do()", "fee",
                              method="MANUAL", task_id="t1")
        assert result.status == "ok"

    def test_traceability_matrix(self):
        r = req_create(self.UC_ID, "FR", "desc", task_id="t1")
        req_create_ac(r.data.req_id, {"x": 1}, "do()", "result == 1", task_id="t1")
        result = req_trace_matrix("t1")
        assert result.status == "ok"
        assert len(result.data["matrix"]) >= 1

    def test_request_clarification(self):
        result = req_clarify("汇率来源?", ["央行API", "第三方"], context="多币种", task_id="t1")
        assert result.status == "ok"
        assert result.data["status"] == "PENDING"


class TestPoC:
    """T3 PoC toolset tests."""

    def test_create(self):
        result = poc_create("精度验证", "Decimal满足需求",
                           "print('13.79')", "13.79", linked_fr="FR-01", task_id="t1")
        assert result.status == "ok"


class TestToken:
    """T4 Token toolset tests."""

    def test_record_call(self):
        result = token_record("analyst", "1", "deepseek-v4-pro", 8000, 3000, task_id="t1")
        assert result.status == "ok"
        assert result.data.agent == "analyst"

    def test_estimate(self):
        result = token_estimate({"type": "multi_currency"}, "deepseek-v4-pro", task_id="t1")
        assert result.status == "ok"
        assert result.data["total_cost"] > 0

    def test_report(self):
        token_record("analyst", "1", "claude-sonnet-5", 5000, 2000, task_id="t2")
        token_record("architect", "2", "claude-sonnet-5", 10000, 5000, task_id="t2")
        result = token_report("t2")
        assert result.status == "ok"
        assert result.data["total_calls"] == 2


class TestArchitecture:
    """T5 Architecture toolset tests."""

    def test_define_context_map(self):
        result = arch_ctx_map(
            contexts=[{"name": "订单服务", "responsibility": "订单管理", "agents": ["analyst"]}],
            relationships=[{"source": "订单服务", "target": "支付网关", "type": "CUSTOMER_SUPPLIER"}],
            task_id="t1",
        )
        assert result.status == "ok"
        assert "plantuml" in result.data

    def test_define_interface(self):
        result = arch_iface("ExchangeRateProvider", "v1",
                           {"from": "Currency", "to": "Currency"},
                           {"rate": "Decimal"}, ["ServiceUnavailable"], task_id="t1")
        assert result.status == "ok"
        assert result.data.version == "v1"

    def test_create_adr(self):
        result = arch_adr("使用Decimal", "多币种精度", "Decimal+quantize",
                         "避免浮点误差", "性能略降", alternatives=["整数(分)"], task_id="t1")
        assert result.status == "ok"
        assert result.data.adr_id == "ADR-001"

    def test_declare_extension_point(self):
        result = arch_ep("ExchangeRateProvider", "极小值货币", "极端汇率", task_id="t1")
        assert result.status == "ok"
