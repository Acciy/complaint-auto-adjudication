"""Rule knowledge base — stores and retrieves activity rules, precedents, and templates."""

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional


@dataclass
class Precedent:
    """A historical case used for reference in arbitration."""
    id: str
    complaint_category: str
    activity_id: str
    verdict: str  # support / reject / human_review
    reasoning: str
    evidence_summary: str
    created_at: str
    confidence: float = 1.0


DEFAULT_RULES = [
    {
        "id": "RULE-001",
        "title": "活动奖励补发条件",
        "category": "activity_reward",
        "content": (
            "满足以下全部条件时，支持补发投诉：\n"
            "1. 用户确实参与了活动（有订单记录/登录记录）\n"
            "2. 用户完成了规则的领取动作（如点击领取按钮）\n"
            "3. 奖励因系统原因未到账（非用户自身原因）\n"
            "4. 在活动申诉有效期内（活动结束后7个工作日内）\n"
            "5. 库存充足，可以补发\n\n"
            "以下情况驳回投诉：\n"
            "1. 用户未完成领取动作（仅登录未点击）\n"
            "2. 用户因违规操作被封禁\n"
            "3. 超过申诉有效期\n"
            "4. 库存耗尽且无法补充"
        ),
        "version": 3,
        "updated_at": "2026-02-15",
    },
    {
        "id": "RULE-002",
        "title": "封号申诉裁断标准",
        "category": "account_ban",
        "content": (
            "支持解封的条件：\n"
            "1. 风控系统标记为误封（false positive）\n"
            "2. 封禁原因与实际行为不符\n"
            "3. 封禁证据链不完整\n\n"
            "驳回申诉的条件：\n"
            "1. 作弊证据确凿（批量注册/脚本/外挂）\n"
            "2. 聊天违规证据确凿（广告/辱骂/诈骗）\n"
            "3. IP/设备指纹异常\n\n"
            "需人工介入：\n"
            "1. 风险评分在40-70之间，证据不够明确\n"
            "2. 用户声称账号被盗用"
        ),
        "version": 5,
        "updated_at": "2026-03-01",
    },
    {
        "id": "RULE-003",
        "title": "功能BUG反馈处理标准",
        "category": "function_bug",
        "content": (
            "BUG分类：\n"
            "1. 已确认BUG → 引导用户等待修复，酌情补偿\n"
            "2. 新BUG → 记录并转交技术团队，给予小额补偿\n"
            "3. 用户误操作 → 解释正确操作方式\n"
            "4. 无法复现 → 请求用户提供更多信息"
        ),
        "version": 2,
        "updated_at": "2026-01-20",
    },
    {
        "id": "RULE-004",
        "title": "投诉分类判定规则",
        "category": "classification",
        "content": (
            "可裁断类投诉（Agent可自动处理）：\n"
            "1. 活动奖励未到账\n"
            "2. 封号申诉\n"
            "3. 支付类退款\n"
            "4. 功能BUG反馈\n\n"
            "不可裁断类（转人工）：\n"
            "1. 人身攻击/辱骂客服（情绪化投诉）\n"
            "2. 涉及法律问题\n"
            "3. 涉及多人/公会纠纷\n"
            "4. 需要线下核实的问题"
        ),
        "version": 1,
        "updated_at": "2026-03-10",
    },
]

DEFAULT_PRECEDENTS = [
    Precedent(
        id="PRE-001", complaint_category="activity_reward",
        activity_id="ACT-SPRING-2026",
        verdict="support",
        reasoning="用户已点击领取按钮，订单完成但奖励未发放，系统日志显示发放队列延迟。属于系统原因，支持补发。",
        evidence_summary="订单ORD-1001已完成，点击时间在活动期内，库存充足。",
        created_at="2026-02-20",
    ),
    Precedent(
        id="PRE-002", complaint_category="activity_reward",
        activity_id="ACT-SPRING-2026",
        verdict="reject",
        reasoning="用户仅登录但未点击领取按钮，不满足活动规则的第2条'需在活动页面点击领取按钮'。驳回投诉。",
        evidence_summary="订单ORD-1002显示用户参与活动但clicked_claim=false。",
        created_at="2026-02-22",
    ),
    Precedent(
        id="PRE-003", complaint_category="account_ban",
        activity_id="",
        verdict="reject",
        reasoning="风控日志显示该用户同IP批量注册12个账号并脚本领取奖励，属于严重作弊。维持封禁。",
        evidence_summary="风控评分95，标记：批量注册/脚本作弊/IP异常/设备指纹异常。",
        created_at="2026-02-25",
    ),
    Precedent(
        id="PRE-004", complaint_category="account_ban",
        activity_id="",
        verdict="human_review",
        reasoning="风控评分55，仅有IP异常标记但无确凿作弊证据，用户声称可能是使用VPN导致。需人工核查。",
        evidence_summary="风控评分55，单条IP异常标记，用户申诉理由合理。",
        created_at="2026-03-01",
    ),
]


class KnowledgeBase:
    """Manages retrieval of rules, precedents, and response templates."""

    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._rules: list[dict] = []
        self._precedents: list[Precedent] = []
        self._load_or_seed()

    def _load_or_seed(self):
        rules_file = self.data_dir / "rules.json"
        if rules_file.exists():
            self._rules = json.loads(rules_file.read_text("utf-8"))
        else:
            self._rules = DEFAULT_RULES
            rules_file.write_text(json.dumps(self._rules, ensure_ascii=False, indent=2), "utf-8")

        precedents_file = self.data_dir / "precedents.json"
        if precedents_file.exists():
            data = json.loads(precedents_file.read_text("utf-8"))
            self._precedents = [Precedent(**p) for p in data]
        else:
            self._precedents = DEFAULT_PRECEDENTS
            self._save_precedents()

    def _save_precedents(self):
        out = []
        for p in self._precedents:
            d = {f: getattr(p, f) for f in [
                "id", "complaint_category", "activity_id", "verdict",
                "reasoning", "evidence_summary", "created_at", "confidence",
            ]}
            out.append(d)
        (self.data_dir / "precedents.json").write_text(
            json.dumps(out, ensure_ascii=False, indent=2), "utf-8")

    def get_rules_by_category(self, category: str) -> list[dict]:
        """Retrieve rules relevant to a complaint category."""
        return [r for r in self._rules if r.get("category") == category]

    def get_all_rules(self) -> list[dict]:
        return list(self._rules)

    def search_rules(self, query: str) -> list[dict]:
        """Simple keyword search across rules."""
        q = query.lower()
        results = []
        for r in self._rules:
            content = r.get("content", "") + r.get("title", "")
            if q in content.lower():
                results.append(r)
        return results

    def get_precedents_by_category(self, category: str, limit: int = 10) -> list[Precedent]:
        """Get similar historical cases."""
        matches = [p for p in self._precedents if p.complaint_category == category]
        matches.sort(key=lambda p: p.created_at, reverse=True)
        return matches[:limit]

    def add_precedent(self, precedent: Precedent):
        self._precedents.append(precedent)
        self._save_precedents()

    def get_rules_context(self, category: str) -> str:
        """Build a context string of all relevant rules for LLM prompt."""
        rules = self.get_rules_by_category(category)
        precedents = self.get_precedents_by_category(category, limit=5)
        parts = []
        for r in rules:
            parts.append(f"## {r['title']} (v{r['version']})\n{r['content']}")
        if precedents:
            parts.append("## 历史判例")
            for p in precedents:
                parts.append(
                    f"- [{p.verdict}] {p.reasoning[:200]}"
                    f"{'...' if len(p.reasoning) > 200 else ''}"
                )
        return "\n\n".join(parts)

    def update_rule(self, rule_id: str, new_content: str):
        """Update a rule's content (used by confidence loop to trigger updates)."""
        for r in self._rules:
            if r["id"] == rule_id:
                r["content"] = new_content
                r["version"] += 1
                r["updated_at"] = datetime.now().strftime("%Y-%m-%d")
                break
        rules_file = self.data_dir / "rules.json"
        rules_file.write_text(json.dumps(self._rules, ensure_ascii=False, indent=2), "utf-8")
