"""Arbitration Agent — 客服仲裁Agent.

Generates the final verdict, creates work orders for supported complaints,
and generates customer-facing reply messages for rejections.
"""

import json
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from core.knowledge_base import KnowledgeBase, Precedent
from core.memory import ConversationMemory
from models.complaint import Complaint
from models.verdict import (
    ArbitrationResult,
    VerdictType,
    WorkOrder,
)
from tools.inventory import InventoryClient
from utils.template import ResponseTemplateEngine
from .base import BaseAgent


class ArbitrationAgent(BaseAgent):
    """Agent 4: Produces the final arbitration — work orders or rejection replies."""

    agent_name = "arbitrator"

    def __init__(self, memory: ConversationMemory, knowledge_base: KnowledgeBase,
                 model: str | None = None):
        super().__init__(memory, model)
        self.kb = knowledge_base
        self.inventory = InventoryClient()
        self.templates = ResponseTemplateEngine()

    def get_system_prompt(self) -> str:
        return """你是一个客服仲裁员。你的任务是根据规则引擎的结论，执行最终操作。

## 你的职责

### 如果规则引擎结论是 support：
1. 调用 create_work_order 创建补发工单
2. 生成回复话术通知用户奖励将补发

### 如果规则引擎结论是 reject：
1. 调用 generate_reply 生成回复话术
2. 话术应包含：驳回原因、具体证据、规则依据、后续建议
3. 语气礼貌但坚定

### 如果规则引擎结论是 human_review：
1. 调用 escalate_to_human 生成转人工通知
2. 整理完整的案件摘要方便人工客服快速了解情况

## 输出格式
```json
{
  "final_verdict": "support|reject|human_review",
  "work_order_created": true/false,
  "work_order_details": {"id": "WO-xxx"} 或 null,
  "reply_message": "给用户的回复话术",
  "internal_notes": "给客服团队的内部备注",
  "evidence_screenshots": ["需要截图的证据key列表"]
}
```"""

    def get_tools(self) -> list[dict]:
        return [
            {
                "name": "create_work_order",
                "description": "创建补发工单并预占库存。需要提供用户ID、奖励类型、奖励ID、数量和原因。",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "user_id": {"type": "string"},
                        "reward_type": {"type": "string", "description": "如 skin, avatar_frame, currency"},
                        "reward_id": {"type": "string"},
                        "quantity": {"type": "integer"},
                        "reason": {"type": "string", "description": "补发原因"},
                    },
                    "required": ["user_id", "reward_type", "reward_id", "quantity", "reason"],
                },
            },
            {
                "name": "generate_reply",
                "description": "根据模板生成回复话术。根据场景选择对应模板。",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "template_name": {
                            "type": "string",
                            "description": "support_activity_reward | reject_not_qualified | reject_fraud_ban | human_review",
                        },
                        "context": {"type": "object", "description": "模板变量上下文"},
                    },
                    "required": ["template_name", "context"],
                },
            },
            {
                "name": "escalate_to_human",
                "description": "将案件转交人工客服处理。",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "complaint_id": {"type": "string"},
                        "reason": {"type": "string", "description": "转人工原因"},
                        "priority": {"type": "string", "description": "high|medium|low"},
                    },
                    "required": ["complaint_id", "reason", "priority"],
                },
            },
        ]

    def execute_tool(self, tool_name: str, tool_input: dict) -> str:
        if tool_name == "create_work_order":
            user_id = tool_input["user_id"]
            reward_type = tool_input["reward_type"]
            reward_id = tool_input["reward_id"]
            quantity = tool_input["quantity"]
            reason = tool_input["reason"]

            # Preoccupy stock
            reserve = self.inventory.preoccupy_stock(reward_id, quantity)
            if not reserve["success"]:
                return json.dumps({"error": reserve["reason"]}, ensure_ascii=False)

            # Issue reward
            issue = self.inventory.issue_reward(reserve["reservation_id"], user_id)
            return json.dumps({
                "success": issue["success"],
                "work_order_id": issue.get("work_order_id", ""),
                "reservation_id": reserve["reservation_id"],
                "item_name": reserve.get("item_name", ""),
                "status": issue.get("status", "issued"),
            }, ensure_ascii=False)

        elif tool_name == "generate_reply":
            template_name = tool_input["template_name"]
            ctx = tool_input.get("context", {})
            try:
                reply = self.templates.render(template_name, **ctx)
                return json.dumps({"reply": reply}, ensure_ascii=False)
            except Exception as e:
                return json.dumps({"error": f"模板渲染失败: {e}"}, ensure_ascii=False)

        elif tool_name == "escalate_to_human":
            ticket_id = f"HD-{uuid.uuid4().hex[:8].upper()}"
            return json.dumps({
                "escalated": True,
                "ticket_id": ticket_id,
                "assigned_queue": "senior_cs",
                "estimated_response": "1-3个工作日",
            }, ensure_ascii=False)

        return json.dumps({"error": f"未知工具: {tool_name}"})

    def arbitrate(self, complaint: Complaint, rule_engine_result: dict) -> ArbitrationResult:
        """Execute the final arbitration based on rule engine results."""
        start = time.perf_counter()

        verdict_str = rule_engine_result.get("verdict", "human_review")
        try:
            verdict = VerdictType(verdict_str)
        except ValueError:
            verdict = VerdictType.HUMAN_REVIEW

        reasoning = rule_engine_result.get("reasoning", "无推理过程")
        confidence = rule_engine_result.get("confidence", 0.5)

        # Build context for the LLM
        prompt = (
            f"## 投诉信息\n{complaint.to_prompt_context()}\n\n"
            f"## 规则引擎结论\n"
            f"裁决: {verdict.value}\n"
            f"置信度: {confidence:.1%}\n"
            f"推理: {reasoning}\n"
            f"详细: {json.dumps(rule_engine_result, ensure_ascii=False, indent=2)[:2000]}"
        )

        result_text = self.run(complaint.id, prompt)
        parsed = self._parse_json(result_text)

        work_order = None
        reply_template = ""
        human_review_reason = None

        # Extract activity info for template context
        extracted = complaint.metadata.get("extracted", {})
        activity_name = extracted.get("activity_name", "相关活动")

        if verdict == VerdictType.SUPPORT:
            compensation = rule_engine_result.get("if_support", {})
            reward_type = compensation.get("compensation_type", "skin")
            reward_id = compensation.get("compensation_id", "SKIN-SPRING-2026-LIMITED")
            quantity = compensation.get("compensation_quantity", 1)

            # Actually create the work order
            reserve = self.inventory.preoccupy_stock(reward_id, quantity)
            if reserve["success"]:
                issue = self.inventory.issue_reward(reserve["reservation_id"], complaint.user_id)
                work_order = WorkOrder(
                    id=issue.get("work_order_id", f"WO-{uuid.uuid4().hex[:8].upper()}"),
                    complaint_id=complaint.id,
                    user_id=complaint.user_id,
                    reward_type=reward_type,
                    reward_id=reward_id,
                    quantity=quantity,
                    reason=reasoning,
                    status="issued" if issue["success"] else "failed",
                    inventory_preoccupied=True,
                )

            reply_template = self.templates.render(
                "support_activity_reward",
                user_id=complaint.user_id,
                activity_name=activity_name,
                evidence_summary=reasoning,
                reward_name=reserve.get("item_name", "限定奖励"),
                quantity=quantity,
                work_order_id=work_order.id if work_order else "N/A",
            )

        elif verdict == VerdictType.REJECT:
            reject_info = rule_engine_result.get("if_reject", {})
            rejection_reason = reject_info.get("rejection_reason", reasoning)
            suggestion = reject_info.get("user_suggestion", "如有疑问请联系人工客服")

            # Determine template based on category
            if complaint.category == "account_ban":
                ban_evidence = [
                    e for e in complaint.evidence_chain if e.source == "risk_control"
                ]
                ban_detail = ban_evidence[0].value if ban_evidence else "违规操作"
                template_name = "reject_fraud_ban"
                reply_template = self.templates.render(
                    template_name,
                    user_id=complaint.user_id,
                    ban_reason=rejection_reason,
                    evidence_detail=ban_detail,
                    clause="5.3",
                )
            else:
                template_name = "reject_not_qualified"
                evidence_summary = rejection_reason
                # Find rule condition that wasn't met
                rule_explanation = (
                    rejection_reason if rejection_reason
                    else "您未完成活动要求的全部领取条件"
                )
                reply_template = self.templates.render(
                    template_name,
                    user_id=complaint.user_id,
                    activity_name=activity_name,
                    rule_explanation=rule_explanation,
                    evidence_summary=evidence_summary,
                    suggestion=suggestion,
                )

        elif verdict == VerdictType.HUMAN_REVIEW:
            human_info = rule_engine_result.get("if_human_review", {})
            human_review_reason = human_info.get("reason", "证据不足需人工判断")
            ticket_id = f"HD-{uuid.uuid4().hex[:8].upper()}"
            reply_template = self.templates.render(
                "human_review",
                user_id=complaint.user_id,
                reason=human_review_reason,
                ticket_id=ticket_id,
            )

        elapsed = (time.perf_counter() - start) * 1000

        # Save as precedent
        self.kb.add_precedent(Precedent(
            id=f"PRE-{uuid.uuid4().hex[:8].upper()}",
            complaint_category=complaint.category.value,
            activity_id=complaint.metadata.get("extracted", {}).get("activity_name", ""),
            verdict=verdict.value,
            reasoning=reasoning,
            evidence_summary="; ".join(
                f"{e.key}: {e.value[:100]}" for e in complaint.evidence_chain[:5]
            ),
            created_at=datetime.now().strftime("%Y-%m-%d"),
            confidence=confidence,
        ))

        return ArbitrationResult(
            complaint_id=complaint.id,
            verdict=verdict,
            confidence=confidence,
            reasoning=reasoning,
            work_order=work_order,
            reply_template=reply_template,
            human_review_reason=human_review_reason,
            processing_time_ms=elapsed,
        )
