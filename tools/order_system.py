"""Mock Order System API — queries user order/purchase records."""

import random
import time
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class OrderRecord:
    order_id: str
    user_id: str
    activity_id: str
    item_name: str
    status: str  # completed, pending, cancelled
    amount: float
    created_at: datetime
    metadata: dict = field(default_factory=dict)


# Simulated order database
_MOCK_ORDERS: dict[str, list[OrderRecord]] = {}


def _seed_orders():
    """Seed realistic mock data for demo purposes."""
    if _MOCK_ORDERS:
        return
    base_time = datetime.now()

    # User A: participated in spring activity, DID click the button
    _MOCK_ORDERS["user_a_001"] = [
        OrderRecord("ORD-1001", "user_a_001", "ACT-SPRING-2026", "春节限定皮肤",
                     "completed", 0.0, base_time - timedelta(days=7),
                     {"clicked_claim": True, "click_time": (base_time - timedelta(days=7)).isoformat()}),
    ]

    # User B: participated in spring activity, did NOT click
    _MOCK_ORDERS["user_b_002"] = [
        OrderRecord("ORD-1002", "user_b_002", "ACT-SPRING-2026", "春节限定皮肤",
                     "completed", 0.0, base_time - timedelta(days=6),
                     {"clicked_claim": False, "click_time": None}),
    ]

    # User C: no activity participation at all
    _MOCK_ORDERS["user_c_003"] = []

    # User D: participated but order was cancelled (fraud suspicion)
    _MOCK_ORDERS["user_d_004"] = [
        OrderRecord("ORD-1004", "user_d_004", "ACT-SPRING-2026", "春节限定皮肤",
                     "cancelled", 0.0, base_time - timedelta(days=5),
                     {"clicked_claim": True, "cancel_reason": "风控标记: 批量注册"}),
    ]


_seed_orders()


class OrderSystemClient:
    """Simulates the order system API for querying user participation data."""

    def __init__(self, base_url: str = ""):
        self.base_url = base_url
        self._call_count = 0

    def query_user_orders(
        self, user_id: str, activity_id: Optional[str] = None,
        days_back: int = 30
    ) -> list[OrderRecord]:
        """Query orders for a user, optionally filtered by activity."""
        self._call_count += 1
        time.sleep(0.05)  # simulate network latency
        orders = _MOCK_ORDERS.get(user_id, [])
        if activity_id:
            orders = [o for o in orders if o.activity_id == activity_id]
        cutoff = datetime.now() - timedelta(days=days_back)
        return [o for o in orders if o.created_at >= cutoff]

    def get_participation_proof(self, user_id: str, activity_id: str) -> dict:
        """Get concrete evidence of user participation in an activity."""
        orders = self.query_user_orders(user_id, activity_id)
        if not orders:
            return {"participated": False, "proof": "该用户无相关活动订单", "orders": []}

        clicked = any(o.metadata.get("clicked_claim") for o in orders)
        completed = any(o.status == "completed" for o in orders if o.metadata.get("clicked_claim"))
        return {
            "participated": True,
            "clicked_claim_button": clicked,
            "order_completed": completed,
            "proof": (
                "用户已点击领取按钮，订单已完成" if clicked and completed
                else "用户已点击领取按钮，但订单异常" if clicked
                else "用户参与活动但未点击领取按钮"
            ),
            "orders": [
                {"id": o.order_id, "status": o.status, "metadata": o.metadata}
                for o in orders
            ],
        }
