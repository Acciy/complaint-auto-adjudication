"""Mock Activity Configuration API — queries current and historical activity rules."""

import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional


@dataclass
class ActivityRule:
    activity_id: str
    name: str
    description: str
    start_time: datetime
    end_time: datetime
    reward_type: str
    reward_id: str
    reward_quantity: int
    claim_conditions: list[str]       # natural language conditions
    auto_issue: bool                  # whether reward is auto-issued
    total_stock: int
    remaining_stock: int
    rules_text: str                   # full rules as natural language


_MOCK_ACTIVITIES: dict[str, ActivityRule] = {}


def _seed_activities():
    if _MOCK_ACTIVITIES:
        return
    base = datetime.now()
    _MOCK_ACTIVITIES["ACT-SPRING-2026"] = ActivityRule(
        activity_id="ACT-SPRING-2026",
        name="2026春节庆典活动",
        description="活动期间登录并点击领取按钮即可获得限定皮肤",
        start_time=base - timedelta(days=14),
        end_time=base - timedelta(days=1),
        reward_type="skin",
        reward_id="SKIN-SPRING-2026-LIMITED",
        reward_quantity=1,
        claim_conditions=[
            "活动期间（1月15日-2月28日）登录游戏",
            "在活动页面点击「领取」按钮",
            "每个账号限领1次",
            "奖励将在点击领取后24小时内发放到背包",
            "如遇发放失败，需在活动结束后7个工作日内联系客服",
        ],
        auto_issue=True,
        total_stock=100000,
        remaining_stock=3200,
        rules_text=(
            "【2026春节庆典活动规则】\n"
            "1. 活动时间：2026年1月15日00:00 - 2026年2月28日23:59\n"
            "2. 参与方式：登录游戏 → 进入活动页面 → 点击「领取」按钮\n"
            "3. 奖励内容：春节限定皮肤 x1\n"
            "4. 发放规则：点击领取后24小时内自动发放至游戏背包\n"
            "5. 特别说明：\n"
            "   - 每个账号仅可领取1次\n"
            "   - 必须在活动期间点击领取按钮才视为有效参与\n"
            "   - 仅登录未点击按钮不视为参与\n"
            "   - 发放失败需在活动结束后7个工作日内联系客服补发\n"
            "6. 违规处理：使用脚本、批量注册等作弊手段将取消资格并封号处理"
        ),
    )
    _MOCK_ACTIVITIES["ACT-ANNIVERSARY-2026"] = ActivityRule(
        activity_id="ACT-ANNIVERSARY-2026",
        name="3周年庆典",
        description="累计登录7天可领取周年限定头像框",
        start_time=base - timedelta(days=30),
        end_time=base,
        reward_type="avatar_frame",
        reward_id="FRAME-ANNIV-2026",
        reward_quantity=1,
        claim_conditions=[
            "活动期间累计登录满7天",
            "在活动页面手动领取",
            "每个账号限领1次",
        ],
        auto_issue=True,
        total_stock=50000,
        remaining_stock=15000,
        rules_text="【3周年庆典规则】...",
    )


_seed_activities()


class ActivityConfigClient:
    """Simulates the activity configuration system."""

    def __init__(self, base_url: str = ""):
        self.base_url = base_url
        self._call_count = 0

    def get_activity(self, activity_id: str) -> Optional[ActivityRule]:
        """Get the full activity configuration."""
        self._call_count += 1
        time.sleep(0.03)
        return _MOCK_ACTIVITIES.get(activity_id)

    def search_activities(self, keyword: str) -> list[ActivityRule]:
        """Search activities by keyword."""
        keyword_lower = keyword.lower()
        return [
            a for a in _MOCK_ACTIVITIES.values()
            if keyword_lower in a.name.lower() or keyword_lower in a.description.lower()
        ]

    def get_claim_conditions(self, activity_id: str) -> list[str]:
        """Get only the claim conditions for an activity."""
        activity = self.get_activity(activity_id)
        return activity.claim_conditions if activity else []

    def get_full_rules(self, activity_id: str) -> Optional[str]:
        """Get the complete rules text."""
        activity = self.get_activity(activity_id)
        return activity.rules_text if activity else None

    def check_stock(self, activity_id: str) -> dict:
        """Check remaining reward stock."""
        activity = self.get_activity(activity_id)
        if not activity:
            return {"available": False, "reason": "活动不存在"}
        return {
            "available": activity.remaining_stock > 0,
            "total": activity.total_stock,
            "remaining": activity.remaining_stock,
            "reward_type": activity.reward_type,
            "reward_id": activity.reward_id,
        }
