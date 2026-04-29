"""Mock Risk Control (风控) API — queries account status, ban reasons, fraud flags."""

import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional


@dataclass
class RiskProfile:
    user_id: str
    is_banned: bool
    ban_reason: Optional[str]
    ban_time: Optional[datetime]
    ban_duration_days: Optional[int]
    risk_score: float                  # 0-100, higher = riskier
    flags: list[str] = field(default_factory=list)
    recent_actions: list[dict] = field(default_factory=list)


_MOCK_RISK: dict[str, RiskProfile] = {}


def _seed_risk():
    if _MOCK_RISK:
        return
    base = datetime.now()
    _MOCK_RISK["user_a_001"] = RiskProfile(
        user_id="user_a_001", is_banned=False, ban_reason=None, ban_time=None,
        ban_duration_days=None, risk_score=5.0,
        flags=[],
        recent_actions=[{"action": "login", "time": base - timedelta(hours=2)}],
    )
    _MOCK_RISK["user_b_002"] = RiskProfile(
        user_id="user_b_002", is_banned=False, ban_reason=None, ban_time=None,
        ban_duration_days=None, risk_score=12.0,
        flags=["高频发言"],
        recent_actions=[{"action": "login", "time": base - timedelta(hours=1)}],
    )
    _MOCK_RISK["user_c_003"] = RiskProfile(
        user_id="user_c_003", is_banned=False, ban_reason=None, ban_time=None,
        ban_duration_days=None, risk_score=3.0,
        flags=[],
        recent_actions=[],
    )
    _MOCK_RISK["user_d_004"] = RiskProfile(
        user_id="user_d_004", is_banned=True,
        ban_reason="批量注册小号 / 脚本作弊领取活动奖励",
        ban_time=base - timedelta(days=3),
        ban_duration_days=365,
        risk_score=95.0,
        flags=["批量注册", "脚本作弊", "IP异常", "设备指纹异常"],
        recent_actions=[
            {"action": "批量注册", "time": base - timedelta(days=4), "detail": "同IP注册12个账号"},
            {"action": "脚本领取", "time": base - timedelta(days=3), "detail": "0.2s间隔连续点击领取按钮"},
        ],
    )
    # User E: banned for chat violation
    _MOCK_RISK["user_e_005"] = RiskProfile(
        user_id="user_e_005", is_banned=True,
        ban_reason="聊天违规: 发布广告引流信息",
        ban_time=base - timedelta(days=1),
        ban_duration_days=7,
        risk_score=70.0,
        flags=["聊天违规", "广告引流"],
        recent_actions=[
            {"action": "发送广告", "time": base - timedelta(days=1),
             "detail": "在10个群发送相同淘宝链接"},
        ],
    )


_seed_risk()


class RiskControlClient:
    """Simulates the risk control system to query user risk profiles."""

    def __init__(self, base_url: str = ""):
        self.base_url = base_url
        self._call_count = 0

    def get_risk_profile(self, user_id: str) -> RiskProfile:
        """Get the full risk profile for a user."""
        self._call_count += 1
        time.sleep(0.05)
        return _MOCK_RISK.get(
            user_id,
            RiskProfile(user_id=user_id, is_banned=False, ban_reason=None,
                        ban_time=None, ban_duration_days=None, risk_score=0.0),
        )

    def check_ban_status(self, user_id: str) -> dict:
        """Quick check: is the user banned, and why?"""
        profile = self.get_risk_profile(user_id)
        return {
            "is_banned": profile.is_banned,
            "ban_reason": profile.ban_reason,
            "ban_duration_days": profile.ban_duration_days,
            "ban_remaining_days": (
                (profile.ban_time + timedelta(days=profile.ban_duration_days or 0)
                 - datetime.now()).days
                if profile.is_banned and profile.ban_time and profile.ban_duration_days
                else None
            ),
            "risk_score": profile.risk_score,
            "flags": profile.flags,
        }

    def get_recent_actions(self, user_id: str, limit: int = 20) -> list[dict]:
        """Get recent suspicious actions for a user."""
        profile = self.get_risk_profile(user_id)
        return profile.recent_actions[:limit]
