"""Configuration for the Complaint Auto-Adjudication System."""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

PROJECT_ROOT = Path(__file__).parent
DATA_DIR = PROJECT_ROOT / "data"
KNOWLEDGE_BASE_DIR = DATA_DIR / "knowledge_base"
SAMPLES_DIR = DATA_DIR / "samples"
LOGS_DIR = DATA_DIR / "logs"

# Convenience alias for KnowledgeBase path
KB_DIR = KNOWLEDGE_BASE_DIR


@dataclass
class Config:
    anthropic_api_key: str = os.getenv("ANTHROPIC_API_KEY", "")
    default_model: str = "claude-sonnet-4-6"

    # Classification thresholds
    complaint_min_confidence: float = 0.6
    max_message_length: int = 2000

    # Rate limiting
    max_complaints_per_user_per_day: int = 10

    # Arbitration
    auto_approve_threshold: float = 0.85
    auto_reject_threshold: float = 0.75
    human_review_below: float = 0.75

    # Confidence loop
    weekly_sample_size: int = 30
    confidence_alert_threshold: float = 0.90

    # External system endpoints (mocked)
    order_api_url: str = os.getenv("ORDER_API_URL", "http://localhost:8001/orders")
    risk_api_url: str = os.getenv("RISK_API_URL", "http://localhost:8002/risk")
    activity_api_url: str = os.getenv("ACTIVITY_API_URL", "http://localhost:8003/activity")
    inventory_api_url: str = os.getenv("INVENTORY_API_URL", "http://localhost:8004/inventory")

    # Logging
    log_level: str = os.getenv("LOG_LEVEL", "INFO")
    log_file: Optional[Path] = LOGS_DIR / "complaint_agent.log"

    # Knowledge base
    kb_rules_file: Path = KNOWLEDGE_BASE_DIR / "rules.json"
    kb_templates_file: Path = KNOWLEDGE_BASE_DIR / "response_templates.json"
    kb_precedents_file: Path = KNOWLEDGE_BASE_DIR / "precedents.json"


config = Config()
