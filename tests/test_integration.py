"""Integration tests — test the full pipeline without requiring LLM calls."""

import sys
import io
from pathlib import Path

# Fix Unicode on Windows
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from models.complaint import Complaint, ComplaintCategory, ComplaintSource, Evidence
from models.verdict import VerdictType, ArbitrationResult, WorkOrder
from core.knowledge_base import KnowledgeBase
from core.memory import ConversationMemory
from config import config, KNOWLEDGE_BASE_DIR


class TestKnowledgeBase:
    """Test knowledge base retrieval."""

    def test_rules_exist(self):
        kb = KnowledgeBase(KNOWLEDGE_BASE_DIR)
        rules = kb.get_all_rules()
        assert len(rules) >= 4, f"Expected >= 4 rules, got {len(rules)}"

    def test_rules_by_category(self):
        kb = KnowledgeBase(KNOWLEDGE_BASE_DIR)
        activity_rules = kb.get_rules_by_category("activity_reward")
        assert len(activity_rules) >= 1

        ban_rules = kb.get_rules_by_category("account_ban")
        assert len(ban_rules) >= 1

    def test_precedents_exist(self):
        kb = KnowledgeBase(KNOWLEDGE_BASE_DIR)
        precedents = kb.get_precedents_by_category("activity_reward")
        assert len(precedents) >= 2

    def test_search_rules(self):
        kb = KnowledgeBase(KNOWLEDGE_BASE_DIR)
        results = kb.search_rules("补发")
        assert len(results) >= 1

    def test_rule_update(self):
        kb = KnowledgeBase(KNOWLEDGE_BASE_DIR)
        original = kb.get_rules_by_category("activity_reward")[0]["content"]
        kb.update_rule("RULE-001", "测试更新内容")
        updated = kb.get_rules_by_category("activity_reward")[0]["content"]
        assert updated == "测试更新内容"
        # Restore
        kb.update_rule("RULE-001", original)


class TestMockTools:
    """Test the mock external system clients."""

    def test_order_system(self):
        from tools.order_system import OrderSystemClient
        client = OrderSystemClient()

        # User A participated and clicked
        proof = client.get_participation_proof("user_a_001", "ACT-SPRING-2026")
        assert proof["participated"] is True
        assert proof["clicked_claim_button"] is True

        # User B participated but didn't click
        proof = client.get_participation_proof("user_b_002", "ACT-SPRING-2026")
        assert proof["participated"] is True
        assert proof["clicked_claim_button"] is False

        # User C didn't participate
        proof = client.get_participation_proof("user_c_003", "ACT-SPRING-2026")
        assert proof["participated"] is False

    def test_risk_control(self):
        from tools.risk_control import RiskControlClient
        client = RiskControlClient()

        # User A is clean
        status = client.check_ban_status("user_a_001")
        assert status["is_banned"] is False
        assert status["risk_score"] < 10

        # User D is banned for fraud
        status = client.check_ban_status("user_d_004")
        assert status["is_banned"] is True
        assert status["risk_score"] > 90
        assert "批量注册" in status["flags"]

    def test_activity_config(self):
        from tools.activity_config import ActivityConfigClient
        client = ActivityConfigClient()

        activity = client.get_activity("ACT-SPRING-2026")
        assert activity is not None
        assert activity.name == "2026春节庆典活动"
        assert len(activity.claim_conditions) >= 5

        # Check stock
        stock = client.check_stock("ACT-SPRING-2026")
        assert stock["available"] is True
        assert stock["reward_type"] == "skin"

    def test_inventory(self):
        from tools.inventory import InventoryClient
        client = InventoryClient()

        # Check availability
        avail = client.check_availability("SKIN-SPRING-2026-LIMITED", 1)
        assert avail["available"] is True

        # Preoccupy
        reserve = client.preoccupy_stock("SKIN-SPRING-2026-LIMITED", 1)
        assert reserve["success"] is True
        assert reserve["reservation_id"].startswith("RES-")

        # Issue
        issue = client.issue_reward(reserve["reservation_id"], "test_user")
        assert issue["success"] is True
        assert issue["work_order_id"].startswith("WO-")

        # Release reservation
        release = client.release_reservation(reserve["reservation_id"])
        assert release["success"] is True


class TestModels:
    """Test data model construction and serialization."""

    def test_complaint_creation(self):
        complaint = Complaint(
            id="CPT-TEST001",
            user_id="user_test",
            source=ComplaintSource.WECHAT,
            category=ComplaintCategory.ACTIVITY_REWARD,
            original_message="测试投诉",
            summary="用户投诉活动奖励未到账",
            is_adjudicable=True,
        )
        ctx = complaint.to_prompt_context()
        assert "CPT-TEST001" in ctx
        assert "user_test" in ctx
        assert "activity_reward" in ctx

    def test_arbitration_result(self):
        result = ArbitrationResult(
            complaint_id="CPT-TEST001",
            verdict=VerdictType.SUPPORT,
            confidence=0.95,
            reasoning="用户满足所有条件",
        )
        report = result.to_report()
        assert "CPT-TEST001" in report
        assert "支持投诉" in report


class TestPipelineWithoutLLM:
    """Test the pipeline data flow using mock data (no actual LLM calls)."""

    def test_tools_integration(self):
        """Test that tools work together correctly."""
        from tools.order_system import OrderSystemClient
        from tools.risk_control import RiskControlClient
        from tools.activity_config import ActivityConfigClient

        order = OrderSystemClient()
        risk = RiskControlClient()
        activity = ActivityConfigClient()

        # Full evidence chain for User A's complaint
        proof = order.get_participation_proof("user_a_001", "ACT-SPRING-2026")
        ban = risk.check_ban_status("user_a_001")
        act = activity.get_activity("ACT-SPRING-2026")

        # User A: participated, clicked, not banned → should get reward
        assert proof["clicked_claim_button"] is True
        assert ban["is_banned"] is False
        assert act is not None

        # Full evidence chain for User D's complaint
        proof_d = order.get_participation_proof("user_d_004", "ACT-SPRING-2026")
        ban_d = risk.check_ban_status("user_d_004")

        # User D: banned for fraud → should be rejected
        assert ban_d["is_banned"] is True
        assert ban_d["risk_score"] > 90


def run_all():
    """Run all tests (without LLM dependency)."""
    tests = [
        TestKnowledgeBase(),
        TestMockTools(),
        TestModels(),
        TestPipelineWithoutLLM(),
    ]

    passed = 0
    failed = 0

    for test_suite in tests:
        suite_name = test_suite.__class__.__name__
        print(f"\n{'='*50}")
        print(f"  {suite_name}")
        print(f"{'='*50}")
        for name in dir(test_suite):
            if name.startswith("test_"):
                method = getattr(test_suite, name)
                try:
                    method()
                    print(f"  ✅ {name}")
                    passed += 1
                except Exception as e:
                    print(f"  ❌ {name}: {e}")
                    failed += 1

    print(f"\n{'='*50}")
    print(f"  Total: {passed} passed, {failed} failed")
    print(f"{'='*50}")
    return failed == 0


if __name__ == "__main__":
    success = run_all()
    sys.exit(0 if success else 1)
