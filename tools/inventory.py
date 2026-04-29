"""Mock Inventory API — manages reward stock and issuance."""

import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class InventoryItem:
    item_id: str
    item_type: str     # skin, avatar_frame, currency, item
    name: str
    total_stock: int
    reserved: int      # pre-occupied but not yet issued
    issued: int


_MOCK_INVENTORY: dict[str, InventoryItem] = {
    "SKIN-SPRING-2026-LIMITED": InventoryItem(
        item_id="SKIN-SPRING-2026-LIMITED", item_type="skin",
        name="春节限定皮肤·龙腾盛世", total_stock=100000, reserved=0, issued=96700,
    ),
    "FRAME-ANNIV-2026": InventoryItem(
        item_id="FRAME-ANNIV-2026", item_type="avatar_frame",
        name="3周年限定头像框", total_stock=50000, reserved=0, issued=34800,
    ),
}


class InventoryClient:
    """Simulates the inventory system for reward issuance."""

    def __init__(self, base_url: str = ""):
        self.base_url = base_url
        self._call_count = 0

    def check_availability(self, item_id: str, quantity: int = 1) -> dict:
        """Check if an item is available in sufficient quantity."""
        self._call_count += 1
        time.sleep(0.03)
        item = _MOCK_INVENTORY.get(item_id)
        if not item:
            return {"available": False, "reason": f"物品 {item_id} 不存在"}
        available = item.total_stock - item.reserved - item.issued
        return {
            "available": available >= quantity,
            "available_count": available,
            "reserved": item.reserved,
            "item_name": item.name,
        }

    def preoccupy_stock(self, item_id: str, quantity: int = 1) -> dict:
        """Pre-occupy (reserve) stock before issuing a work order."""
        self._call_count += 1
        time.sleep(0.05)
        item = _MOCK_INVENTORY.get(item_id)
        if not item:
            return {"success": False, "reason": f"物品 {item_id} 不存在"}

        available = item.total_stock - item.reserved - item.issued
        if available < quantity:
            return {"success": False, "reason": f"库存不足 (可用{available}, 需{quantity})"}

        item.reserved += quantity
        reservation_id = f"RES-{uuid.uuid4().hex[:8].upper()}"
        return {
            "success": True,
            "reservation_id": reservation_id,
            "item_id": item_id,
            "quantity": quantity,
            "item_name": item.name,
        }

    def issue_reward(self, reservation_id: str, user_id: str) -> dict:
        """Issue a reserved reward to a user."""
        self._call_count += 1
        time.sleep(0.08)
        # In production, look up reservation; here we just simulate success
        work_order_id = f"WO-{uuid.uuid4().hex[:8].upper()}"
        return {
            "success": True,
            "work_order_id": work_order_id,
            "user_id": user_id,
            "status": "issued",
            "issued_at": datetime.now().isoformat(),
        }

    def release_reservation(self, reservation_id: str) -> dict:
        """Release a reservation if the work order is cancelled."""
        self._call_count += 1
        return {"success": True, "reservation_id": reservation_id, "status": "released"}
