"""Complaint Classification Agent — 投诉归类Agent.

Determines whether an incoming message is a rule-adjudicable complaint,
extracts structured information, and filters out emotional/non-complaint messages.
"""

import json
import uuid
from datetime import datetime

from core.memory import ConversationMemory
from models.complaint import Complaint, ComplaintCategory, ComplaintSource
from .base import BaseAgent


class ComplaintClassifierAgent(BaseAgent):
    """Agent 1: Classifies incoming messages into complaint categories."""

    agent_name = "classifier"

    def get_system_prompt(self) -> str:
        return """你是一个客服投诉分类专家。你的任务是分析用户在社群（微信群/Discord）中发送的消息，判断其是否为可裁断的有效投诉。

## 你的职责
1. 判断消息是否为"可裁断类投诉"（活动补发/封号申诉/功能BUG/支付问题）
2. 剔除情绪化无效投诉（纯抱怨、人身攻击、无具体诉求的）
3. 对有效投诉，提取结构化信息

## 输出格式
请严格输出以下JSON格式（不要包含其他文字）：
```json
{
  "is_valid_complaint": true/false,
  "category": "activity_reward|account_ban|function_bug|payment_issue|emotional|not_complaint",
  "summary": "用户投诉的一句话摘要",
  "extracted_info": {
    "activity_name": "从消息中提取的活动名称，无则为null",
    "specific_issue": "用户描述的具体问题",
    "expected_resolution": "用户期望的解决方案"
  },
  "confidence": 0.0-1.0,
  "reasoning": "你的分类理由（一句话）"
}
```

## 分类标准
- **activity_reward**: 活动奖励未到账、没收到皮肤/道具
- **account_ban**: 账号被封、被禁言、被踢出群
- **function_bug**: 功能异常、页面打不开、充值不到账
- **payment_issue**: 充值扣款未到账、重复扣款
- **emotional**: 纯发泄情绪、辱骂、无具体诉求
- **not_complaint**: 闲聊、咨询、打招呼等非投诉消息

## 注意事项
- 即使消息带有情绪，只要有明确诉求（如"活动皮肤没给我"），仍应归类为有效投诉
- 仅有无意义辱骂但无具体诉求的，归类为emotional
- confidence应反映你对分类的确定程度"""

    def get_tools(self) -> list[dict]:
        return []  # Classifier uses LLM reasoning only, no external tools

    def classify(self, message: str, source: ComplaintSource = ComplaintSource.WECHAT,
                 user_id: str = "") -> Complaint:
        """Classify a single message and return a structured Complaint."""
        complaint_id = f"CPT-{uuid.uuid4().hex[:8].upper()}"

        result = self.run(complaint_id, message)
        parsed = self._parse_json(result)

        if parsed and parsed.get("is_valid_complaint"):
            try:
                category = ComplaintCategory(parsed["category"])
            except ValueError:
                category = ComplaintCategory.OTHER

            return Complaint(
                id=complaint_id,
                user_id=user_id or f"unknown_{complaint_id[:6]}",
                source=source,
                category=category,
                original_message=message,
                summary=parsed.get("summary", message[:100]),
                classification_confidence=parsed.get("confidence", 0.5),
                is_adjudicable=True,
                metadata={"extracted": parsed.get("extracted_info", {}),
                          "raw_classification": parsed},
            )
        else:
            reason = (parsed or {}).get("reasoning", "分类器判定为非有效投诉")
            return Complaint(
                id=complaint_id,
                user_id=user_id or f"unknown_{complaint_id[:6]}",
                source=source,
                category=ComplaintCategory.NOT_COMPLAINT,
                original_message=message,
                summary=reason,
                classification_confidence=parsed.get("confidence", 0.5) if parsed else 0.0,
                is_adjudicable=False,
            )
