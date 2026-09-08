"""Chart generation functions for A-share daily report."""

from .dashboard import generate_dashboard
from .moneyflow import generate_moneyflow
from .sentiment import generate_sentiment
from .topic import generate_topic
from .weekly_chart import generate_weekly_chart
from .weekly_text import generate_weekly_text

__all__ = [
    "generate_sentiment",
    "generate_moneyflow",
    "generate_dashboard",
    "generate_topic",
    "generate_weekly_chart",
    "generate_weekly_text",
]
