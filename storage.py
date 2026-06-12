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

logger.info(f"Storage dir: {DATA_DIR}")

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
    try:
        with open(TAGS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
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
