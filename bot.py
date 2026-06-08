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

# Стани для анкети
ANKETA_NAME, ANKETA_AGE, ANKETA_ABOUT, ANKETA_HOBBY, ANKETA_FACT = range(5)

# ─────────────────────────────────────────────
# Сховища даних (в пам'яті)
# ─────────────────────────────────────────────
activity: dict[int, dict[int, dict]] = defaultdict(dict)
profiles: dict[int, dict] = {}   # user_id -> profile dict

# ─────────────────────────────────────────────
# Питання (нестандартні)
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

ACTIVITY_POLL_OPTIONS = {
    "weekend": {"question": "🗓 Що плануєте на ці вихідні?", "options": ["Настільні ігри 🎲", "Похід/прогулянка 🥾", "Кафе/ресторан ☕", "Кіно/серіали 🎬", "Нічого конкретного 😴", "Щось інше (пишіть в чат!)"], "multiple": True},
    "boardgames": {"question": "🎲 Хто готовий зіграти в настільні ігри найближчим часом?", "options": ["Так, цього тижня! 🙌", "Так, наступного тижня", "Можливо, залежить від часу", "Поки не можу 😔"], "multiple": False},
    "hike": {"question": "🥾 Хто хотів би сходити в похід?", "options": ["Я в! 💪", "Залежить від маршруту", "Залежить від дати", "Не моє, але бажаю удачі 😄"], "multiple": False},
    "cafe": {"question": "☕ Хто за зустріч у кафе?", "options": ["Я! ☕", "Можливо", "Цього разу не зможу"], "multiple": False},
    "howwasday": {"question": "🌙 Як пройшов ваш день?", "options": ["🔥 Відмінно!", "😊 Добре", "😐 Нормально", "😔 Важкувато", "🤦 Краще не питай"], "multiple": False},
    "monday": {"question": "📅 Куди збираємось компанією цього тижня?", "options": ["Настільні ігри 🎲", "Похід/прогулянка 🥾", "Кафе/бар ☕", "Кіно 🎬", "Квест або інша активність 🎯", "Онлайн-вечір 💻", "Поки нікуди 😴"], "multiple": True},
}

# ─────────────────────────────────────────────
# Погода
# ─────────────────────────────────────────────

async def fetch_weather() -> dict | None:
    url = f"https://wttr.in/{WEATHER_CITY}?format=j1"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status == 200:
                    return await resp.json()
    except Exception as e:
        logger.error(f"Weather fetch error: {e}")
    return None

def weather_emoji(code: int) -> str:
    if code in (113,): return "☀️"
    if code in (116,): return "🌤"
    if code in (119, 122): return "☁️"
    if code in (143, 248, 260): return "🌫"
    if code in (176, 179, 182, 185, 263, 266, 281, 284, 293, 296, 299, 302, 305, 308, 311, 314, 317, 320, 323, 326, 329, 332, 335, 338, 350, 353, 356, 359, 362, 365, 368, 371, 374, 377): return "🌧"
    if code in (200, 386, 389, 392, 395): return "⛈"
    return "🌡"

def weather_advice(code: int, temp: int, wind: int) -> str:
    advices = []
    if code in (176, 263, 266, 293, 296, 299, 302, 305, 308, 353, 356, 359):
        advices.append("не забудь парасолю ☂️")
    if code in (200, 386, 389):
        advices.append("краще залишитись вдома під час грози ⛈")
    if code in (179, 323, 326, 329, 332, 335, 338, 368, 371):
        advices.append("одягни тепліше, очікується сніг 🌨")
    if temp < 5:
        advices.append("добре вкутайся, на вулиці холодно 🧣")
    elif temp < 12:
        advices.append("захопи куртку 🧥")
    elif temp > 28:
        advices.append("пий більше води і ховайся в тінь 🌊")
    if wind > 40:
        advices.append("сильний вітер — тримай капелюха! 💨")
    if not advices:
        advices.append("чудовий день для прогулянки! 🚶")
    return ", ".join(advices).capitalize()

def build_weather_text(data: dict) -> str:
    current = data["current_condition"][0]
    temp = int(current["temp_C"])
    feels = int(current["FeelsLikeC"])
    wind = int(current["windspeedKmph"])
    humidity = int(current["humidity"])
    desc_code = int(current["weatherCode"])
    emoji = weather_emoji(desc_code)
    advice = weather_advice(desc_code, temp, wind)

    return (
        f"🌍 *Погода в {WEATHER_CITY_UA} на сьогодні*\n\n"
        f"{emoji} *{temp}°C* (відчувається як {feels}°C)\n"
        f"💨 Вітер: {wind} км/год\n"
        f"💧 Вологість: {humidity}%\n\n"
        f"💡 _{advice}_\n\n"
        f"Гарного дня! ☀️"
    )

async def cmd_weather(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⏳ Отримую погоду...")
    data = await fetch_weather()
    if data:
        await update.message.reply_text(build_weather_text(data), parse_mode="Markdown")
    else:
        await update.message.reply_text("😔 Не вдалось отримати погоду. Спробуй пізніше.")

async def scheduled_weather(context: ContextTypes.DEFAULT_TYPE):
    data = await fetch_weather()
    if not data:
        return
    text = build_weather_text(data)
    await context.bot.send_message(chat_id=context.job.data["chat_id"], text=text, parse_mode="Markdown")

# ─────────────────────────────────────────────
# Анкета (ConversationHandler)
# ─────────────────────────────────────────────

async def anketa_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        "📋 *Заповнюємо анкету!* Я задам 5 коротких питань.\n\n"
        "Як тебе звати? _(ім'я або нікнейм)_",
        parse_mode="Markdown"
    )
    return ANKETA_NAME

async def anketa_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["anketa_name"] = update.message.text
    await update.message.reply_text("Скільки тобі років? 🎂")
    return ANKETA_AGE

async def anketa_age(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["anketa_age"] = update.message.text
    await update.message.reply_text("Розкажи про себе кількома словами — хто ти, чим займаєшся? 🧑‍💻")
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

    text = (
        f"✅ *Анкету збережено!* Ось як вона виглядає:\n\n"
        f"👤 *Ім'я:* {profile['name']}\n"
        f"🎂 *Вік:* {profile['age']}\n"
        f"🧑‍💻 *Про себе:* {profile['about']}\n"
        f"🎨 *Хобі:* {profile['hobby']}\n"
        f"💡 *Факт:* {profile['fact']}\n\n"
        f"Тепер будь-хто може переглянути твою анкету командою /profile @{user.username or user.first_name}"
    )
    await update.message.reply_text(text, parse_mode="Markdown")
    return ConversationHandler.END

async def anketa_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("❌ Анкетування скасовано.")
    return ConversationHandler.END

async def show_profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показати анкету: /profile або /profile @username"""
    # Перевірити чи є mention в повідомленні
    target_user_id = None
    target_name = None

    entities = update.message.entities or []
    for entity in entities:
        if entity.type == "mention":
            username = update.message.text[entity.offset+1:entity.offset+entity.length]
            # Шукаємо по username
            for uid, p in profiles.items():
                if p.get("username") and p["username"].lower() == username.lower():
                    target_user_id = uid
                    break
            if not target_user_id:
                await update.message.reply_text(f"😔 Анкету для @{username} не знайдено. Може вони ще не заповнили?")
                return
        elif entity.type == "text_mention":
            target_user_id = entity.user.id

    # Якщо немає mention — показати свою анкету
    if not target_user_id:
        target_user_id = update.effective_user.id

    profile = profiles.get(target_user_id)
    if not profile:
        if target_user_id == update.effective_user.id:
            await update.message.reply_text(
                "📋 У тебе ще немає анкети! Заповни її командою /anketa"
            )
        else:
            await update.message.reply_text("😔 Ця людина ще не заповнила анкету.")
        return

    mention = f"@{profile['username']}" if profile.get("username") else profile["tg_name"]
    text = (
        f"👤 *Анкета: {profile['name']}* ({mention})\n\n"
        f"🎂 *Вік:* {profile['age']}\n"
        f"🧑‍💻 *Про себе:* {profile['about']}\n"
        f"🎨 *Хобі:* {profile['hobby']}\n"
        f"💡 *Цікавий факт:* {profile['fact']}"
    )
    await update.message.reply_text(text, parse_mode="Markdown")

async def list_profiles(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Список всіх хто заповнив анкету."""
    if not profiles:
        await update.message.reply_text("📭 Ще ніхто не заповнив анкету. Будь першим — /anketa")
        return
    lines = ["📋 *Хто вже заповнив анкету:*\n"]
    for uid, p in profiles.items():
        mention = f"@{p['username']}" if p.get("username") else p["tg_name"]
        lines.append(f"• {p['name']} ({mention}) — /profile @{p.get('username', p['tg_name'])}")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

# ─────────────────────────────────────────────
# Збір усіх (тег + автовидалення)
# ─────────────────────────────────────────────

async def gather_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Тегає всіх учасників з активності і видаляє через 1 хв."""
    chat_id = update.effective_chat.id
    chat_data = activity.get(chat_id, {})

    if not chat_data:
        await update.message.reply_text(
            "😔 Поки нікого немає в списку. Активність рахується з моменту /autostart."
        )
        return

    mentions = []
    for uid, u in chat_data.items():
        if u.get("username"):
            mentions.append(f"@{u['username']}")
        else:
            mentions.append(f"[{u['name']}](tg://user?id={uid})")

    custom_text = " ".join(context.args) if context.args else "Збір! 👋"

    text = (
        f"📢 *{custom_text}*\n\n"
        + " ".join(mentions)
        + "\n\n_Це повідомлення видалиться через 1 хвилину_ 🗑"
    )

    sent = await update.message.reply_text(text, parse_mode="Markdown")

    # Видалити через 60 секунд
    context.job_queue.run_once(
        delete_message,
        when=60,
        data={"chat_id": chat_id, "message_id": sent.message_id},
    )
    # Видалити також команду /gather
    try:
        await update.message.delete()
    except Exception:
        pass

async def delete_message(context: ContextTypes.DEFAULT_TYPE):
    try:
        await context.bot.delete_message(
            chat_id=context.job.data["chat_id"],
            message_id=context.job.data["message_id"]
        )
    except Exception as e:
        logger.warning(f"Could not delete message: {e}")

# ─────────────────────────────────────────────
# Допоміжні
# ─────────────────────────────────────────────

async def send_poll(bot, chat_id, key):
    data = ACTIVITY_POLL_OPTIONS[key]
    await bot.send_poll(chat_id=chat_id, question=data["question"], options=data["options"],
                        is_anonymous=False, allows_multiple_answers=data["multiple"])

def medal(rank):
    return {1: "🥇", 2: "🥈", 3: "🥉"}.get(rank, "▪️")

async def track_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat_id = update.effective_chat.id
    if not user or user.is_bot:
        return
    if user.id not in activity[chat_id]:
        activity[chat_id][user.id] = {"name": user.first_name, "username": user.username, "count": 0}
    activity[chat_id][user.id]["name"] = user.first_name
    activity[chat_id][user.id]["username"] = user.username
    activity[chat_id][user.id]["count"] += 1

# ─────────────────────────────────────────────
# Команди
# ─────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "👋 *Привіт! Я ваш груповий бот-організатор!*\n\n"
        "📊 /poll — вихідні\n"
        "🎲 /boardgames — настільні ігри\n"
        "🥾 /hike — похід\n"
        "☕ /cafe — кафе\n"
        "🌙 /howwasday — як пройшов день\n"
        "📅 /weekplan — плани на тиждень\n"
        "🌤 /weather — погода в Братиславі\n"
        "💡 /organize — оголосити захід\n"
        "❓ /question — рандомне питання\n"
        "💬 /topic — тема для обговорення\n"
        "📈 /report — звіт активності\n"
        "🔄 /resetstats — скинути статистику\n"
        "📋 /anketa — заповнити анкету про себе\n"
        "👤 /profile — переглянути анкету (/profile @username)\n"
        "📜 /profiles — хто заповнив анкету\n"
        "📢 /gather — зібрати всіх тегами (видається через 1 хв)\n"
        "🤖 /autostart — увімкнути авто-повідомлення\n"
        "ℹ️ /help — довідка"
    )
    await update.message.reply_text(text, parse_mode="Markdown")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start(update, context)

async def poll_weekend(update, context): await send_poll(context.bot, update.effective_chat.id, "weekend")
async def poll_boardgames(update, context): await send_poll(context.bot, update.effective_chat.id, "boardgames")
async def poll_hike(update, context): await send_poll(context.bot, update.effective_chat.id, "hike")
async def poll_cafe(update, context): await send_poll(context.bot, update.effective_chat.id, "cafe")
async def poll_howwasday(update, context): await send_poll(context.bot, update.effective_chat.id, "howwasday")
async def poll_weekplan(update, context): await send_poll(context.bot, update.effective_chat.id, "monday")

async def activity_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    chat_data = activity.get(chat_id, {})
    if not chat_data:
        await update.message.reply_text("📭 Статистика порожня — напиши /autostart щоб почати рахунок.")
        return
    sorted_users = sorted(chat_data.items(), key=lambda x: x[1]["count"], reverse=True)
    total = sum(u["count"] for _, u in sorted_users)
    active = [(uid, u) for uid, u in sorted_users if u["count"] > 0]
    silent = [(uid, u) for uid, u in sorted_users if u["count"] == 0]
    lines = [f"📈 *Звіт активності групи*\n_(всього повідомлень: {total})_\n"]
    for rank, (uid, u) in enumerate(active, 1):
        bar_len = min(int(u["count"] / max(active[0][1]["count"], 1) * 10), 10)
        bar = "█" * bar_len + "░" * (10 - bar_len)
        pct = round(u["count"] / total * 100) if total else 0
        lines.append(f"{medal(rank)} *{u['name']}* — {u['count']} повід. ({pct}%)\n`{bar}`")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")
    if silent:
        mentions = [f"@{u['username']}" if u.get("username") else f"[{u['name']}](tg://user?id={uid})" for uid, u in silent]
        await update.message.reply_text(
            "👻 *Хто там мовчить?*\n\n" + " ".join(mentions) + "\n\nАу, ви живі? 😄 Як справи?",
            parse_mode="Markdown"
        )

async def reset_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    activity[update.effective_chat.id] = {}
    await update.message.reply_text("🔄 Статистика скинута!")

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
    responses = {"org_yes": f"✅ {user} іде!", "org_maybe": f"🤔 {user} може бути", "org_no": f"❌ {user} не зможе"}
    if r := responses.get(query.data):
        await query.message.reply_text(r)

async def random_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"❓ {random.choice(RANDOM_QUESTIONS)}")

async def discussion_topic(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(random.choice(DISCUSSION_TOPICS), parse_mode="Markdown")

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

async def scheduled_weekend_poll(context): await send_poll(context.bot, context.job.data["chat_id"], "weekend")
async def scheduled_howwasday_poll(context): await send_poll(context.bot, context.job.data["chat_id"], "howwasday")
async def scheduled_monday_poll(context): await send_poll(context.bot, context.job.data["chat_id"], "monday")

async def scheduled_weekly_report(context: ContextTypes.DEFAULT_TYPE):
    chat_id = context.job.data["chat_id"]
    chat_data = activity.get(chat_id, {})
    if not chat_data:
        return
    sorted_users = sorted(chat_data.items(), key=lambda x: x[1]["count"], reverse=True)
    total = sum(u["count"] for _, u in sorted_users)
    active = [(uid, u) for uid, u in sorted_users if u["count"] > 0]
    silent = [(uid, u) for uid, u in sorted_users if u["count"] == 0]
    lines = [f"📈 *Тижневий звіт активності*\n_(повідомлень за тиждень: {total})_\n"]
    for rank, (uid, u) in enumerate(active, 1):
        bar_len = min(int(u["count"] / max(active[0][1]["count"], 1) * 10), 10) if active else 0
        bar = "█" * bar_len + "░" * (10 - bar_len)
        pct = round(u["count"] / total * 100) if total else 0
        lines.append(f"{medal(rank)} *{u['name']}* — {u['count']} повід. ({pct}%)\n`{bar}`")
    await context.bot.send_message(chat_id=chat_id, text="\n".join(lines), parse_mode="Markdown")
    if silent:
        mentions = [f"@{u['username']}" if u.get("username") else f"[{u['name']}](tg://user?id={uid})" for uid, u in silent]
        await context.bot.send_message(chat_id=chat_id,
            text="👻 *Хто мовчав цього тижня?*\n\n" + " ".join(mentions) + "\n\nАу! Як справи? 💙",
            parse_mode="Markdown")
    for uid in activity[chat_id]:
        activity[chat_id][uid]["count"] = 0

async def setup_jobs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    jq = context.job_queue
    for name in [str(chat_id), f"{chat_id}_friday", f"{chat_id}_evening", f"{chat_id}_monday", f"{chat_id}_report", f"{chat_id}_weather"]:
        for job in jq.get_jobs_by_name(name):
            job.schedule_removal()

    jq.run_repeating(scheduled_random_message, interval=5*3600, first=60, data={"chat_id": chat_id}, name=str(chat_id))
    jq.run_daily(scheduled_weekend_poll, time=time(10, 0, tzinfo=KYIV_TZ), days=(4,), data={"chat_id": chat_id}, name=f"{chat_id}_friday")
    jq.run_daily(scheduled_howwasday_poll, time=time(21, 0, tzinfo=KYIV_TZ), days=tuple(range(7)), data={"chat_id": chat_id}, name=f"{chat_id}_evening")
    jq.run_daily(scheduled_monday_poll, time=time(10, 0, tzinfo=KYIV_TZ), days=(0,), data={"chat_id": chat_id}, name=f"{chat_id}_monday")
    jq.run_daily(scheduled_weekly_report, time=time(20, 0, tzinfo=KYIV_TZ), days=(6,), data={"chat_id": chat_id}, name=f"{chat_id}_report")
    jq.run_daily(scheduled_weather, time=time(8, 0, tzinfo=KYIV_TZ), days=tuple(range(7)), data={"chat_id": chat_id}, name=f"{chat_id}_weather")

    await update.message.reply_text(
        "✅ *Автоматичні повідомлення увімкнено!*\n\n"
        "🌤 08:00 — погода в Братиславі\n"
        "📅 Понеділок 10:00 — куди йдемо?\n"
        "🗓 П'ятниця 10:00 — плани на вихідні\n"
        "🌙 Щодня 21:00 — як пройшов день\n"
        "📈 Неділя 20:00 — тижневий звіт\n"
        "❓ Кожні ~5 год (7:00–22:00) — рандомне питання",
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

    # Трекер повідомлень
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, track_message), group=0)

    # Анкета (ConversationHandler)
    anketa_handler = ConversationHandler(
        entry_points=[CommandHandler("anketa", anketa_start)],
        states={
            ANKETA_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, anketa_name)],
            ANKETA_AGE:  [MessageHandler(filters.TEXT & ~filters.COMMAND, anketa_age)],
            ANKETA_ABOUT:[MessageHandler(filters.TEXT & ~filters.COMMAND, anketa_about)],
            ANKETA_HOBBY:[MessageHandler(filters.TEXT & ~filters.COMMAND, anketa_hobby)],
            ANKETA_FACT: [MessageHandler(filters.TEXT & ~filters.COMMAND, anketa_fact)],
        },
        fallbacks=[CommandHandler("cancel", anketa_cancel)],
    )
    app.add_handler(anketa_handler)

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("poll", poll_weekend))
    app.add_handler(CommandHandler("boardgames", poll_boardgames))
    app.add_handler(CommandHandler("hike", poll_hike))
    app.add_handler(CommandHandler("cafe", poll_cafe))
    app.add_handler(CommandHandler("howwasday", poll_howwasday))
    app.add_handler(CommandHandler("weekplan", poll_weekplan))
    app.add_handler(CommandHandler("weather", cmd_weather))
    app.add_handler(CommandHandler("organize", organize))
    app.add_handler(CommandHandler("question", random_question))
    app.add_handler(CommandHandler("topic", discussion_topic))
    app.add_handler(CommandHandler("report", activity_report))
    app.add_handler(CommandHandler("resetstats", reset_stats))
    app.add_handler(CommandHandler("profile", show_profile))
    app.add_handler(CommandHandler("profiles", list_profiles))
    app.add_handler(CommandHandler("gather", gather_all))
    app.add_handler(CommandHandler("autostart", setup_jobs))
    app.add_handler(CallbackQueryHandler(organize_callback, pattern="^org_"))

    logger.info("Бот запущено!")
    app.run_polling()

if __name__ == "__main__":
    main()
