"""Data Forensics Agent — 数据取证Agent.

Calls external systems (order, risk control, activity config) to gather
an evidence chain for the complaint.
"""

import json
from datetime import datetime

from core.memory import ConversationMemory
from models.complaint import Complaint, Evidence
from models.verdict import VerdictType
from tools.order_system import OrderSystemClient
from tools.risk_control import RiskControlClient
from tools.activity_config import ActivityConfigClient
from tools.inventory import InventoryClient
from .base import BaseAgent


class DataForensicsAgent(BaseAgent):
    """Agent 2: Gathers evidence from external systems."""

    agent_name = "forensics"

    def __init__(self, memory: ConversationMemory, model: str | None = None):
        super().__init__(memory, model)
        self.order_client = OrderSystemClient()
        self.risk_client = RiskControlClient()
        self.activity_client = ActivityConfigClient()
        self.inventory_client = InventoryClient()

    def get_system_prompt(self) -> str:
        return """你是一个数据取证专家。你负责调用各个外部系统来收集用户投诉相关的证据链。

## 可用工具
你需要根据投诉类别，智能选择要调用的工具：

1. **query_order_system**: 查询用户订单/活动参与记录
2. **query_risk_control**: 查询风控系统（封禁状态、风险评分、可疑行为）
3. **query_activity_rules**: 查询活动规则配置
4. **check_inventory**: 检查奖励库存

## 取证策略
- activity_reward → 先查活动规则，再查订单，再查库存
- account_ban → 先查风控状态，再查近期可疑行为
- function_bug → 查订单（如果是充值类），查活动配置
- payment_issue → 查订单系统

## 输出格式
完成所有工具调用后，输出JSON格式的取证报告：
```json
{
  "evidence_summary": "证据链总结",
  "key_findings": ["发现1", "发现2"],
  "contradictions": ["用户声称与事实不符之处，如无则为空数组"],
  "evidence_completeness": 0.0-1.0,
  "further_investigation_needed": true/false,
  "further_investigation_reason": "如需进一步调查的原因"
}
```"""

    def get_tools(self) -> list[dict]:
        return [
            {
                "name": "query_order_system",
                "description": "查询用户的订单和活动参与记录。返回用户是否参与了指定活动、是否点击了领取按钮、订单状态等。",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "user_id": {"type": "string", "description": "用户ID"},
                        "activity_id": {"type": "string", "description": "活动ID，如不确定可留空"},
                    },
                    "required": ["user_id"],
                },
            },
            {
                "name": "query_risk_control",
                "description": "查询风控系统。返回用户封禁状态、风险评分、风控标记、近期可疑行为。",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "user_id": {"type": "string", "description": "用户ID"},
                    },
                    "required": ["user_id"],
                },
            },
            {
                "name": "query_activity_rules",
                "description": "查询活动规则配置。返回活动时间、领取条件、奖励内容、库存信息。",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "activity_id": {"type": "string", "description": "活动ID，如不确定可传关键词搜索"},
                    },
                    "required": ["activity_id"],
                },
            },
            {
                "name": "check_inventory",
                "description": "检查奖励物品的库存是否充足。",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "item_id": {"type": "string", "description": "奖励物品ID"},
                        "quantity": {"type": "integer", "description": "需要的数量", "default": 1},
                    },
                    "required": ["item_id"],
                },
            },
        ]

    def execute_tool(self, tool_name: str, tool_input: dict) -> str:
        user_id = tool_input.get("user_id", "")

        if tool_name == "query_order_system":
            activity_id = tool_input.get("activity_id") or None
            result = self.order_client.query_user_orders(user_id, activity_id)
            proof = self.order_client.get_participation_proof(
                user_id, activity_id or "ACT-SPRING-2026")
            return json.dumps(proof, ensure_ascii=False, default=str)

        elif tool_name == "query_risk_control":
            ban = self.risk_client.check_ban_status(user_id)
            actions = self.risk_client.get_recent_actions(user_id)
            result = {"ban_status": ban, "recent_actions": actions}
            return json.dumps(result, ensure_ascii=False, default=str)

        elif tool_name == "query_activity_rules":
            activity_id = tool_input.get("activity_id", "")
            activity = self.activity_client.get_activity(activity_id)
            if not activity:
                results = self.activity_client.search_activities(activity_id)
                if results:
                    activity = results[0]
            if activity:
                rules = {
                    "activity_id": activity.activity_id,
                    "name": activity.name,
                    "rules_text": activity.rules_text,
                    "claim_conditions": activity.claim_conditions,
                    "reward": {
                        "type": activity.reward_type,
                        "id": activity.reward_id,
                        "quantity": activity.reward_quantity,
                    },
                    "time_range": f"{activity.start_time} ~ {activity.end_time}",
                }
                return json.dumps(rules, ensure_ascii=False, default=str)
            return json.dumps({"error": f"未找到活动: {activity_id}"}, ensure_ascii=False)

        elif tool_name == "check_inventory":
            item_id = tool_input.get("item_id", "")
            quantity = tool_input.get("quantity", 1)
            result = self.inventory_client.check_availability(item_id, quantity)
            return json.dumps(result, ensure_ascii=False)

        return json.dumps({"error": f"未知工具: {tool_name}"})

    def investigate(self, complaint: Complaint) -> list[Evidence]:
        """Run forensics investigation for a complaint and return evidence chain."""
        prompt = (
            f"请对以下投诉进行数据取证调查：\n\n"
            f"{complaint.to_prompt_context()}\n\n"
            f"根据投诉类别（{complaint.category.value}），请调用相关工具收集证据。"
        )

        result_text = self.run(complaint.id, prompt)
        evidence = self._extract_evidence(complaint, result_text)
        complaint.evidence_chain = evidence
        return evidence

    def _extract_evidence(self, complaint: Complaint, forensics_report: str) -> list[Evidence]:
        """Parse forensics report and build evidence list."""
        evidence_list: list[Evidence] = []
        parsed = self._parse_json(forensics_report)

        # Record the forensics report itself
        evidence_list.append(Evidence(
            key="forensics_report",
            value=forensics_report[:2000],
            source="forensics_agent",
            confidence=parsed.get("evidence_completeness", 0.8) if parsed else 0.8,
            raw_response=parsed,
        ))

        # Get order data
        if complaint.category == "activity_reward":
            extracted = complaint.metadata.get("extracted", {})
            activity_name = extracted.get("activity_name", "") or "春节"

            # Try to find matching activity
            activities = self.activity_client.search_activities(activity_name)
            for act in activities:
                evidence_list.append(Evidence(
                    key="activity_rules",
                    value=f"活动: {act.name}, 领取条件: {'; '.join(act.claim_conditions)}",
                    source="activity_config",
                    raw_response={"activity_id": act.activity_id, "rules": act.rules_text},
                ))

                # Get order evidence
                proof = self.order_client.get_participation_proof(
                    complaint.user_id, act.activity_id)
                evidence_list.append(Evidence(
                    key="participation_proof",
                    value=proof.get("proof", ""),
                    source="order_system",
                    raw_response=proof,
                ))

                # Check inventory
                stock = self.inventory_client.check_availability(act.reward_id)
                evidence_list.append(Evidence(
                    key="inventory_status",
                    value=f"库存可用: {stock.get('available')}, 剩余: {stock.get('available_count')}",
                    source="inventory",
                    raw_response=stock,
                ))

        # Get risk data
        if complaint.category in ("account_ban", "activity_reward"):
            ban = self.risk_client.check_ban_status(complaint.user_id)
            evidence_list.append(Evidence(
                key="risk_status",
                value=f"封禁: {ban['is_banned']}, 风险分: {ban['risk_score']}, 标记: {ban['flags']}",
                source="risk_control",
                raw_response=ban,
            ))

        return evidence_list
