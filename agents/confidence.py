"""Confidence Loop Agent — 置信度闭环Agent.

Weekly samples 30 cases, compares Agent verdicts against human labels,
and triggers rule updates when confidence drops below 90%.
"""

import json
import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from core.knowledge_base import KnowledgeBase
from core.memory import ConversationMemory
from models.complaint import Complaint, ComplaintCategory
from models.verdict import ArbitrationResult, VerdictType
from .base import BaseAgent


@dataclass
class WeeklyAuditReport:
    """Results of a weekly confidence audit."""
    week_start: str
    week_end: str
    sample_size: int
    agent_verdicts: list[str]  # list of verdict strings
    human_labels: list[str]    # list of verdict strings
    agreement_count: int
    agreement_rate: float
    category_breakdown: dict = field(default_factory=dict)
    discrepancy_cases: list[dict] = field(default_factory=list)
    rules_update_triggered: bool = False
    suggested_rule_updates: list[dict] = field(default_factory=list)


class ConfidenceLoopAgent(BaseAgent):
    """Agent 5: Monitors system accuracy and triggers rule improvements."""

    agent_name = "confidence_loop"

    def __init__(self, memory: ConversationMemory, knowledge_base: KnowledgeBase,
                 samples_dir: Path, model: str | None = None):
        super().__init__(memory, model)
        self.kb = knowledge_base
        self.samples_dir = samples_dir
        self.samples_dir.mkdir(parents=True, exist_ok=True)

    def get_system_prompt(self) -> str:
        return """你是一个质量控制专家。你的任务是对比 Agent 裁决结果与人工标注的差异，评估系统准确性。

## 分析内容
对于每个不一致的案例，分析：
1. Agent 为什么会判错？
2. 是规则不完善还是证据获取有问题？
3. 应该如何改进？

## 输出格式
```json
{
  "overall_assessment": "整体评估（一句话）",
  "agreement_rate": 0.XX,
  "discrepancy_analysis": [
    {
      "case_id": "xxx",
      "agent_verdict": "xxx",
      "human_label": "xxx",
      "root_cause": "规则不完善|证据缺失|边界情况|LLM推理错误",
      "suggested_fix": "具体改进建议"
    }
  ],
  "rule_update_suggestions": [
    {
      "rule_id": "RULE-XXX",
      "current_issue": "当前规则的问题",
      "suggested_content": "建议修改为..."
    }
  ]
}
```"""

    def get_tools(self) -> list[dict]:
        return [
            {
                "name": "get_rule",
                "description": "获取指定规则的完整内容。",
                "input_schema": {
                    "type": "object",
                    "properties": {"rule_id": {"type": "string"}},
                    "required": ["rule_id"],
                },
            },
            {
                "name": "update_rule",
                "description": "更新规则内容（仅在确认需要修改时使用）。",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "rule_id": {"type": "string"},
                        "new_content": {"type": "string"},
                    },
                    "required": ["rule_id", "new_content"],
                },
            },
        ]

    def execute_tool(self, tool_name: str, tool_input: dict) -> str:
        if tool_name == "get_rule":
            rule_id = tool_input["rule_id"]
            rules = [r for r in self.kb.get_all_rules() if r["id"] == rule_id]
            if rules:
                return json.dumps(rules[0], ensure_ascii=False, indent=2)
            return json.dumps({"error": f"未找到规则: {rule_id}"})

        elif tool_name == "update_rule":
            self.kb.update_rule(tool_input["rule_id"], tool_input["new_content"])
            return json.dumps({"updated": True, "rule_id": tool_input["rule_id"]})

        return json.dumps({"error": f"未知工具: {tool_name}"})

    def run_weekly_audit(
        self,
        recent_cases: list[dict],  # list of {complaint, agent_verdict, human_label}
    ) -> WeeklyAuditReport:
        """Run the weekly confidence audit on a sample of cases."""
        now = datetime.now()
        week_start = (now - timedelta(days=7)).strftime("%Y-%m-%d")
        week_end = now.strftime("%Y-%m-%d")

        # Sample up to 30 cases
        sample_size = min(30, len(recent_cases))
        samples = random.sample(recent_cases, sample_size) if recent_cases else []

        agent_verdicts = [s["agent_verdict"] for s in samples]
        human_labels = [s["human_label"] for s in samples]

        agreement = sum(a == h for a, h in zip(agent_verdicts, human_labels))
        agreement_rate = agreement / sample_size if sample_size > 0 else 1.0

        # Find discrepancies
        discrepancies = []
        category_counts: dict[str, dict] = {}
        for i, s in enumerate(samples):
            # Track category stats
            cat = s.get("category", "unknown")
            if cat not in category_counts:
                category_counts[cat] = {"total": 0, "correct": 0}
            category_counts[cat]["total"] += 1
            if agent_verdicts[i] == human_labels[i]:
                category_counts[cat]["correct"] += 1

            # Record discrepancy
            if agent_verdicts[i] != human_labels[i]:
                discrepancies.append({
                    "case_id": s.get("complaint_id", f"case_{i}"),
                    "category": cat,
                    "agent_verdict": agent_verdicts[i],
                    "human_label": human_labels[i],
                    "complaint_summary": s.get("summary", ""),
                })

        # Build category breakdown
        category_breakdown = {}
        for cat, stats in category_counts.items():
            category_breakdown[cat] = {
                **stats,
                "accuracy": stats["correct"] / stats["total"] if stats["total"] > 0 else 0,
            }

        # Trigger rule update check if below threshold
        rules_triggered = agreement_rate < 0.90
        suggested_updates = []

        if rules_triggered and discrepancies:
            # Use LLM to analyze discrepancies
            analysis_prompt = (
                f"以下是一致性审计中发现的 {len(discrepancies)} 个不一致案例：\n\n"
                f"{json.dumps(discrepancies, ensure_ascii=False, indent=2)}\n\n"
                f"当前ALM一致率为 {agreement_rate:.1%}，低于90%阈值。\n"
                f"请分析每个案例的根因，并建议规则更新。"
            )
            analysis_result = self.run("weekly_audit", analysis_prompt)
            parsed = self._parse_json(analysis_result)
            if parsed:
                suggested_updates = parsed.get("rule_update_suggestions", [])

        return WeeklyAuditReport(
            week_start=week_start,
            week_end=week_end,
            sample_size=sample_size,
            agent_verdicts=agent_verdicts,
            human_labels=human_labels,
            agreement_count=agreement,
            agreement_rate=agreement_rate,
            category_breakdown=category_breakdown,
            discrepancy_cases=discrepancies,
            rules_update_triggered=rules_triggered,
            suggested_rule_updates=suggested_updates,
        )

    def save_audit_report(self, report: WeeklyAuditReport):
        """Save audit report to disk."""
        report_path = self.samples_dir / f"audit_{report.week_start}.json"
        data = {
            "week_start": report.week_start,
            "week_end": report.week_end,
            "sample_size": report.sample_size,
            "agreement_count": report.agreement_count,
            "agreement_rate": report.agreement_rate,
            "category_breakdown": report.category_breakdown,
            "discrepancy_cases": report.discrepancy_cases,
            "rules_update_triggered": report.rules_update_triggered,
            "suggested_rule_updates": report.suggested_rule_updates,
        }
        report_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), "utf-8")
