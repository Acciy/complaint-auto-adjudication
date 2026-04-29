"""Response template engine for customer-facing replies."""

import json
from pathlib import Path
from typing import Optional

from jinja2 import Template


DEFAULT_TEMPLATES = {
    "support_activity_reward": (
        "亲爱的玩家 {{ user_id }}，您好！\n\n"
        "关于您反馈的「{{ activity_name }}」奖励未到账问题，经核实：\n"
        "您在活动期间已满足领取条件（{{ evidence_summary }}），\n"
        "但由于系统发放延迟未能及时到账。\n\n"
        "我们已为您补发奖励：{{ reward_name }} x{{ quantity }}，\n"
        "工单编号：{{ work_order_id }}，预计 2 小时内到账。\n\n"
        "如有其他疑问，欢迎随时联系我们。给您带来的不便敬请谅解！🙏"
    ),
    "reject_not_qualified": (
        "亲爱的玩家 {{ user_id }}，您好！\n\n"
        "关于您反馈的「{{ activity_name }}」奖励问题，经核实：\n"
        "根据活动规则，{{ rule_explanation }}\n"
        "而系统记录显示：{{ evidence_summary }}\n\n"
        "因此，本次投诉不符合活动补发条件，无法为您补发奖励。\n"
        "{{ suggestion }}\n\n"
        "感谢您的理解与支持！"
    ),
    "reject_fraud_ban": (
        "亲爱的玩家 {{ user_id }}，您好！\n\n"
        "关于您反馈的账号封禁问题，经风控系统核实：\n"
        "您的账号因「{{ ban_reason }}」被系统处以封禁处罚。\n\n"
        "{{ evidence_detail }}\n\n"
        "根据《用户协议》第 {{ clause }} 条，该行为属于违规操作，\n"
        "封禁决定予以维持。如有异议，可通过官网申诉入口提交申诉材料。\n\n"
        "感谢您的理解！"
    ),
    "human_review": (
        "亲爱的玩家 {{ user_id }}，您好！\n\n"
        "我们已收到您的反馈，由于情况较为复杂（{{ reason }}），\n"
        "已转交人工客服团队进行进一步核实。\n\n"
        "预计 1-3 个工作日内给您答复，请您耐心等待。\n"
        "工单编号：{{ ticket_id }}\n\n"
        "感谢您的理解与支持！"
    ),
}


class ResponseTemplateEngine:
    """Renders templated responses for different verdict types."""

    def __init__(self, templates_file: Optional[Path] = None):
        if templates_file and templates_file.exists():
            self.templates = json.loads(templates_file.read_text("utf-8"))
        else:
            self.templates = DEFAULT_TEMPLATES

    def render(self, template_name: str, **kwargs) -> str:
        template_str = self.templates.get(template_name)
        if not template_str:
            return f"[模板 {template_name} 不存在] {kwargs}"
        return Template(template_str).render(**kwargs)

    def get_template_names(self) -> list[str]:
        return list(self.templates.keys())
