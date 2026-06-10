import asyncio
import logging
import random
import pytz
import aiohttp
from datetime import datetime, time, timedelta, date
from collections import defaultdict
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    ContextTypes, MessageHandler, filters,
)
import storage

logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

KYIV_TZ = pytz.timezone("Europe/Bratislava")  # UTC+1/+2 (Братислава)

def he(text: str) -> str:
    return str(text).replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")


WEATHER_LAT, WEATHER_LON = "48.1486", "17.1077"

_events: dict = storage.load_events()
_event_counter: int = max((e["id"] for evs in _events.values() for e in evs), default=0)

def next_event_id():
    global _event_counter
    _event_counter += 1
    return _event_counter

activity: dict = defaultdict(dict)
_challenges: dict = {}

# Язык чата: { chat_id: "ru" }
_lang: dict = {}

def lang(chat_id) -> str:
    return _lang.get(chat_id, "ru")

def t(chat_id, uk_text: str, ru_text: str) -> str:
    return ru_text if lang(chat_id) == "ru" else uk_text


RANDOM_QUESTIONS = [
    "🍑 Если бы твои органы могли писать жалобы на тебя — какой орган подал бы самую толстую папку и за что именно?",
    "🚿 Что ты делаешь в душе с таким серьёзным выражением лица, что если бы кто-то увидел — сразу бы вызвал врача?",
    "😏 Какая твоя самая острая фраза, которую ты говоришь с улыбкой — а человек понимает только через час?",
    "🍷 Опиши свой тип людей тремя словами. Первое слово должно быть «проблемный».",
    "🔥 Что ты делаешь в кровати, о чём не расскажешь маме? (еда в 2 ночи тоже считается)",
    "🤡 С какой своей чертой характера ты уже смирился и даже сделал её своей фишкой?",
    "👅 Какое твоё самое странное кулинарное сочетание, которое ты ешь и защищаешь как адвокат?",
    "🛁 Если бы твой душ транслировался в прямом эфире — на каком моменте ты бы выключил камеру?",
    "💀 Какая твоя самая тёмная мысль в 3 ночи, которую ты никогда не напишешь в группе? (пиши тут, мы не расскажем)",
    "🐍 С кем из группы ты точно выжил бы на необитаемом острове — и кого бы съел первым?",
    "🍺 Какая у тебя репутация на вечеринках — и насколько она соответствует реальности?",
    "😳 Если бы твой телефон получил право голоса и рассказал компании о твоих поисковых запросах — что бы он сказал?",
    "🌶 Что тебя заводит в людях настолько, что ты готов это признать здесь анонимно?",
    "🧠 Какая мысль занимает в твоей голове 80% места — и ты стыдишься, что это не что-то важное?",
    "💘 Расскажи о своём самом фантастическом плане соблазнения, который провалился настолько эпично, что до сих пор смешно?",
    "🎪 Какой у тебя скрытый интерес, о котором знает максимум один человек и то случайно?",
    "🍑 Если бы твоё тело могло выставлять оценки твоим решениям — какая средняя оценка и за что самая низкая?",
    "🤫 Что ты делаешь, когда думаешь, что за тобой никто не следит? Тут можно признаться.",
    "🎭 Какую роль ты играешь на людях — и кем ты являешься на самом деле в 2 ночи наедине с собой?",
    "🔞 Какой у тебя самый странный turn-on, которого ты стыдишься? Еда, голоса, запахи — всё считается.",
    "🧟 Если бы твои бывшие могли написать один общий отзыв о тебе — что там было бы?",
    "💅 Какая твоя самая большая манипуляция, которую ты оправдываешь словом «я просто честный»?",
    "🛌 Что ты делаешь в кровати час перед сном вместо того чтобы спать — и не говори что читаешь?",
    "🍻 Какое предложение ты произнёс пьяным и утром нашёл в черновиках как «сообщение лучше не отправлять»?",
    "😈 Какое твоё самое коварное качество, которое ты называешь «стратегическим мышлением»?",
    "🦷 Какая твоя гигиеническая привычка, которую ты считаешь необязательной — а врачи бы ужаснулись?",
    "🎯 Опиши свою личную жизнь с помощью названия фильма. Чем трагичнее название — тем точнее.",
    "🌚 В котором часу твой внутренний ребёнок берёт контроль и что он тогда делает?",
    "💔 Какая самая длинная отмазка, которую ты придумал чтобы не идти на встречу — и она сработала?",
    "🤢 Какую еду ты ел прямо из кастрюли стоя над плитой и даже не стыдишься?",
    "🎲 Если бы судьба решала твою личную жизнь броском кубика — что бы изменилось?",
    "🏆 Какое твоё самое большое достижение, которого нет ни в одном резюме, но ты им гордишься как олимпийской медалью?",
    "🐾 Если бы твоя кошка или собака могли говорить — что бы они рассказали этой группе в первую очередь?",
    "👀 Какое твоё самое неадекватное ревнивое поведение, которое ты оправдывал словом «я просто беспокоюсь»?",
    "🌊 Что тебя возбуждает так, что ты готов признаться? (интеллект, власть, запах борща — все варианты валидны)",
]

DISCUSSION_TOPICS = [
    "🗣 *Тема:* Есть места в Братиславе, где время как будто останавливается. Где у вас такое место?",
    "🗣 *Тема:* Взрослые отношения — почему с возрастом найти настоящих друзей становится сложнее?",
    "🗣 *Тема:* Настольные игры — это диагностика характера или просто игра?",
    "🗣 *Тема:* Идеальный вечер с компанией — что должно быть обязательно и чего не должно быть?",
    "🗣 *Тема:* Поход в горы — у кого уже есть травма и кто готов повторить?",
    "🗣 *Тема:* Red flag или green flag — что сразу говорит вам всё о человеке?",
    "🗣 *Тема:* Лучший способ отдохнуть после тяжёлой недели — у каждого свой.",
    "🗣 *Тема:* Какое место в Братиславе надо показать гостю, который приехал впервые?",
    "🔞 *Тема:* Первый поцелуй — романтично или кринжово? Кто готов рассказать?",
    "😬 *Тема:* Худшее свидание в вашей жизни — детали, подробности, без цензуры.",
    "🍺 *Тема:* Есть корпоратив или вечеринка после которой вы стыдились на следующий день — что произошло?",
    "💔 *Тема:* Самая глупая причина, по которой вы расходились или ссорились — признайтесь.",
    "🌶 *Тема:* Что в людях вас заводит — и нет, не обязательно в романтическом смысле?",
    "🤐 *Тема:* Есть мысль, которую вы никогда не скажете вслух в этой компании — что это?",
    "😂 *Тема:* Самый кринжовый момент вашего подросткового возраста — кто первый?",
    "🛏 *Тема:* Ваши отношения со сном — роман, трагедия или холодная война?",
    "💸 *Тема:* На что вы тратите деньги и потом стыдитесь это признавать?",
    "🧲 *Тема:* Какая черта характера притягивает вас в людях как магнит — и почему это почти всегда плохо заканчивается?",
]

WEEKLY_CHALLENGES = [
    "💪 Вызов недели: познакомиться с кем-то новым в группе!",
    "💪 Вызов недели: предложить идею для следующей встречи!",
    "💪 Вызов недели: написать что-то позитивное в группу каждый день!",
    "💪 Вызов недели: попробовать новое место в Братиславе и рассказать об этом!",
]

EVENT_TYPES_RU = {
    "boardgames": "🎲 Настольные игры",
    "hike":       "🥾 Поход / прогулка",
    "cafe":       "☕ Кафе / бар",
    "cinema":     "🎬 Кино",
    "quest":      "🎯 Квест / активность",
    "online":     "💻 Онлайн-вечер",
    "custom":     "✏️ Своя идея",
}

def EVENT_TYPES(chat_id=None):
    return EVENT_TYPES_RU

DAYS_RU = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
DAY_EMOJI = ["📅","📅","📅","📅","🎉","🎉","😴"]
MONTHS_RU = ["янв","фев","мар","апр","май","июн","июл","авг","сен","окт","ноя","дек"]

def next_date_for_weekday(weekday_index: int) -> date:
    """Return the next upcoming date for a given weekday (0=Mon ... 6=Sun)."""
    today = datetime.now(KYIV_TZ).date()
    days_ahead = (weekday_index - today.weekday()) % 7
    if days_ahead == 0:
        days_ahead = 7
    return today + timedelta(days=days_ahead)

def day_label(weekday_index: int) -> str:
    """e.g. 'Пт 13 июн'"""
    d = next_date_for_weekday(weekday_index)
    return f"{DAY_EMOJI[weekday_index]} {DAYS_RU[weekday_index]} {d.day} {MONTHS_RU[d.month-1]}"

def custom_date_weekday_name(date_str: str) -> str:
    """Convert dd.mm.yyyy string to weekday name."""
    try:
        d = datetime.strptime(date_str, "%d.%m.%Y")
        return DAYS_RU[d.weekday()]
    except Exception:
        return ""

def DAYS(chat_id=None):
    return DAYS_RU

# ── Погода ────────────────────────────────────

async def fetch_weather_full():
    url = (
        "https://api.open-meteo.com/v1/forecast"
        f"?latitude={WEATHER_LAT}&longitude={WEATHER_LON}"
        "&current=temperature_2m,apparent_temperature,weathercode,windspeed_10m,relative_humidity_2m"
        "&hourly=temperature_2m,weathercode,precipitation_probability"
        "&forecast_days=1"
        "&timezone=Europe%2FBratislava"
    )
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(url, timeout=aiohttp.ClientTimeout(total=10)) as r:
                if r.status == 200:
                    return await r.json()
    except Exception as e:
        logger.error(f"Weather: {e}")
    return None

async def fetch_weather():
    return await fetch_weather_full()

def wmo_emoji(c):
    if c == 0: return "☀️"
    if c in (1,2): return "🌤"
    if c == 3: return "☁️"
    if c in (45,48): return "🌫"
    if 51<=c<=67: return "🌧"
    if 71<=c<=77: return "🌨"
    if 80<=c<=82: return "🌦"
    if c in (95,96,99): return "⛈"
    return "🌡"

def wmo_desc(c):
    return {0:"Ясно",1:"Преимущественно ясно",2:"Переменная облачность",3:"Облачно",
            45:"Туман",51:"Морось",61:"Дождь",63:"Умеренный дождь",65:"Сильный дождь",
            71:"Снег",80:"Ливень",95:"Гроза"}.get(c,"Переменная погода")

def weather_tip_full(slots):
    codes = [s["code"] for s in slots]
    temps = [s["temp"] for s in slots]
    has_rain  = any(51<=c<=82 for c in codes)
    has_storm = any(c in (95,96,99) for c in codes)
    has_snow  = any(71<=c<=77 for c in codes)
    min_t = min(temps)
    max_t = max(temps)

    funny = []
    if has_storm:
        funny.append("Гроза? Оставайся дома, стань человеком-диваном ⛈🛋")
    elif has_rain:
        funny.append("Дождь идёт — хороший повод не выходить и смотреть сериалы 🌧🍿")
    elif has_snow:
        funny.append("Снежок! Отлично, если ты пингвин 🐧❄️")
    elif max_t > 28:
        funny.append("Жара! Одевайся как солнечная батарея и плавь тротуары ☀️🥵")
    elif min_t < 3:
        funny.append("Холодно как в сердце того, кто не отвечает на сообщения 🥶")
    elif max_t > 18:
        funny.append("Погода — 10 из 10, даже монитор стыдно открывать 🌞")
    else:
        funny.append("Обычная братиславская погода — непредсказуемая как настроение в понедельник 😅")
    return funny[0]

def build_weather_full(data):
    hours_map = {8: "🌅 Утро",  11: "☀️ Полдень",
                 14: "🌤 День",  17: "🌇 Вечер", 20: "🌙 Ночь"}

    hourly_times = data["hourly"]["time"]
    hourly_temps = data["hourly"]["temperature_2m"]
    hourly_codes = data["hourly"]["weathercode"]
    hourly_prec  = data["hourly"]["precipitation_probability"]

    slots = []
    for target_h, label in hours_map.items():
        idx = next((i for i, t in enumerate(hourly_times) if f"T{target_h:02d}:00" in t), None)
        if idx is None:
            continue
        temp = round(hourly_temps[idx])
        code = int(hourly_codes[idx])
        prec = int(hourly_prec[idx])
        emoji = wmo_emoji(code)
        desc  = wmo_desc(code)
        prec_str = f" 💧{prec}%" if prec > 20 else ""
        slots.append({
            "label": label, "temp": temp, "code": code,
            "emoji": emoji, "desc": desc, "prec_str": prec_str
        })

    now = datetime.now(pytz.timezone("Europe/Bratislava"))
    date_str = now.strftime("%d.%m.%Y")
    weekdays = ["Понедельник","Вторник","Среда","Четверг","Пятница","Суббота","Воскресенье"]
    weekday = weekdays[now.weekday()]
    lines = [f"🌍 *Погода в Братиславе*\n📅 {weekday}, {date_str}\n"]
    for s in slots:
        lines.append(f"{s['label']}: {s['emoji']} {s['temp']}°C — {s['desc']}{s['prec_str']}")

    tip = weather_tip_full(slots) if slots else "Хорошего дня! ☀️"
    lines.append(f"\n💡 _{tip}_")
    return "\n".join(lines)

def build_weather_text(data):
    return build_weather_full(data)

async def cmd_weather(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("⏳ Получаю погоду...")
    data = await fetch_weather_full()
    if data:
        await msg.edit_text(build_weather_full(data), parse_mode="Markdown")
    else:
        await msg.edit_text("😔 Не удалось получить погоду.")

async def sched_weather(context: ContextTypes.DEFAULT_TYPE):
    data = await fetch_weather_full()
    if data:
        await context.bot.send_message(
            context.job.data["chat_id"], build_weather_full(data), parse_mode="Markdown"
        )

async def sched_morning_news(context: ContextTypes.DEFAULT_TYPE):
    chat_id = context.job.data["chat_id"]
    messages = [
        "📰 *Новость дня:* Учёные выяснили, что кофе с утра — это не зависимость, а стратегия выживания ☕",
        "📰 *Новость дня:* Исследование показало: люди которые отвечают на сообщения сразу — редкий вид 🦄",
        "📰 *Новость дня:* Эксперты подтвердили: понедельник существует, и с этим ничего не поделать 📅",
        "📰 *Новость дня:* Зафиксировано рекордное количество людей которые сказали «я уже иду» и не вышли 🚶",
    ]
    await context.bot.send_message(chat_id, random.choice(messages), parse_mode="Markdown")

# ── Трекер — анкета + теги + активность ───────

async def track_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user    = update.effective_user
    chat_id = update.effective_chat.id
    if not user or user.is_bot:
        return

    storage.register_user(user)

    text = (update.message.text or "").strip()
    low  = text.lower()

    # Анкета: "о себе ..."
    if low.startswith("о себе") or low.startswith("про себе"):
        prefix = "о себе" if low.startswith("о себе") else "про себе"
        info = text[len(prefix):].strip(" :—-\n")
        if info:
            profiles = storage.load_profiles()
            existing = profiles.get(user.id) or profiles.get(str(user.id)) or {}
            profiles.pop(str(user.id), None)
            profiles[user.id] = {
                "text": info,
                "username": user.username or "",
                "tg_name": user.first_name,
                "instagram": existing.get("instagram", ""),
                "work": existing.get("work", ""),
            }
            storage.save_profiles(profiles)
            await update.message.reply_text(
                f"✅ Сохранено, {user.first_name}!\n\n{info}\n\nПосмотреть: /profile"
            )
        else:
            await update.message.reply_text(
                "📋 Напиши текст после «о себе», например:\nо себе Привет! Меня зовут Иван, 27 лет 🙂"
            )

    # Instagram
    if low.startswith("мой инстаграм ") or low.startswith("мій інстаграм "):
        prefix = "мой инстаграм " if low.startswith("мой инстаграм ") else "мій інстаграм "
        insta = text[len(prefix):].strip().lstrip("@")
        if insta:
            profiles = storage.load_profiles()
            p = profiles.get(user.id) or profiles.get(str(user.id)) or {"text": "", "username": user.username or "", "tg_name": user.first_name}
            p["instagram"] = insta
            p["tg_name"] = user.first_name
            p["username"] = user.username or p.get("username", "")
            # Save under consistent key
            profiles.pop(str(user.id), None)
            profiles[user.id] = p
            storage.save_profiles(profiles)
            await update.message.reply_text(f"📸 Instagram сохранён: @{insta}")
        return

    # Work / місце роботи
    if low.startswith("моя работа ") or low.startswith("моя робота "):
        prefix = "моя работа " if low.startswith("моя работа ") else "моя робота "
        work_val = text[len(prefix):].strip()
        if work_val:
            profiles = storage.load_profiles()
            p = profiles.get(user.id) or profiles.get(str(user.id)) or {"text": "", "username": user.username or "", "tg_name": user.first_name}
            p["work"] = work_val
            p["tg_name"] = user.first_name
            p["username"] = user.username or p.get("username", "")
            # Save under consistent key
            profiles.pop(str(user.id), None)
            profiles[user.id] = p
            storage.save_profiles(profiles)
            await update.message.reply_text(f"💼 Место работы сохранено: {work_val}")
        return

    # AI: если сообщение начинается с имени бота или триггеров
    petya_triggers = ("пєтя,", "петя,", "пєтя питання", "петя питання", "петро,", "петро питання", "ai,", "шт,")
    if any(low.startswith(t) for t in petya_triggers) or (low.startswith("пєтя ") and len(low) > 6) or (low.startswith("петя ") and len(low) > 5) or (low.startswith("петро ") and len(low) > 6):
        question = text
        for t in ("пєтя,", "петя,", "петро,", "пєтя ", "петя ", "петро ", "ai, ", "шт, "):
            if low.startswith(t):
                question = text[len(t):].strip()
                break
        if question:
            thinking = await update.message.reply_text("🤔 Думаю...")
            answer = await ask_ai(question)
            await thinking.edit_text(f"🤖 {answer}")
            if user.id not in activity[chat_id]:
                activity[chat_id][user.id] = {"name": user.first_name, "count": 0}
            activity[chat_id][user.id]["name"] = user.first_name
            activity[chat_id][user.id]["count"] += 1
            return

    # Вызов меню через имя бота
    if low.strip() in ("пєтя", "петя", "petya", "пєтя!", "петя!", "пєтя?", "петя?",
                        "петро", "петро!", "петро?", "петр"):
        petya_texts = [
            f"🤖✨ Пётр Интерактивный материализовался!\n\nМеня позвали — значит кому-то стало скучно 😏\n\nЧтобы заполнить анкету — напиши о себе и дальше свой текст\nЧтобы спросить меня что-то — начни с Петя, и я отвечу 🫡",
            f"🤖 О, меня позвали! Или кто-то соскучился или что-то случилось 😄\n\nАнкета: напиши о себе и дальше свой текст\nВопрос мне: Петя, [вопрос] — и я не промолчу 🎤",
            f"🫡 Пётр здесь, слушаю и полностью в теме!\n\nЗаполни анкету: о себе + текст\nСпрашивай меня: Петя, + запрос — дам ответ который тебя удивит 🤌",
        ]
        import random as _r
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("📋 Анкеты участников",    callback_data="menu_profiles")],
            [InlineKeyboardButton("🎉 Предложить ивент",     callback_data="menu_event"),
             InlineKeyboardButton("📅 Активные ивенты",      callback_data="menu_events")],
            [InlineKeyboardButton("🌤 Погода",               callback_data="menu_weather")],
            [InlineKeyboardButton("❓ Острый вопрос",         callback_data="menu_question"),
             InlineKeyboardButton("💬 Тема",                 callback_data="menu_topic")],
            [InlineKeyboardButton("📊 Отчёт активности",     callback_data="menu_report")],
        ])
        await update.message.reply_text(_r.choice(petya_texts), parse_mode="Markdown", reply_markup=kb)

    # Анонимное сообщение
    if low.startswith("анонім ") or low.startswith("анон ") or low.startswith("anonym "):
        for prefix in ("анонім ", "анон ", "anonym "):
            if low.startswith(prefix):
                anon_text = text[len(prefix):].strip()
                break
        if anon_text:
            try:
                await update.message.delete()
            except Exception:
                pass
            await context.bot.send_message(
                chat_id,
                "🎭 Анонимное сообщение:\n\n" + anon_text
            )
        return

    # Активность
    if user.id not in activity[chat_id]:
        activity[chat_id][user.id] = {"name": user.first_name, "count": 0}
    activity[chat_id][user.id]["name"]   = user.first_name
    activity[chat_id][user.id]["count"] += 1

# ── ChatGPT / Groq ──────────────────────────────────────────────────────────

async def ask_ai(question: str) -> str:
    import os
    api_key = os.environ.get("GROQ_API_KEY", "")
    if not api_key:
        return (
            "😔 Groq API ключ не настроен.\n"
            "Добавь GROQ_API_KEY в Railway Variables.\n"
            "Получи бесплатно: console.groq.com"
        )
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {
        "model": "llama-3.3-70b-versatile",
        "messages": [
            {"role": "system", "content": (
                "Ты — Пётр Интерактивный, неадекватный но добродушный ассистент группы друзей в Братиславе. "
                "Отвечай ИСКЛЮЧИТЕЛЬНО на русском языке — никакого другого. "
                "Твой стиль: кринжовый юмор, пошлые но не вульгарные шутки, неожиданные сравнения, "
                "саркастические советы, абсурдные аналогии. "
                "Ты как тот друг который всегда скажет что-то неуместное но точное. "
                "Будь кратким — максимум 4-5 предложений. "
                "Если просят анекдот — расскажи пошлый но смешной, без мата. "
                "Если просят совет — дай его но с таким кринжовым поворотом что человек засмеётся. "
                "Если просят фильм — посоветуй с описанием типа 'там есть сцена где...' и сделай это смешно. "
                "Если вопрос серьёзный — отвечай серьёзно но добавь один кринжовый комментарий в конце. "
                "Никогда не начинай с 'Конечно!' или 'Я рад помочь' — это скучно и не в твоём стиле. "
                "Начинай ответ сразу с сути или с неожиданного комментария."
            )},
            {"role": "user", "content": question}
        ],
        "max_tokens": 400,
        "temperature": 0.9,
    }
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(url, json=payload, headers=headers,
                              timeout=aiohttp.ClientTimeout(total=30)) as r:
                if r.status == 200:
                    data = await r.json()
                    return data["choices"][0]["message"]["content"].strip()
                else:
                    err = await r.text()
                    logger.error(f"Groq error {r.status}: {err}")
                    return "😔 Ошибка при обращении к ИИ. Попробуй позже."
    except Exception as e:
        logger.error(f"Groq exception: {e}")
        return "😔 Не удалось получить ответ от ИИ."

# ── Приветствие новых участников ──────────────────────────────────────────────────

async def welcome_new_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.new_chat_members:
        return
    chat_id = update.effective_chat.id
    for member in update.message.new_chat_members:
        if member.is_bot:
            continue
        storage.register_user(member)
        name = member.first_name
        try:
            await context.bot.send_message(
                chat_id,
                f"👋 Добро пожаловать, {name}!\n\n"
                f"Рад видеть тебя в нашей компании 🎉\n\n"
                f"📋 *Заполни анкету* — напиши сообщение:\n"
                f"_о себе_ и дальше расскажи кто ты, откуда, что любишь\n\n"
                f"📸 Instagram: напиши _мой инстаграм @твой\\_ник_\n"
                f"💼 Работа: напиши _моя работа Название компании_\n\n"
                f"📌 *Правила группы:*\n"
                f"✅ Будь активным — пиши, предлагай ивенты, отвечай\n"
                f"😊 Будь позитивным — токсичность тут не в моде\n"
                f"🤝 Уважай других — мы все здесь ради хорошего времени\n"
                f"🎉 Предлагай идеи — лучшая идея та, которую ты предложил\n\n"
                f"Напиши *Петя* или /start чтобы увидеть что я умею 🤖",
                parse_mode="Markdown"
            )
        except Exception as e:
            logger.error(f"welcome_new_member error: {e}")


# ── Анкеты ────────────────────────────────────

async def cmd_profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    profiles  = storage.load_profiles()
    target_id = None

    for entity in (update.message.entities or []):
        if entity.type == "mention":
            uname = update.message.text[entity.offset+1 : entity.offset+entity.length]
            for uid, p in profiles.items():
                if (p.get("username") or "").lower() == uname.lower():
                    target_id = int(uid)
                    break
            if target_id is None:
                await update.message.reply_text(f"😔 Анкета для @{uname} не найдена.")
                return
        elif entity.type == "text_mention":
            target_id = entity.user.id

    if target_id is None:
        target_id = update.effective_user.id

    p = profiles.get(int(target_id)) or profiles.get(str(target_id))
    if not p:
        if int(target_id) == update.effective_user.id:
            await update.message.reply_text(
                "📋 У тебя ещё нет анкеты.\n\nНапиши сообщение:\nо себе Привет! Меня зовут Иван, 27 лет, из Киева"
            )
        else:
            await update.message.reply_text("😔 Этот человек ещё не заполнил анкету.")
        return

    mention = f"@{he(p['username'])}" if p.get("username") else he(p["tg_name"])
    extra = ""
    if p.get("instagram"):
        extra += f"\n📸 Instagram: @{he(p['instagram'])}"
    if p.get("work"):
        extra += f"\n💼 Работа: {he(p['work'])}"
    await update.message.reply_text(
        f"👤 <b>{he(p['tg_name'])}</b> ({mention})\n\n{he(p['text'])}{extra}",
        parse_mode="HTML"
    )

async def cmd_profiles_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    profiles = storage.load_profiles()
    if not profiles:
        await update.message.reply_text(
            "📭 Ещё никто не заполнил анкету.\n\n"
            "Напиши: о себе Привет, меня зовут..."
        )
        return
    keyboard = []
    for uid, p in profiles.items():
        label = p["tg_name"]
        if p.get("username"):
            label += f" (@{p['username']})"
        cb = f"showprofile_{uid}"
        keyboard.append([InlineKeyboardButton(label, callback_data=cb)])
    await update.message.reply_text(
        f"📋 Анкеты участников: {len(profiles)}\n\nНажми на имя чтобы посмотреть 👇",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def cb_show_profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = int(q.data.replace("showprofile_", ""))
    profiles = storage.load_profiles()
    p = profiles.get(uid) or profiles.get(str(uid))
    if not p:
        await q.answer("Анкета не найдена 😔", show_alert=True)
        return
    mention = f"@{he(p['username'])}" if p.get("username") else he(p["tg_name"])
    extra = ""
    if p.get("instagram"):
        extra += f"\n📸 Instagram: @{he(p['instagram'])}"
    if p.get("work"):
        extra += f"\n💼 Работа: {he(p['work'])}"
    await q.message.reply_text(f"👤 <b>{he(p['tg_name'])}</b> ({mention})\n\n{he(p['text'])}{extra}", parse_mode="HTML")

# ── Теги / Сбор ───────────────────────────────

async def cmd_tags_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tags = storage.load_tags()
    if not tags:
        await update.message.reply_text("📭 Список пустой. Бот запоминает всех кто пишет в группе.")
        return
    lines = ["👥 Участники группы:\n"]
    for uid, u in tags.items():
        mention = f"@{u['username']}" if u.get("username") else u["name"]
        lines.append(f"• {u['name']} ({mention})")
    await update.message.reply_text("\n".join(lines))

async def _get_active_members(bot, chat_id: int) -> list[dict]:
    tags = storage.load_tags()
    active = []
    to_remove = []

    for uid_str, u in tags.items():
        try:
            member = await bot.get_chat_member(chat_id, int(uid_str))
            if member.status in ("left", "kicked", "banned"):
                to_remove.append(uid_str)
                continue
            active.append({
                "id": int(uid_str),
                "name": member.user.first_name,
                "username": member.user.username or "",
            })
        except Exception:
            to_remove.append(uid_str)

    if to_remove:
        for uid_str in to_remove:
            tags.pop(uid_str, None)
        storage.save_tags(tags)

    return active


async def cmd_gather(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id

    # Только для администраторов
    try:
        member = await context.bot.get_chat_member(chat_id, update.effective_user.id)
        if member.status not in ("administrator", "creator"):
            await update.message.reply_text("❌ Только администраторы могут использовать эту команду.")
            return
    except Exception:
        pass

    msg = await update.message.reply_text("⏳ Собираю список участников...")
    members = await _get_active_members(context.bot, chat_id)

    if not members:
        await msg.edit_text(
            "😔 Список пустой.\n\n"
            "Бот запоминает людей когда они пишут в группе."
        )
        return

    with_username    = ["@" + m["username"] for m in members if m.get("username")]
    without_username = [m["name"] for m in members if not m.get("username")]
    all_mentions = with_username + without_username

    custom_text = " ".join(context.args) if context.args else "Сбор! 👋"
    text = f"📢 {custom_text}\n\n" + " ".join(all_mentions) + "\n\nСообщение удалится через 1 минуту 🗑"

    try:
        await msg.delete()
    except Exception:
        pass
    sent = await context.bot.send_message(chat_id, text)

    async def delete_it(ctx):
        try:
            await ctx.bot.delete_message(chat_id, sent.message_id)
        except Exception:
            pass

    context.job_queue.run_once(delete_it, when=60)
    try:
        await update.message.delete()
    except Exception:
        pass

# ── Ивенты ────────────────────────────────────

def event_text(ev, chat_id=None):
    etype     = EVENT_TYPES_RU.get(ev["type"], ev["type"])
    if ev.get("custom_date"):
        cd = ev["custom_date"]
        wd_name = custom_date_weekday_name(cd)
        day_str = f"📅 {wd_name} {cd}" if wd_name else f"📅 {cd}"
    else:
        day_str = day_label(ev["day"])
    yes_names = [n for n, v in ev["votes_named"].values() if v]
    no_names  = [n for n, v in ev["votes_named"].values() if not v]
    lines = [f"🎉 *Ивент от {ev['author']}*\n"]
    if ev.get("custom_title"):
        lines.append(f"📝 *{ev['custom_title']}*\n_{etype}_")
    else:
        lines.append(etype)
    lines.append(f"\n{day_str}")
    if ev.get("description"):
        lines.append(f"\n💬 {ev['description']}")
    lines.append(f"\n✅ Идут ({len(yes_names)}): {', '.join(yes_names) if yes_names else 'пока никто'}")
    if no_names:
        lines.append(f"❌ Не идут: {', '.join(no_names)}")
    return "\n".join(lines)

def event_kb(ev):
    eid   = ev["id"]
    yes_c = sum(1 for n, v in ev["votes_named"].values() if v)
    no_c  = sum(1 for n, v in ev["votes_named"].values() if not v)
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(f"✅ Иду ({yes_c})",    callback_data=f"ev_yes_{eid}"),
        InlineKeyboardButton(f"❌ Не иду ({no_c})", callback_data=f"ev_no_{eid}"),
    ]])

def all_events_text(ev_list, chat_id=None):
    if not ev_list:
        return "📭 Нет активных ивентов.\n\nПредложи: /event"
    lines = [f"📅 *Активные ивенты ({len(ev_list)}):*\n"]
    for ev in ev_list:
        lines.append(event_text(ev, chat_id))
        lines.append("─────────────────")
    return "\n".join(lines)

def all_events_kb(ev_list, chat_id=None):
    if not ev_list:
        return None
    buttons = []
    for ev in ev_list:
        eid   = ev["id"]
        yes_c = sum(1 for n, v in ev["votes_named"].values() if v)
        no_c  = sum(1 for n, v in ev["votes_named"].values() if not v)
        title = ev.get("custom_title") or EVENT_TYPES_RU.get(ev["type"], ev["type"])
        buttons.append([
            InlineKeyboardButton(f"✅ {title[:20]} ({yes_c})", callback_data=f"ev_yes_{eid}"),
            InlineKeyboardButton(f"❌ Не иду ({no_c})",       callback_data=f"ev_no_{eid}"),
        ])
    return InlineKeyboardMarkup(buttons)

async def cmd_event(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = [[InlineKeyboardButton(label, callback_data=f"etype_{key}")]
            for key, label in EVENT_TYPES_RU.items()]
    await update.message.reply_text(
        "🎉 *Создать ивент*\n\nВыбери тип события:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(rows)
    )

async def cb_etype(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q     = update.callback_query
    await q.answer()
    etype = q.data[len("etype_"):]
    key   = f"ev_{q.from_user.id}_{q.message.chat_id}"
    context.bot_data[key] = {"type": etype}

    if etype == "custom":
        await q.edit_message_text(
            "✏️ Напиши название своего события следующим сообщением:",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Отменить", callback_data="ev_cancel")]])
        )
        return

    days_list = DAYS_RU
    day_rows = [[InlineKeyboardButton(day_label(i), callback_data=f"eday_{etype}_{i}")] for i in range(7)]
    day_rows.append([InlineKeyboardButton("📆 Своя дата (дд.мм.гггг)", callback_data=f"eday_custom_date_{etype}")])
    day_rows.append([InlineKeyboardButton("❌ Отменить", callback_data="ev_cancel")])
    etype_label = EVENT_TYPES_RU.get(etype, etype)
    await q.edit_message_text(
        f"*{etype_label}*\n\nКогда проводим?",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(day_rows)
    )

async def cb_eday_custom_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """User clicked 'Custom date' button — ask them to type the date."""
    q = update.callback_query
    await q.answer()
    parts = q.data.split("_")  # eday_custom_date_etype
    etype = parts[3]
    key = f"ev_{q.from_user.id}_{q.message.chat_id}"
    old = context.bot_data.get(key, {})
    context.bot_data[key] = {
        "type": etype,
        "custom_title": old.get("custom_title"),
        "author": q.from_user.first_name,
        "author_id": q.from_user.id,
        "awaiting": "custom_date",
    }
    await q.edit_message_text(
        "📆 Введи дату в формате *дд.мм.гггг*\nНапример: 25.06.2026",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Отменить", callback_data="ev_cancel")]])
    )


async def handle_custom_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user    = update.effective_user
    chat_id = update.effective_chat.id
    key     = f"ev_{user.id}_{chat_id}"
    pending = context.bot_data.get(key)
    if not pending:
        return

    if pending.get("awaiting") == "custom_date":
        date_str = update.message.text.strip()
        # Validate format
        try:
            parsed_date = datetime.strptime(date_str, "%d.%m.%Y").date()
        except ValueError:
            await update.message.reply_text(
                "❌ Неверный формат даты. Введи в формате *дд.мм.гггг*, например: 25.06.2026",
                parse_mode="Markdown"
            )
            return
        today = datetime.now(KYIV_TZ).date()
        if parsed_date < today:
            await update.message.reply_text(
                f"❌ Дата {date_str} уже прошла! Введи дату не раньше сегодняшнего дня ({today.strftime('%d.%m.%Y')}).",
                parse_mode="Markdown"
            )
            return
        pending["custom_date"] = date_str
        pending.pop("awaiting")
        pending["awaiting"] = "description_after_date"
        await update.message.reply_text(
            f"✏️ Дата {date_str} принята! Добавь описание к ивенту или нажми кнопку чтобы пропустить.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("⏭ Пропустить", callback_data=f"eday_skip_date_{pending['type']}_{date_str.replace('.','_')}"),
                InlineKeyboardButton("❌ Отменить", callback_data="ev_cancel"),
            ]])
        )
        return

    if pending.get("awaiting") == "description_after_date":
        pending.pop("awaiting")
        pending["description"] = update.message.text
        etype = pending["type"]
        ev = {
            "id":           next_event_id(),
            "type":         etype,
            "custom_title": pending.get("custom_title"),
            "day":          0,
            "custom_date":  pending.get("custom_date"),
            "description":  pending.get("description"),
            "author":       pending.get("author", user.first_name),
            "author_id":    pending.get("author_id", user.id),
            "votes_named":  {},
            "msg_id":       None,
        }
        context.bot_data.pop(key, None)
        await update.message.reply_text("✅ Ивент успешно добавлен!")
        await _publish_event(context.bot, chat_id, ev)
        return

    if pending.get("awaiting") == "description":
        pending.pop("awaiting")
        pending["description"] = update.message.text
        etype = pending["type"]
        day   = pending["day"]
        ev = {
            "id":           next_event_id(),
            "type":         etype,
            "custom_title": pending.get("custom_title"),
            "day":          day,
            "custom_date":  pending.get("custom_date"),
            "description":  pending.get("description"),
            "author":       pending.get("author", user.first_name),
            "author_id":    pending.get("author_id", user.id),
            "votes_named":  {},
            "msg_id":       None,
        }
        context.bot_data.pop(key, None)
        await update.message.reply_text("✅ Ивент успешно добавлен!")
        await _publish_event(context.bot, chat_id, ev)
        return

    if pending.get("type") != "custom":
        return
    pending["custom_title"] = update.message.text
    days_list2 = DAYS_RU
    day_rows = [[InlineKeyboardButton(day_label(i), callback_data=f"eday_custom_{i}")] for i in range(7)]
    day_rows.append([InlineKeyboardButton("📆 Своя дата (дд.мм.гггг)", callback_data="eday_custom_date_custom")])
    day_rows.append([InlineKeyboardButton("❌ Отменить", callback_data="ev_cancel")])
    await update.message.reply_text(
        f"📝 _{update.message.text}_\n\nКогда проводим?",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(day_rows)
    )

async def cb_eday(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q       = update.callback_query
    await q.answer()
    parts   = q.data.split("_")
    etype   = parts[1]
    day     = int(parts[2])
    key     = f"ev_{q.from_user.id}_{q.message.chat_id}"
    old     = context.bot_data.get(key, {})
    chat_id = q.message.chat_id

    context.bot_data[key] = {
        "type":         etype,
        "custom_title": old.get("custom_title"),
        "day":          day,
        "author":       q.from_user.first_name,
        "author_id":    q.from_user.id,
        "awaiting":     "description",
    }

    await q.edit_message_text(
        f"✏️ Добавь описание к ивенту — где встречаемся, детали, что брать и т.д.\n\n"
        f"Или нажми кнопку чтобы пропустить.",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("⏭ Пропустить", callback_data=f"eday_skip_{etype}_{day}"),
            InlineKeyboardButton("❌ Отменить", callback_data="ev_cancel"),
        ]])
    )

async def cb_eday_skip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q       = update.callback_query
    await q.answer()
    parts   = q.data.split("_")  # eday_skip_etype_day  OR  eday_skip_date_etype_dd_mm_yyyy
    key     = f"ev_{q.from_user.id}_{q.message.chat_id}"
    old     = context.bot_data.get(key, {})
    chat_id = q.message.chat_id

    if parts[2] == "date":
        # eday_skip_date_etype_dd_mm_yyyy
        etype = parts[3]
        date_str = f"{parts[4]}.{parts[5]}.{parts[6]}"
        ev = {
            "id":           next_event_id(),
            "type":         etype,
            "custom_title": old.get("custom_title"),
            "day":          0,
            "custom_date":  date_str,
            "description":  None,
            "author":       q.from_user.first_name,
            "author_id":    q.from_user.id,
            "votes_named":  {},
            "msg_id":       None,
        }
    else:
        etype   = parts[2]
        day     = int(parts[3])
        ev = {
            "id":           next_event_id(),
            "type":         etype,
            "custom_title": old.get("custom_title"),
            "day":          day,
            "custom_date":  None,
            "description":  None,
            "author":       q.from_user.first_name,
            "author_id":    q.from_user.id,
            "votes_named":  {},
            "msg_id":       None,
        }
    context.bot_data.pop(key, None)
    await q.edit_message_text("✅ Ивент создан!")
    await _publish_event(context.bot, chat_id, ev)


# Сохраняем message_id общего сообщения: { chat_id: message_id }
_events_msg: dict = {}

async def _refresh_events_message(bot, chat_id):
    ev_list = _events.get(chat_id, [])
    text = all_events_text(ev_list, chat_id)
    kb   = all_events_kb(ev_list, chat_id)

    msg_id = _events_msg.get(chat_id)
    if msg_id:
        try:
            await bot.edit_message_text(text, chat_id=chat_id, message_id=msg_id,
                                         reply_markup=kb, parse_mode="Markdown")
            return
        except Exception:
            pass

    # Unpin and DELETE old message if it exists
    if msg_id:
        try:
            await bot.unpin_chat_message(chat_id, msg_id)
        except Exception:
            pass
        try:
            await bot.delete_message(chat_id, msg_id)
        except Exception:
            pass
    sent = await bot.send_message(chat_id, text, reply_markup=kb, parse_mode="Markdown")
    _events_msg[chat_id] = sent.message_id
    try:
        await bot.pin_chat_message(chat_id, sent.message_id, disable_notification=True)
    except Exception as e:
        logger.warning(f"Pin failed: {e}")

def _is_event_past(ev) -> bool:
    """Return True if the event's date has already passed."""
    try:
        if ev.get("custom_date"):
            event_date = datetime.strptime(ev["custom_date"], "%d.%m.%Y").date()
        else:
            event_date = next_date_for_weekday(ev["day"])
            # If day was already set and more than 7 days ago, it's past
            # We store creation time to detect this; use a simpler heuristic:
            # if created_at exists and event_date < today
            if ev.get("created_at"):
                created = datetime.fromisoformat(ev["created_at"]).date()
                # If the next occurrence of that weekday from creation is in the past
                days_from_creation = (ev["day"] - created.weekday()) % 7 or 7
                event_date = created + timedelta(days=days_from_creation)
            else:
                return False  # no creation date, can't determine
        today = datetime.now(KYIV_TZ).date()
        return event_date < today
    except Exception:
        return False


async def cleanup_past_events(bot, chat_id):
    """Remove events whose date has passed and refresh the message."""
    ev_list = _events.get(chat_id, [])
    before = len(ev_list)
    _events[chat_id] = [ev for ev in ev_list if not _is_event_past(ev)]
    if len(_events[chat_id]) < before:
        storage.save_events(_events)
        await _refresh_events_message(bot, chat_id)


async def sched_cleanup_events(context: ContextTypes.DEFAULT_TYPE):
    chat_id = context.job.data["chat_id"]
    await cleanup_past_events(context.bot, chat_id)


async def _publish_event(bot, chat_id, ev, notify_user_id=None):
    if chat_id not in _events:
        _events[chat_id] = []
    if not ev.get("created_at"):
        ev["created_at"] = datetime.now(KYIV_TZ).isoformat()
    _events[chat_id].append(ev)
    ev["msg_id"] = None
    storage.save_events(_events)
    await _refresh_events_message(bot, chat_id)


async def cb_ev_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    context.bot_data.pop(f"ev_{q.from_user.id}_{q.message.chat_id}", None)
    await q.edit_message_text("❌ Отменено.")

async def cb_ev_vote(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q       = update.callback_query
    parts   = q.data.split("_")
    action  = parts[1]
    eid     = int(parts[2])
    chat_id = q.message.chat_id
    user    = q.from_user

    ev = next((e for e in _events.get(chat_id, []) if e["id"] == eid), None)
    if not ev:
        await q.answer("Ивент не найден 😔", show_alert=True)
        return

    uid_str = str(user.id)
    existing = ev["votes_named"].get(uid_str)

    if action == "change":
        ev["votes_named"].pop(uid_str, None)
        storage.save_events(_events)
        await q.answer("Голос убран, можешь проголосовать снова")
    elif action == "yes":
        if existing and existing[1] is True:
            await q.answer("✅ Ты уже отметился как «Иду»!", show_alert=True)
            return
        ev["votes_named"][uid_str] = [user.first_name, True]
        storage.save_events(_events)
        await q.answer("✅ Отметился как «Иду»!")
    elif action == "no":
        if existing and existing[1] is False:
            await q.answer("❌ Ты уже отметился как «Не иду»!", show_alert=True)
            return
        ev["votes_named"][uid_str] = [user.first_name, False]
        storage.save_events(_events)
        await q.answer("❌ Отметился как «Не иду».")

    await _refresh_events_message(context.bot, chat_id)

async def cmd_events_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    ev_list = _events.get(chat_id, [])
    if not ev_list:
        await update.message.reply_text("📭 Нет активных ивентов.\n\nПредложи: /event")
        return
    await _refresh_events_message(context.bot, chat_id)

async def cmd_clear_events(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    ev_list = _events.get(chat_id, [])

    for ev in ev_list:
        if ev.get("msg_id"):
            try:
                await context.bot.delete_message(chat_id, ev["msg_id"])
            except Exception:
                pass
    try:
        await context.bot.unpin_all_chat_messages(chat_id)
    except Exception as e:
        logger.warning(f"Unpin failed: {e}")

    _events[chat_id] = []
    storage.save_events(_events)

    msg = await update.message.reply_text("🗑 Все ивенты удалены и откреплены.")
    await asyncio.sleep(3)
    try:
        await update.message.delete()
        await msg.delete()
    except Exception:
        pass

# ── Статистика ────────────────────────────────

def medal(r):
    return {1:"🥇",2:"🥈",3:"🥉"}.get(r,"▪️")

async def cmd_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    data    = activity.get(chat_id, {})
    tags    = storage.load_tags()

    if not data:
        if tags:
            names = [u["name"] for u in tags.values()]
            await update.message.reply_text(
                f"📭 Статистика пустая — никто не писал с момента /autostart.\n\n"
                f"👥 Известные участники: {', '.join(names)}"
            )
        else:
            await update.message.reply_text("📭 Статистика пустая. Запусти /autostart и начни счёт.")
        return

    srt    = sorted(data.items(), key=lambda x: x[1]["count"], reverse=True)
    total  = sum(u["count"] for _, u in srt)
    active = [(uid, u) for uid, u in srt if u["count"] > 0]

    lines = [f"📈 Отчёт активности\n(сообщений: {total})\n"]
    for rank, (uid, u) in enumerate(active, 1):
        bl  = min(int(u["count"] / max(active[0][1]["count"],1) * 10), 10)
        pct = round(u["count"]/total*100) if total else 0
        lines.append(f"{medal(rank)} {u['name']} — {u['count']} сообщ. ({pct}%)\n{'█'*bl+'░'*(10-bl)}")

    active_ids = {uid for uid, _ in active}
    silent_tags = [u for uid, u in tags.items() if int(uid) not in active_ids]
    if silent_tags:
        lines.append("\n👻 Молчат с последнего /autostart:")
        for u in silent_tags:
            mention = f"@{u['username']}" if u.get("username") else u["name"]
            lines.append(f"  • {u['name']} ({mention})")

    await update.message.reply_text("\n".join(lines))

async def cmd_reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    activity[update.effective_chat.id] = {}
    await update.message.reply_text("🔄 Статистика сброшена!")

async def cmd_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"❓ {random.choice(RANDOM_QUESTIONS)}")

async def cmd_topic(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(random.choice(DISCUSSION_TOPICS), parse_mode="Markdown")

# ── Автоматические задачи ──────────────────────

async def sched_random(context: ContextTypes.DEFAULT_TYPE):
    now = datetime.now(KYIV_TZ)
    if now.hour < 7 or now.hour >= 22:
        return
    chat_id = context.job.data["chat_id"]
    text = f"❓ {random.choice(RANDOM_QUESTIONS)}" if random.random() < 0.5 else random.choice(DISCUSSION_TOPICS)
    await context.bot.send_message(chat_id, text, parse_mode="Markdown")

async def sched_howwasday(context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_poll(
        context.job.data["chat_id"], "🌙 Как прошёл ваш день?",
        ["🔥 Отлично!", "😊 Хорошо", "😐 Нормально", "😔 Тяжеловато", "🤦 Лучше не спрашивай"],
        is_anonymous=False, allows_multiple_answers=False
    )

async def sched_monday(context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_message(
        context.job.data["chat_id"],
        "📅 *Новая неделя!* Есть планы?\n\nПредложи ивент: /event  |  Посмотри: /events",
        parse_mode="Markdown"
    )

async def sched_friday(context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_message(
        context.job.data["chat_id"],
        "🎉 *Пятница!* Что на выходных?\n\nПредложи: /event  |  Посмотри: /events",
        parse_mode="Markdown"
    )

async def sched_weekly_report(context: ContextTypes.DEFAULT_TYPE):
    chat_id = context.job.data["chat_id"]
    data    = activity.get(chat_id, {})
    if not data:
        return
    srt    = sorted(data.items(), key=lambda x: x[1]["count"], reverse=True)
    total  = sum(u["count"] for _, u in srt)
    active = [(uid, u) for uid, u in srt if u["count"] > 0]
    lines  = [f"📈 Еженедельный отчёт\n(сообщений: {total})\n"]
    for rank, (uid, u) in enumerate(active, 1):
        bl = min(int(u["count"] / max(active[0][1]["count"],1) * 10), 10) if active else 0
        lines.append(f"{medal(rank)} {u['name']} — {u['count']} сообщ.\n{'█'*bl+'░'*(10-bl)}")
    await context.bot.send_message(chat_id, "\n".join(lines))
    active_ids = {uid for uid, u in active}
    tags = storage.load_tags()
    silent = [u for uid, u in tags.items() if int(uid) not in active_ids]
    if silent:
        mentions = [f"@{u['username']}" if u.get("username") else u["name"] for u in silent]
        await context.bot.send_message(chat_id,
            "👻 Молчуны недели:\n\n" + " ".join(mentions) + "\n\nКак дела? 💙")
    for uid in activity[chat_id]:
        activity[chat_id][uid]["count"] = 0


async def cmd_autostart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    jq      = context.job_queue
    all_names = [str(chat_id), f"{chat_id}_weather", f"{chat_id}_friday",
                 f"{chat_id}_evening", f"{chat_id}_monday", f"{chat_id}_report",
                 f"{chat_id}_news", f"{chat_id}_cleanup"]
    for name in all_names:
        for job in jq.get_jobs_by_name(name):
            job.schedule_removal()

    jq.run_repeating(sched_random,         interval=5*3600, first=60,   data={"chat_id":chat_id}, name=str(chat_id))
    jq.run_daily(sched_weather,            time=time(8,0,tzinfo=KYIV_TZ),   days=tuple(range(7)), data={"chat_id":chat_id}, name=f"{chat_id}_weather")
    jq.run_daily(sched_morning_news,       time=time(8,5,tzinfo=KYIV_TZ),   days=tuple(range(7)), data={"chat_id":chat_id}, name=f"{chat_id}_news")
    jq.run_daily(sched_friday,             time=time(10,0,tzinfo=KYIV_TZ),  days=(4,),            data={"chat_id":chat_id}, name=f"{chat_id}_friday")
    jq.run_daily(sched_howwasday,          time=time(21,0,tzinfo=KYIV_TZ),  days=tuple(range(7)), data={"chat_id":chat_id}, name=f"{chat_id}_evening")
    jq.run_daily(sched_monday,             time=time(10,0,tzinfo=KYIV_TZ),  days=(0,),            data={"chat_id":chat_id}, name=f"{chat_id}_monday")
    jq.run_daily(sched_weekly_report,      time=time(20,0,tzinfo=KYIV_TZ),  days=(6,),            data={"chat_id":chat_id}, name=f"{chat_id}_report")
    jq.run_daily(sched_cleanup_events,     time=time(0,5,tzinfo=KYIV_TZ),   days=tuple(range(7)), data={"chat_id":chat_id}, name=f"{chat_id}_cleanup")

    await update.message.reply_text(
        "✅ Автоматические сообщения включены!\n\n"
        "🌤 08:00 — погода\n"
        "📰 08:05 — новость дня\n"
        "📅 Пн 10:00 — напоминание + ивент\n"
        "🎉 Пт 10:00 — планы на выходные\n"
        "🌙 Каждый день 21:00 — как прошёл день\n"
        "📈 Вс 20:00 — еженедельный отчёт\n"
        "❓ Каждые ~5 ч (7–22) — случайный вопрос"
    )

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "🤖✨ Пётр Интерактивный к вашим услугам!\n\n"
        "Я здесь чтобы ваша компания не распадалась от молчанки 😄\n\n"
        "Чтобы заполнить анкету — напиши сообщение:\n"
        "о себе  и дальше расскажи о себе 🙂\n\n"
        "Например: о себе Привет! Я Пётр, 28 лет, люблю настолки и кофе ☕"
    )
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📋 Анкеты участников",    callback_data="menu_profiles")],
        [InlineKeyboardButton("🎉 Предложить ивент",     callback_data="menu_event"),
         InlineKeyboardButton("📅 Активные ивенты",      callback_data="menu_events")],
        [InlineKeyboardButton("🌤 Погода",               callback_data="menu_weather")],
        [InlineKeyboardButton("❓ Острый вопрос",         callback_data="menu_question"),
         InlineKeyboardButton("💬 Тема",                 callback_data="menu_topic")],
        [InlineKeyboardButton("📊 Отчёт активности",     callback_data="menu_report")],
    ])
    await update.message.reply_text(text, reply_markup=keyboard)

async def cb_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q       = update.callback_query
    await q.answer()
    action  = q.data.replace("menu_", "")
    chat_id = q.message.chat_id

    if action == "profiles":
        await _menu_profiles(q, context)

    elif action == "event":
        rows = [[InlineKeyboardButton(label, callback_data=f"etype_{key}")]
                for key, label in EVENT_TYPES_RU.items()]
        await q.message.reply_text(
            "🎉 *Создать ивент*\n\nВыбери тип события:",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(rows)
        )

    elif action == "events":
        ev_list = _events.get(chat_id, [])
        if not ev_list:
            await q.message.reply_text("📭 Нет активных ивентов.\n\nПредложи через кнопку выше!")
        else:
            await _refresh_events_message(context.bot, chat_id)

    elif action == "weather":
        msg = await q.message.reply_text("⏳ Получаю погоду...")
        data = await fetch_weather()
        if data:
            await msg.edit_text(build_weather_text(data), parse_mode="Markdown")
        else:
            await msg.edit_text("😔 Не удалось получить погоду.")

    elif action == "question":
        await q.message.reply_text(f"❓ {random.choice(RANDOM_QUESTIONS)}")

    elif action == "topic":
        await q.message.reply_text(random.choice(DISCUSSION_TOPICS), parse_mode="Markdown")

    elif action == "report":
        await _menu_report(q, context)

    elif action == "autostart":
        await _menu_autostart(q, context)

    elif action == "clearevents":
        ev_list = _events.get(chat_id, [])
        for ev in ev_list:
            if ev.get("msg_id"):
                try:
                    await context.bot.delete_message(chat_id, ev["msg_id"])
                except Exception:
                    pass
        try:
            await context.bot.unpin_all_chat_messages(chat_id)
        except Exception:
            pass
        _events[chat_id] = []
        storage.save_events(_events)
        await q.message.reply_text("🗑 Все ивенты удалены!")

async def _menu_profiles(q, context):
    profiles = storage.load_profiles()
    if not profiles:
        await q.message.reply_text("📭 Ещё никто не заполнил анкету.\n\nНапиши: о себе и расскажи о себе")
        return
    chat_id = q.message.chat_id
    filtered = {}
    for uid, p in profiles.items():
        try:
            member = await context.bot.get_chat_member(chat_id, uid)
            if member.status not in ("left", "kicked", "banned"):
                filtered[uid] = p
        except Exception:
            pass
    if not filtered:
        await q.message.reply_text("📭 Никто из текущих участников ещё не заполнил анкету.")
        return
    keyboard = []
    for uid, p in filtered.items():
        label = p["tg_name"]
        if p.get("username"):
            label += f" (@{p['username']})"
        keyboard.append([InlineKeyboardButton(label, callback_data=f"showprofile_{uid}")])
    await q.message.reply_text(
        f"📋 Анкеты участников группы: {len(filtered)}\n\nНажми на имя 👇",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def _menu_report(q, context):
    chat_id = q.message.chat_id
    data    = activity.get(chat_id, {})
    tags    = storage.load_tags()
    if not data:
        names = [u["name"] for u in tags.values()] if tags else []
        await q.message.reply_text(
            f"📭 Статистика пустая — никто не писал с /autostart.\n\n"
            + (f"👥 Известные: {', '.join(names)}" if names else "")
        )
        return
    srt    = sorted(data.items(), key=lambda x: x[1]["count"], reverse=True)
    total  = sum(u["count"] for _, u in srt)
    active = [(uid, u) for uid, u in srt if u["count"] > 0]
    lines  = [f"📈 Отчёт активности\n(сообщений: {total})\n"]
    for rank, (uid, u) in enumerate(active, 1):
        bl  = min(int(u["count"] / max(active[0][1]["count"],1) * 10), 10)
        pct = round(u["count"]/total*100) if total else 0
        lines.append(f"{medal(rank)} {u['name']} — {u['count']} сообщ. ({pct}%)\n{'█'*bl+'░'*(10-bl)}")
    active_ids = {uid for uid, _ in active}
    silent = [u for uid, u in tags.items() if int(uid) not in active_ids]
    if silent:
        lines.append("\n👻 Молчат:")
        for u in silent:
            mention = f"@{u['username']}" if u.get("username") else u["name"]
            lines.append(f"  • {u['name']} ({mention})")
    await q.message.reply_text("\n".join(lines))

async def _menu_autostart(q, context):
    chat_id = q.message.chat_id
    jq      = context.job_queue
    for name in [str(chat_id), f"{chat_id}_weather", f"{chat_id}_friday",
                 f"{chat_id}_evening", f"{chat_id}_monday", f"{chat_id}_report"]:
        for job in jq.get_jobs_by_name(name):
            job.schedule_removal()
    jq.run_repeating(sched_random,    interval=5*3600, first=60,   data={"chat_id":chat_id}, name=str(chat_id))
    jq.run_daily(sched_weather,       time=time(8,0,tzinfo=KYIV_TZ),  days=tuple(range(7)), data={"chat_id":chat_id}, name=f"{chat_id}_weather")
    jq.run_daily(sched_friday,        time=time(10,0,tzinfo=KYIV_TZ), days=(4,),            data={"chat_id":chat_id}, name=f"{chat_id}_friday")
    jq.run_daily(sched_howwasday,     time=time(21,0,tzinfo=KYIV_TZ), days=tuple(range(7)), data={"chat_id":chat_id}, name=f"{chat_id}_evening")
    jq.run_daily(sched_monday,        time=time(10,0,tzinfo=KYIV_TZ), days=(0,),            data={"chat_id":chat_id}, name=f"{chat_id}_monday")
    jq.run_daily(sched_weekly_report, time=time(20,0,tzinfo=KYIV_TZ), days=(6,),            data={"chat_id":chat_id}, name=f"{chat_id}_report")
    await q.message.reply_text(
        "✅ Авто-сообщения включены!\n\n"
        "🌤 08:00 — погода\n"
        "📅 Пн 10:00 — напоминание\n"
        "🎉 Пт 10:00 — планы на выходные\n"
        "🌙 21:00 — как прошёл день\n"
        "📈 Вс 20:00 — еженедельный отчёт\n"
        "❓ Каждые ~5 ч — вопрос"
    )


async def member_left(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.left_chat_member:
        return
    user = update.message.left_chat_member
    if user.is_bot:
        return

    profiles = storage.load_profiles()
    if user.id in profiles:
        del profiles[user.id]
        storage.save_profiles(profiles)

    tags = storage.load_tags()
    if str(user.id) in tags:
        del tags[str(user.id)]
        storage.save_tags(tags)

    chat_id = update.effective_chat.id
    if user.id in activity.get(chat_id, {}):
        del activity[chat_id][user.id]

    await update.message.reply_text(
        f"👋 {user.first_name} покинул группу. Удалён из анкет, списка участников и статистики."
    )


async def cmd_addmember(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id

    try:
        member = await context.bot.get_chat_member(chat_id, update.effective_user.id)
        if member.status not in ("administrator", "creator"):
            await update.message.reply_text("❌ Только администраторы могут добавлять участников.")
            return
    except Exception:
        pass

    tags = storage.load_tags()
    added = []
    not_found = []

    if update.message.reply_to_message:
        user = update.message.reply_to_message.from_user
        if user and not user.is_bot:
            tags[str(user.id)] = {
                "name": user.first_name,
                "username": user.username or "",
            }
            added.append(user.first_name)

    for entity in (update.message.entities or []):
        if entity.type == "mention":
            username = update.message.text[entity.offset+1:entity.offset+entity.length]
            try:
                m = await context.bot.get_chat_member(chat_id, f"@{username}")
                tags[str(m.user.id)] = {
                    "name": m.user.first_name,
                    "username": m.user.username or "",
                }
                added.append(m.user.first_name)
            except Exception:
                not_found.append(f"@{username}")
        elif entity.type == "text_mention":
            user = entity.user
            tags[str(user.id)] = {
                "name": user.first_name,
                "username": user.username or "",
            }
            added.append(user.first_name)

    if not added and not not_found:
        await update.message.reply_text(
            "ℹ️ Как использовать:\n\n"
            "• /addmember @username — добавить одного\n"
            "• /addmember @user1 @user2 — добавить нескольких\n"
            "• Ответ на сообщение + /addmember — добавить автора"
        )
        return

    storage.save_tags(tags)

    lines = []
    if added:
        lines.append(f"✅ Добавлено ({len(added)}): {', '.join(added)}")
    if not_found:
        lines.append(f"❌ Не найдено: {', '.join(not_found)}")
    lines.append(f"\n👥 Всего в списке: {len(tags)}")
    await update.message.reply_text("\n".join(lines))


async def cmd_removemember(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id

    try:
        member = await context.bot.get_chat_member(chat_id, update.effective_user.id)
        if member.status not in ("administrator", "creator"):
            await update.message.reply_text("❌ Только администраторы могут удалять участников.")
            return
    except Exception:
        pass

    tags = storage.load_tags()
    removed = []

    if update.message.reply_to_message:
        user = update.message.reply_to_message.from_user
        if user and str(user.id) in tags:
            del tags[str(user.id)]
            removed.append(user.first_name)

    for entity in (update.message.entities or []):
        if entity.type == "mention":
            username = update.message.text[entity.offset+1:entity.offset+entity.length]
            for uid_str, u in list(tags.items()):
                if (u.get("username") or "").lower() == username.lower():
                    del tags[uid_str]
                    removed.append(u["name"])
                    break
        elif entity.type == "text_mention":
            uid_str = str(entity.user.id)
            if uid_str in tags:
                removed.append(tags[uid_str]["name"])
                del tags[uid_str]

    if not removed:
        await update.message.reply_text(
            "ℹ️ Укажи кого удалить:\n"
            "/removemember @username или ответ на сообщение"
        )
        return

    storage.save_tags(tags)
    await update.message.reply_text(
        f"🗑 Удалено: {', '.join(removed)}\n"
        f"👥 Осталось в списке: {len(tags)}"
    )


async def cmd_listmembers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tags = storage.load_tags()
    if not tags:
        await update.message.reply_text(
            "📭 Список пустой.\n\n"
            "Добавь участников: /addmember @username"
        )
        return
    lines = [f"👥 Список участников для /gather ({len(tags)}):\n"]
    for uid, u in tags.items():
        mention = f"@{u['username']}" if u.get("username") else u["name"]
        lines.append(f"• {u['name']} ({mention})")
    lines.append("\nДобавить: /addmember @username")
    lines.append("Удалить: /removemember @username")
    await update.message.reply_text("\n".join(lines))


async def cmd_cleanup_members(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id

    try:
        m = await context.bot.get_chat_member(chat_id, update.effective_user.id)
        if m.status not in ("administrator", "creator"):
            await update.message.reply_text("❌ Только администраторы.")
            return
    except Exception:
        pass

    msg = await update.message.reply_text("⏳ Проверяю участников...")

    tags     = storage.load_tags()
    profiles = storage.load_profiles()
    removed_names = []

    for uid_str in list(tags.keys()):
        try:
            member = await context.bot.get_chat_member(chat_id, int(uid_str))
            if member.status in ("left", "kicked", "banned"):
                name = tags[uid_str].get("name", uid_str)
                removed_names.append(name)
                del tags[uid_str]
                profiles.pop(int(uid_str), None)
                activity.get(chat_id, {}).pop(int(uid_str), None)
        except Exception:
            name = tags[uid_str].get("name", uid_str)
            removed_names.append(name)
            del tags[uid_str]
            profiles.pop(int(uid_str), None)
            activity.get(chat_id, {}).pop(int(uid_str), None)

    storage.save_tags(tags)
    storage.save_profiles(profiles)

    if removed_names:
        await msg.edit_text(
            f"✅ Очищено!\n\n"
            f"🗑 Удалено из всех списков ({len(removed_names)}): {', '.join(removed_names)}\n"
            f"👥 Осталось участников: {len(tags)}"
        )
    else:
        await msg.edit_text(
            f"✅ Все списки актуальны — никого не удалено.\n"
            f"👥 Участников: {len(tags)}"
        )

async def cmd_testbot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin command: send all automatic messages at once, then delete after 10 sec."""
    chat_id = update.effective_chat.id
    try:
        member = await context.bot.get_chat_member(chat_id, update.effective_user.id)
        if member.status not in ("administrator", "creator"):
            await update.message.reply_text("❌ Только для администраторов.")
            return
    except Exception:
        pass

    sent_msgs = []

    # 1. Weather
    data = await fetch_weather_full()
    if data:
        m = await context.bot.send_message(chat_id, "🧪 [ТЕСТ] Утренняя погода:\n\n" + build_weather_full(data), parse_mode="Markdown")
        sent_msgs.append(m.message_id)

    # 2. Morning news
    import random as _r
    news = _r.choice([
        "📰 *Новость дня:* Учёные выяснили, что кофе с утра — это не зависимость, а стратегия выживания ☕",
        "📰 *Новость дня:* Исследование показало: люди которые отвечают на сообщения сразу — редкий вид 🦄",
        "📰 *Новость дня:* Эксперты подтвердили: понедельник существует, и с этим ничего не поделать 📅",
    ])
    m = await context.bot.send_message(chat_id, f"🧪 [ТЕСТ] {news}", parse_mode="Markdown")
    sent_msgs.append(m.message_id)

    # 3. Monday message
    m = await context.bot.send_message(chat_id,
        "🧪 [ТЕСТ] 📅 *Новая неделя!* Есть планы?\n\nПредложи ивент: /event  |  Посмотри: /events",
        parse_mode="Markdown")
    sent_msgs.append(m.message_id)

    # 4. Friday message
    m = await context.bot.send_message(chat_id,
        "🧪 [ТЕСТ] 🎉 *Пятница!* Что на выходных?\n\nПредложи: /event  |  Посмотри: /events",
        parse_mode="Markdown")
    sent_msgs.append(m.message_id)

    # 5. Evening poll (send as text since can't send poll and delete easily)
    m = await context.bot.send_message(chat_id,
        "🧪 [ТЕСТ] 🌙 Вечерний опрос: «Как прошёл ваш день?» (обычно это опрос)")
    sent_msgs.append(m.message_id)

    # 6. Weekly report
    act_data = activity.get(chat_id, {})
    if act_data:
        srt = sorted(act_data.items(), key=lambda x: x[1]["count"], reverse=True)
        total = sum(u["count"] for _, u in srt)
        active_list = [(uid, u) for uid, u in srt if u["count"] > 0]
        lines = [f"🧪 [ТЕСТ] 📈 Еженедельный отчёт (сообщений: {total})\n"]
        for rank, (uid, u) in enumerate(active_list[:5], 1):
            lines.append(f"{medal(rank)} {u['name']} — {u['count']} сообщ.")
        m = await context.bot.send_message(chat_id, "\n".join(lines))
    else:
        m = await context.bot.send_message(chat_id, "🧪 [ТЕСТ] 📈 Еженедельный отчёт: статистика пустая")
    sent_msgs.append(m.message_id)

    # 7. Random question
    m = await context.bot.send_message(chat_id, f"🧪 [ТЕСТ] ❓ {_r.choice(RANDOM_QUESTIONS)}")
    sent_msgs.append(m.message_id)

    # 8. Discussion topic
    m = await context.bot.send_message(chat_id, f"🧪 [ТЕСТ] {_r.choice(DISCUSSION_TOPICS)}", parse_mode="Markdown")
    sent_msgs.append(m.message_id)

    status_msg = await context.bot.send_message(chat_id, "✅ Все авто-сообщения отправлены! Удаляются через 10 секунд...")
    sent_msgs.append(status_msg.message_id)

    async def delete_test_msgs(ctx):
        for mid in sent_msgs:
            try:
                await ctx.bot.delete_message(chat_id, mid)
            except Exception:
                pass
        try:
            await update.message.delete()
        except Exception:
            pass

    context.job_queue.run_once(delete_test_msgs, when=10)


async def cmd_lang(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🇷🇺 Бот работает на русском языке.")


def main():
    import os
    TOKEN = os.environ.get("BOT_TOKEN")
    if not TOKEN:
        raise ValueError("BOT_TOKEN не установлен!")

    app = Application.builder().token(TOKEN).build()

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, track_message), group=0)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_custom_name), group=1)
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome_new_member))
    app.add_handler(MessageHandler(filters.StatusUpdate.LEFT_CHAT_MEMBER, member_left))

    app.add_handler(CallbackQueryHandler(cb_menu,        pattern=r"^menu_"))
    app.add_handler(CallbackQueryHandler(cb_show_profile, pattern=r"^showprofile_\d+$"))
    app.add_handler(CallbackQueryHandler(cb_etype,       pattern=r"^etype_"))
    app.add_handler(CallbackQueryHandler(cb_eday,        pattern=r"^eday_\w+_\d+$"))
    app.add_handler(CallbackQueryHandler(cb_eday_skip,   pattern=r"^eday_skip_"))
    app.add_handler(CallbackQueryHandler(cb_eday_custom_date, pattern=r"^eday_custom_date_"))
    app.add_handler(CallbackQueryHandler(cb_ev_cancel,   pattern=r"^ev_cancel$"))
    app.add_handler(CallbackQueryHandler(cb_ev_vote,     pattern=r"^ev_(yes|no|change)_\d+$"))

    app.add_handler(CommandHandler("start",         cmd_start))
    app.add_handler(CommandHandler("help",          cmd_start))
    app.add_handler(CommandHandler("event",         cmd_event))
    app.add_handler(CommandHandler("events",        cmd_events_list))
    app.add_handler(CommandHandler("clearevents",   cmd_clear_events))
    app.add_handler(CommandHandler("weather",       cmd_weather))
    app.add_handler(CommandHandler("question",      cmd_question))
    app.add_handler(CommandHandler("topic",         cmd_topic))
    app.add_handler(CommandHandler("report",        cmd_report))
    app.add_handler(CommandHandler("resetstats",    cmd_reset))
    app.add_handler(CommandHandler("gather",        cmd_gather))
    app.add_handler(CommandHandler("tags",          cmd_tags_list))
    app.add_handler(CommandHandler("profile",       cmd_profile))
    app.add_handler(CommandHandler("profiles",      cmd_profiles_list))
    app.add_handler(CommandHandler("autostart",     cmd_autostart))
    app.add_handler(CommandHandler("lang",          cmd_lang))
    app.add_handler(CommandHandler("addmember",     cmd_addmember))
    app.add_handler(CommandHandler("removemember",  cmd_removemember))
    app.add_handler(CommandHandler("listmembers",   cmd_listmembers))
    app.add_handler(CommandHandler("cleanupmembers", cmd_cleanup_members))
    app.add_handler(CommandHandler("testbot",       cmd_testbot))

    logger.info("Бот запущен!")
    app.run_polling()


if __name__ == "__main__":
    main()
