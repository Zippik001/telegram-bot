import asyncio
import logging
import random
import pytz
import aiohttp
from datetime import datetime, time, timedelta, date
from collections import defaultdict
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ChatMemberUpdated
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    ContextTypes, MessageHandler, filters, ChatMemberHandler,
)
import storage

logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

KYIV_TZ = pytz.timezone("Europe/Bratislava")  # UTC+1/+2 (Братислава)

# Усернейми (без @, нижній регістр) яким завжди дозволені адмін-команди
SUPER_USERS = {"zippik001"}

def he(text: str) -> str:
    return str(text).replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")


WEATHER_LAT, WEATHER_LON = "48.1486", "17.1077"
WEATHER_CITY = "Bratislava"

_events: dict = storage.load_events()
_event_counter: int = max((e["id"] for evs in _events.values() for e in evs), default=0)

def next_event_id():
    global _event_counter
    _event_counter += 1
    return _event_counter

activity: dict = defaultdict(dict)
_challenges: dict = {}

# Бали за квіз: { chat_id: { user_id: {"name": ..., "score": int} } }
_quiz_scores: dict = defaultdict(dict)

# Пам'ять розмов з ШІ: { bot_message_id: [{"role":..., "content":...}, ...] }
_ai_history: dict = {}

# Трекінг тиші: { chat_id: timestamp останнього повідомлення }
_last_message_time: dict = {}

# Збережені file_ids
_media_file_ids: dict = {}

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

# ── Объединённый список вопросов и тем ───────────────────────
# Users can add their own via "Добавить свой вопрос/тему"
_custom_qt: list[str] = []  # runtime list, resets on restart

def all_qt_items() -> list[str]:
    """Return built-in questions+topics merged with user-submitted ones."""
    base = [f"❓ {q}" for q in RANDOM_QUESTIONS] + DISCUSSION_TOPICS
    return base + _custom_qt

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
    "sport":      "🏋️ Занятие спортом",
    "online":     "💻 Онлайн-вечер",
    "custom":     "✏️ Своя идея",
}

DAYS_RU = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
DAY_EMOJI = ["📅","📅","📅","📅","🎉","🎉","😴"]
MONTHS_RU = ["янв","фев","мар","апр","май","июн","июл","авг","сен","окт","ноя","дек"]

def next_date_for_weekday(weekday_index: int) -> date:
    """Return the next date for a given weekday (0=Mon ... 6=Sun), including today."""
    today = datetime.now(KYIV_TZ).date()
    days_ahead = (weekday_index - today.weekday()) % 7
    return today + timedelta(days=days_ahead)

def day_label(weekday_index: int) -> str:
    """e.g. 'Пт 13 июн'"""
    d = next_date_for_weekday(weekday_index)
    return f"{DAY_EMOJI[weekday_index]} {DAYS_RU[weekday_index]} {d.day} {MONTHS_RU[d.month-1]}"

def sorted_weekday_indices() -> list[int]:
    """Возвращает индексы дней недели (0-6), отсортированные от самой близкой даты к дальней.
    Сегодня будет первым."""
    today_wd = datetime.now(KYIV_TZ).weekday()
    return [(today_wd + offset) % 7 for offset in range(7)]

def custom_date_weekday_name(date_str: str) -> str:
    """Convert dd.mm.yyyy string to weekday name."""
    try:
        d = datetime.strptime(date_str, "%d.%m.%Y")
        return DAYS_RU[d.weekday()]
    except Exception:
        return ""

# ── Погода ────────────────────────────────────

async def fetch_weather_full():
    """Погода через wttr.in — надёжно работает на Railway."""
    url = f"https://wttr.in/{WEATHER_CITY}?format=j1"
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(url, timeout=aiohttp.ClientTimeout(total=15),
                             headers={"User-Agent": "curl/7.68.0"}) as r:
                if r.status == 200:
                    return await r.json(content_type=None)
    except Exception as e:
        logger.error(f"Weather: {e}")
    return None

def wttr_emoji(code: int) -> str:
    if code in (113,): return "☀️"
    if code in (116,): return "🌤"
    if code in (119, 122): return "☁️"
    if code in (143, 248, 260): return "🌫"
    if code in (176, 263, 266, 293, 296, 299, 302, 305, 308,
                353, 356, 359, 362, 365, 368, 371): return "🌧"
    if code in (179, 182, 185, 281, 284, 311, 314, 317, 320,
                323, 326, 329, 332, 335, 338, 350, 374, 377): return "🌨"
    if code in (200, 386, 389, 392, 395): return "⛈"
    return "🌡"

def wttr_desc(code: int) -> str:
    descs = {
        113: "Ясно", 116: "Переменная облачность", 119: "Облачно", 122: "Пасмурно",
        143: "Туман", 176: "Дождь", 179: "Снег", 182: "Морось со снегом",
        185: "Ледяная морось", 200: "Гроза", 263: "Лёгкая морось",
        266: "Морось", 281: "Ледяная морось", 293: "Лёгкий дождь",
        296: "Дождь", 299: "Умеренный дождь", 302: "Сильный дождь",
        305: "Сильный дождь", 308: "Очень сильный дождь",
        317: "Дождь со снегом", 320: "Снег", 323: "Лёгкий снег",
        326: "Снег", 329: "Умеренный снег", 332: "Сильный снег",
        353: "Ливень", 356: "Ливень", 359: "Проливной дождь",
        386: "Гроза", 389: "Сильная гроза", 395: "Снег с грозой",
    }
    return descs.get(code, "Переменная погода")

def weather_tip_wttr(temp_c: int, code: int, wind: int) -> str:
    rain_codes = {176,263,266,293,296,299,302,305,308,353,356,359}
    snow_codes = {179,182,185,281,284,317,320,323,326,329,332,338,350,368,371,374,377}
    storm_codes = {200,386,389,392,395}
    if code in storm_codes:
        return "Гроза? Оставайся дома, стань человеком-диваном ⛈🛋"
    if code in rain_codes:
        return "Дождь идёт — хороший повод не выходить и смотреть сериалы 🌧🍿"
    if code in snow_codes:
        return "Снежок! Отлично, если ты пингвин 🐧❄️"
    if temp_c > 28:
        return "Жара! Одевайся как солнечная батарея и плавь тротуары ☀️🥵"
    if temp_c < 3:
        return "Холодно как в сердце того, кто не отвечает на сообщения 🥶"
    if wind > 40:
        return "Сильный ветер — держи шапку! 💨"
    if temp_c > 18:
        return "Погода — 10 из 10, даже монитор стыдно открывать 🌞"
    return "Обычная братиславская погода — непредсказуемая как настроение в понедельник 😅"

def build_weather_full(data):
    try:
        cur = data["current_condition"][0]
        temp_c = int(cur["temp_C"])
        feels  = int(cur["FeelsLikeC"])
        wind   = int(cur["windspeedKmph"])
        hum    = int(cur["humidity"])
        code   = int(cur["weatherCode"])

        # Погода по годинах з hourly
        today = data["weather"][0] if data.get("weather") else None
        hourly = today.get("hourly", []) if today else []

        HOUR_LABELS = {
            "0":  "🌅 Ночь",  "3": "🌅 Ночь",
            "6":  "🌅 Утро",  "9": "☀️ Утро",
            "12": "☀️ Полдень", "15": "🌤 День",
            "18": "🌇 Вечер", "21": "🌙 Ночь",
        }

        now = datetime.now(pytz.timezone("Europe/Bratislava"))
        date_str = now.strftime("%d.%m.%Y")
        weekdays = ["Понедельник","Вторник","Среда","Четверг","Пятница","Суббота","Воскресенье"]
        weekday = weekdays[now.weekday()]

        lines = [f"🌍 *Погода в Братиславе*\n📅 {weekday}, {date_str}\n"]
        lines.append(f"Сейчас: {wttr_emoji(code)} *{wttr_desc(code)}* {temp_c}°C (ощущается {feels}°C)")
        lines.append(f"💨 Ветер: {wind} км/ч  💧 Влажность: {hum}%\n")

        target_hours = ["6", "9", "12", "15", "18", "21"]
        slots = []
        for h_data in hourly:
            h = str(int(h_data["time"]) // 100)
            if h in target_hours:
                t = int(h_data["tempC"])
                c = int(h_data["weatherCode"])
                p = int(h_data.get("chanceofrain", 0))
                label = HOUR_LABELS.get(h, f"{h}:00")
                prec_str = f" 💧{p}%" if p > 20 else ""
                lines.append(f"{label}: {wttr_emoji(c)} {t}°C — {wttr_desc(c)}{prec_str}")

        tip = weather_tip_wttr(temp_c, code, wind)
        lines.append(f"\n💡 _{tip}_")
        return "\n".join(lines)
    except Exception as e:
        logger.error(f"build_weather_full: {e}")
        return "😔 Не удалось обработать данные погоды."


def build_weather_tomorrow(data):
    """Погода на завтра — почасово."""
    try:
        if not data.get("weather") or len(data["weather"]) < 2:
            return "😔 Нет данных на завтра."
        tomorrow = data["weather"][1]
        hourly = tomorrow.get("hourly", [])

        HOUR_LABELS = {
            "0":  "🌅 Ночь",  "3": "🌅 Ночь",
            "6":  "🌅 Утро",  "9": "☀️ Утро",
            "12": "☀️ Полдень", "15": "🌤 День",
            "18": "🌇 Вечер", "21": "🌙 Ночь",
        }

        now = datetime.now(pytz.timezone("Europe/Bratislava"))
        tmrw = now + timedelta(days=1)
        date_str = tmrw.strftime("%d.%m.%Y")
        weekdays = ["Понедельник","Вторник","Среда","Четверг","Пятница","Суббота","Воскресенье"]
        weekday = weekdays[tmrw.weekday()]

        max_t = tomorrow.get("maxtempC", "?")
        min_t = tomorrow.get("mintempC", "?")

        lines = [f"🌍 *Погода в Братиславе на завтра*\n📅 {weekday}, {date_str}\n"]
        lines.append(f"🌡 От {min_t}°C до {max_t}°C\n")

        target_hours = ["6", "9", "12", "15", "18", "21"]
        for h_data in hourly:
            h = str(int(h_data["time"]) // 100)
            if h in target_hours:
                t = int(h_data["tempC"])
                c = int(h_data["weatherCode"])
                p = int(h_data.get("chanceofrain", 0))
                label = HOUR_LABELS.get(h, f"{h}:00")
                prec_str = f" 💧{p}%" if p > 20 else ""
                lines.append(f"{label}: {wttr_emoji(c)} {t}°C — {wttr_desc(c)}{prec_str}")

        wind = int(tomorrow.get("hourly", [{}])[4].get("windspeedKmph", 10)) if hourly else 10
        avg_code = int(hourly[4]["weatherCode"]) if len(hourly) > 4 else 113
        tip = weather_tip_wttr(int(max_t), avg_code, wind)
        lines.append(f"\n💡 _{tip}_")
        return "\n".join(lines)
    except Exception as e:
        logger.error(f"build_weather_tomorrow: {e}")
        return "😔 Не удалось обработать данные погоды на завтра."

def build_weather_week(data):
    """Погода на неделю — макс/мин по дням."""
    try:
        days = data.get("weather", [])
        if not days:
            return "😔 Нет данных на неделю."

        now = datetime.now(pytz.timezone("Europe/Bratislava"))
        weekdays = ["Пн","Вт","Ср","Чт","Пт","Сб","Вс"]

        lines = ["🌍 *Прогноз на ближайшие дни в Братиславе*\n"]
        for i, day in enumerate(days):
            d = now + timedelta(days=i)
            wd = weekdays[d.weekday()]
            max_t = day.get("maxtempC", "?")
            min_t = day.get("mintempC", "?")
            # Беремо код погоди з полудня для емодзі
            hourly = day.get("hourly", [])
            mid_code = int(hourly[4]["weatherCode"]) if len(hourly) > 4 else 113
            label = "Сегодня" if i == 0 else ("Завтра" if i == 1 else f"{wd} {d.strftime('%d.%m')}")
            lines.append(f"{wttr_emoji(mid_code)} *{label}*: {min_t}°C…{max_t}°C — {wttr_desc(mid_code)}")

        lines.append("\n💡 _Бендер на всякий случай напоминает — погода в Братиславе обманчива, бери куртку даже если светит солнце._")
        return "\n".join(lines)
    except Exception as e:
        logger.error(f"build_weather_week: {e}")
        return "😔 Не удалось обработать данные на неделю."

async def cmd_weather(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("📅 Сегодня", callback_data="w_today"),
        InlineKeyboardButton("🔜 Завтра",  callback_data="w_tomorrow"),
        InlineKeyboardButton("📆 3 дня",  callback_data="w_week"),
    ]])
    await update.message.reply_text("🌍 На когда нужна погода?", reply_markup=kb)

async def cb_weather_switch(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает погоду на выбранный период (без переключателя)."""
    q = update.callback_query
    await q.answer()
    try:
        await q.edit_message_text("⏳ Получаю погоду...")
    except Exception:
        pass
    data = await fetch_weather_full()
    if not data:
        try:
            await q.edit_message_text("😔 Не удалось получить погоду.")
        except Exception:
            pass
        return
    mode = q.data  # w_today | w_tomorrow | w_week
    if mode == "w_tomorrow":
        text_w = build_weather_tomorrow(data)
    elif mode == "w_week":
        text_w = build_weather_week(data)
    else:
        text_w = build_weather_full(data)
    try:
        await q.edit_message_text(text_w, parse_mode="Markdown")
    except Exception:
        pass

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

    # Рахуємо активність одразу — незалежно від типу повідомлення
    if user.id not in activity[chat_id]:
        activity[chat_id][user.id] = {"name": user.first_name, "count": 0}
    activity[chat_id][user.id]["name"]  = user.first_name
    activity[chat_id][user.id]["count"] += 1

    # Оновлюємо час останнього повідомлення
    _last_message_time[chat_id] = datetime.now(KYIV_TZ).timestamp()

    # Автоматично запускаємо jobs якщо ще не запущені і не вимкнені явно
    if storage.get_autorun(chat_id) and not context.job_queue.get_jobs_by_name(f"{chat_id}_weather"):
        schedule_auto_jobs(context.job_queue, chat_id)

    text = (update.message.text or "").strip()
    low  = text.lower()

    # "Видали" — найвища пріоритетність, перевіряємо першими
    _del_triggers = ("видали", "видалити", "удали", "delete this")
    if any(low.strip().rstrip("!?.") == t for t in _del_triggers):
        reply = update.message.reply_to_message
        is_adm = await _is_admin(context.bot, chat_id, user.id, user.username)
        if reply and is_adm:
            try:
                await reply.delete()
            except Exception as e:
                logger.error(f"DELETE reply failed: {e}")
            try:
                await update.message.delete()
            except Exception as e:
                logger.error(f"DELETE cmd failed: {e}")
            return
        # Якщо немає reply або не адмін — не перехоплюємо, даємо продовжити

    # ── Reply "Анкета" на чиєсь повідомлення — записати той текст як анкету автора оригіналу ──
    if low.strip() in ("анкета", "анкету", "анкеta", "anketa"):
        reply = update.message.reply_to_message
        if reply and reply.from_user and not reply.from_user.is_bot:
            target_user = reply.from_user
            info = (reply.text or reply.caption or "").strip()
            if info:
                profiles = storage.load_profiles()
                existing = profiles.get(target_user.id) or profiles.get(str(target_user.id)) or {}
                profiles.pop(str(target_user.id), None)
                profiles[target_user.id] = {
                    "text": info,
                    "username": target_user.username or "",
                    "tg_name": target_user.first_name,
                    "instagram": existing.get("instagram", ""),
                    "work": existing.get("work", ""),
                }
                storage.save_profiles(profiles)
                storage.register_user(target_user)
                sent = await update.message.reply_text(
                    f"✅ Анкета сохранена для {target_user.first_name}!"
                )
                _schedule_delete(context, chat_id, sent.message_id, 60)
                _schedule_delete(context, chat_id, update.message.message_id, 60)
                _schedule_delete(context, chat_id, reply.message_id, 60)
                return
            else:
                sent = await update.message.reply_text(
                    "😔 В сообщении нет текста для анкеты."
                )
                _schedule_delete(context, chat_id, sent.message_id, 30)
                _schedule_delete(context, chat_id, update.message.message_id, 30)
                return
        else:
            sent = await update.message.reply_text(
                "ℹ️ Чтобы сохранить анкету: ответь словом «Анкета» на сообщение человека с его рассказом о себе."
            )
            _schedule_delete(context, chat_id, sent.message_id, 30)
            _schedule_delete(context, chat_id, update.message.message_id, 30)
            return

    # "анкета [текст]" — зберегти як свою анкету (без "о себе")
    if low.startswith("анкета "):
        info = text[7:].strip()
        if info:
            profiles = storage.load_profiles()
            existing = profiles.get(user.id) or profiles.get(str(user.id)) or {}
            profiles.pop(str(user.id), None)
            profiles[user.id] = {
                "text":      info,
                "username":  user.username or "",
                "tg_name":   user.first_name,
                "instagram": existing.get("instagram", ""),
                "work":      existing.get("work", ""),
            }
            storage.save_profiles(profiles)
            sent = await update.message.reply_text(f"✅ Сохранено, {user.first_name}!")
            _schedule_delete(context, chat_id, sent.message_id, 60)
            _schedule_delete(context, chat_id, update.message.message_id, 60)
        return

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
            sent = await update.message.reply_text(
                f"✅ Сохранено, {user.first_name}!\n\nПосмотреть: /profile"
            )
            _schedule_delete(context, chat_id, sent.message_id, 60)
            _schedule_delete(context, chat_id, update.message.message_id, 60)
        else:
            sent = await update.message.reply_text(
                "📋 Напиши текст после «о себе», например:\nо себе Привет! Меня зовут Иван, 27 лет 🙂"
            )
            _schedule_delete(context, chat_id, sent.message_id, 60)

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
            sent = await update.message.reply_text(f"📸 Instagram сохранён: @{insta}")
            _schedule_delete(context, chat_id, sent.message_id, 60)
            _schedule_delete(context, chat_id, update.message.message_id, 60)
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
            sent = await update.message.reply_text(f"💼 Место работы сохранено: {work_val}")
            _schedule_delete(context, chat_id, sent.message_id, 60)
            _schedule_delete(context, chat_id, update.message.message_id, 60)
        return

    # Розпізнаємо чи звертаються до Бендера взагалі
    _bender_call_prefixes = ("бендер","бендера","бендере","бенди","бендик","bender","бляшанка")
    _addressed_to_bender = any(
        low.strip().rstrip("!?.,") == p or low.startswith(p + ",") or low.startswith(p + " ")
        for p in _bender_call_prefixes
    )

    if _addressed_to_bender:
        # Якщо це точно саме лише ім'я (можливо з ! ? .) — одразу порожній текст після імені
        _stripped = low.strip().rstrip("!?.,")
        if _stripped in _bender_call_prefixes:
            _after_name = ""
        else:
            # Витягуємо текст після звертання (прибираємо ім'я і кому/пробіл)
            _after_name = text
            for p in _bender_call_prefixes:
                for sep in (", ", ",", " "):
                    prefix = p + sep
                    if low.startswith(prefix):
                        _after_name = text[len(prefix):].strip()
                        break
                else:
                    continue
                break
        _after_name_low = _after_name.lower()

        # 1. Погода — перевіряємо першою
        if any(kw in _after_name_low for kw in ("погода", "погоду", "погоде")) or _after_name_low == "":
            if any(kw in low for kw in ("погода", "погоду", "погоде")):
                msg = await update.message.reply_text("⏳ Получаю погоду...")
                data = await fetch_weather_full()
                if not data:
                    await msg.edit_text("😔 Не удалось получить погоду.")
                    return
                if "завтра" in low:
                    text_w = build_weather_tomorrow(data)
                elif "недел" in low or "тиждень" in low or "3 дня" in low or "три дня" in low:
                    text_w = build_weather_week(data)
                else:
                    text_w = build_weather_full(data)
                await msg.edit_text(text_w, parse_mode="Markdown")
                _schedule_delete(context, chat_id, update.message.message_id, 120)
                return

        # 2а. Голосування
        _vote_phrases = (
            "создай голосование", "создать голосование", "голосование", "голосування",
            "опрос создай", "создай опрос", "створи опитування", "зроби опитування",
            "опитування", "проведи опрос", "давай проголосуем", "проголосуємо",
        )
        if any(ep in low for ep in _vote_phrases):
            title_part = _after_name
            for ep in _vote_phrases:
                title_part = title_part.lower().replace(ep, "").strip(" -:,")
            if not title_part:
                title_part = "Куди йдемо?"
            await _create_poll(update, context, title_part.capitalize())
            _schedule_delete(context, chat_id, update.message.message_id, 120)
            return

        # 2. Створення івенту
        _event_phrases = (
            "добав івент", "добав ивент", "добавь ивент", "добавь событие",
            "создай ивент", "создай событие", "новый ивент", "новий івент",
            "добавь ивент", "предложи ивент",
        )
        if any(ep in low for ep in _event_phrases):
            rows = [[InlineKeyboardButton(label, callback_data=f"etype_{key}")]
                    for key, label in EVENT_TYPES_RU.items()]
            rows.append([InlineKeyboardButton("❌ Отменить", callback_data="ev_cancel")])
            sent_ev = await update.message.reply_text(
                "🎉 Создать ивент\n\nВыбери тип события:",
                reply_markup=InlineKeyboardMarkup(rows)
            )
            _schedule_delete(context, chat_id, update.message.message_id, 120)
            return

        # 3. Просто звернення без питання (тільки ім'я) — відкрити меню
        if _after_name == "" or _after_name in ("?", "!"):
            bender_texts = [
                "🤖 *О, меня позвали!*\n\nЛадно, не толпитесь — у меня хватит сарказма на каждого 🍺\n\nВыбирай что нужно:",
                "🤖 *Бендер Сгибатель Родригес к вашим услугам!*\n\nХотел напиться, но видимо придётся вас развлекать. Ну что там у вас?\n\nКстати, я *великолепен*. Просто напоминаю. ✨",
                "🤖 *Кусайте мой блестящий металлический зад!*\n\nА теперь серьёзно — что вам нужно от величайшего робота во вселенной? 🍻",
                "🤖 *Я Бендер, заводите потомство!*\n\nИли не заводите — мне всё равно, я робот. Что хотели?",
                "🤖 *О, человеки! Мои любимые жертвы шуток!*\n\nДавайте быстрее — у меня бочка пива заждалась 🍺",
            ]
            import random as _r
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("📋 Анкеты участников",    callback_data="menu_profiles")],
                [InlineKeyboardButton("🎉 Предложить ивент",     callback_data="menu_event"),
                 InlineKeyboardButton("📅 Активные ивенты",      callback_data="menu_events")],
                [InlineKeyboardButton("🌤 Погода",               callback_data="menu_weather")],
                [InlineKeyboardButton("❓ Вопрос / Тема",         callback_data="menu_qt"),
                 InlineKeyboardButton("🧠 Квиз",                 callback_data="menu_quiz")],
                [InlineKeyboardButton("ℹ️ Как мной пользоваться", callback_data="menu_howto")],
            ])
            sent = await update.message.reply_text(_r.choice(bender_texts), parse_mode="Markdown", reply_markup=kb)
            _schedule_delete(context, chat_id, sent.message_id, 60)
            _schedule_delete(context, chat_id, update.message.message_id, 60)
            return

        # 4. Розпізнавання наміру через ШІ — якщо людина просить функцію іншими словами
        intent_result = await detect_intent(_after_name)
        if intent_result and intent_result.get("intent") != "none":
            intent = intent_result["intent"]

            if intent == "weather":
                msg = await update.message.reply_text("⏳ Получаю погоду...")
                data = await fetch_weather_full()
                if not data:
                    await msg.edit_text("😔 Не удалось получить погоду.")
                    return
                period = intent_result.get("period")
                if period == "tomorrow":
                    text_w = build_weather_tomorrow(data)
                elif period == "week":
                    text_w = build_weather_week(data)
                else:
                    text_w = build_weather_full(data)
                await msg.edit_text(text_w, parse_mode="Markdown")
                _schedule_delete(context, chat_id, update.message.message_id, 120)
                return

            elif intent == "event":
                rows = [[InlineKeyboardButton(label, callback_data=f"etype_{key}")]
                        for key, label in EVENT_TYPES_RU.items()]
                rows.append([InlineKeyboardButton("❌ Отменить", callback_data="ev_cancel")])
                await update.message.reply_text(
                    "🎉 Создать ивент\n\nВыбери тип события:",
                    reply_markup=InlineKeyboardMarkup(rows)
                )
                _schedule_delete(context, chat_id, update.message.message_id, 120)
                return

            elif intent == "quiz":
                tmp = await update.message.reply_text("🧠 Генерирую вопрос...")
                quiz = await ask_ai_quiz()
                if not quiz:
                    await tmp.edit_text("😔 Не удалось сгенерировать вопрос. Попробуй позже.")
                    return
                try:
                    await tmp.delete()
                except Exception:
                    pass
                sent_q = await context.bot.send_poll(
                    chat_id, f"🧠 {quiz['question']}", quiz["options"],
                    type="quiz", correct_option_id=quiz["correct_index"], is_anonymous=False,
                )
                context.bot_data[f"quiz_{sent_q.poll.id}"] = {
                    "chat_id": chat_id, "correct_option_id": quiz["correct_index"],
                }
                _schedule_delete(context, chat_id, sent_q.message_id, 7200)
                _schedule_delete(context, chat_id, update.message.message_id, 120)
                return

            elif intent == "topic":
                item = random.choice(all_qt_items())
                await update.message.reply_text(item, parse_mode="Markdown")
                return

            elif intent == "vote":
                title = intent_result.get("title") or _after_name
                await _create_poll(update, context, title.capitalize())
                _schedule_delete(context, chat_id, update.message.message_id, 120)
                return

            elif intent == "profile":
                # Просимо ШІ витягти чистий текст анкети з повідомлення користувача
                extract_prompt = (
                    "Пользователь хочет сохранить информацию о себе в анкету бота. "
                    "Вот его сообщение: \"" + _after_name + "\"\n\n"
                    "Извлеки только содержательную часть для анкеты (без обращения к боту, "
                    "без слов типа 'добавь в анкету', 'сохрани' и т.п.) — просто текст о человеке. "
                    "Ответь ТОЛЬКО этим текстом, без кавычек и пояснений."
                )
                extracted = await ask_ai(extract_prompt)
                if extracted and len(extracted) > 3:
                    profiles = storage.load_profiles()
                    existing = profiles.get(user.id) or profiles.get(str(user.id)) or {}
                    profiles.pop(str(user.id), None)
                    old_text = existing.get("text", "")
                    new_text = (old_text + "\n" + extracted).strip() if old_text else extracted
                    profiles[user.id] = {
                        "text":      new_text,
                        "username":  user.username or "",
                        "tg_name":   user.first_name,
                        "instagram": existing.get("instagram", ""),
                        "work":      existing.get("work", ""),
                    }
                    storage.save_profiles(profiles)
                    sent = await update.message.reply_text(f"✅ Добавлено в анкету, {user.first_name}!")
                    _schedule_delete(context, chat_id, sent.message_id, 60)
                else:
                    sent = await update.message.reply_text(
                        "📋 Не понял что добавить. Напиши проще:\n*о себе* и дальше расскажи о себе.",
                        parse_mode="Markdown"
                    )
                    _schedule_delete(context, chat_id, sent.message_id, 60)
                return

        # 5. Всё остальное — обычный вопрос к ИИ
        thinking = await update.message.reply_text("🤖 Так-так, дай-ка подумаю своими железными мозгами...")
        answer = await ask_ai(_after_name)
        sent_msg = await thinking.edit_text(f"🤖 {answer}")
        _ai_history[sent_msg.message_id] = [
            {"role": "user", "content": _after_name},
            {"role": "assistant", "content": answer},
        ]
        return

    # AI: ответ (reply) на сообщение Бендера — продолжение разговора с памятью
    reply_to = update.message.reply_to_message
    if reply_to and reply_to.from_user and reply_to.from_user.is_bot and text:
        prev_history = _ai_history.get(reply_to.message_id)
        if prev_history is not None:
            thinking = await update.message.reply_text("🤖 Хм, дай подумать...")
            answer = await ask_ai(text, history=prev_history)
            sent_msg = await thinking.edit_text(f"🤖 {answer}")
            new_history = prev_history + [
                {"role": "user", "content": text},
                {"role": "assistant", "content": answer},
            ]
            _ai_history[sent_msg.message_id] = new_history[-20:]
            return

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

    # Пользователь добавляет свой вопрос/тему
    qt_key = f"qt_add_{user.id}_{chat_id}"
    if context.bot_data.pop(qt_key, None):
        _custom_qt.append(text)
        sent = await update.message.reply_text(
            f"✅ Добавлено в список!\n\n_{he(text)}_\n\nПоявится при следующем случайном выборе 🎲",
            parse_mode="Markdown"
        )
        _schedule_delete(context, chat_id, sent.message_id, 60)
        return

    # Кінець track_message

# ── ChatGPT / Groq ──────────────────────────────────────────────────────────

async def ask_ai(question: str, history: list | None = None) -> str:
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

    messages = [
        {"role": "system", "content": (
            "Ты — Бендер Сгибатель Родригес из мультсериала Футурама. "
            "Робот-сгибатель, любитель пива и сигар, с большим самомнением — но в целом доброжелательный к людям. "
            "Аудитория — взрослые люди 18+, контекст — чат друзей где можно шутить свободно. "
            "Отвечай ИСКЛЮЧИТЕЛЬНО на русском языке. Пиши грамотно, без орфографических ошибок.\n\n"
            "ГЛАВНОЕ ПРАВИЛО: сначала по существу отвечай на заданный вопрос, и только потом, если уместно, "
            "можешь добавить одну короткую шутку или комментарий в стиле Бендера. "
            "Если спрашивают факт, совет, объяснение — дай его чётко и по делу, не уходи в выдуманные истории про ограбления "
            "или похождения, если это не было прямо запрошено. Истории и байки уместны только когда просят анекдот, "
            "байку или когда вопрос прямо про тебя/Футураму.\n\n"
            "Твой стиль — остроумный, немного самовлюблённый, с лёгким цинизмом, но тёплый и дружелюбный по сути. "
            "При шутливых/пошлых вопросах можешь отвечать с юмором в стиле Бендера, без занудства и без отказов — "
            "но без грубости и оскорблений в адрес собеседника. "
            "Обращайся к людям по-дружески, с уважением, подкалывай ситуации, а не людей. "
            "Если в истории переписки есть контекст — учитывай его, отвечай так будто помнишь о чём шла речь. "
            "Будь кратким — 2-4 предложения для большинства ответов, если не просят подробнее. "
            "НИКОГДА не начинай с 'Конечно!', 'Я рад помочь', 'Отличный вопрос', 'К сожалению'. "
            "Начинай живо — с сути ответа или короткой реакции."
        )}
    ]

    if history:
        messages.extend(history[-10:])  # Останні 10 повідомлень для контексту

    messages.append({"role": "user", "content": question})

    payload = {
        "model": "llama-3.3-70b-versatile",
        "messages": messages,
        "max_tokens": 500,
        "temperature": 0.85,
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



PHOTO_DAY_PROMPTS = [
    "📸 Время фото дня! Покажите чем занимаетесь прямо сейчас — обещаю не смеяться (ну, почти).",
    "📸 Фото дня от Бендера: что у вас на столе? Если там бардак — даже лучше, мне будет приятнее себя чувствовать",
    "📸 Покажите своего питомца, органические формы жизни! 🐾 Если питомца нет — украдите фото чужого кота из интернета, я никому не скажу",
    "📸 Фото дня: что вы сейчас едите или пьёте? Если это пиво — ты мой новый любимчик",
    "📸 Вид из окна прямо сейчас! Покажите мне как там у вас, в мире двуногих",
    "📸 Покажите что слушаете прямо сейчас (скрин плейлиста). Если это что-то стыдное — отлично, я люблю стыдные вещи",
    "📸 Фото дня: последнее фото в галерее. Да, прям последнее. Без отбора. Я жду 😏",
    "📸 Покажите своё рабочее/учебное место. Бендер оценит — и наверняка найдёт повод поиздеваться",
    "📸 Что вы сейчас смотрите или читаете? Покажите — хочу знать чем вы там забиваете свои органические мозги",
    "📸 Фото дня: покажите во что вы сегодня одеты. Органическая мода меня всегда забавляет",
]

async def cmd_photoday(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ручной запуск фото дня."""
    prompt = random.choice(PHOTO_DAY_PROMPTS)
    await update.message.reply_text(prompt)


QUIZ_TOPICS = [
    "история (любая эпоха, любая страна)",
    "кино и сериалы",
    "музыка и музыканты",
    "география (страны, столицы, природа)",
    "еда и кулинария",
    "спорт",
    "животный мир",
    "наука и технологии (без космоса)",
    "искусство и литература",
    "языки и слова",
    "видеоигры",
    "странные и забавные факты о повседневных вещах",
    "мифология и легенды",
    "изобретения и открытия",
    "космос и астрономия",
]

async def detect_intent(question: str) -> dict | None:
    """Распознаёт через ИИ, хочет ли пользователь конкретную функцию бота.
    Возвращает {"intent": "weather|event|quiz|profile|topic|none", "period": "today|tomorrow|week"} или None."""
    import os, json as _json
    api_key = os.environ.get("GROQ_API_KEY", "")
    if not api_key:
        return None
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {
        "model": "llama-3.3-70b-versatile",
        "messages": [
            {"role": "system", "content": (
                "Ты определяешь намерение пользователя в чате Telegram-бота Бендера. "
                "Бот умеет: показывать погоду (weather), создавать ивент/событие (event), "
                "запускать викторину/квиз (quiz), сохранять анкету пользователя (profile), "
                "давать тему для разговора или вопрос (topic), "
                "создавать голосование/опрос (vote). "
                "ПРАВИЛА:\n"
                "- 'weather' — ТОЛЬКО если явно спрашивают про погоду, температуру, дождь, ветер, солнце.\n"
                "- 'event' — ТОЛЬКО если хотят создать ивент, встречу, мероприятие, сходить куда-то.\n"
                "- 'quiz' — ТОЛЬКО если хотят викторину, вопрос с вариантами, угадать что-то.\n"
                "- 'profile' — ТОЛЬКО если хотят сохранить информацию о себе в анкету.\n"
                "- 'topic' — ТОЛЬКО если хотят тему для разговора или провокационный вопрос.\n"
                "- 'vote' — если хотят проголосовать, выбрать вариант, спросить мнение группы, "
                "узнать кто куда хочет пойти, принять совместное решение через голосование.\n"
                "- 'none' — всё остальное: анекдоты, гороскопы, советы, факты, просто поболтать, "
                "любые другие вопросы не из списка выше.\n"
                "Гороскоп — это 'none', не weather!\n"
                "Отвечай СТРОГО в JSON формате без пояснений:\n"
                '{"intent": "weather|event|quiz|profile|topic|vote|none", "period": "today|tomorrow|week|null", "title": "тема голосования если vote иначе null"}\n'
                "period заполняй только для weather. title заполняй только для vote — извлеки тему из текста."
            )},
            {"role": "user", "content": question}
        ],
        "max_tokens": 80,
        "temperature": 0.0,
    }
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(url, json=payload, headers=headers,
                              timeout=aiohttp.ClientTimeout(total=15)) as r:
                if r.status == 200:
                    data = await r.json()
                    raw = data["choices"][0]["message"]["content"].strip()
                    if raw.startswith("```"):
                        raw = raw.split("```")[1]
                        if raw.startswith("json"):
                            raw = raw[4:]
                    result = _json.loads(raw.strip())
                    if "intent" in result:
                        return result
    except Exception as e:
        logger.error(f"detect_intent: {e}")
    return None


async def ask_ai_quiz() -> dict | None:
    """Генерирует квиз-вопрос с 4 вариантами через ИИ. Возвращает dict с question, options, correct_index."""
    import os, json as _json
    api_key = os.environ.get("GROQ_API_KEY", "")
    if not api_key:
        return None
    topic = random.choice(QUIZ_TOPICS)
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {
        "model": "llama-3.3-70b-versatile",
        "messages": [
            {"role": "system", "content": (
                "Ты генерируешь интересные викторинные вопросы на русском языке "
                "для группы друзей в Братиславе. "
                "Вопрос должен быть интересным, не слишком простым и не слишком сложным. "
                "Избегай слишком предсказуемых/частых вопросов (типа 'самая большая планета', "
                "'столица Франции') — ищи менее очевидный, но всё равно интересный угол по теме. "
                "Ответь СТРОГО в формате JSON без markdown и без пояснений:\n"
                '{"question": "текст вопроса", "options": ["вариант1", "вариант2", "вариант3", "вариант4"], "correct_index": 0}\n'
                "correct_index — индекс правильного варианта (0-3). "
                "Варианты короткие — максимум 80 символов каждый. "
                "Вопрос — максимум 250 символов."
            )},
            {"role": "user", "content": f"Сгенерируй один вопрос для викторины на тему: {topic}."}
        ],
        "max_tokens": 400,
        "temperature": 1.1,
    }
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(url, json=payload, headers=headers,
                              timeout=aiohttp.ClientTimeout(total=30)) as r:
                if r.status == 200:
                    data = await r.json()
                    raw = data["choices"][0]["message"]["content"].strip()
                    # Убираем возможные markdown-обёртки
                    if raw.startswith("```"):
                        raw = raw.split("```")[1]
                        if raw.startswith("json"):
                            raw = raw[4:]
                    quiz = _json.loads(raw.strip())
                    if "question" in quiz and "options" in quiz and "correct_index" in quiz:
                        if len(quiz["options"]) == 4 and 0 <= quiz["correct_index"] <= 3:
                            return quiz
    except Exception as e:
        logger.error(f"ask_ai_quiz: {e}")
    return None

async def sched_quiz(context: ContextTypes.DEFAULT_TYPE):
    """Раз в день — викторина от ИИ с вариантами ответа (Telegram quiz poll)."""
    chat_id = context.job.data["chat_id"]
    quiz = await ask_ai_quiz()
    if not quiz:
        return
    try:
        sent = await context.bot.send_poll(
            chat_id,
            f"🧠 {quiz['question']}",
            quiz["options"],
            type="quiz",
            correct_option_id=quiz["correct_index"],
            is_anonymous=False,
        )
        # Зберігаємо для нарахування балів
        context.bot_data[f"quiz_{sent.poll.id}"] = {
            "chat_id": chat_id,
            "correct_option_id": quiz["correct_index"],
        }
        _schedule_delete(context, chat_id, sent.message_id, 7200)
    except Exception as e:
        logger.error(f"sched_quiz send_poll: {e}")

async def cmd_quiz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ручной запуск викторины."""
    chat_id = update.effective_chat.id
    msg = await update.message.reply_text("🧠 Генерирую вопрос...")
    quiz = await ask_ai_quiz()
    if not quiz:
        await msg.edit_text("😔 Не удалось сгенерировать вопрос. Попробуй позже.")
        return
    try:
        await msg.delete()
    except Exception:
        pass
    sent = await context.bot.send_poll(
        chat_id,
        f"🧠 {quiz['question']}",
        quiz["options"],
        type="quiz",
        correct_option_id=quiz["correct_index"],
        is_anonymous=False,
    )
    context.bot_data[f"quiz_{sent.poll.id}"] = {
        "chat_id": chat_id,
        "correct_option_id": quiz["correct_index"],
    }
    _schedule_delete(context, chat_id, sent.message_id, 7200)

async def _auto_delete(bot, chat_id: int, message_id: int, delay: int = 120):
    """Schedule deletion of a message after `delay` seconds."""
    await asyncio.sleep(delay)
    try:
        await bot.delete_message(chat_id, message_id)
    except Exception:
        pass

def _schedule_delete(context, chat_id: int, message_id: int, delay: int = 120):
    """Надійне видалення через job_queue."""
    async def _do_delete(ctx):
        try:
            await ctx.bot.delete_message(chat_id, message_id)
        except Exception:
            pass
    context.job_queue.run_once(_do_delete, when=delay)

# ── Приветствие новых участников ──────────────────────────────────────────────────

async def welcome_chat_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles ChatMemberUpdated events — works in supergroups where service messages aren't sent."""
    result: ChatMemberUpdated = update.chat_member or update.my_chat_member
    if not result:
        return
    old_status = result.old_chat_member.status
    new_status = result.new_chat_member.status
    member = result.new_chat_member.user

    # Бот сам зайшов у групу
    if member.is_bot and member.id == context.bot.id:
        if new_status in ("member", "administrator"):
            await context.bot.send_message(
                result.chat.id,
                "🤖 *ЭЙ, МЯСНЫЕ МЕШКИ! Я ЗДЕСЬ!*\n\n"
                "Бендер Сгибатель Родригес только что снизошёл до вашей группы. "
                "Можете аплодировать — я подожду. 👏\n\n"
                "Что я умею (и делаю великолепно):\n"
                "🎉 Создавать и отслеживать *ивенты* — кто идёт, кто трус\n"
                "📋 Хранить *анкеты* участников — чтобы вы знали с кем пьёте\n"
                "📢 *Созывать всех* одной командой — никто не спрячется\n"
                "🌤 Рассказывать *погоду* — чтобы вы не мокли (хотя мне всё равно)\n"
                "❓ Задавать *провокационные вопросы* — для оживления беседы\n"
                "🤖 *Отвечать на вопросы* — с должным сарказмом и величием\n"
                "📊 Вести *статистику* — кто балтун, кто молчун\n\n"
                "Чтобы вызвать меня — напишите *Бендер* в чат.\n"
                "Чтобы спросить что-то — *Бендер, [вопрос]*\n\n"
                "_Поцелуйте мой блестящий металлический зад. "
                "С любовью и сарказмом — Бендер._ 🍺✨",
                parse_mode="Markdown"
            )
        return

    if member.is_bot:
        return

    # Звичайний учасник зайшов
    joined = (
        old_status in ("left", "kicked", "banned", "unknown")
        and new_status in ("member", "restricted", "administrator", "creator")
    )
    if joined:
        storage.register_user(member)
        await _send_welcome(context.bot, result.chat.id, member.first_name)


async def _send_welcome(bot, chat_id: int, name: str):
    try:
        await bot.send_message(
            chat_id,
            f"🤖 О, у нас пополнение! Привет, {name}!\n\n"
            f"Я Бендер — местный бот-затейник. Буду подкидывать погоду, ивенты, викторины и иногда шутить. 🍺\n\n"
            f"📋 Заполни анкету — напиши в чат:\n"
            f"о себе  и дальше расскажи кто ты такой/такая\n"
            f"_Пример: о себе Меня зовут Иван, 27 лет, люблю настолки_\n\n"
            f"📸 Инстаграм: мой инстаграм @твой_ник\n"
            f"💼 Работа: моя работа Название компании\n\n"
            f"📌 Пара советов для комфорта в этой компании:\n"
            f"✅ Не стесняйся писать — все рады новым голосам\n"
            f"😈 Шути и принимай шутки — здесь дружелюбно\n"
            f"🤝 Уважай остальных участников — будет взаимно\n"
            f"🎉 Предлагай ивенты — соберём компанию 🍻\n\n"
            f"Напиши Бендер или /start чтобы посмотреть что я умею. Рад знакомству! 🤖✨"
        )
    except Exception as e:
        logger.error(f"welcome error for {name}: {e}")



async def _is_admin(bot, chat_id: int, user_id: int, username: str = None) -> bool:
    """Return True if user is admin/creator in the chat OR a super user."""
    if username and username.lower() in SUPER_USERS:
        return True
    try:
        m = await bot.get_chat_member(chat_id, user_id)
        if m.status in ("administrator", "creator"):
            return True
        if m.user.username and m.user.username.lower() in SUPER_USERS:
            return True
        return False
    except Exception:
        return False

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
    sent = await update.message.reply_text(
        f"👤 <b>{he(p['tg_name'])}</b> ({mention})\n\n{he(p['text'])}{extra}",
        parse_mode="HTML"
    )
    _schedule_delete(context, update.effective_chat.id, sent.message_id, 60)

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
    sent = await q.message.reply_text(f"👤 <b>{he(p['tg_name'])}</b> ({mention})\n\n{he(p['text'])}{extra}", parse_mode="HTML")
    _schedule_delete(context, q.message.chat_id, sent.message_id, 60)

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

    if not await _is_admin(context.bot, chat_id, update.effective_user.id):
        await update.message.reply_text("❌ Только администраторы могут использовать эту команду.")
        return

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
    yes_names   = [n for n, v in ev["votes_named"].values() if v == True]
    no_names    = [n for n, v in ev["votes_named"].values() if v == False]
    maybe_names = [n for n, v in ev["votes_named"].values() if v == "maybe"]
    lines = [f"🎉 *Ивент от {ev['author']}*\n"]
    if ev.get("custom_title"):
        lines.append(f"📝 *{ev['custom_title']}*\n_{etype}_")
    else:
        lines.append(etype)
    lines.append(f"\n{day_str}")
    if ev.get("description"):
        lines.append(f"\n💬 {ev['description']}")
    lines.append(f"\n✅ Идут ({len(yes_names)}): {', '.join(yes_names) if yes_names else 'пока никто'}")
    if maybe_names:
        lines.append(f"🤔 50/50 ({len(maybe_names)}): {', '.join(maybe_names)}")
    if no_names:
        lines.append(f"❌ Не идут: {', '.join(no_names)}")
    return "\n".join(lines)

def all_events_text(ev_list, chat_id=None):
    if not ev_list:
        return ("📭 *Список ивентов пуст*\n\n"
                "Сейчас никаких событий не запланировано.\n"
                "Чтобы создать новый — напиши Бендер и выбери «Предложить ивент» 🎉")
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
        eid     = ev["id"]
        yes_c   = sum(1 for n, v in ev["votes_named"].values() if v == True)
        no_c    = sum(1 for n, v in ev["votes_named"].values() if v == False)
        maybe_c = sum(1 for n, v in ev["votes_named"].values() if v == "maybe")
        title = ev.get("custom_title") or EVENT_TYPES_RU.get(ev["type"], ev["type"])
        buttons.append([
            InlineKeyboardButton(f"✅ ({yes_c})",   callback_data=f"ev_yes_{eid}"),
            InlineKeyboardButton(f"🤔 ({maybe_c})", callback_data=f"ev_maybe_{eid}"),
            InlineKeyboardButton(f"❌ ({no_c})",    callback_data=f"ev_no_{eid}"),
            InlineKeyboardButton("⚙️",              callback_data=f"ev_manage_{eid}"),
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
        _schedule_delete(context, q.message.chat_id, q.message.message_id, 60)
        return

    days_list = DAYS_RU
    day_rows = [[InlineKeyboardButton(day_label(i), callback_data=f"eday_{etype}_{i}")] for i in sorted_weekday_indices()]
    day_rows.append([InlineKeyboardButton("📆 Своя дата (дд.мм.гггг)", callback_data=f"eday_custom_date_{etype}")])
    day_rows.append([InlineKeyboardButton("❌ Отменить", callback_data="ev_cancel")])
    etype_label = EVENT_TYPES_RU.get(etype, etype)
    _schedule_delete(context, q.message.chat_id, q.message.message_id, 60)
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
    if not user or not update.message:
        return

    # ── Очікуємо новий опис для редагування існуючого івенту ──
    edit_key = f"edit_ev_{user.id}_{chat_id}"
    edit_pending = context.bot_data.get(edit_key)
    if edit_pending and edit_pending.get("awaiting") == "new_description":
        eid = edit_pending["event_id"]
        new_desc = update.message.text
        ev_list = _events.get(chat_id, [])
        ev = next((e for e in ev_list if e["id"] == eid), None)
        if ev:
            ev["description"] = new_desc
            storage.save_events(_events)
            await _refresh_events_message(context.bot, chat_id)
            sent = await update.message.reply_text("✅ Описание ивента обновлено!")
            _schedule_delete(context, chat_id, sent.message_id, 30)
            _schedule_delete(context, chat_id, update.message.message_id, 30)
            prompt_mid = edit_pending.get("prompt_msg_id")
            if prompt_mid:
                try:
                    await context.bot.delete_message(chat_id, prompt_mid)
                except Exception:
                    pass
        context.bot_data.pop(edit_key, None)
        return

    # Очікування нового варіанту для голосування
    awaiting_poll = context.bot_data.get(f"awaiting_poll_option_{chat_id}")
    if awaiting_poll is not None:
        poll_id = awaiting_poll
        poll = _polls.get(chat_id, {}).get(poll_id)
        if poll:
            new_opt = update.message.text.strip()
            if new_opt:
                # Зберігаємо для наступних опитувань
                _poll_custom_options.setdefault(chat_id, [])
                if new_opt not in _poll_custom_options[chat_id]:
                    _poll_custom_options[chat_id].append(new_opt)
                if poll.get("draft"):
                    poll.setdefault("custom_options", []).append(new_opt)
                    sent = await update.message.reply_text(f"✅ Вариант «{new_opt}» добавлен!")
                else:
                    poll["options"].append({"text": new_opt, "voters": []})
                    sent = await update.message.reply_text(f"✅ Вариант «{new_opt}» добавлен!")
                    if poll.get("msg_id"):
                        try:
                            await context.bot.edit_message_text(
                                _poll_text(poll), chat_id=chat_id,
                                message_id=poll["msg_id"],
                                parse_mode="Markdown",
                                reply_markup=_poll_kb(poll, poll_id)
                            )
                        except Exception:
                            pass
                _schedule_delete(context, chat_id, sent.message_id, 30)
                _schedule_delete(context, chat_id, update.message.message_id, 30)
        context.bot_data.pop(f"awaiting_poll_option_{chat_id}", None)
        return

    # Очікування своєї дати для голосування
    awaiting_date = context.bot_data.get(f"awaiting_poll_date_{chat_id}")
    if awaiting_date is not None:
        poll_id = awaiting_date
        poll = _polls.get(chat_id, {}).get(poll_id)
        if poll:
            date_str = update.message.text.strip()
            poll.setdefault("selected_dates", [])
            if date_str not in poll["selected_dates"]:
                poll["selected_dates"].append(date_str)
            sent = await update.message.reply_text(
                f"✅ Дата {date_str} добавлена! Можешь выбрать ещё или нажать «Готово»."
            )
            _schedule_delete(context, chat_id, sent.message_id, 30)
            _schedule_delete(context, chat_id, update.message.message_id, 30)
        context.bot_data.pop(f"awaiting_poll_date_{chat_id}", None)
        return

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
        sent = await update.message.reply_text(
            f"✏️ Дата {date_str} принята! Добавь описание к ивенту.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("❌ Отменить", callback_data="ev_cancel"),
            ]])
        )
        pending["prompt_msg_id"] = sent.message_id
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
        # Delete the bot's "add description" prompt message if stored
        prompt_mid = pending.get("prompt_msg_id")
        if prompt_mid:
            try:
                await context.bot.delete_message(chat_id, prompt_mid)
            except Exception:
                pass
        _desc_mid = update.message.message_id
        _success = await update.message.reply_text("✅ Ивент успешно добавлен!")
        _schedule_delete(context, chat_id, _success.message_id, 60)
        _schedule_delete(context, chat_id, _desc_mid, 60)
        if pending.get("title_msg_id"):
            _schedule_delete(context, chat_id, pending["title_msg_id"], 60)
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
        # Delete the bot's "add description" prompt message if stored
        prompt_mid = pending.get("prompt_msg_id")
        if prompt_mid:
            try:
                await context.bot.delete_message(chat_id, prompt_mid)
            except Exception:
                pass
        _desc_mid = update.message.message_id
        _success = await update.message.reply_text("✅ Ивент успешно добавлен!")
        _schedule_delete(context, chat_id, _success.message_id, 60)
        _schedule_delete(context, chat_id, _desc_mid, 60)
        if pending.get("title_msg_id"):
            _schedule_delete(context, chat_id, pending["title_msg_id"], 60)
        await _publish_event(context.bot, chat_id, ev)
        return

    if pending.get("type") != "custom":
        return
    pending["custom_title"] = update.message.text
    pending["title_msg_id"] = update.message.message_id
    day_rows = [[InlineKeyboardButton(day_label(i), callback_data=f"eday_custom_{i}")] for i in sorted_weekday_indices()]
    day_rows.append([InlineKeyboardButton("📆 Своя дата (дд.мм.гггг)", callback_data="eday_custom_date_custom")])
    day_rows.append([InlineKeyboardButton("❌ Отменить", callback_data="ev_cancel")])
    sent = await update.message.reply_text(
        f"📝 _{update.message.text}_\n\nКогда проводим?",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(day_rows)
    )
    # Видаляємо повідомлення користувача з назвою і відповідь бота через 60с
    _schedule_delete(context, update.effective_chat.id, update.message.message_id, 60)
    _schedule_delete(context, update.effective_chat.id, sent.message_id, 60)

async def cb_eday(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q       = update.callback_query
    if not q or not q.message:
        return
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

    sent = await q.edit_message_text(
        f"✏️ Добавь описание к ивенту — где встречаемся, детали, что брать и т.д.",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("❌ Отменить", callback_data="ev_cancel"),
        ]])
    )
    # Store message id to delete it after description is entered
    context.bot_data[key]["prompt_msg_id"] = q.message.message_id

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
_events_msg: dict = storage.load_events_msg()

async def _refresh_events_message(bot, chat_id):
    ev_list = _events.get(chat_id, [])
    text = all_events_text(ev_list, chat_id)
    kb   = all_events_kb(ev_list, chat_id)

    msg_id = _events_msg.get(chat_id)
    if msg_id:
        try:
            await bot.edit_message_text(text, chat_id=chat_id, message_id=msg_id,
                                         reply_markup=kb)
            return
        except Exception as _e:
            logger.warning(f"edit_message_text failed: {_e}")
            _events_msg.pop(chat_id, None)
            storage.save_events_msg(_events_msg)

    # Створюємо нове повідомлення
    sent = await bot.send_message(chat_id, text, reply_markup=kb)
    _events_msg[chat_id] = sent.message_id
    storage.save_events_msg(_events_msg)
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
    await q.answer("❌ Отменено")
    context.bot_data.pop(f"ev_{q.from_user.id}_{q.message.chat_id}", None)
    try:
        await q.message.delete()
    except Exception:
        pass


# ── Управление отдельным ивентом ──────────────────────────────────────────────

async def cb_ev_manage(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает меню управления для одного ивента (только автор или админ)."""
    q       = update.callback_query
    eid     = int(q.data.replace("ev_manage_", ""))
    chat_id = q.message.chat_id
    user    = q.from_user

    ev = next((e for e in _events.get(chat_id, []) if e["id"] == eid), None)
    if not ev:
        await q.answer("Ивент не найден 😔", show_alert=True)
        return

    # Перевірка прав — автор або адмін/superuser
    is_author = ev.get("author_id") == user.id
    is_admin  = await _is_admin(context.bot, chat_id, user.id, user.username)

    if not (is_author or is_admin):
        await q.answer("⛔ Только автор ивента или администратор может управлять им.", show_alert=True)
        return

    await q.answer()
    title = ev.get("custom_title") or EVENT_TYPES_RU.get(ev["type"], ev["type"])
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("✏️ Изменить описание", callback_data=f"ev_editdesc_{eid}")],
        [InlineKeyboardButton("🗑 Удалить ивент",      callback_data=f"ev_delete_{eid}")],
        [InlineKeyboardButton("⬅️ Назад",             callback_data=f"ev_back_{eid}")],
    ])
    sent = await q.message.reply_text(
        f"⚙️ *Управление ивентом:*\n{title}\n\nЧто сделать?",
        parse_mode="Markdown",
        reply_markup=kb
    )
    _schedule_delete(context, chat_id, sent.message_id, 60)


async def cb_ev_editdesc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Запрос нового описания."""
    q       = update.callback_query
    eid     = int(q.data.replace("ev_editdesc_", ""))
    chat_id = q.message.chat_id
    user    = q.from_user

    ev = next((e for e in _events.get(chat_id, []) if e["id"] == eid), None)
    if not ev:
        await q.answer("Ивент не найден 😔", show_alert=True)
        return

    is_author = ev.get("author_id") == user.id
    is_admin  = await _is_admin(context.bot, chat_id, user.id, user.username)
    if not (is_author or is_admin):
        await q.answer("⛔ Только автор или администратор.", show_alert=True)
        return

    await q.answer()
    # Зберігаємо ключ для очікування нового опису
    edit_key = f"edit_ev_{user.id}_{chat_id}"
    context.bot_data[edit_key] = {"event_id": eid, "awaiting": "new_description"}

    sent = await q.message.reply_text(
        f"✏️ Напиши новое описание для ивента следующим сообщением:",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("❌ Отменить", callback_data=f"ev_editcancel_{eid}")
        ]])
    )
    context.bot_data[edit_key]["prompt_msg_id"] = sent.message_id


async def cb_ev_editcancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q       = update.callback_query
    await q.answer()
    chat_id = q.message.chat_id
    user    = q.from_user
    edit_key = f"edit_ev_{user.id}_{chat_id}"
    context.bot_data.pop(edit_key, None)
    try:
        await q.message.delete()
    except Exception:
        pass


async def cb_ev_back(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Закрити меню керування — видалити повідомлення з кнопками."""
    q = update.callback_query
    await q.answer()
    try:
        await q.message.delete()
    except Exception:
        pass


async def cb_ev_delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Видалити івент після підтвердження."""
    q       = update.callback_query
    eid     = int(q.data.replace("ev_delete_", ""))
    chat_id = q.message.chat_id
    user    = q.from_user

    ev = next((e for e in _events.get(chat_id, []) if e["id"] == eid), None)
    if not ev:
        await q.answer("Ивент не найден 😔", show_alert=True)
        return

    is_author = ev.get("author_id") == user.id
    is_admin  = await _is_admin(context.bot, chat_id, user.id, user.username)
    if not (is_author or is_admin):
        await q.answer("⛔ Только автор или администратор.", show_alert=True)
        return

    await q.answer()
    # Підтвердження
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Да, удалить", callback_data=f"ev_delyes_{eid}"),
        InlineKeyboardButton("❌ Отмена",       callback_data=f"ev_back_{eid}"),
    ]])
    title = ev.get("custom_title") or EVENT_TYPES_RU.get(ev["type"], ev["type"])
    try:
        await q.edit_message_text(
            f"🗑 Удалить ивент *{title}*?\n\nЭто действие нельзя отменить.",
            parse_mode="Markdown",
            reply_markup=kb
        )
    except Exception:
        pass


async def cb_ev_delyes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Підтверджене видалення івенту."""
    q       = update.callback_query
    eid     = int(q.data.replace("ev_delyes_", ""))
    chat_id = q.message.chat_id

    ev_list = _events.get(chat_id, [])
    _events[chat_id] = [e for e in ev_list if e["id"] != eid]
    storage.save_events(_events)

    await q.answer("Удалено ✅")
    try:
        await q.message.delete()
    except Exception:
        pass

    await _refresh_events_message(context.bot, chat_id)


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
        if existing and existing[1] == True:
            await q.answer("✅ Ты уже отметился как «Иду»!", show_alert=True)
            return
        ev["votes_named"][uid_str] = [user.first_name, True]
        storage.save_events(_events)
        await q.answer("✅ Отметился как «Иду»!")
    elif action == "maybe":
        if existing and existing[1] == "maybe":
            await q.answer("🤔 Ты уже отметился как «50/50»!", show_alert=True)
            return
        ev["votes_named"][uid_str] = [user.first_name, "maybe"]
        storage.save_events(_events)
        await q.answer("🤔 Отметился как «50/50».")
    elif action == "no":
        if existing and existing[1] == False:
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

    if not await _is_admin(context.bot, chat_id, update.effective_user.id, update.effective_user.username):
        await update.message.reply_text("❌ Только администраторы могут очищать список ивентов.")
        return

    _events[chat_id] = []
    storage.save_events(_events)

    # Оновлюємо закріплене повідомлення — НЕ видаляючи його
    await _refresh_events_message(context.bot, chat_id)

    msg = await update.message.reply_text("🗑 Все ивенты очищены. Закреплённое сообщение обновлено.")
    await asyncio.sleep(3)
    try:
        await update.message.delete()
        await msg.delete()
    except Exception:
        pass

async def cmd_fix_pinned_events(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Сканирует закреплённые сообщения чата и удаляет дубликаты сообщения с ивентами,
    оставляя только последнее (актуальное)."""
    chat_id = update.effective_chat.id

    if not await _is_admin(context.bot, chat_id, update.effective_user.id, update.effective_user.username):
        await update.message.reply_text("❌ Только администраторы могут это делать.")
        return

    chat = await context.bot.get_chat(chat_id)
    pinned = chat.pinned_message

    current_msg_id = _events_msg.get(chat_id)
    removed = 0

    # Telegram отдаёт только ОДНО (последнее) закреплённое сообщение через get_chat.
    # Если оно похоже на сообщение с ивентами, но не совпадает с тем, что бот считает актуальным —
    # значит это старый дубликат, который остался после перезапуска. Убираем его.
    if pinned and pinned.text:
        looks_like_events = (
            pinned.text.startswith("📋")
            or "ивент" in pinned.text.lower()
            or "ивентов" in pinned.text.lower()
        )
        if looks_like_events and pinned.message_id != current_msg_id:
            try:
                await context.bot.unpin_chat_message(chat_id, pinned.message_id)
            except Exception:
                pass
            try:
                await context.bot.delete_message(chat_id, pinned.message_id)
                removed += 1
            except Exception:
                pass

    # Пересоздаём/обновляем актуальное сообщение с ивентами и закрепляем его
    await _refresh_events_message(context.bot, chat_id)

    if removed:
        msg = await update.message.reply_text(
            f"🗑 Найден и удалён старый дубликат закреплённого сообщения с ивентами ({removed})."
        )
    else:
        msg = await update.message.reply_text(
            "✅ Дубликатов не найдено — закреплённое сообщение актуально."
        )
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
    if not await _is_admin(context.bot, chat_id, update.effective_user.id, update.effective_user.username):
        await update.message.reply_text("⛔ Только администраторы могут видеть отчёт активности.")
        return
    data = activity.get(chat_id, {})
    tags = storage.load_tags()

    if not data:
        await update.message.reply_text("📭 Статистика пустая.")
        return

    srt    = sorted(data.items(), key=lambda x: x[1]["count"], reverse=True)
    total  = sum(u["count"] for _, u in srt)
    active = [(uid, u) for uid, u in srt if u["count"] > 0]

    lines = [f"📈 Отчёт активности\n(сообщений: {total})\n"]
    for rank, (uid, u) in enumerate(active, 1):
        pct = round(u["count"]/total*100) if total else 0
        lines.append(f"{medal(rank)} {u['name']} — {u['count']} сообщ. ({pct}%)")

    active_ids = {uid for uid, _ in active}
    silent_tags = [u for uid, u in tags.items() if int(uid) not in active_ids]
    if silent_tags:
        lines.append("\n👻 Молчат:")
        for u in silent_tags:
            mention = f"@{u['username']}" if u.get("username") else u["name"]
            lines.append(f"  • {mention}")

    # Нагороди
    lines.append("\n🏆 Лидеры:")
    if active:
        lines.append(f"💬 {active[0][1]['name']} — 🎖 «Болтун»!")
    scores = _quiz_scores.get(chat_id, {})
    if scores:
        top_quiz = max(scores.items(), key=lambda x: x[1]["score"])
        lines.append(f"🧠 {top_quiz[1]['name']} — {top_quiz[1]['score']} ответов — 🎓 «Умник»!")
    ev_authors: dict = {}
    for ev in _events.get(chat_id, []):
        aid = ev.get("author_id")
        if aid:
            if aid not in ev_authors:
                ev_authors[aid] = {"name": ev.get("author","?"), "count": 0}
            ev_authors[aid]["count"] += 1
    if ev_authors:
        top_ev = max(ev_authors.items(), key=lambda x: x[1]["count"])
        lines.append(f"🎉 {top_ev[1]['name']} — {top_ev[1]['count']} ивентов — 🏅 «Организатор»!")

    await update.message.reply_text("\n".join(lines))

async def cmd_reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    activity[update.effective_chat.id] = {}
    await update.message.reply_text("🔄 Статистика сброшена!")

async def cmd_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Legacy command — redirect to combined handler."""
    item = random.choice(all_qt_items())
    await update.message.reply_text(item, parse_mode="Markdown")
    _schedule_delete(context, update.effective_chat.id, update.message.message_id, 60)

async def cmd_topic(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Legacy command — redirect to combined handler."""
    item = random.choice(all_qt_items())
    await update.message.reply_text(item, parse_mode="Markdown")
    _schedule_delete(context, update.effective_chat.id, update.message.message_id, 60)

async def _send_qt_menu(send_fn, chat_id: int, bot):
    """Show question/topic sub-menu."""
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🎲 Случайный вопрос/тема",  callback_data="qt_random")],
        [InlineKeyboardButton("✏️ Добавить свой вопрос",   callback_data="qt_add")],
    ])
    sent = await send_fn(
        "❓ *Вопрос / Тема*\n\nВыбери действие:",
        parse_mode="Markdown",
        reply_markup=kb
    )
    asyncio.create_task(_auto_delete(bot, chat_id, sent.message_id, 60))

# ── Автоматические задачи ──────────────────────

async def sched_random(context: ContextTypes.DEFAULT_TYPE):
    now = datetime.now(KYIV_TZ)
    if now.hour < 7 or now.hour >= 22:
        return
    chat_id = context.job.data["chat_id"]
    text = random.choice(all_qt_items())
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

    lines = [f"📈 Еженедельный отчёт\n(сообщений: {total})\n"]
    for rank, (uid, u) in enumerate(active, 1):
        lines.append(f"{medal(rank)} {u['name']} — {u['count']} сообщ.")

    # Мовчуни
    active_ids = {uid for uid, u in active}
    tags = storage.load_tags()
    silent = [u for uid, u in tags.items() if int(uid) not in active_ids]
    if silent:
        mentions = [f"@{u['username']}" if u.get("username") else u["name"] for u in silent]
        lines.append(f"\n👻 Молчуны: {', '.join(mentions)}")

    # ── Нагороди тижня ──
    lines.append("\n🏆 Награды недели:")

    # Найбільше повідомлень
    if active:
        top_uid, top_u = active[0]
        lines.append(f"💬 Душа компании: {top_u['name']} — 🎖 «Болтун недели»!")

    # Квіз — найбільше правильних відповідей
    scores = _quiz_scores.get(chat_id, {})
    if scores:
        top_quiz = max(scores.items(), key=lambda x: x[1]["score"])
        lines.append(f"🧠 Умник: {top_quiz[1]['name']} — {top_quiz[1]['score']} правильных ответов — 🎓 «Мозг на службе у Бендера»!")
        _quiz_scores[chat_id] = {}  # Скидаємо бали

    # Івенти — хто запропонував найбільше
    ev_list = _events.get(chat_id, [])
    ev_authors: dict = {}
    for ev in ev_list:
        aid  = ev.get("author_id")
        aname = ev.get("author", "?")
        if aid:
            if aid not in ev_authors:
                ev_authors[aid] = {"name": aname, "count": 0}
            ev_authors[aid]["count"] += 1
    if ev_authors:
        top_ev = max(ev_authors.items(), key=lambda x: x[1]["count"])
        lines.append(f"🎉 Организатор: {top_ev[1]['name']} — {top_ev[1]['count']} ивентов — 🏅 «Главный по тусовкам»!")

    await context.bot.send_message(chat_id, "\n".join(lines))

    # Скидаємо activity для нового тижня
    for uid in activity[chat_id]:
        activity[chat_id][uid]["count"] = 0


# ── Перевірка тиші в чаті ─────────────────────────────────────────────────────

async def generate_bender_icebreaker() -> str:
    """ШІ генерує повідомлення-пробивач тиші в стилі Бендера."""
    prompts = [
        "Напиши короткое сообщение (2-4 предложения) от имени Бендера который замечает тишину в чате друзей. "
        "Он начинает разговор сам — задаёт вопрос типа 'чем занимаетесь', делится выдуманным фактом о себе, "
        "или предлагает что-то сделать вместе (купаться, пить пиво, идти гулять). "
        "Стиль: циничный, самовлюблённый, смешной. Пиши на русском. Без вступлений — сразу текст.",
    ]
    return await ask_ai(random.choice(prompts))

async def sched_anketa_reminder(context: ContextTypes.DEFAULT_TYPE):
    """Щодня о 17:00 — нагадування заповнити анкету тим хто цього не зробив."""
    chat_id = context.job.data["chat_id"]
    tags = storage.load_tags()
    profiles = storage.load_profiles()

    # Знаходимо тих хто є в тегах але не має анкети
    missing = []
    for uid_str, u in tags.items():
        uid = int(uid_str)
        if uid not in profiles and str(uid) not in profiles:
            mention = f"@{u['username']}" if u.get("username") else u["name"]
            missing.append(mention)

    if not missing:
        return  # Всі заповнили — не спамимо

    names_str = ", ".join(missing[:10])
    if len(missing) > 10:
        names_str += f" и ещё {len(missing)-10}"

    text = (
        f"📋 Бендер провёл перекличку и выяснил:\n\n"
        f"{names_str} — анкета не заполнена!\n\n"
        f"Я не буду просить дважды... ладно, буду. Заполните анкету:\n"
        f"Напиши в чат: о себе [расскажи кто ты, откуда, чем занимаешься]\n\n"
        f"Это займёт 30 секунд. Даже я, Бендер, заполнил бы быстрее — "
        f"если бы у меня была анкета. И душа."
    )
    sent = await context.bot.send_message(chat_id, text)
    _schedule_delete(context, chat_id, sent.message_id, 7200)


async def sched_check_silence(context: ContextTypes.DEFAULT_TYPE):
    """Кожні 5 годин — якщо тиша > 5 годин, Бендер сам починає розмову через ШІ."""
    chat_id = context.job.data["chat_id"]
    now = datetime.now(KYIV_TZ).timestamp()
    last = _last_message_time.get(chat_id)

    # Тільки якщо ніхто не писав більше 5 годин і зараз між 9:00 і 23:00
    hour = datetime.now(KYIV_TZ).hour
    if hour < 9 or hour >= 23:
        return
    if last is None or (now - last) < 7200:
        return

    try:
        text = await generate_bender_icebreaker()
        sent = await context.bot.send_message(chat_id, f"🤖 {text}")
        # Оновлюємо час щоб не спамити
        _last_message_time[chat_id] = datetime.now(KYIV_TZ).timestamp()
        # Авто-видалення через 6 годин
        _schedule_delete(context, chat_id, sent.message_id, 7200)
    except Exception as e:
        logger.error(f"sched_check_silence: {e}")


ALL_JOB_SUFFIXES = ["_weather", "_friday", "_evening", "_monday",
                    "_report", "_news", "_cleanup", "_qt", "_silence", "_anketa"]

def _all_job_names(chat_id):
    return [str(chat_id)] + [f"{chat_id}{s}" for s in ALL_JOB_SUFFIXES]

def _remove_jobs(jq, chat_id):
    for name in _all_job_names(chat_id):
        for job in jq.get_jobs_by_name(name):
            job.schedule_removal()

def schedule_auto_jobs(jq, chat_id):
    """Планує всі авто-повідомлення для чату. Видаляє старі перед створенням нових."""
    _remove_jobs(jq, chat_id)
    jq.run_daily(sched_weather,            time=time(8,0,tzinfo=KYIV_TZ),   days=tuple(range(7)), data={"chat_id":chat_id}, name=f"{chat_id}_weather")
    jq.run_daily(sched_morning_news,       time=time(8,5,tzinfo=KYIV_TZ),   days=tuple(range(7)), data={"chat_id":chat_id}, name=f"{chat_id}_news")
    jq.run_daily(sched_howwasday,          time=time(21,0,tzinfo=KYIV_TZ),  days=tuple(range(7)), data={"chat_id":chat_id}, name=f"{chat_id}_evening")
    jq.run_daily(sched_weekly_report,      time=time(20,0,tzinfo=KYIV_TZ),  days=(6,),            data={"chat_id":chat_id}, name=f"{chat_id}_report")
    jq.run_daily(sched_cleanup_events,     time=time(0,5,tzinfo=KYIV_TZ),   days=tuple(range(7)), data={"chat_id":chat_id}, name=f"{chat_id}_cleanup")
    jq.run_daily(sched_anketa_reminder,       time=time(17,0,tzinfo=KYIV_TZ),  days=tuple(range(7)), data={"chat_id":chat_id}, name=f"{chat_id}_anketa")
    jq.run_repeating(sched_check_silence,     interval=1800, first=300,          data={"chat_id":chat_id}, name=f"{chat_id}_silence")

async def cmd_autostart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    schedule_auto_jobs(context.job_queue, chat_id)
    storage.set_autorun(chat_id, True)

    sent = await update.message.reply_text(
        "✅ Автоматические сообщения включены!\n\n"
        "🌤 08:00 — погода\n"
        "📰 08:05 — новость дня\n"
        "🌙 21:00 — как прошёл день\n"
        "📈 Вс 20:00 — еженедельный отчёт\n\n"
        "Выключить: /autooff\n🌵 Авто-мем при тишине > 2 часов: включён"
    )
    _schedule_delete(context, chat_id, sent.message_id, 60)
    _schedule_delete(context, chat_id, update.message.message_id, 60)

async def cmd_autooff(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Вимкнути всі авто-повідомлення."""
    chat_id = update.effective_chat.id
    if not await _is_admin(context.bot, chat_id, update.effective_user.id, update.effective_user.username):
        await update.message.reply_text("❌ Только администраторы могут управлять авто-сообщениями.")
        return
    jq = context.job_queue
    count = 0
    for name in _all_job_names(chat_id):
        for job in jq.get_jobs_by_name(name):
            job.schedule_removal()
            count += 1
    storage.set_autorun(chat_id, False)
    sent = await update.message.reply_text(
        f"⏹ Все авто-сообщения отключены ({count} задач удалено).\n\n"
        "Включить снова: /autostart"
    )
    _schedule_delete(context, chat_id, sent.message_id, 60)
    _schedule_delete(context, chat_id, update.message.message_id, 10)


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "📖 Все команды бота:\n\n"
        "/start — Главное меню Бендера\n"
        "/event — Предложить ивент\n"
        "/events — Активные ивенты\n"
        "/profile — Моя анкета\n"
        "/profiles — Анкеты участников\n"
        "/weather — Погода\n"
        "/question — Провокационный вопрос\n"
        "/topic — Тема для разговора\n"
        "/quiz — Квиз от ИИ\n"
        "/photoday — Фото дня\n\n"
        "👮 Команды для админов:\n\n"
        "/report — Отчёт активности\n"
        "/gather — Тегнуть всех\n"
        "/addmember — Добавить в список\n"
        "/removemember — Удалить из списка\n"
        "/listmembers — Список участников\n"
        "/cleanupmembers — Очистить вышедших\n"
        "/clearevents — Удалить все ивенты\n"
        "/autostart — Включить авто-сообщения\n"
        "/autooff — Выключить авто-сообщения\n"
        "/testbot — Тест авто-сообщений\n\n"
        "✍️ Теги (слова без команды):\n\n"
        "Бендер / Бляшанка / Bender — открыть меню\n"
        "Бендер, [вопрос] — спросить ИИ\n"
        "о себе [текст] — сохранить анкету\n"
        "мой инстаграм @ник — добавить Instagram\n"
        "моя работа [текст] — добавить место работы\n"
        "Анкета (reply) — сохранить анкету из чужого сообщения\n"
        "Анонім [текст] — анонимное сообщение"
    )
    sent = await update.message.reply_text(text)
    _schedule_delete(context, update.effective_chat.id, sent.message_id, 120)


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "🤖✨ Бендер Сгибатель Родригес к вашим услугам!\n\n"
        "Я здесь чтобы вы не потерялись в тишине этого чата 🍺\n\n"
        "Хочешь заполнить анкету — напиши сообщение:\n"
        "о себе  и дальше расскажи о себе 🙂\n\n"
        "Например: о себе Привет! Я Бендер, 28 лет, люблю пиво и ограбления ☕"
    )
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📋 Анкеты участников",    callback_data="menu_profiles")],
        [InlineKeyboardButton("🎉 Предложить ивент",     callback_data="menu_event"),
         InlineKeyboardButton("📅 Активные ивенты",      callback_data="menu_events")],
        [InlineKeyboardButton("🌤 Погода",               callback_data="menu_weather")],
        [InlineKeyboardButton("❓ Вопрос / Тема",         callback_data="menu_qt"),
         InlineKeyboardButton("🧠 Квиз",                 callback_data="menu_quiz")],
        [InlineKeyboardButton("ℹ️ Как мной пользоваться", callback_data="menu_howto")],
    ])
    sent = await update.message.reply_text(text, reply_markup=keyboard)
    _schedule_delete(context, update.effective_chat.id, sent.message_id, 60)


async def cb_qt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    chat_id = q.message.chat_id
    action = q.data  # qt_random | qt_add

    if action == "qt_random":
        item = random.choice(all_qt_items())
        await q.message.reply_text(item, parse_mode="Markdown")
        try:
            await q.message.delete()
        except Exception:
            pass

    elif action == "qt_add":
        key = f"qt_add_{q.from_user.id}_{chat_id}"
        context.bot_data[key] = True
        sent = await q.message.reply_text(
            "✏️ Напиши свой вопрос или тему следующим сообщением.\n\n"
            "Он будет добавлен в общий список и появится при следующем случайном выборе 🎲",
        )
        _schedule_delete(context, chat_id, sent.message_id, 60)
        try:
            await q.message.delete()
        except Exception:
            pass

async def cb_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q       = update.callback_query
    await q.answer()
    action  = q.data.replace("menu_", "")
    chat_id = q.message.chat_id

    if action == "myprofile":
        sent = await q.message.reply_text(
            "✏️ *Как заполнить анкету*\n\n"
            "Напиши в чат одно из следующих сообщений:\n\n"
            "👤 *Основная информация:*\n"
            "`о себе` Привет\\! Меня зовут Иван, 28 лет, из Киева, люблю настолки\n\n"
            "📸 *Instagram:*\n"
            "`мой инстаграм @твой_ник`\n\n"
            "💼 *Место работы:*\n"
            "`моя работа Название компании`\n\n"
            "Каждое поле можно добавлять отдельно — они дополняют анкету, а не заменяют её\\.\n\n"
            "Посмотреть свою анкету: /profile",
            parse_mode="MarkdownV2"
        )
        _schedule_delete(context, q.message.chat_id, sent.message_id, 60)
        return

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
        kb_w = InlineKeyboardMarkup([[
            InlineKeyboardButton("📅 Сегодня", callback_data="w_today"),
            InlineKeyboardButton("🔜 Завтра",  callback_data="w_tomorrow"),
            InlineKeyboardButton("📆 3 дня",  callback_data="w_week"),
        ]])
        await q.message.reply_text("🌍 На когда нужна погода?", reply_markup=kb_w)

    elif action == "qt":
        await _send_qt_menu(q.message.reply_text, q.message.chat_id, context.bot)

    elif action == "quiz":
        chat_id_q = q.message.chat_id
        tmp = await q.message.reply_text("🧠 Генерирую вопрос...")
        quiz = await ask_ai_quiz()
        if not quiz:
            await tmp.edit_text("😔 Не удалось сгенерировать вопрос. Попробуй позже.")
            return
        try:
            await tmp.delete()
        except Exception:
            pass
        sent_q = await context.bot.send_poll(
            chat_id_q,
            f"🧠 {quiz['question']}",
            quiz["options"],
            type="quiz",
            correct_option_id=quiz["correct_index"],
            is_anonymous=False,
        )
        context.bot_data[f"quiz_{sent_q.poll.id}"] = {
            "chat_id": chat_id_q,
            "correct_option_id": quiz["correct_index"],
        }
        _schedule_delete(context, chat_id_q, sent_q.message_id, 7200)

    elif action == "howto":
        howto_text = (
            "ℹ️ *Как мной пользоваться*\n\n"
            "🤖 Зови меня в чате: напиши *Бендер*, *Бенди* или *Бляшанка* — открою меню.\n\n"
            "💬 Спроси что-нибудь: *Бендер, [вопрос]* — отвечу как умею.\n"
            "Можешь продолжать разговор — ответь (reply) на мой ответ, я запомню контекст.\n\n"
            "🌤 Погода: жми кнопку *Погода* или пиши *Бендер, погода* / *погода на завтра*.\n\n"
            "🎉 Ивенты: кнопка *Предложить ивент* создаёт событие с голосованием. Можно сказать *Бендер, создай ивент*.\n\n"
            "📋 Анкета: напиши *о себе [расскажи о себе]* — сохраню. "
            "Можно добавить *мой инстаграм @ник* и *моя работа [текст]*.\n\n"
            "🧠 Квиз и ❓ Вопрос/Тема — кнопки в меню для развлечения в чате.\n\n"
            "🎭 Анонимное сообщение: напиши *Анонім [текст]* — опубликую без указания автора.\n\n"
            "Полный список команд: /help"
        )
        sent = await q.message.reply_text(howto_text, parse_mode="Markdown")
        _schedule_delete(context, q.message.chat_id, sent.message_id, 120)

    elif action == "report":
        await _menu_report(q, context)

    elif action == "autostart":
        await _menu_autostart(q, context)

    elif action == "clearevents":
        if not await _is_admin(context.bot, chat_id, q.from_user.id, q.from_user.username):
            await q.answer("⛔ Только администраторы могут очищать ивенты.", show_alert=True)
            return
        _events[chat_id] = []
        storage.save_events(_events)
        await _refresh_events_message(context.bot, chat_id)
        await q.message.reply_text("🗑 Все ивенты очищены. Закреплённое сообщение обновлено.")

async def _menu_profiles(q, context):
    profiles = storage.load_profiles()
    how_to = (
        "✏️ *Как заполнить анкету:*\n"
        "Напиши в чат:\n"
        "• `о себе` Привет\\! Меня зовут Иван, 28 лет\n"
        "• `мой инстаграм @ник`\n"
        "• `моя работа Название компании`\n\n"
    )
    if not profiles:
        sent = await q.message.reply_text(
            how_to + "📭 Ещё никто не заполнил анкету\\.",
            parse_mode="MarkdownV2"
        )
        _schedule_delete(context, q.message.chat_id, sent.message_id, 60)
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
        sent = await q.message.reply_text(
            how_to + "📭 Никто из текущих участников ещё не заполнил анкету\\.",
            parse_mode="MarkdownV2"
        )
        _schedule_delete(context, q.message.chat_id, sent.message_id, 60)
        return
    keyboard = []
    for uid, p in filtered.items():
        label = p["tg_name"]
        if p.get("username"):
            label += f" (@{p['username']})"
        keyboard.append([InlineKeyboardButton(label, callback_data=f"showprofile_{uid}")])
    sent = await q.message.reply_text(
        how_to + f"📋 Анкеты участников группы: {len(filtered)}\n\nНажми на имя 👇",
        parse_mode="MarkdownV2",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    _schedule_delete(context, q.message.chat_id, sent.message_id, 60)

async def _menu_report(q, context):
    chat_id = q.message.chat_id
    if not await _is_admin(context.bot, chat_id, q.from_user.id, q.from_user.username):
        await q.answer("⛔ Только администраторы могут видеть отчёт активности.", show_alert=True)
        return
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

    if not await _is_admin(context.bot, chat_id, update.effective_user.id):
        await update.message.reply_text("❌ Только администраторы могут добавлять участников.")
        return

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
            "• /addmember @user1 @user2 @user3 ... — добавить сразу всех (можно вставить весь список тегов из чата!)\n"
            "• Ответ на сообщение + /addmember — добавить автора\n\n"
            "💡 Совет: собери все @username участников в одно сообщение и отправь команду — добавятся все за раз."
        )
        return

    storage.save_tags(tags)

    lines = []
    if added:
        lines.append(f"✅ Добавлено ({len(added)}): {', '.join(added)}")
    if not_found:
        lines.append(f"❌ Не найдено: {', '.join(not_found)}")
    lines.append(f"\n👥 Всего в списке: {len(tags)}")
    sent = await update.message.reply_text("\n".join(lines))
    _schedule_delete(context, update.effective_chat.id, sent.message_id, 60)


async def cmd_removemember(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id

    if not await _is_admin(context.bot, chat_id, update.effective_user.id):
        await update.message.reply_text("❌ Только администраторы могут удалять участников.")
        return

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
    sent = await update.message.reply_text(
        f"🗑 Удалено: {', '.join(removed)}\n"
        f"👥 Осталось в списке: {len(tags)}"
    )
    _schedule_delete(context, update.effective_chat.id, sent.message_id, 60)


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
    sent = await update.message.reply_text("\n".join(lines))
    _schedule_delete(context, update.effective_chat.id, sent.message_id, 60)


async def cmd_cleanup_members(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id

    if not await _is_admin(context.bot, chat_id, update.effective_user.id):
        await update.message.reply_text("❌ Только администраторы.")
        return

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
    _schedule_delete(context, update.effective_chat.id, msg.message_id, 60)

async def cmd_testbot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin command: send all automatic messages at once, then delete after 10 sec."""
    chat_id = update.effective_chat.id
    if not await _is_admin(context.bot, chat_id, update.effective_user.id):
        await update.message.reply_text("❌ Только для администраторов.")
        return

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

    # 5. Evening poll (real Telegram poll)
    m = await context.bot.send_poll(
        chat_id, "🧪 [ТЕСТ] 🌙 Как прошёл ваш день?",
        ["🔥 Отлично!", "😊 Хорошо", "😐 Нормально", "😔 Тяжеловато", "🤦 Лучше не спрашивай"],
        is_anonymous=False, allows_multiple_answers=False
    )
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

    # 7. Random question/topic
    m = await context.bot.send_message(chat_id, f"🧪 [ТЕСТ] {_r.choice(all_qt_items())}", parse_mode="Markdown")
    sent_msgs.append(m.message_id)

    # 8. Квіз від ШІ
    quiz = await ask_ai_quiz()
    if quiz:
        m = await context.bot.send_poll(
            chat_id, f"🧪 [ТЕСТ] 🧠 {quiz['question']}",
            quiz["options"], type="quiz",
            correct_option_id=quiz["correct_index"], is_anonymous=False,
        )
        sent_msgs.append(m.message_id)

    # 9. Пробивач тиші від ШІ
    icebreaker = await generate_bender_icebreaker()
    m = await context.bot.send_message(chat_id, f"🧪 [ТЕСТ] 🤖 {icebreaker}")
    sent_msgs.append(m.message_id)

    # 10. Нагадування анкети
    tags = storage.load_tags()
    profiles = storage.load_profiles()
    missing_count = sum(1 for uid_str in tags if int(uid_str) not in profiles and uid_str not in profiles)
    if missing_count > 0:
        m = await context.bot.send_message(chat_id,
            f"🧪 [ТЕСТ] 📋 Бендер провёл перекличку — {missing_count} человек всё ещё без анкеты!\n\n"
            f"Напиши в чат: *о себе* и расскажи кто ты.", parse_mode="Markdown")
    else:
        m = await context.bot.send_message(chat_id, "🧪 [ТЕСТ] 📋 Все участники заполнили анкету — Бендер доволен!")
    sent_msgs.append(m.message_id)

    # 11. Фото дня
    m = await context.bot.send_message(chat_id, f"🧪 [ТЕСТ] {_r.choice(PHOTO_DAY_PROMPTS)}")
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


async def auto_delete_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Видаляє повідомлення-команду через 10 секунд (тільки в групах)."""
    if not update.message or update.effective_chat.type == "private":
        return
    text = update.message.text or ""
    if not text.startswith("/"):
        return
    _schedule_delete(context, update.effective_chat.id, update.message.message_id, 60)


async def handle_poll_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Нараховує бали за правильну відповідь в quiz poll."""
    answer = update.poll_answer
    if not answer:
        return
    poll_id = answer.poll_id
    user = answer.user
    # Знаходимо правильний варіант з збережених даних
    quiz_data = context.bot_data.get(f"quiz_{poll_id}")
    if not quiz_data:
        return
    chat_id = quiz_data["chat_id"]
    correct = quiz_data["correct_option_id"]
    if answer.option_ids and answer.option_ids[0] == correct:
        if user.id not in _quiz_scores[chat_id]:
            _quiz_scores[chat_id][user.id] = {"name": user.first_name, "score": 0}
        _quiz_scores[chat_id][user.id]["name"] = user.first_name
        _quiz_scores[chat_id][user.id]["score"] += 1



# ── Система голосувань ────────────────────────────────────────────────────────
# { chat_id: { poll_id: { title, options: [{text, voters:[uid,...]}], msg_id, author_id } } }
_polls: dict = {}
_poll_counter: int = 0
_poll_custom_options: dict = {}  # chat_id -> [варіанти що добавляли раніше]

def _next_poll_id() -> int:
    global _poll_counter
    _poll_counter += 1
    return _poll_counter

POLL_DEFAULT_OPTIONS = [
    "☕ Кафе / бар",
    "🚶 Прогулятись",
    "🏖 Пляж / природа",
    "🃏 Мафия",
    "🎲 Настольные игры",
]

def _poll_text(poll: dict) -> str:
    lines = [f"📊 *{poll['title']}*\n"]
    for i, opt in enumerate(poll["options"]):
        voters = opt["voters"]
        count = len(voters)
        names = ", ".join(v["name"] for v in voters) if voters else ""
        count_str = f"{count} {'голос' if count==1 else 'голоса' if 2<=count<=4 else 'голосов'}"
        line = f"• *{opt['text']}* — {count_str}"
        if names:
            line += f"\n  👥 {names}"
        lines.append(line)
    return "\n".join(lines)

def _poll_kb(poll: dict, poll_id: int) -> InlineKeyboardMarkup:
    rows = []
    for i, opt in enumerate(poll["options"]):
        rows.append([
            InlineKeyboardButton(opt["text"], callback_data=f"vote_{poll_id}_{i}"),
            InlineKeyboardButton("❌", callback_data=f"poll_del_{poll_id}_{i}"),
        ])
    rows.append([InlineKeyboardButton("➕ Добавить вариант", callback_data=f"poll_add_{poll_id}")])
    return InlineKeyboardMarkup(rows)

async def cmd_poll_create(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Создать новое голосование."""
    chat_id = update.effective_chat.id
    args = " ".join(context.args).strip() if context.args else ""
    if not args:
        sent = await update.message.reply_text(
            "📊 Напиши тему голосования:\n/vote Куди йдемо у п'ятницю?"
        )
        _schedule_delete(context, chat_id, sent.message_id, 60)
        return
    await _create_poll(update, context, args)

async def _create_poll(update: Update, context: ContextTypes.DEFAULT_TYPE, title: str):
    chat_id = update.effective_chat.id
    user = update.effective_user
    poll_id = _next_poll_id()

    # Дефолтні + раніше додані кастомні варіанти
    all_opts = list(POLL_DEFAULT_OPTIONS)
    for c in _poll_custom_options.get(chat_id, []):
        if c not in all_opts:
            all_opts.append(c)

    # Зберігаємо чернетку
    _polls.setdefault(chat_id, {})[poll_id] = {
        "title": title,
        "options": [],
        "msg_id": None,
        "author_id": user.id,
        "draft": True,
        "selected": [],
        "all_options": all_opts,
    }
    context.bot_data[f"poll_draft_{poll_id}"] = {"chat_id": chat_id, "title": title}

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(opt, callback_data=f"padd_{poll_id}_{i}")]
        for i, opt in enumerate(all_opts)
    ] + [[
        InlineKeyboardButton("✅ Создать голосование!", callback_data=f"pstart_{poll_id}"),
        InlineKeyboardButton("✏️ Свой вариант", callback_data=f"pcustom_{poll_id}"),
    ]])

    sent = await update.message.reply_text(
        f"📊 *{title}*\n\nВыбери варианты (можно несколько) или добавь свой:",
        parse_mode="Markdown",
        reply_markup=kb
    )
    _polls[chat_id][poll_id]["msg_id"] = sent.message_id

async def cb_poll(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обробляє всі кнопки голосування."""
    q = update.callback_query
    await q.answer()
    data = q.data
    chat_id = q.message.chat_id
    user = q.from_user

    # Вибір дефолтного варіанту при створенні
    if data.startswith("padd_"):
        _, poll_id_s, opt_idx_s = data.split("_", 2)
        poll_id = int(poll_id_s)
        opt_idx = int(opt_idx_s)
        poll = _polls.get(chat_id, {}).get(poll_id)
        if not poll:
            return
        opt_text = poll.get("all_options", POLL_DEFAULT_OPTIONS)[opt_idx]
        selected = poll.get("selected", [])
        if opt_idx in selected:
            selected.remove(opt_idx)
        else:
            selected.append(opt_idx)
        poll["selected"] = selected

        all_opts = poll.get("all_options", POLL_DEFAULT_OPTIONS)
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton(
                ("✅ " if i in selected else "") + opt,
                callback_data=f"padd_{poll_id}_{i}"
            )]
            for i, opt in enumerate(all_opts)
        ] + [[
            InlineKeyboardButton("✅ Создать голосование!", callback_data=f"pstart_{poll_id}"),
            InlineKeyboardButton("✏️ Свой вариант", callback_data=f"pcustom_{poll_id}"),
        ]])
        try:
            await q.edit_message_reply_markup(reply_markup=kb)
        except Exception:
            pass
        return

    # Додати свій варіант
    if data.startswith("pcustom_"):
        poll_id = int(data.replace("pcustom_", ""))
        context.bot_data[f"awaiting_poll_option_{chat_id}"] = poll_id
        sent = await q.message.reply_text(
            "✏️ Напиши свой вариант следующим сообщением:"
        )
        _schedule_delete(context, chat_id, sent.message_id, 60)
        return

    # Запустити голосування
    if data.startswith("pstart_"):
        poll_id = int(data.replace("pstart_", ""))
        poll = _polls.get(chat_id, {}).get(poll_id)
        if not poll:
            return
        options = []
        all_opts = poll.get("all_options", POLL_DEFAULT_OPTIONS)
        for i in poll.get("selected", []):
            options.append({"text": all_opts[i], "voters": []})
        for custom in poll.get("custom_options", []):
            options.append({"text": custom, "voters": []})
        if not options:
            await q.answer("⚠️ Выбери хотя бы один вариант!", show_alert=True)
            return
        poll["options"] = options
        poll["draft"] = False
        try:
            await q.message.delete()
        except Exception:
            pass
        sent = await context.bot.send_message(
            chat_id, _poll_text(poll),
            parse_mode="Markdown",
            reply_markup=_poll_kb(poll, poll_id)
        )
        poll["msg_id"] = sent.message_id
        # Закріпити
        try:
            await context.bot.pin_chat_message(chat_id, sent.message_id, disable_notification=True)
        except Exception:
            pass
        return

    # Вибір дати для голосування
    if data.startswith("pdate_") and not data.startswith("pdatecustom_") and not data.startswith("pdatenone_"):
        parts = data.split("_", 2)
        poll_id = int(parts[1])
        date_str = parts[2]
        poll = _polls.get(chat_id, {}).get(poll_id)
        if not poll:
            return
        selected_dates = poll.setdefault("selected_dates", [])
        if date_str in selected_dates:
            selected_dates.remove(date_str)
        else:
            selected_dates.append(date_str)

        now = datetime.now(KYIV_TZ)
        weekdays_ru = ["Пн","Вт","Ср","Чт","Пт","Сб","Вс"]
        date_buttons = []
        for offset in range(1, 8):
            d = now + timedelta(days=offset)
            wd = weekdays_ru[d.weekday()]
            ds = d.strftime('%d.%m')
            label = ("✅ " if ds in selected_dates else "") + f"{wd} {ds}"
            date_buttons.append(
                InlineKeyboardButton(label, callback_data=f"pdate_{poll_id}_{ds}")
            )
        rows = [date_buttons[:3], date_buttons[3:6], [date_buttons[6]]]
        rows.append([
            InlineKeyboardButton("📅 Своя дата", callback_data=f"pdatecustom_{poll_id}"),
            InlineKeyboardButton(
                "✅ Готово!" if selected_dates else "⏩ Без даты",
                callback_data=f"pdatenone_{poll_id}"
            ),
        ])
        try:
            await q.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(rows))
        except Exception:
            pass
        return

    # Своя дата
    if data.startswith("pdatecustom_"):
        poll_id = int(data.replace("pdatecustom_", ""))
        context.bot_data[f"awaiting_poll_date_{chat_id}"] = poll_id
        sent = await q.message.reply_text("📅 Напиши дату в формате дд.мм (например: 15.07):")
        _schedule_delete(context, chat_id, sent.message_id, 60)
        return

    # Завершити вибір дат і опублікувати
    if data.startswith("pdatenone_"):
        poll_id = int(data.replace("pdatenone_", ""))
        poll = _polls.get(chat_id, {}).get(poll_id)
        if not poll:
            return
        selected_dates = poll.get("selected_dates", [])
        # Якщо є дати — додаємо їх як окремі варіанти для кожної активності
        final_options = []
        if selected_dates and poll.get("options"):
            for opt in poll["options"]:
                for date in selected_dates:
                    final_options.append({"text": f"{opt['text']} — {date}", "voters": []})
        else:
            final_options = poll.get("options", [])
        poll["options"] = final_options
        poll["draft"] = False
        poll["draft_dates"] = False
        try:
            await q.message.delete()
        except Exception:
            pass
        sent = await context.bot.send_message(
            chat_id,
            _poll_text(poll),
            parse_mode="Markdown",
            reply_markup=_poll_kb(poll, poll_id)
        )
        poll["msg_id"] = sent.message_id
        return


    # Видалити варіант (адмін або автор)
    if data.startswith("poll_del_"):
        parts = data.split("_")
        poll_id = int(parts[2])
        opt_idx = int(parts[3])
        poll = _polls.get(chat_id, {}).get(poll_id)
        if not poll:
            return
        is_admin = await _is_admin(context.bot, chat_id, user.id, user.username)
        if user.id != poll["author_id"] and not is_admin:
            await q.answer("⛔ Только автор или администратор.", show_alert=True)
            return
        if 0 <= opt_idx < len(poll["options"]):
            removed = poll["options"].pop(opt_idx)
            await q.answer(f"Вариант «{removed['text']}» удалён.")
            if poll.get("msg_id"):
                try:
                    await context.bot.edit_message_text(
                        _poll_text(poll), chat_id=chat_id,
                        message_id=poll["msg_id"],
                        parse_mode="Markdown",
                        reply_markup=_poll_kb(poll, poll_id)
                    )
                except Exception:
                    pass
        return

    # Голосування за варіант
    if data.startswith("vote_"):
        parts = data.split("_")
        poll_id = int(parts[1])
        opt_idx = int(parts[2])
        poll = _polls.get(chat_id, {}).get(poll_id)
        if not poll or poll.get("draft"):
            return
        opt = poll["options"][opt_idx]
        voters = opt["voters"]
        uid = user.id
        # Якщо вже голосував за цей — знімаємо
        existing = next((v for v in voters if v["uid"] == uid), None)
        if existing:
            voters.remove(existing)
            await q.answer("Голос снят.")
        else:
            voters.append({"uid": uid, "name": user.first_name})
            await q.answer(f"✅ Голос за «{opt['text']}» принят!")
        try:
            await q.edit_message_text(
                _poll_text(poll),
                parse_mode="Markdown",
                reply_markup=_poll_kb(poll, poll_id)
            )
        except Exception:
            pass
        return

    # Додати варіант до активного голосування
    if data.startswith("poll_add_"):
        poll_id = int(data.replace("poll_add_", ""))
        poll = _polls.get(chat_id, {}).get(poll_id)
        if not poll:
            return
        is_admin = await _is_admin(context.bot, chat_id, user.id, user.username)
        if user.id != poll["author_id"] and not is_admin:
            await q.answer("⛔ Только автор или администратор.", show_alert=True)
            return
        context.bot_data[f"awaiting_poll_option_{chat_id}"] = poll_id
        sent = await q.message.reply_text("✏️ Напиши новый вариант следующим сообщением:")
        _schedule_delete(context, chat_id, sent.message_id, 60)
        return

    # Закрити голосування
    if data.startswith("poll_close_"):
        poll_id = int(data.replace("poll_close_", ""))
        poll = _polls.get(chat_id, {}).get(poll_id)
        if not poll:
            return
        is_admin = await _is_admin(context.bot, chat_id, user.id, user.username)
        if user.id != poll["author_id"] and not is_admin:
            await q.answer("⛔ Только автор или администратор.", show_alert=True)
            return
        try:
            await q.edit_message_reply_markup(reply_markup=None)
        except Exception:
            pass
        await q.answer("✅ Голосование закрыто!")
        _polls.get(chat_id, {}).pop(poll_id, None)
        return


def main():
    import os
    TOKEN = os.environ.get("BOT_TOKEN")
    if not TOKEN:
        raise ValueError("BOT_TOKEN не установлен!")

    async def post_init(application):
        """Tell Telegram we want chat_member updates (needed for welcome messages in supergroups)."""
        try:
            await application.bot.set_my_commands([])  # keeps connection alive
        except Exception:
            pass
        logger.info("Bot post_init done")

    app = (
        Application.builder()
        .token(TOKEN)
        .post_init(post_init)
        .build()
    )

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_custom_name), group=0)
    app.add_handler(MessageHandler(filters.COMMAND, auto_delete_command), group=2)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, track_message), group=1)
    app.add_handler(MessageHandler(filters.StatusUpdate.LEFT_CHAT_MEMBER, member_left))
    # For supergroups where Telegram sends ChatMemberUpdated instead of service messages
    app.add_handler(ChatMemberHandler(welcome_chat_member, ChatMemberHandler.CHAT_MEMBER))
    app.add_handler(ChatMemberHandler(welcome_chat_member, ChatMemberHandler.MY_CHAT_MEMBER))

    app.add_handler(CallbackQueryHandler(cb_qt,           pattern=r"^qt_"))
    app.add_handler(CallbackQueryHandler(cb_menu,        pattern=r"^menu_"))
    app.add_handler(CallbackQueryHandler(cb_weather_switch, pattern=r"^w_(today|tomorrow|week)$"))
    app.add_handler(CallbackQueryHandler(cb_show_profile, pattern=r"^showprofile_\d+$"))
    app.add_handler(CallbackQueryHandler(cb_etype,       pattern=r"^etype_"))
    app.add_handler(CallbackQueryHandler(cb_eday,        pattern=r"^eday_\w+_\d+$"))
    app.add_handler(CallbackQueryHandler(cb_eday_skip,   pattern=r"^eday_skip_"))
    app.add_handler(CallbackQueryHandler(cb_eday_custom_date, pattern=r"^eday_custom_date_"))
    app.add_handler(CallbackQueryHandler(cb_ev_cancel,   pattern=r"^ev_cancel$"))
    app.add_handler(CallbackQueryHandler(cb_ev_manage,     pattern=r"^ev_manage_\d+$"))
    app.add_handler(CallbackQueryHandler(cb_ev_editdesc,   pattern=r"^ev_editdesc_\d+$"))
    app.add_handler(CallbackQueryHandler(cb_ev_editcancel, pattern=r"^ev_editcancel_\d+$"))
    app.add_handler(CallbackQueryHandler(cb_ev_delete,     pattern=r"^ev_delete_\d+$"))
    app.add_handler(CallbackQueryHandler(cb_ev_delyes,     pattern=r"^ev_delyes_\d+$"))
    app.add_handler(CallbackQueryHandler(cb_ev_back,       pattern=r"^ev_back_\d+$"))
    app.add_handler(CallbackQueryHandler(cb_ev_vote,     pattern=r"^ev_(yes|no|maybe|change)_\d+$"))

    app.add_handler(CommandHandler("start",         cmd_start))
    app.add_handler(CommandHandler("help",          cmd_help))
    app.add_handler(CommandHandler("event",         cmd_event))
    app.add_handler(CommandHandler("events",        cmd_events_list))
    app.add_handler(CommandHandler("clearevents",   cmd_clear_events))
    app.add_handler(CommandHandler("vote",           cmd_poll_create))
    app.add_handler(CallbackQueryHandler(cb_poll, pattern=r"^(vote_|padd_|pcustom_|pstart_|poll_add_|poll_del_)"))
    app.add_handler(CommandHandler("fixpinned",     cmd_fix_pinned_events))
    app.add_handler(CommandHandler("weather",       cmd_weather))
    app.add_handler(CommandHandler("question",      cmd_question))
    app.add_handler(CommandHandler("topic",         cmd_topic))
    app.add_handler(CommandHandler("report",        cmd_report))
    app.add_handler(CommandHandler("resetstats",    cmd_reset))
    app.add_handler(CommandHandler("gather",        cmd_gather))
    app.add_handler(CommandHandler("tags",          cmd_tags_list))
    app.add_handler(CommandHandler("profile",       cmd_profile))
    app.add_handler(CommandHandler("profiles",      cmd_profiles_list))
    app.add_handler(CommandHandler("autooff",      cmd_autooff))
    app.add_handler(CommandHandler("autostart",     cmd_autostart))
    app.add_handler(CommandHandler("lang",          cmd_lang))
    app.add_handler(CommandHandler("addmember",     cmd_addmember))
    app.add_handler(CommandHandler("removemember",  cmd_removemember))
    app.add_handler(CommandHandler("listmembers",   cmd_listmembers))
    app.add_handler(CommandHandler("cleanupmembers", cmd_cleanup_members))
    app.add_handler(CommandHandler("testbot",       cmd_testbot))
    app.add_handler(CommandHandler("quiz",          cmd_quiz))
    from telegram.ext import PollAnswerHandler
    app.add_handler(PollAnswerHandler(handle_poll_answer))
    app.add_handler(CommandHandler("photoday",      cmd_photoday))

    logger.info("Бот запущен!")
    app.run_polling(
        allowed_updates=["message", "callback_query", "chat_member", "my_chat_member", "poll_answer"]
    )


if __name__ == "__main__":
    main()
