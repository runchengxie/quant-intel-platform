"""Notifier 抽象：解耦 a_share_daily 投递层对 daily_messenger.post_feishu 的具体依赖。

senders 通过 Notifier 协议发送飞书 webhook 文字兜底，具体实现可注入。
默认实现 FeishuWebhookNotifier 惰性 import post_feishu，保持降级友好。
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol


class Notifier(Protocol):
    def notify_text(self, *, title: str, path: Path) -> bool:
        """发送文字兜底通知。返回是否成功。"""
        ...


class FeishuWebhookNotifier:
    """基于 daily_messenger.tools.post_feishu 的适配器（惰性 import）。"""

    def notify_text(self, *, title: str, path: Path) -> bool:
        from daily_messenger.tools import post_feishu  # 惰性，保留降级

        code = post_feishu.run(
            ["--channel", "daily", "--mode", "post", "--summary", str(path), "--title", title]
        )
        return code == 0
