"""Verdict and arbitration result models."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class VerdictType(str, Enum):
    SUPPORT = "support"             # 支持投诉，补发
    REJECT = "reject"               # 驳回投诉
    HUMAN_REVIEW = "human_review"   # 需人工介入


@dataclass
class WorkOrder:
    """A compensation work order."""
    id: str
    complaint_id: str
    user_id: str
    reward_type: str               # e.g. "skin", "currency", "item"
    reward_id: str
    quantity: int
    reason: str
    status: str = "pending"        # pending, issued, failed
    created_at: datetime = field(default_factory=datetime.now)
    issued_at: Optional[datetime] = None
    inventory_preoccupied: bool = False


@dataclass
class ArbitrationResult:
    """Final result from the Arbitration Agent."""
    complaint_id: str
    verdict: VerdictType
    confidence: float
    reasoning: str                 # chain reasoning from rule engine
    work_order: Optional[WorkOrder] = None
    reply_template: str = ""       # customer-facing reply
    evidence_screenshots: list[str] = field(default_factory=list)
    human_review_reason: Optional[str] = None
    processing_time_ms: float = 0.0
    created_at: datetime = field(default_factory=datetime.now)

    def to_report(self) -> str:
        lines = [
            "=" * 60,
            f"裁决结果 | 投诉ID: {self.complaint_id}",
            f"结论: {self._verdict_label()}",
            f"置信度: {self.confidence:.1%}",
            f"处理耗时: {self.processing_time_ms:.0f}ms",
            f"理由: {self.reasoning}",
        ]
        if self.work_order:
            lines.append(
                f"补发工单: {self.work_order.id} | "
                f"奖励: {self.work_order.reward_type}:{self.work_order.reward_id} x{self.work_order.quantity}"
            )
        if self.reply_template:
            lines.append(f"\n回复话术:\n{self.reply_template}")
        if self.human_review_reason:
            lines.append(f"\n需人工介入原因: {self.human_review_reason}")
        lines.append("=" * 60)
        return "\n".join(lines)

    def _verdict_label(self) -> str:
        return {VerdictType.SUPPORT: "✅ 支持投诉",
                VerdictType.REJECT: "❌ 驳回投诉",
                VerdictType.HUMAN_REVIEW: "⚠️ 需人工介入"}[self.verdict]
