import json
import os

DATA_DIR = "/data"
os.makedirs(DATA_DIR, exist_ok=True)

PROFILES_FILE = f"{DATA_DIR}/profiles.json"
TAGS_FILE     = f"{DATA_DIR}/tags.json"
EVENTS_FILE   = f"{DATA_DIR}/events.json"

# ── Profiles ──────────────────────────────────

def load_profiles() -> dict:
    try:
        with open(PROFILES_FILE, encoding="utf-8") as f:
            return {int(k): v for k, v in json.load(f).items()}
    except Exception:
        return {}

def save_profiles(data: dict):
    with open(PROFILES_FILE, "w", encoding="utf-8") as f:
        json.dump({str(k): v for k, v in data.items()}, f, ensure_ascii=False, indent=2)

# ── Tags (список учасників для /gather) ───────

def load_tags() -> dict:
    """Повертає { str(user_id): {name, username} }"""
    try:
        with open(TAGS_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def save_tags(data: dict):
    with open(TAGS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def register_user(user):
    """Додає/оновлює користувача в tags при кожному повідомленні."""
    tags = load_tags()
    tags[str(user.id)] = {
        "name": user.first_name,
        "username": user.username or "",
    }
    save_tags(tags)

# ── Events ────────────────────────────────────

def load_events() -> dict:
    try:
        with open(EVENTS_FILE, encoding="utf-8") as f:
            return {int(k): v for k, v in json.load(f).items()}
    except Exception:
        return {}

def save_events(data: dict):
    with open(EVENTS_FILE, "w", encoding="utf-8") as f:
        json.dump({str(k): v for k, v in data.items()}, f, ensure_ascii=False, indent=2)
