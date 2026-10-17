"""Telegram Bot API bilan ishlash (qo'shimcha kutubxona talab qilmaydi).

Token ikki joydan olinadi:
  1. Sozlamalar bo'limidagi `telegram_bot_token` qiymati (tavsiya etiladi)
  2. TELEGRAM_BOT_TOKEN muhit o'zgaruvchisi

Adminlarga xabar yuborish uchun `telegram_admin_chat_id` sozlamasiga
chat ID larni vergul bilan ajratib yozish kerak.
"""
import json
import logging
import os
import urllib.error
import urllib.parse
import urllib.request

logger = logging.getLogger(__name__)

API_ROOT = "https://api.telegram.org"
TIMEOUT = 30


class TelegramError(Exception):
    """Telegram API xatosi."""


# ---------------------------------------------------------------------------
# Sozlamalar
# ---------------------------------------------------------------------------
def get_token():
    from apps.core.models import SystemSetting

    token = (SystemSetting.get("telegram_bot_token", "") or "").strip()
    if not token:
        token = (os.environ.get("TELEGRAM_BOT_TOKEN", "") or "").strip()
    return token


def is_configured():
    return bool(get_token())


def admin_chat_ids():
    from apps.core.models import SystemSetting

    raw = SystemSetting.get("telegram_admin_chat_id", "") or ""
    raw = raw or os.environ.get("TELEGRAM_ADMIN_CHAT_ID", "")
    ids = []
    for part in str(raw).replace(";", ",").split(","):
        part = part.strip()
        if not part:
            continue
        try:
            ids.append(int(part))
        except ValueError:
            logger.warning("Telegram admin chat_id noto'g'ri: %s", part)
    return ids


# ---------------------------------------------------------------------------
# Quyi daraja: API chaqiruvi
# ---------------------------------------------------------------------------
def api_call(method, payload=None, timeout=TIMEOUT):
    token = get_token()
    if not token:
        raise TelegramError(
            "Telegram bot tokeni kiritilmagan. Sozlamalar bo'limida "
            "`telegram_bot_token` ni to'ldiring."
        )
    url = f"{API_ROOT}/bot{token}/{method}"
    data = json.dumps(payload or {}).encode("utf-8")
    request = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        try:
            body = json.loads(exc.read().decode("utf-8"))
        except Exception:
            raise TelegramError(f"Telegram xatosi: HTTP {exc.code}") from exc
        raise TelegramError(
            body.get("description") or f"Telegram xatosi: HTTP {exc.code}"
        ) from exc
    except urllib.error.URLError as exc:
        raise TelegramError(f"Telegramga ulanib bo'lmadi: {exc.reason}") from exc

    if not body.get("ok"):
        raise TelegramError(body.get("description", "Noma'lum Telegram xatosi"))
    return body.get("result")


# ---------------------------------------------------------------------------
# Yuqori daraja
# ---------------------------------------------------------------------------
def get_me():
    return api_call("getMe", timeout=10)


# Bot username ni har safar so'ramaslik uchun kesh
_BOT_USERNAME_CACHE = {"value": ""}


def bot_username():
    """Botning @username ini qaytaradi (keshlanadi, tarmoqqa kamdan-kam murojaat)."""
    from apps.core.models import SystemSetting

    saved = (SystemSetting.get("telegram_bot_username", "") or "").strip().lstrip("@")
    if saved:
        return saved
    if _BOT_USERNAME_CACHE["value"]:
        return _BOT_USERNAME_CACHE["value"]
    if not is_configured():
        return ""
    try:
        me = get_me() or {}
    except TelegramError as exc:
        logger.info("bot username aniqlanmadi: %s", exc)
        return ""
    name = (me.get("username") or "").strip()
    if name:
        _BOT_USERNAME_CACHE["value"] = name
        try:
            SystemSetting.set(
                "telegram_bot_username", name, "Bot username (avtomatik aniqlanadi)"
            )
        except Exception:  # pragma: no cover
            pass
    return name


def bot_link(start_param=""):
    """Botga to'g'ridan-to'g'ri havola: https://t.me/bot_nomi"""
    name = bot_username()
    if not name:
        return ""
    url = f"https://t.me/{name}"
    if start_param:
        url += f"?start={start_param}"
    return url


def send_message(chat_id, text, reply_markup=None, disable_preview=True):
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": disable_preview,
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup
    return api_call("sendMessage", payload)


def safe_send(chat_id, text, reply_markup=None):
    """Xatolik yuz bersa dastur to'xtamaydi; (ok, xabar) qaytaradi."""
    try:
        send_message(chat_id, text, reply_markup=reply_markup)
        return True, ""
    except TelegramError as exc:
        logger.warning("Telegram yuborilmadi (%s): %s", chat_id, exc)
        return False, str(exc)


def notify_admins(text):
    """Barcha admin chatlarga xabar yuboradi. Yuborilgan chatlar sonini qaytaradi."""
    sent = 0
    for chat_id in admin_chat_ids():
        ok, _ = safe_send(chat_id, text)
        if ok:
            sent += 1
    return sent


def get_updates(offset=None, timeout=25, allowed_updates=None):
    payload = {"timeout": timeout}
    if offset is not None:
        payload["offset"] = offset
    if allowed_updates:
        payload["allowed_updates"] = allowed_updates
    return api_call("getUpdates", payload, timeout=timeout + 10) or []


def delete_webhook():
    try:
        return api_call("deleteWebhook", {"drop_pending_updates": False}, timeout=10)
    except TelegramError as exc:
        logger.info("deleteWebhook: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Webhook (serverga joylashtirilgan holat uchun)
# ---------------------------------------------------------------------------
def webhook_secret():
    """Webhook manzilidagi maxfiy qism. Bo'lmasa avtomatik yaratiladi."""
    import secrets as _secrets

    from apps.core.models import SystemSetting

    value = (SystemSetting.get("telegram_webhook_secret", "") or "").strip()
    if not value:
        value = _secrets.token_urlsafe(24)
        SystemSetting.set(
            "telegram_webhook_secret", value, "Webhook manzilidagi maxfiy kalit"
        )
    return value


def set_webhook(url, secret=None, drop_pending=False):
    """Telegramga yangilanishlarni shu manzilga yuborishni aytadi."""
    payload = {
        "url": url,
        "allowed_updates": ["message"],
        "drop_pending_updates": bool(drop_pending),
        "max_connections": 20,
    }
    if secret:
        # Telegram har so'rovda shu qiymatni sarlavhada qaytaradi
        payload["secret_token"] = secret
    return api_call("setWebhook", payload, timeout=20)


def get_webhook_info():
    return api_call("getWebhookInfo", timeout=10)


# ---------------------------------------------------------------------------
# Klaviaturalar
# ---------------------------------------------------------------------------
def phone_request_keyboard(button_text="📱 Raqamimni yuborish"):
    return {
        "keyboard": [[{"text": button_text, "request_contact": True}]],
        "resize_keyboard": True,
        "one_time_keyboard": True,
    }


def main_menu_keyboard():
    return {
        "keyboard": [
            [{"text": "📚 Mening kitoblarim"}, {"text": "📝 Testlarim"}],
            [{"text": "ℹ️ Yordam"}],
        ],
        "resize_keyboard": True,
    }


def link_keyboard(url, text="📝 Testni boshlash"):
    return {"inline_keyboard": [[{"text": text, "url": url}]]}


def remove_keyboard():
    return {"remove_keyboard": True}
