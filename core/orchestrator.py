"""Complaint Orchestrator — coordinates the multi-agent pipeline.

Pipeline:
  Classifier → Forensics → Rule Engine → Arbitrator
                    ↑                          ↓
              (evidence loop)            (confidence loop — weekly)
"""

import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

from config import config
from core.knowledge_base import KnowledgeBase
from core.memory import ConversationMemory
from models.complaint import Complaint, ComplaintCategory, ComplaintSource
from models.verdict import ArbitrationResult, VerdictType
from agents.classifier import ComplaintClassifierAgent
from agents.forensics import DataForensicsAgent
from agents.rule_engine import RuleEngineAgent
from agents.arbitrator import ArbitrationAgent
from agents.confidence import ConfidenceLoopAgent, WeeklyAuditReport
from utils.logger import get_logger


@dataclass
class PipelineResult:
    """Full pipeline execution result."""
    pipeline_id: str
    complaint: Complaint
    rule_engine_result: dict
    arbitration: ArbitrationResult
    total_time_ms: float
    agent_timings: dict = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)


class ComplaintOrchestrator:
    """Main orchestrator that coordinates the 5-agent pipeline."""

    def __init__(self, model: str | None = None):
        self.model = model or config.default_model
        self.memory = ConversationMemory()
        self.kb = KnowledgeBase(config.KNOWLEDGE_BASE_DIR)
        self.logger = get_logger("orchestrator")

        # Initialize agents
        self.classifier = ComplaintClassifierAgent(self.memory, self.model)
        self.forensics = DataForensicsAgent(self.memory, self.model)
        self.rule_engine = RuleEngineAgent(self.memory, self.kb, self.model)
        self.arbitrator = ArbitrationAgent(self.memory, self.kb, self.model)
        self.confidence_loop = ConfidenceLoopAgent(
            self.memory, self.kb, config.SAMPLES_DIR, self.model)

        # Audit history
        self._recent_cases: list[dict] = []

    def process(self, message: str, user_id: str = "",
                source: ComplaintSource = ComplaintSource.WECHAT) -> PipelineResult:
        """Run the full complaint processing pipeline.

        Returns PipelineResult if processed, or None if classified as non-complaint.
        """
        pipeline_id = f"PIPE-{uuid.uuid4().hex[:8].upper()}"
        total_start = time.perf_counter()
        timings: dict[str, float] = {}
        errors: list[str] = []

        self.logger.info(f"[{pipeline_id}] 开始处理 | user={user_id} | msg={message[:60]}...")

        # Step 1: Classification
        t0 = time.perf_counter()
        try:
            complaint = self.classifier.classify(message, source, user_id)
        except Exception as e:
            errors.append(f"分类失败: {e}")
            complaint = Complaint(
                id=f"CPT-{uuid.uuid4().hex[:8].upper()}",
                user_id=user_id, source=source,
                category=ComplaintCategory.NOT_COMPLAINT,
                original_message=message, summary=f"分类异常: {e}",
                is_adjudicable=False,
            )
        timings["classification"] = (time.perf_counter() - t0) * 1000

        if not complaint.is_adjudicable:
            self.logger.info(
                f"[{pipeline_id}] 非可裁断投诉 | category={complaint.category.value} | "
                f"confidence={complaint.classification_confidence:.1%}")
            return PipelineResult(
                pipeline_id=pipeline_id,
                complaint=complaint,
                rule_engine_result={},
                arbitration=ArbitrationResult(
                    complaint_id=complaint.id,
                    verdict=VerdictType.HUMAN_REVIEW,
                    confidence=0.0,
                    reasoning="非可裁断投诉，分类器已过滤",
                    human_review_reason=f"类别: {complaint.category.value} — {complaint.summary}",
                ),
                total_time_ms=(time.perf_counter() - total_start) * 1000,
                agent_timings=timings,
                errors=errors,
            )

        # Step 2: Data Forensics
        t0 = time.perf_counter()
        try:
            evidence = self.forensics.investigate(complaint)
            complaint.evidence_chain = evidence
        except Exception as e:
            errors.append(f"取证失败: {e}")
        timings["forensics"] = (time.perf_counter() - t0) * 1000

        # Step 3: Rule Engine
        t0 = time.perf_counter()
        try:
            rule_result = self.rule_engine.reason(complaint)
        except Exception as e:
            errors.append(f"规则引擎失败: {e}")
            rule_result = {
                "verdict": "human_review",
                "confidence": 0.0,
                "reasoning": f"规则引擎异常: {e}",
            }
        timings["rule_engine"] = (time.perf_counter() - t0) * 1000

        # Step 4: Arbitration
        t0 = time.perf_counter()
        try:
            arbitration = self.arbitrator.arbitrate(complaint, rule_result)
        except Exception as e:
            errors.append(f"仲裁失败: {e}")
            arbitration = ArbitrationResult(
                complaint_id=complaint.id,
                verdict=VerdictType.HUMAN_REVIEW,
                confidence=0.0,
                reasoning=f"仲裁异常: {e}",
                human_review_reason="系统错误，需人工处理",
            )
        timings["arbitration"] = (time.perf_counter() - t0) * 1000

        total_time = (time.perf_counter() - total_start) * 1000

        # Record for confidence loop
        self._recent_cases.append({
            "complaint_id": complaint.id,
            "category": complaint.category.value,
            "agent_verdict": arbitration.verdict.value,
            "human_label": "",  # to be filled by annotator
            "summary": complaint.summary,
            "timestamp": datetime.now().isoformat(),
        })

        self.logger.info(
            f"[{pipeline_id}] 完成 | verdict={arbitration.verdict.value} | "
            f"confidence={arbitration.confidence:.1%} | total={total_time:.0f}ms | "
            f"errors={len(errors)}")

        return PipelineResult(
            pipeline_id=pipeline_id,
            complaint=complaint,
            rule_engine_result=rule_result,
            arbitration=arbitration,
            total_time_ms=total_time,
            agent_timings=timings,
            errors=errors,
        )

    def process_dry_run(self, message: str, user_id: str = "",
                        source: ComplaintSource = ComplaintSource.WECHAT) -> PipelineResult:
        """Process without calling external APIs — uses mock data only."""
        return self.process(message, user_id, source)

    def submit_human_label(self, complaint_id: str, human_label: str):
        """Submit a human label for a previously processed case."""
        for case in self._recent_cases:
            if case["complaint_id"] == complaint_id:
                case["human_label"] = human_label
                break

    def run_weekly_confidence_audit(self) -> WeeklyAuditReport:
        """Run the weekly confidence audit."""
        labeled_cases = [c for c in self._recent_cases if c["human_label"]]
        report = self.confidence_loop.run_weekly_audit(labeled_cases)
        self.confidence_loop.save_audit_report(report)
        self.logger.info(
            f"每周置信度审计完成 | 一致率: {report.agreement_rate:.1%} | "
            f"样本数: {report.sample_size} | 触发规则更新: {report.rules_update_triggered}")
        return report

    def get_stats(self) -> dict:
        """Get system statistics."""
        recent = self._recent_cases[-100:]
        verdict_counts = {}
        for c in recent:
            v = c["agent_verdict"]
            verdict_counts[v] = verdict_counts.get(v, 0) + 1

        labeled = [c for c in recent if c["human_label"]]
        agreement = sum(
            1 for c in labeled if c["agent_verdict"] == c["human_label"]
        ) if labeled else 0

        return {
            "total_processed": len(self._recent_cases),
            "recent_100_verdicts": verdict_counts,
            "labeled_count": len(labeled),
            "agreement_rate": agreement / len(labeled) if labeled else None,
            "memory_entries": sum(len(v) for v in self.memory._entries.values()),
        }
