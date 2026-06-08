import asyncio
import logging
import random
import pytz
import aiohttp
from collections import defaultdict
from datetime import datetime, time
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    ContextTypes, MessageHandler, ConversationHandler, filters,
)

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

KYIV_TZ = pytz.timezone("Europe/Kyiv")
WEATHER_CITY = "Bratislava"
WEATHER_CITY_UA = "Братислава"
WEATHER_LAT = "48.1486"
WEATHER_LON = "17.1077"

# ConversationHandler стани
ANKETA_NAME, ANKETA_AGE, ANKETA_ABOUT, ANKETA_HOBBY, ANKETA_FACT = range(5)
EVENT_TYPE, EVENT_DAY, EVENT_CUSTOM = range(5, 8)

# ─────────────────────────────────────────────
# Сховища в пам'яті
# ─────────────────────────────────────────────
activity: dict[int, dict[int, dict]] = defaultdict(dict)
profiles: dict[int, dict] = {}
# events: { chat_id: [ {id, type, day, author, author_id, votes: {user_id: bool}} ] }
events: dict[int, list] = defaultdict(list)
event_counter = 0

# ─────────────────────────────────────────────
# Контент
# ─────────────────────────────────────────────
RANDOM_QUESTIONS = [
    "🧠 Якщо б ваш мозок міг автоматично видалити одну навичку і замінити її іншою — що б ви поміняли?",
    "🌀 Є щось що ви робите абсолютно не так, як усі — і вам байдуже?",
    "🕳 Яка ваша найбільша «кроляча нора» — тема або хобі, куди ви провалюєтесь і забуваєте про час?",
    "🦸 Якби у вас була суперсила, але про неї не можна нікому казати — яку б обрали?",
    "📦 Якби ви могли надіслати посилку собі 10-річному — що б туди поклали?",
    "🎲 Яке рішення у житті ви прийняли «навмання» — і воно виявилось правильним?",
    "🌍 Якби можна було жити в будь-якій країні рік без наслідків — куди б поїхали і чому саме туди?",
    "🔇 Якби ви мали провести тиждень у повній тиші без телефону — що б найбільше бракувало?",
    "🎭 Яку роль ви граєте в компанії друзів, яку самі за собою помітили?",
    "🏚 Є місце з дитинства, яке хотілося б ще раз побачити — яке?",
    "🧩 Що в людях вас приваблює з першого погляду — і це не зовнішність?",
    "⏳ Якщо б вам залишився один «вільний» рік без жодних зобов'язань — як би ви його провели?",
    "🌙 Який момент у житті ви хотіли б заморозити і повертатись до нього?",
    "🎵 Є пісня, яка переносить вас в конкретне місце або момент — яка?",
    "🤝 Яку одну звичку іншої людини ви таємно хотіли б перейняти?",
    "🧳 Якщо завтра вас змусять поїхати в дорогу на місяць з одним рюкзаком — що обов'язково візьмете?",
    "💬 Є фраза або порада, яку вам колись сказали і вона досі живе в голові — яка?",
    "🎯 Яку річ ви відкладаєте роками, але точно знаєте що колись зробите?",
    "🌧 Дощова субота вдома — це для вас катастрофа чи ідеальний день?",
    "🐾 Якби ваш характер був твариною — яка б це була і чому саме вона?",
]

DISCUSSION_TOPICS = [
    "🗣 *Тема:* Є місця в Братиславі, де час ніби зупиняється. Які вони для вас?",
    "🗣 *Тема:* Як ви знаходите нових друзів у дорослому віці — це взагалі реально?",
    "🗣 *Тема:* Настільні ігри — це просто розваги чи щось більше про людей?",
    "🗣 *Тема:* Що робить вечір з компанією ідеальним? Місце, люди, атмосфера — що важливіше?",
    "🗣 *Тема:* Ви плануєте відпочинок заздалегідь чи їдете «куди очі дивляться»?",
    "🗣 *Тема:* Похід у гори — терапія чи тортури? Що вас туди тягне або відлякує?",
    "🗣 *Тема:* Є щось, чим ви захоплювались у дитинстві і досі не кинули?",
    "🗣 *Тема:* Яке місце в Братиславі треба обов'язково показати гостю, якого привезли вперше?",
]

EVENT_TYPES = {
    "boardgames": "🎲 Настільні ігри",
    "hike":       "🥾 Похід / прогулянка",
    "cafe":       "☕ Кафе / бар",
    "cinema":     "🎬 Кіно",
    "quest":      "🎯 Квест / активність",
    "online":     "💻 Онлайн-вечір",
    "custom":     "✏️ Своя ідея...",
}

DAYS = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Нд"]
DAY_EMOJI = ["📅","📅","📅","📅","🎉","🎉","😴"]

# ─────────────────────────────────────────────
# Погода (Open-Meteo — безкоштовно, без ключа)
# ─────────────────────────────────────────────

async def fetch_weather() -> dict | None:
    url = (
        f"https://api.open-meteo.com/v1/forecast"
        f"?latitude={WEATHER_LAT}&longitude={WEATHER_LON}"
        f"&current=temperature_2m,apparent_temperature,weathercode,windspeed_10m,relative_humidity_2m"
        f"&timezone=Europe/Bratislava"
    )
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(url, timeout=aiohttp.ClientTimeout(total=10)) as r:
                if r.status == 200:
                    return await r.json()
    except Exception as e:
        logger.error(f"Weather error: {e}")
    return None

def wmo_emoji(code: int) -> str:
    if code == 0: return "☀️"
    if code in (1, 2): return "🌤"
    if code == 3: return "☁️"
    if code in (45, 48): return "🌫"
    if code in range(51, 68): return "🌧"
    if code in range(71, 78): return "🌨"
    if code in range(80, 83): return "🌦"
    if code in (95, 96, 99): return "⛈"
    return "🌡"

def wmo_desc(code: int) -> str:
    descs = {
        0: "Ясно", 1: "Переважно ясно", 2: "Мінлива хмарність", 3: "Хмарно",
        45: "Туман", 48: "Паморозь",
        51: "Мряка", 53: "Мряка", 55: "Сильна мряка",
        61: "Дощ", 63: "Помірний дощ", 65: "Сильний дощ",
        71: "Сніг", 73: "Помірний сніг", 75: "Сильний сніг",
        80: "Злива", 81: "Сильна злива", 95: "Гроза", 99: "Гроза з градом",
    }
    return descs.get(code, "Змінна погода")

def weather_advice(code: int, temp: float, wind: float) -> str:
    tips = []
    if code in range(51, 68) or code in range(80, 83): tips.append("візьми парасолю ☂️")
    if code in (95, 96, 99): tips.append("краще залишись вдома, гроза ⛈")
    if code in range(71, 78): tips.append("обережно — слизько, є сніг 🌨")
    if temp < 5: tips.append("вдягнись тепло 🧣")
    elif temp < 12: tips.append("захопи куртку 🧥")
    elif temp > 28: tips.append("пий більше води 💧")
    if wind > 40: tips.append("сильний вітер 💨")
    if not tips: tips.append("чудовий день для прогулянки! 🚶")
    return ", ".join(tips).capitalize()

def build_weather_text(data: dict) -> str:
    c = data["current"]
    temp = round(c["temperature_2m"])
    feels = round(c["apparent_temperature"])
    wind = round(c["windspeed_10m"])
    humidity = round(c["relative_humidity_2m"])
    code = int(c["weathercode"])
    emoji = wmo_emoji(code)
    desc = wmo_desc(code)
    advice = weather_advice(code, temp, wind)
    return (
        f"🌍 *Погода в {WEATHER_CITY_UA} на сьогодні*\n\n"
        f"{emoji} *{desc}* · {temp}°C (відчувається {feels}°C)\n"
        f"💨 Вітер: {wind} км/год  💧 Вологість: {humidity}%\n\n"
        f"💡 _{advice}_\n\n"
        f"Гарного дня! ☀️"
    )

async def cmd_weather(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("⏳ Отримую погоду...")
    data = await fetch_weather()
    if data:
        await msg.edit_text(build_weather_text(data), parse_mode="Markdown")
    else:
        await msg.edit_text("😔 Не вдалось отримати погоду. Спробуй пізніше.")

async def scheduled_weather(context: ContextTypes.DEFAULT_TYPE):
    data = await fetch_weather()
    if data:
        await context.bot.send_message(
            chat_id=context.job.data["chat_id"],
            text=build_weather_text(data),
            parse_mode="Markdown"
        )

# ─────────────────────────────────────────────
# Івенти
# ─────────────────────────────────────────────

def make_event_id() -> int:
    global event_counter
    event_counter += 1
    return event_counter

def event_keyboard(event: dict) -> InlineKeyboardMarkup:
    eid = event["id"]
    yes_count = sum(1 for v in event["votes"].values() if v is True)
    no_count  = sum(1 for v in event["votes"].values() if v is False)
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(f"✅ Йду ({yes_count})", callback_data=f"ev_yes_{eid}"),
            InlineKeyboardButton(f"❌ Не йду ({no_count})", callback_data=f"ev_no_{eid}"),
        ],
        [InlineKeyboardButton("👥 Хто йде?", callback_data=f"ev_who_{eid}")],
    ])

def event_text(event: dict) -> str:
    day = event["day"]
    etype = EVENT_TYPES.get(event["type"], event["type"])
    title = event.get("custom_title") or etype
    author = event["author"]
    yes_list = [n for uid, (n, v) in event["votes_named"].items() if v is True]
    lines = [
        f"📣 *Новий івент від {author}*\n",
        f"{etype}",
    ]
    if event.get("custom_title"):
        lines.append(f"📝 _{event['custom_title']}_")
    lines.append(f"\n{DAY_EMOJI[day]} *День:* {DAYS[day]}")
    lines.append(f"\n✅ Йдуть: {', '.join(yes_list) if yes_list else 'поки ніхто'}")
    return "\n".join(lines)

async def cmd_event(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    keyboard = [
        [InlineKeyboardButton(label, callback_data=f"etype_{key}")]
        for key, label in EVENT_TYPES.items()
    ]
    await update.message.reply_text(
        "🎉 *Створити івент*\n\nОбери тип події:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return EVENT_TYPE

async def event_type_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    etype = query.data.replace("etype_", "")
    context.user_data["new_event_type"] = etype

    if etype == "custom":
        await query.edit_message_text("✏️ Напиши назву своєї події:")
        return EVENT_CUSTOM

    # Вибір дня
    day_buttons = [
        [InlineKeyboardButton(f"{DAY_EMOJI[i]} {DAYS[i]}", callback_data=f"eday_{i}")]
        for i in range(7)
    ]
    await query.edit_message_text(
        f"*{EVENT_TYPES[etype]}*\n\nКоли проводимо?",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(day_buttons)
    )
    return EVENT_DAY

async def event_custom_title(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["new_event_custom"] = update.message.text
    day_buttons = [
        [InlineKeyboardButton(f"{DAY_EMOJI[i]} {DAYS[i]}", callback_data=f"eday_{i}")]
        for i in range(7)
    ]
    await update.message.reply_text(
        f"📝 _{update.message.text}_\n\nКоли проводимо?",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(day_buttons)
    )
    return EVENT_DAY

async def event_day_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    day = int(query.data.replace("eday_", ""))
    user = query.from_user

    etype = context.user_data.get("new_event_type", "custom")
    custom_title = context.user_data.get("new_event_custom")

    event = {
        "id": make_event_id(),
        "type": etype,
        "custom_title": custom_title,
        "day": day,
        "author": user.first_name,
        "author_id": user.id,
        "votes": {},        # user_id -> True/False
        "votes_named": {},  # user_id -> (name, True/False)
    }
    chat_id = query.message.chat_id
    events[chat_id].append(event)

    await query.edit_message_text(
        event_text(event),
        parse_mode="Markdown",
        reply_markup=event_keyboard(event)
    )
    return ConversationHandler.END

async def event_vote_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data  # ev_yes_3 / ev_no_3 / ev_who_3

    parts = data.split("_")
    action = parts[1]
    eid = int(parts[2])
    chat_id = query.message.chat_id
    user = query.from_user

    event = next((e for e in events[chat_id] if e["id"] == eid), None)
    if not event:
        await query.answer("Івент не знайдено 😔", show_alert=True)
        return

    if action == "who":
        yes = [n for uid, (n, v) in event["votes_named"].items() if v is True]
        no  = [n for uid, (n, v) in event["votes_named"].items() if v is False]
        text = f"👥 *Хто йде на '{EVENT_TYPES.get(event['type'], event['type'])}'*\n\n"
        text += f"✅ Йдуть: {', '.join(yes) if yes else 'поки ніхто'}\n"
        text += f"❌ Не йдуть: {', '.join(no) if no else '—'}"
        await query.answer(text, show_alert=True)
        return

    vote = (action == "yes")
    event["votes"][user.id] = vote
    event["votes_named"][user.id] = (user.first_name, vote)

    try:
        await query.edit_message_text(
            event_text(event),
            parse_mode="Markdown",
            reply_markup=event_keyboard(event)
        )
    except Exception:
        pass

async def cmd_events_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    chat_events = events.get(chat_id, [])
    if not chat_events:
        await update.message.reply_text(
            "📭 Поки немає активних івентів.\n\nЗапропонуй свій — /event"
        )
        return
    await update.message.reply_text(f"📋 *Активні івенти ({len(chat_events)}):*", parse_mode="Markdown")
    for event in chat_events:
        await update.message.reply_text(
            event_text(event),
            parse_mode="Markdown",
            reply_markup=event_keyboard(event)
        )

async def cmd_clear_events(update: Update, context: ContextTypes.DEFAULT_TYPE):
    events[update.effective_chat.id] = []
    await update.message.reply_text("🗑 Список івентів очищено.")

# ─────────────────────────────────────────────
# Анкета
# ─────────────────────────────────────────────

async def anketa_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        "📋 *Заповнюємо анкету!* 5 коротких питань.\n\nЯк тебе звати? _(ім'я або нікнейм)_",
        parse_mode="Markdown"
    )
    return ANKETA_NAME

async def anketa_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["anketa_name"] = update.message.text
    await update.message.reply_text("Скільки тобі років? 🎂")
    return ANKETA_AGE

async def anketa_age(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["anketa_age"] = update.message.text
    await update.message.reply_text("Розкажи про себе — хто ти, чим займаєшся? 🧑‍💻")
    return ANKETA_ABOUT

async def anketa_about(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["anketa_about"] = update.message.text
    await update.message.reply_text("Які твої хобі або захоплення? 🎨")
    return ANKETA_HOBBY

async def anketa_hobby(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["anketa_hobby"] = update.message.text
    await update.message.reply_text("І останнє — один цікавий або несподіваний факт про тебе 😄")
    return ANKETA_FACT

async def anketa_fact(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    context.user_data["anketa_fact"] = update.message.text
    profile = {
        "name": context.user_data["anketa_name"],
        "age": context.user_data["anketa_age"],
        "about": context.user_data["anketa_about"],
        "hobby": context.user_data["anketa_hobby"],
        "fact": context.user_data["anketa_fact"],
        "username": user.username,
        "tg_name": user.first_name,
    }
    profiles[user.id] = profile
    mention = f"@{user.username}" if user.username else user.first_name
    await update.message.reply_text(
        f"✅ *Анкету збережено!*\n\n"
        f"👤 *Ім'я:* {profile['name']}\n"
        f"🎂 *Вік:* {profile['age']}\n"
        f"🧑‍💻 *Про себе:* {profile['about']}\n"
        f"🎨 *Хобі:* {profile['hobby']}\n"
        f"💡 *Факт:* {profile['fact']}\n\n"
        f"Переглянути: /profile",
        parse_mode="Markdown"
    )
    return ConversationHandler.END

async def anketa_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("❌ Анкетування скасовано.")
    return ConversationHandler.END

async def show_profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    target_user_id = None
    for entity in (update.message.entities or []):
        if entity.type == "mention":
            username = update.message.text[entity.offset+1:entity.offset+entity.length]
            for uid, p in profiles.items():
                if p.get("username", "").lower() == username.lower():
                    target_user_id = uid
                    break
            if not target_user_id:
                await update.message.reply_text(f"😔 Анкету для @{username} не знайдено.")
                return
        elif entity.type == "text_mention":
            target_user_id = entity.user.id

    if not target_user_id:
        target_user_id = update.effective_user.id

    profile = profiles.get(target_user_id)
    if not profile:
        msg = "📋 У тебе ще немає анкети! Заповни — /anketa" if target_user_id == update.effective_user.id else "😔 Ця людина ще не заповнила анкету."
        await update.message.reply_text(msg)
        return

    mention = f"@{profile['username']}" if profile.get("username") else profile["tg_name"]
    await update.message.reply_text(
        f"👤 *Анкета: {profile['name']}* ({mention})\n\n"
        f"🎂 *Вік:* {profile['age']}\n"
        f"🧑‍💻 *Про себе:* {profile['about']}\n"
        f"🎨 *Хобі:* {profile['hobby']}\n"
        f"💡 *Цікавий факт:* {profile['fact']}",
        parse_mode="Markdown"
    )

async def list_profiles(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not profiles:
        await update.message.reply_text("📭 Ще ніхто не заповнив анкету. Першим буде /anketa")
        return
    lines = ["📋 *Хто вже заповнив анкету:*\n"]
    for uid, p in profiles.items():
        mention = f"@{p['username']}" if p.get("username") else p["tg_name"]
        lines.append(f"• {p['name']} ({mention})")
    lines.append("\nНапиши /profile @username щоб переглянути")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

# ─────────────────────────────────────────────
# Збір усіх + активність
# ─────────────────────────────────────────────

async def track_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat_id = update.effective_chat.id
    if not user or user.is_bot:
        return
    if user.id not in activity[chat_id]:
        activity[chat_id][user.id] = {"name": user.first_name, "username": user.username, "count": 0}
    activity[chat_id][user.id].update({"name": user.first_name, "username": user.username})
    activity[chat_id][user.id]["count"] += 1

async def gather_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    chat_data = activity.get(chat_id, {})
    if not chat_data:
        await update.message.reply_text("😔 Список порожній. Починається рахунок з /autostart.")
        return
    mentions = []
    for uid, u in chat_data.items():
        mentions.append(f"@{u['username']}" if u.get("username") else f"[{u['name']}](tg://user?id={uid})")
    custom_text = " ".join(context.args) if context.args else "Збір! 👋"
    text = f"📢 *{custom_text}*\n\n" + " ".join(mentions) + "\n\n_Повідомлення видалиться через 1 хвилину_ 🗑"
    sent = await update.message.reply_text(text, parse_mode="Markdown")
    context.job_queue.run_once(delete_message, when=60, data={"chat_id": chat_id, "message_id": sent.message_id})
    try:
        await update.message.delete()
    except Exception:
        pass

async def delete_message(context: ContextTypes.DEFAULT_TYPE):
    try:
        await context.bot.delete_message(chat_id=context.job.data["chat_id"], message_id=context.job.data["message_id"])
    except Exception as e:
        logger.warning(f"Delete failed: {e}")

def medal(rank):
    return {1: "🥇", 2: "🥈", 3: "🥉"}.get(rank, "▪️")

async def activity_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    chat_data = activity.get(chat_id, {})
    if not chat_data:
        await update.message.reply_text("📭 Статистика порожня — запусти /autostart щоб почати рахунок.")
        return
    sorted_users = sorted(chat_data.items(), key=lambda x: x[1]["count"], reverse=True)
    total = sum(u["count"] for _, u in sorted_users)
    active = [(uid, u) for uid, u in sorted_users if u["count"] > 0]
    silent = [(uid, u) for uid, u in sorted_users if u["count"] == 0]
    lines = [f"📈 *Звіт активності*\n_(повідомлень всього: {total})_\n"]
    for rank, (uid, u) in enumerate(active, 1):
        bar_len = min(int(u["count"] / max(active[0][1]["count"], 1) * 10), 10)
        bar = "█" * bar_len + "░" * (10 - bar_len)
        pct = round(u["count"] / total * 100) if total else 0
        lines.append(f"{medal(rank)} *{u['name']}* — {u['count']} повід. ({pct}%)\n`{bar}`")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")
    if silent:
        mentions = [f"@{u['username']}" if u.get("username") else f"[{u['name']}](tg://user?id={uid})" for uid, u in silent]
        await update.message.reply_text(
            "👻 *Хто мовчить?*\n\n" + " ".join(mentions) + "\n\nАу, ви живі? 😄",
            parse_mode="Markdown"
        )

async def reset_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    activity[update.effective_chat.id] = {}
    await update.message.reply_text("🔄 Статистику скинуто!")

# ─────────────────────────────────────────────
# Команди
# ─────────────────────────────────────────────

async def random_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"❓ {random.choice(RANDOM_QUESTIONS)}")

async def discussion_topic(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(random.choice(DISCUSSION_TOPICS), parse_mode="Markdown")

async def organize(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Приклад: `/organize Похід 15 червня! Хто з нами?`", parse_mode="Markdown")
        return
    idea = " ".join(context.args)
    organizer = update.effective_user.first_name
    keyboard = [[
        InlineKeyboardButton("✅ Я в!", callback_data="org_yes"),
        InlineKeyboardButton("🤔 Може бути", callback_data="org_maybe"),
        InlineKeyboardButton("❌ Не зможу", callback_data="org_no"),
    ]]
    await update.message.reply_text(
        f"📣 *{organizer} пропонує:*\n\n_{idea}_\n\nХто йде?",
        parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def organize_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user.first_name
    r = {"org_yes": f"✅ {user} іде!", "org_maybe": f"🤔 {user} може бути", "org_no": f"❌ {user} не зможе"}.get(query.data)
    if r:
        await query.message.reply_text(r)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 *Привіт! Я ваш груповий бот-організатор!*\n\n"
        "🎉 /event — запропонувати івент\n"
        "📋 /events — список активних івентів\n"
        "🗑 /clearevents — очистити список івентів\n"
        "🌤 /weather — погода в Братиславі\n"
        "❓ /question — рандомне питання\n"
        "💬 /topic — тема для обговорення\n"
        "💡 /organize — оголосити захід (старий формат)\n"
        "📈 /report — звіт активності\n"
        "🔄 /resetstats — скинути статистику\n"
        "📢 /gather — зібрати всіх тегами\n"
        "📋 /anketa — заповнити анкету про себе\n"
        "👤 /profile — переглянути анкету\n"
        "📜 /profiles — хто заповнив анкету\n"
        "🤖 /autostart — увімкнути авто-повідомлення\n"
        "ℹ️ /help — довідка",
        parse_mode="Markdown"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start(update, context)

# ─────────────────────────────────────────────
# Автоматичні повідомлення
# ─────────────────────────────────────────────

async def scheduled_random_message(context: ContextTypes.DEFAULT_TYPE):
    now = datetime.now(KYIV_TZ)
    if now.hour < 7 or now.hour >= 22:
        return
    chat_id = context.job.data["chat_id"]
    text = f"❓ {random.choice(RANDOM_QUESTIONS)}" if random.random() < 0.5 else random.choice(DISCUSSION_TOPICS)
    await context.bot.send_message(chat_id=chat_id, text=text, parse_mode="Markdown")

async def scheduled_howwasday(context: ContextTypes.DEFAULT_TYPE):
    from telegram import Poll
    await context.bot.send_poll(
        chat_id=context.job.data["chat_id"],
        question="🌙 Як пройшов ваш день?",
        options=["🔥 Відмінно!", "😊 Добре", "😐 Нормально", "😔 Важкувато", "🤦 Краще не питай"],
        is_anonymous=False, allows_multiple_answers=False
    )

async def scheduled_monday(context: ContextTypes.DEFAULT_TYPE):
    chat_id = context.job.data["chat_id"]
    await context.bot.send_message(
        chat_id=chat_id,
        text="📅 *Новий тиждень!*\n\nЩо плануємо — пропонуй івент: /event",
        parse_mode="Markdown"
    )

async def scheduled_friday(context: ContextTypes.DEFAULT_TYPE):
    chat_id = context.job.data["chat_id"]
    await context.bot.send_message(
        chat_id=chat_id,
        text="🎉 *П'ятниця!* Є плани на вихідні?\n\nЗапропонуй івент: /event\nАбо переглянь існуючі: /events",
        parse_mode="Markdown"
    )

async def scheduled_weekly_report(context: ContextTypes.DEFAULT_TYPE):
    chat_id = context.job.data["chat_id"]
    chat_data = activity.get(chat_id, {})
    if not chat_data:
        return
    sorted_users = sorted(chat_data.items(), key=lambda x: x[1]["count"], reverse=True)
    total = sum(u["count"] for _, u in sorted_users)
    active = [(uid, u) for uid, u in sorted_users if u["count"] > 0]
    silent = [(uid, u) for uid, u in sorted_users if u["count"] == 0]
    lines = [f"📈 *Тижневий звіт*\n_(повідомлень: {total})_\n"]
    for rank, (uid, u) in enumerate(active, 1):
        bar_len = min(int(u["count"] / max(active[0][1]["count"], 1) * 10), 10) if active else 0
        lines.append(f"{medal(rank)} *{u['name']}* — {u['count']} повід.\n`{'█'*bar_len+'░'*(10-bar_len)}`")
    await context.bot.send_message(chat_id=chat_id, text="\n".join(lines), parse_mode="Markdown")
    if silent:
        mentions = [f"@{u['username']}" if u.get("username") else f"[{u['name']}](tg://user?id={uid})" for uid, u in silent]
        await context.bot.send_message(chat_id=chat_id,
            text="👻 *Мовчуни тижня:*\n\n" + " ".join(mentions) + "\n\nЯк справи? 💙",
            parse_mode="Markdown")
    for uid in activity[chat_id]:
        activity[chat_id][uid]["count"] = 0

async def setup_jobs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    jq = context.job_queue
    for name in [str(chat_id), f"{chat_id}_friday", f"{chat_id}_evening",
                 f"{chat_id}_monday", f"{chat_id}_report", f"{chat_id}_weather"]:
        for job in jq.get_jobs_by_name(name):
            job.schedule_removal()

    jq.run_repeating(scheduled_random_message, interval=5*3600, first=60,
                     data={"chat_id": chat_id}, name=str(chat_id))
    jq.run_daily(scheduled_weather, time=time(8, 0, tzinfo=KYIV_TZ),
                 days=tuple(range(7)), data={"chat_id": chat_id}, name=f"{chat_id}_weather")
    jq.run_daily(scheduled_friday, time=time(10, 0, tzinfo=KYIV_TZ),
                 days=(4,), data={"chat_id": chat_id}, name=f"{chat_id}_friday")
    jq.run_daily(scheduled_howwasday, time=time(21, 0, tzinfo=KYIV_TZ),
                 days=tuple(range(7)), data={"chat_id": chat_id}, name=f"{chat_id}_evening")
    jq.run_daily(scheduled_monday, time=time(10, 0, tzinfo=KYIV_TZ),
                 days=(0,), data={"chat_id": chat_id}, name=f"{chat_id}_monday")
    jq.run_daily(scheduled_weekly_report, time=time(20, 0, tzinfo=KYIV_TZ),
                 days=(6,), data={"chat_id": chat_id}, name=f"{chat_id}_report")

    await update.message.reply_text(
        "✅ *Автоматичні повідомлення увімкнено!*\n\n"
        "🌤 08:00 — погода в Братиславі\n"
        "📅 Понеділок 10:00 — нагадування запропонувати івент\n"
        "🎉 П'ятниця 10:00 — плани на вихідні\n"
        "🌙 Щодня 21:00 — як пройшов день\n"
        "📈 Неділя 20:00 — тижневий звіт\n"
        "❓ Кожні ~5 год (7–22) — рандомне питання",
        parse_mode="Markdown"
    )

# ─────────────────────────────────────────────
# Запуск
# ─────────────────────────────────────────────

def main():
    import os
    TOKEN = os.environ.get("BOT_TOKEN")
    if not TOKEN:
        raise ValueError("Встановіть змінну середовища BOT_TOKEN!")

    app = Application.builder().token(TOKEN).build()

    # Трекер
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, track_message), group=0)

    # Анкета
    app.add_handler(ConversationHandler(
        entry_points=[CommandHandler("anketa", anketa_start)],
        states={
            ANKETA_NAME:  [MessageHandler(filters.TEXT & ~filters.COMMAND, anketa_name)],
            ANKETA_AGE:   [MessageHandler(filters.TEXT & ~filters.COMMAND, anketa_age)],
            ANKETA_ABOUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, anketa_about)],
            ANKETA_HOBBY: [MessageHandler(filters.TEXT & ~filters.COMMAND, anketa_hobby)],
            ANKETA_FACT:  [MessageHandler(filters.TEXT & ~filters.COMMAND, anketa_fact)],
        },
        fallbacks=[CommandHandler("cancel", anketa_cancel)],
    ))

    # Івент
    app.add_handler(ConversationHandler(
        entry_points=[CommandHandler("event", cmd_event)],
        states={
            EVENT_TYPE:   [CallbackQueryHandler(event_type_chosen, pattern="^etype_")],
            EVENT_CUSTOM: [MessageHandler(filters.TEXT & ~filters.COMMAND, event_custom_title)],
            EVENT_DAY:    [CallbackQueryHandler(event_day_chosen, pattern="^eday_")],
        },
        fallbacks=[CommandHandler("cancel", anketa_cancel)],
    ))

    app.add_handler(CallbackQueryHandler(event_vote_callback, pattern="^ev_"))
    app.add_handler(CallbackQueryHandler(organize_callback, pattern="^org_"))

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("weather", cmd_weather))
    app.add_handler(CommandHandler("question", random_question))
    app.add_handler(CommandHandler("topic", discussion_topic))
    app.add_handler(CommandHandler("organize", organize))
    app.add_handler(CommandHandler("report", activity_report))
    app.add_handler(CommandHandler("resetstats", reset_stats))
    app.add_handler(CommandHandler("gather", gather_all))
    app.add_handler(CommandHandler("events", cmd_events_list))
    app.add_handler(CommandHandler("clearevents", cmd_clear_events))
    app.add_handler(CommandHandler("profile", show_profile))
    app.add_handler(CommandHandler("profiles", list_profiles))
    app.add_handler(CommandHandler("autostart", setup_jobs))

    logger.info("Бот запущено!")
    app.run_polling()

if __name__ == "__main__":
    main()
