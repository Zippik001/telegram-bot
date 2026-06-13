import json
import logging
import os

logger = logging.getLogger(__name__)

# Якщо /data не існує (немає Volume) — зберігаємо поруч з ботом
DATA_DIR = "/data" if os.path.isdir("/data") else os.path.dirname(os.path.abspath(__file__))
os.makedirs(DATA_DIR, exist_ok=True)

PROFILES_FILE = os.path.join(DATA_DIR, "profiles.json")
TAGS_FILE     = os.path.join(DATA_DIR, "tags.json")
EVENTS_FILE   = os.path.join(DATA_DIR, "events.json")

AUTORUN_FILE  = os.path.join(DATA_DIR, "autorun.json")

logger.info(f"Storage dir: {DATA_DIR}")

# ── Autorun (увімк/вимк авто-повідомлень по чатах) ────

_autorun_cache: dict | None = None

def _load_autorun() -> dict:
    global _autorun_cache
    if _autorun_cache is not None:
        return _autorun_cache
    try:
        with open(AUTORUN_FILE, encoding="utf-8") as f:
            _autorun_cache = json.load(f)
    except Exception:
        _autorun_cache = {}
    return _autorun_cache

def get_autorun(chat_id) -> bool:
    """За замовчуванням True (авто-повідомлення увімкнені)."""
    data = _load_autorun()
    return data.get(str(chat_id), True)

def set_autorun(chat_id, value: bool):
    global _autorun_cache
    data = _load_autorun()
    data[str(chat_id)] = value
    _autorun_cache = data
    try:
        with open(AUTORUN_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"set_autorun: {e}")

# ── Profiles ──────────────────────────────────

def load_profiles() -> dict:
    """Повертає { int(user_id): {text, username, tg_name} }"""
    try:
        with open(PROFILES_FILE, encoding="utf-8") as f:
            return {int(k): v for k, v in json.load(f).items()}
    except FileNotFoundError:
        return {}
    except Exception as e:
        logger.error(f"load_profiles: {e}")
        return {}

def save_profiles(data: dict):
    try:
        with open(PROFILES_FILE, "w", encoding="utf-8") as f:
            json.dump({str(k): v for k, v in data.items()}, f, ensure_ascii=False, indent=2)
        logger.info(f"Profiles saved: {len(data)} records → {PROFILES_FILE}")
    except Exception as e:
        logger.error(f"save_profiles: {e}")

# In-memory кеш — щоб уникнути гонки умов при частих записах
_tags_cache: dict | None = None

# ── Tags ──────────────────────────────────────

def load_tags() -> dict:
    """Повертає { str(user_id): {name, username} } — з кешу якщо є."""
    global _tags_cache
    if _tags_cache is not None:
        return dict(_tags_cache)
    try:
        with open(TAGS_FILE, encoding="utf-8") as f:
            data = json.load(f)
            _tags_cache = data
            return dict(data)
    except FileNotFoundError:
        _tags_cache = {}
        return {}
    except Exception as e:
        logger.error(f"load_tags: {e}")
        return {}

def save_tags(data: dict):
    global _tags_cache
    try:
        with open(TAGS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        _tags_cache = dict(data)
    except Exception as e:
        logger.error(f"save_tags: {e}")

def register_user(user):
    """Зберігає учасника при кожному повідомленні (з кешем у пам'яті)."""
    global _tags_cache
    if _tags_cache is None:
        _tags_cache = load_tags()

    uid = str(user.id)
    new_entry = {
        "name":     user.first_name,
        "username": user.username or "",
    }
    if _tags_cache.get(uid) != new_entry:
        _tags_cache[uid] = new_entry
        save_tags(_tags_cache)

# ── Events ────────────────────────────────────

def load_events() -> dict:
    try:
        with open(EVENTS_FILE, encoding="utf-8") as f:
            return {int(k): v for k, v in json.load(f).items()}
    except FileNotFoundError:
        return {}
    except Exception as e:
        logger.error(f"load_events: {e}")
        return {}

def save_events(data: dict):
    try:
        with open(EVENTS_FILE, "w", encoding="utf-8") as f:
            json.dump({str(k): v for k, v in data.items()}, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"save_events: {e}")

# ── Events pinned-message tracking (chat_id -> message_id) ───

EVENTS_MSG_FILE = os.path.join(DATA_DIR, "events_msg.json")

def load_events_msg() -> dict:
    try:
        with open(EVENTS_MSG_FILE, encoding="utf-8") as f:
            return {int(k): v for k, v in json.load(f).items()}
    except FileNotFoundError:
        return {}
    except Exception as e:
        logger.error(f"load_events_msg: {e}")
        return {}

def save_events_msg(data: dict):
    try:
        with open(EVENTS_MSG_FILE, "w", encoding="utf-8") as f:
            json.dump({str(k): v for k, v in data.items()}, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"save_events_msg: {e}")
