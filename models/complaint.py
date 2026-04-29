"""Complaint data models."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class ComplaintCategory(str, Enum):
    ACTIVITY_REWARD = "activity_reward"       # 活动奖励未到账
    ACCOUNT_BAN = "account_ban"                # 封号申诉
    FUNCTION_BUG = "function_bug"              # 功能BUG反馈
    PAYMENT_ISSUE = "payment_issue"            # 支付问题
    OTHER = "other"                            # 其他
    NOT_COMPLAINT = "not_complaint"            # 非投诉消息
    EMOTIONAL = "emotional"                    # 情绪化无效投诉


class ComplaintSource(str, Enum):
    WECHAT = "wechat"
    DISCORD = "discord"
    APP_FEEDBACK = "app_feedback"


@dataclass
class Evidence:
    """Single piece of evidence collected during forensics."""
    key: str
    value: str
    source: str                           # e.g. "order_system", "risk_control"
    timestamp: datetime = field(default_factory=datetime.now)
    confidence: float = 1.0               # reliability of this evidence
    raw_response: Optional[dict] = None   # raw API response


@dataclass
class Complaint:
    """A structured complaint after classification."""
    id: str
    user_id: str
    source: ComplaintSource
    category: ComplaintCategory
    original_message: str
    summary: str                          # LLM-extracted summary
    timestamp: datetime = field(default_factory=datetime.now)
    classification_confidence: float = 0.0
    is_adjudicable: bool = False
    evidence_chain: list[Evidence] = field(default_factory=list)
    related_rules: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)

    def to_prompt_context(self) -> str:
        """Render complaint as context for downstream agents."""
        evidence_text = "\n".join(
            f"  [{e.source}] {e.key}: {e.value} (置信度: {e.confidence:.0%})"
            for e in self.evidence_chain
        )
        return (
            f"投诉ID: {self.id}\n"
            f"用户ID: {self.user_id}\n"
            f"来源: {self.source.value}\n"
            f"类别: {self.category.value}\n"
            f"摘要: {self.summary}\n"
            f"可裁断性: {'是' if self.is_adjudicable else '否'}\n"
            f"证据链:\n{evidence_text or '  (无)'}\n"
            f"关联规则: {', '.join(self.related_rules) or '(无)'}"
        )
