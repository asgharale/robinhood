import logging

import httpx
from django.conf import settings

log = logging.getLogger(__name__)


def notify_admins(text: str) -> None:
    """Send a plain-text Bale message to every admin chat. Never raises."""
    token, chat_ids = settings.BALE_BOT_TOKEN, settings.BALE_ADMIN_IDS
    if not token or not chat_ids:
        log.warning("bale notify skipped: TESTBOTTOKEN or ADMIN_IDS not set")
        return
    url = f"https://tapi.bale.ai/bot{token}/sendMessage"
    for chat_id in chat_ids:
        try:
            r = httpx.post(url, json={"chat_id": chat_id, "text": text[:4000]},
                           timeout=10, trust_env=False)
            r.raise_for_status()
        except Exception as e:
            # don't log str(e): httpx errors include the URL, which contains the token
            log.warning("bale notify to %s failed: %s", chat_id, type(e).__name__)