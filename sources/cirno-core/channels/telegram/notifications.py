"""Render Inbox notifications for the bound personal Telegram account."""

from urllib.parse import urlencode

from cirno.bus.delivery import DeliveryRequest
from cirno.bus.events import OutboundMessage
from cirno.session.keys import CIRNO_SESSION_KEY


def notification_message(notice, binding):
    zh = binding.get("language", "").startswith("zh")
    titles = {"operations": "待操作事项" if zh else "Action required",
              "conversations": "任务报告" if zh else "Report", "system": "系统通知" if zh else "System notification"}
    parts = [titles[notice["category"]]]
    if title := notice["data"].get("session_title"):
        parts.append(title)
    parts.append(notice["body"])
    if notice["kind"] == "question":
        parts.extend(f"{index}. {text}" for index, text in enumerate(notice["data"].get("options", []), 1))
    for path in notice["data"].get("artifacts", []):
        parts.append(path)
    parts.append("打开 Cirno 收件箱查看或处理。" if zh else "Open Cirno Inbox to view or respond.")
    metadata = {"_telegram_binding": binding["id"], "_telegram_category": notice["category"],
                "_inbox_notice": notice["id"], "_telegram_action_label": "打开 Cirno 收件箱" if zh else "Open Cirno Inbox"}
    if binding.get("webui_url"):
        metadata["_telegram_action_url"] = binding["webui_url"].rstrip("/") + "/#/inbox?" + urlencode({
            "category": notice["category"], "chat": notice["session_key"] or CIRNO_SESSION_KEY,
        })
    return OutboundMessage(
        channel="telegram", chat_id=binding["chat_id"], content="\n\n".join(part for part in parts if part),
        metadata=metadata,
        delivery=DeliveryRequest("inbox:" + binding["id"] + ":" + notice["id"] + ":" + notice["revision"],
                                 notice["session_key"] or CIRNO_SESSION_KEY, notice["data"].get("session_generation")),
    )
