"""Rule Engine Agent — 规则引擎Agent.

Extracts rules from knowledge base and performs chain-of-thought reasoning
to determine if the complaint should be supported, rejected, or escalated.
"""

import json
from typing import Optional

from core.knowledge_base import KnowledgeBase
from core.memory import ConversationMemory
from models.complaint import Complaint
from models.verdict import VerdictType
from .base import BaseAgent


class RuleEngineAgent(BaseAgent):
    """Agent 3: Applies rules and performs chain reasoning to reach a verdict."""

    agent_name = "rule_engine"

    def __init__(self, memory: ConversationMemory, knowledge_base: KnowledgeBase,
                 model: str | None = None):
        super().__init__(memory, model)
        self.kb = knowledge_base

    def get_system_prompt(self) -> str:
        return """你是一个规则推理引擎。你的任务是基于证据链和活动规则，进行长链推理，判断投诉是否成立。

## 推理流程（必须逐步执行）

### 步骤1：确认事实
- 列出证据链中每一项的明确结论
- 区分"用户声称的事实"和"系统记录的客观事实"

### 步骤2：逐条对照规则
- 从规则库中提取每条适用规则
- 逐条检查证据是否满足规则条件

### 步骤3：发现矛盾
- 用户声称与事实不符之处
- 证据之间的互相矛盾之处

### 步骤4：得出结论
输出以下三种结论之一：
- **support**: 所有规则条件均满足，且用户诉求合理 → 支持投诉
- **reject**: 明确不满足某条规则，或用户存在欺诈行为 → 驳回投诉
- **human_review**: 证据不足、规则模糊、或存在需要人工判断的灰色地带 → 转人工

## 输出格式
```json
{
  "verdict": "support|reject|human_review",
  "confidence": 0.0-1.0,
  "chain_of_thought": [
    {"step": 1, "action": "确认事实", "finding": "..."},
    {"step": 2, "action": "对照规则", "finding": "..."},
    {"step": 3, "action": "发现矛盾", "finding": "..."},
    {"step": 4, "action": "得出结论", "finding": "..."}
  ],
  "matched_rules": ["RULE-001"],
  "reasoning": "最终推理总结（100字以内）",
  "if_support": {
    "compensation_type": "奖励类型",
    "compensation_id": "奖励ID",
    "compensation_quantity": 1
  },
  "if_reject": {
    "rejection_reason": "驳回原因",
    "user_suggestion": "给用户的建议"
  },
  "if_human_review": {
    "reason": "需要人工介入的原因",
    "suggested_action": "建议人工客服的操作"
  }
}
```"""

    def get_tools(self) -> list[dict]:
        return [
            {
                "name": "lookup_rules",
                "description": "从知识库检索适用于当前投诉类别的规则文本。",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "category": {
                            "type": "string",
                            "description": "投诉类别: activity_reward, account_ban, function_bug, payment_issue",
                        },
                    },
                    "required": ["category"],
                },
            },
            {
                "name": "lookup_precedents",
                "description": "检索历史相似判例，用于参考一致性判断。",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "category": {
                            "type": "string",
                            "description": "投诉类别",
                        },
                    },
                    "required": ["category"],
                },
            },
        ]

    def execute_tool(self, tool_name: str, tool_input: dict) -> str:
        if tool_name == "lookup_rules":
            category = tool_input.get("category", "")
            rules = self.kb.get_rules_by_category(category)
            context = self.kb.get_rules_context(category)
            return context

        elif tool_name == "lookup_precedents":
            category = tool_input.get("category", "")
            precedents = self.kb.get_precedents_by_category(category, limit=5)
            if not precedents:
                return "该类别暂无历史判例。"
            parts = []
            for p in precedents:
                parts.append(
                    f"[{p.verdict}] ID={p.id} | {p.reasoning[:300]}\n"
                    f"  证据摘要: {p.evidence_summary[:200]}"
                )
            return "\n\n".join(parts)

        return json.dumps({"error": f"未知工具: {tool_name}"})

    def reason(self, complaint: Complaint) -> dict:
        """Run chain-of-thought reasoning on a complaint and return verdict dict."""
        evidence_context = (
            "## 证据链\n" +
            "\n".join(
                f"- [{e.source}] {e.key}: {e.value}"
                for e in complaint.evidence_chain
            )
            if complaint.evidence_chain else "(无证据)"
        )

        prompt = (
            f"请对以下投诉进行规则推理：\n\n"
            f"{complaint.to_prompt_context()}\n\n"
            f"{evidence_context}\n\n"
            f"请先调用 lookup_rules 获取相关规则，\n"
            f"再调用 lookup_precedents 获取历史判例，\n"
            f"然后按照系统提示词的步骤进行推理。"
        )

        result_text = self.run(complaint.id, prompt)
        parsed = self._parse_json(result_text)

        if parsed:
            return parsed
        else:
            return {
                "verdict": "human_review",
                "confidence": 0.3,
                "chain_of_thought": [],
                "reasoning": f"规则引擎输出解析失败，原文: {result_text[:300]}",
                "if_human_review": {
                    "reason": "规则引擎输出格式异常",
                    "suggested_action": "人工阅读规则引擎原始输出并手动判断",
                },
            }
