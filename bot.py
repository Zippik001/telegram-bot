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
WEATHER_LAT = "48.1486"
WEATHER_LON = "17.1077"
WEATHER_CITY_UA = "Братислава"

# ── Стани ConversationHandler ──
ANKETA_TEXT = 0
EVENT_AWAITING_CUSTOM = 10

# ── Сховища ──
activity: dict[int, dict[int, dict]] = defaultdict(dict)
profiles: dict[int, dict] = {}
events: dict[int, list] = defaultdict(list)
_event_counter = 0

# ─────────────────────────────────────────────
# Контент — питання
# ─────────────────────────────────────────────
RANDOM_QUESTIONS = [
    "🍑 Якби частини тіла могли голосувати на виборах — яка б перемогла і яку б обіцяла програму?",
    "🎪 Ви коли-небудь робили щось настільки кринжове, що досі прокидаєтесь о 3 ночі від цього спогаду?",
    "🧠 Якби ваш внутрішній монолог транслювався вголос останні 10 хвилин — скільки людей би встали і пішли?",
    "🍷 Що ви робите коли п'яні і думаєте що виглядаєте круто — але насправді ні?",
    "😈 Яка ваша найбільш морально сумнівна харчова звичка? Їжа з підлоги рахується.",
    "🎭 Якби ваше сексуальне життя було жанром кіно — що це було б? Трилер? Комедія? Документалка про дикий захід?",
    "🚿 Які монологи ви виголошуєте в душі — і кому вони адресовані?",
    "🤡 Яка найбезглуздіша річ через яку ви реально посварились з людиною?",
    "💀 Якщо чесно — яка ваша найбільш некрофільна звичка? (Netflix до 4 ранку рахується)",
    "🐒 Якби еволюція пішла інакше і люди лишились мавпами — які соцмережі були б у мавп?",
    "🔞 Яка ваша найдивніша фантазія яку ви б ніколи не реалізували — і слава богу?",
    "🎲 Якби за кожен раз коли ви кажете «я вже йду» і не йдете — платили штраф, скільки б ви вже заборгували?",
    "🍕 Є їжа яку ви їсте тільки наодинці бо соромно? Розкажіть. Тут всі свої.",
    "💘 Яку найдурнішу річ ви зробили заради того щоб сподобатись комусь?",
    "🧟 О котрій годині ви перетворюєтесь з людини на щось страшніше — і що саме?",
    "🎵 Яка пісня є вашою guilty pleasure яку ви слухаєте тільки в навушниках щоб ніхто не бачив?",
    "🏆 Яке ваше найбільше досягнення яке не можна вписати в резюме але ви ним гордитесь?",
    "👻 Яка ситуація змушує вас хотіти буквально зникнути крізь землю?",
    "🦆 Якби вас можна було описати одним твариною в стані стресу — яка б це була і чому?",
    "😏 Яка ваша найкраща відмазка якій ви самі вже не вірите але продовжуєте використовувати?",
    "🔥 Якби ваше тіло виставляло рахунки за все що ви з ним робите — яка б стаття витрат була найбільшою?",
    "🤫 Є щось що всі у вашому оточенні роблять і вважають нормальним — а ви таємно думаєте що це дико?",
    "💤 Яка ваша найдивніша звичка перед сном яку ви б не зізнались нікому тверезому?",
    "🎬 Якби знімали фільм про ваш найбільш незручний момент у житті — який рейтинг би він отримав і чому?",
    "🧃 Яка дитяча звичка у вас досі є — і не треба соромитись, тут ніхто не ідеальний?",
]

DISCUSSION_TOPICS = [
    "🗣 *Тема:* Є місця в Братиславі де час ніби зупиняється. Де у вас таке місце?",
    "🗣 *Тема:* Дорослі стосунки — чому з віком знайти справжніх друзів стає складніше?",
    "🗣 *Тема:* Настільні ігри — це діагностика характеру чи просто гра? Що ви дізнались про людей?",
    "🗣 *Тема:* Ідеальний вечір з компанією — що має бути обов'язково і чого не має бути взагалі?",
    "🗣 *Тема:* Похід у гори — у кого вже є травма і хто готовий повторити?",
    "🗣 *Тема:* Є щось в Братиславі що вас щиро дивує — добре чи погано?",
    "🗣 *Тема:* Red flag або green flag — що одразу говорить вам все про людину?",
    "🗣 *Тема:* Найкращий спосіб відпочити після важкого тижня — у кожного свій, розкажіть.",
]

EVENT_TYPES = {
    "boardgames": "🎲 Настільні ігри",
    "hike":       "🥾 Похід / прогулянка",
    "cafe":       "☕ Кафе / бар",
    "cinema":     "🎬 Кіно",
    "quest":      "🎯 Квест / активність",
    "online":     "💻 Онлайн-вечір",
    "custom":     "✏️ Своя ідея",
}

DAYS = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Нд"]
DAY_EMOJI = ["📅", "📅", "📅", "📅", "🎉", "🎉", "😴"]

# ─────────────────────────────────────────────
# Погода
# ─────────────────────────────────────────────

async def fetch_weather() -> dict | None:
    url = (
        f"https://api.open-meteo.com/v1/forecast"
        f"?latitude={WEATHER_LAT}&longitude={WEATHER_LON}"
        f"&current=temperature_2m,apparent_temperature,weathercode,windspeed_10m,relative_humidity_2m"
        f"&timezone=Europe%2FBratislava"
    )
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(url, timeout=aiohttp.ClientTimeout(total=10)) as r:
                if r.status == 200:
                    return await r.json()
    except Exception as e:
        logger.error(f"Weather error: {e}")
    return None

def wmo_emoji(code):
    if code == 0: return "☀️"
    if code in (1, 2): return "🌤"
    if code == 3: return "☁️"
    if code in (45, 48): return "🌫"
    if 51 <= code <= 67: return "🌧"
    if 71 <= code <= 77: return "🌨"
    if 80 <= code <= 82: return "🌦"
    if code in (95, 96, 99): return "⛈"
    return "🌡"

def wmo_desc(code):
    return {0:"Ясно",1:"Переважно ясно",2:"Мінлива хмарність",3:"Хмарно",
            45:"Туман",48:"Паморозь",51:"Мряка",61:"Дощ",63:"Помірний дощ",
            65:"Сильний дощ",71:"Сніг",80:"Злива",95:"Гроза"}.get(code, "Змінна погода")

def weather_advice(code, temp, wind):
    tips = []
    if 51 <= code <= 67 or 80 <= code <= 82: tips.append("візьми парасолю ☂️")
    if code in (95, 96, 99): tips.append("краще залишись вдома, гроза ⛈")
    if 71 <= code <= 77: tips.append("є сніг — обережно на дорозі 🌨")
    if temp < 5: tips.append("вдягнись тепло 🧣")
    elif temp < 12: tips.append("захопи куртку 🧥")
    elif temp > 28: tips.append("пий більше води 💧")
    if wind > 40: tips.append("сильний вітер 💨")
    if not tips: tips.append("чудовий день для прогулянки 🚶")
    return tips[0].capitalize()

def build_weather_text(data):
    c = data["current"]
    temp = round(c["temperature_2m"])
    feels = round(c["apparent_temperature"])
    wind = round(c["windspeed_10m"])
    humidity = round(c["relative_humidity_2m"])
    code = int(c["weathercode"])
    return (
        f"🌍 *Погода в {WEATHER_CITY_UA}*\n\n"
        f"{wmo_emoji(code)} *{wmo_desc(code)}* · {temp}°C (відчувається {feels}°C)\n"
        f"💨 Вітер: {wind} км/год  💧 Вологість: {humidity}%\n\n"
        f"💡 _{weather_advice(code, temp, wind)}_\n\n"
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
        await context.bot.send_message(context.job.data["chat_id"], build_weather_text(data), parse_mode="Markdown")

# ─────────────────────────────────────────────
# Івенти — без ConversationHandler (inline кнопки)
# ─────────────────────────────────────────────

def new_event_id():
    global _event_counter
    _event_counter += 1
    return _event_counter

def event_card_text(ev):
    etype = EVENT_TYPES.get(ev["type"], ev["type"])
    day_str = f"{DAY_EMOJI[ev['day']]} {DAYS[ev['day']]}"
    yes_names = [name for uid, (name, v) in ev["votes_named"].items() if v]
    return (
        f"🎉 *Івент від {ev['author']}*\n\n"
        f"{'📝 ' + ev['custom_title'] if ev.get('custom_title') else etype}\n"
        f"{'_' + etype + '_' if ev.get('custom_title') else ''}\n"
        f"{day_str}\n\n"
        f"✅ Йдуть: {', '.join(yes_names) if yes_names else 'поки ніхто'}"
    ).replace("\n\n\n", "\n\n")

def event_card_kb(ev):
    eid = ev["id"]
    yes_c = sum(1 for _, v in ev["votes"].values() if v)
    no_c  = sum(1 for _, v in ev["votes"].values() if not v)
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(f"✅ Йду ({yes_c})",    callback_data=f"ev_yes_{eid}"),
            InlineKeyboardButton(f"❌ Не йду ({no_c})", callback_data=f"ev_no_{eid}"),
        ],
        [InlineKeyboardButton("👥 Хто йде?", callback_data=f"ev_who_{eid}")],
    ])

async def cmd_event(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показати кнопки вибору типу події."""
    rows = [[InlineKeyboardButton(label, callback_data=f"etype_{key}")] for key, label in EVENT_TYPES.items()]
    await update.message.reply_text(
        "🎉 *Створити івент*\n\nОбери тип події:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(rows)
    )

async def cb_event_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Крок 1 — обрано тип, показуємо дні тижня."""
    q = update.callback_query
    await q.answer()
    etype = q.data[len("etype_"):]

    # Зберігаємо стан у bot_data щоб не залежати від ConversationHandler
    key = f"ev_pending_{q.from_user.id}_{q.message.chat_id}"
    context.bot_data[key] = {"type": etype, "msg_id": q.message.message_id}

    if etype == "custom":
        await q.edit_message_text(
            "✏️ Напиши назву своєї події у відповідь на це повідомлення:\n_(або /cancel щоб скасувати)_",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Скасувати", callback_data="ev_cancel")]])
        )
        return

    day_rows = [[InlineKeyboardButton(f"{DAY_EMOJI[i]} {DAYS[i]}", callback_data=f"eday_{etype}_{i}")] for i in range(7)]
    day_rows.append([InlineKeyboardButton("❌ Скасувати", callback_data="ev_cancel")])
    await q.edit_message_text(
        f"*{EVENT_TYPES[etype]}*\n\nКоли проводимо?",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(day_rows)
    )

async def cb_event_day(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Крок 2 — обрано день, створюємо івент."""
    q = update.callback_query
    await q.answer()
    parts = q.data.split("_")  # eday_boardgames_3
    etype = parts[1]
    day = int(parts[2])

    key = f"ev_pending_{q.from_user.id}_{q.message.chat_id}"
    pending = context.bot_data.pop(key, {})
    custom_title = pending.get("custom_title")

    ev = {
        "id": new_event_id(),
        "type": etype,
        "custom_title": custom_title,
        "day": day,
        "author": q.from_user.first_name,
        "author_id": q.from_user.id,
        "votes": {},        # uid -> (name, bool)
        "votes_named": {},  # uid -> (name, bool)
    }
    events[q.message.chat_id].append(ev)

    await q.edit_message_text(event_card_text(ev), parse_mode="Markdown", reply_markup=event_card_kb(ev))

async def cb_event_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    key = f"ev_pending_{q.from_user.id}_{q.message.chat_id}"
    context.bot_data.pop(key, None)
    await q.edit_message_text("❌ Створення івенту скасовано.")

async def handle_custom_event_title(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ловить текстове повідомлення як назву кастомного івенту."""
    user = update.effective_user
    chat_id = update.effective_chat.id
    key = f"ev_pending_{user.id}_{chat_id}"
    pending = context.bot_data.get(key)
    if not pending or pending.get("type") != "custom":
        return  # не стан очікування назви
    
    context.bot_data.pop(key, None)
    custom_title = update.message.text
    
    day_rows = [[InlineKeyboardButton(f"{DAY_EMOJI[i]} {DAYS[i]}", callback_data=f"eday_custom_{i}")] for i in range(7)]
    day_rows.append([InlineKeyboardButton("❌ Скасувати", callback_data="ev_cancel")])
    
    # Зберігаємо custom_title назад
    context.bot_data[key] = {"type": "custom", "custom_title": custom_title}
    
    await update.message.reply_text(
        f"📝 _{custom_title}_\n\nКоли проводимо?",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(day_rows)
    )

async def cb_event_vote(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    parts = q.data.split("_")  # ev_yes_3 / ev_no_3 / ev_who_3
    action = parts[1]
    eid = int(parts[2])
    chat_id = q.message.chat_id
    user = q.from_user

    ev = next((e for e in events[chat_id] if e["id"] == eid), None)
    if not ev:
        await q.answer("Івент не знайдено 😔", show_alert=True)
        return

    if action == "who":
        yes = [n for uid, (n, v) in ev["votes_named"].items() if v]
        no  = [n for uid, (n, v) in ev["votes_named"].items() if not v]
        text = (
            f"✅ Йдуть ({len(yes)}): {', '.join(yes) if yes else '—'}\n"
            f"❌ Не йдуть ({len(no)}): {', '.join(no) if no else '—'}"
        )
        await q.answer(text, show_alert=True)
        return

    vote = (action == "yes")
    ev["votes"][user.id] = (user.first_name, vote)
    ev["votes_named"][user.id] = (user.first_name, vote)

    try:
        await q.edit_message_text(event_card_text(ev), parse_mode="Markdown", reply_markup=event_card_kb(ev))
    except Exception:
        pass

async def cmd_events_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    ev_list = events.get(chat_id, [])
    if not ev_list:
        await update.message.reply_text("📭 Поки немає активних івентів.\n\nЗапропонуй свій: /event")
        return
    await update.message.reply_text(f"📋 *Активні івенти ({len(ev_list)}):*", parse_mode="Markdown")
    for ev in ev_list:
        await update.message.reply_text(event_card_text(ev), parse_mode="Markdown", reply_markup=event_card_kb(ev))

async def cmd_clear_events(update: Update, context: ContextTypes.DEFAULT_TYPE):
    events[update.effective_chat.id] = []
    await update.message.reply_text("🗑 Список івентів очищено.")

# ─────────────────────────────────────────────
# Анкета — простий ConversationHandler (один крок — весь текст)
# ─────────────────────────────────────────────

async def anketa_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    # Зберігаємо стан: ця людина зараз заповнює анкету
    context.bot_data[f"anketa_pending_{user.id}"] = True
    await update.message.reply_text(
        "📋 *Анкета*\n\n"
        "Напиши будь-що про себе в одному повідомленні — в довільній формі.\n"
        "Ім'я, вік, звідки, чим займаєшся, хобі, цікаві факти — все що хочеш щоб знали.\n\n"
        "_Напиши текст нижче або /cancel щоб скасувати._",
        parse_mode="Markdown"
    )

async def anketa_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.bot_data.pop(f"anketa_pending_{update.effective_user.id}", None)
    await update.message.reply_text("❌ Скасовано.")

async def show_profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    target_id = None
    for entity in (update.message.entities or []):
        if entity.type == "mention":
            uname = update.message.text[entity.offset+1:entity.offset+entity.length]
            for uid, p in profiles.items():
                if (p.get("username") or "").lower() == uname.lower():
                    target_id = uid
                    break
            if not target_id:
                await update.message.reply_text(f"😔 Анкету для @{uname} не знайдено.")
                return
        elif entity.type == "text_mention":
            target_id = entity.user.id

    if not target_id:
        target_id = update.effective_user.id

    p = profiles.get(target_id)
    if not p:
        if target_id == update.effective_user.id:
            await update.message.reply_text("📋 У тебе ще немає анкети. Заповни — /anketa")
        else:
            await update.message.reply_text("😔 Ця людина ще не заповнила анкету.")
        return

    mention = f"@{p['username']}" if p.get("username") else p["tg_name"]
    await update.message.reply_text(
        f"👤 *Анкета: {p['tg_name']}* ({mention})\n\n{p['text']}",
        parse_mode="Markdown"
    )

async def cmd_profiles_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not profiles:
        await update.message.reply_text("📭 Ще ніхто не заповнив анкету. Першим: /anketa")
        return
    lines = ["📋 *Хто вже заповнив анкету:*\n"]
    for uid, p in profiles.items():
        mention = f"@{p['username']}" if p.get("username") else p["tg_name"]
        lines.append(f"• {p['tg_name']} ({mention})")
    lines.append("\nНапиши /profile @username щоб переглянути")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

# ─────────────────────────────────────────────
# Активність та збір
# ─────────────────────────────────────────────

async def track_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat_id = update.effective_chat.id
    if not user or user.is_bot:
        return

    # Якщо людина заповнює анкету — зберігаємо і виходимо
    anketa_key = f"anketa_pending_{user.id}"
    if context.bot_data.get(anketa_key):
        context.bot_data.pop(anketa_key)
        profiles[user.id] = {
            "text": update.message.text,
            "username": user.username,
            "tg_name": user.first_name,
        }
        mention = f"@{user.username}" if user.username else user.first_name
        await update.message.reply_text(
            f"✅ *Анкету збережено!*\n\n"
            f"_{update.message.text}_\n\n"
            f"Переглянути: /profile або /profile {mention}",
            parse_mode="Markdown"
        )
        return

    # Рахуємо активність
    if user.id not in activity[chat_id]:
        activity[chat_id][user.id] = {"name": user.first_name, "username": user.username, "count": 0}
    activity[chat_id][user.id].update({"name": user.first_name, "username": user.username})
    activity[chat_id][user.id]["count"] += 1

def medal(r):
    return {1:"🥇",2:"🥈",3:"🥉"}.get(r,"▪️")

async def cmd_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    data = activity.get(chat_id, {})
    if not data:
        await update.message.reply_text("📭 Статистика порожня. Запусти /autostart щоб почати рахунок.")
        return
    srt = sorted(data.items(), key=lambda x: x[1]["count"], reverse=True)
    total = sum(u["count"] for _, u in srt)
    active = [(uid, u) for uid, u in srt if u["count"] > 0]
    silent = [(uid, u) for uid, u in srt if u["count"] == 0]
    lines = [f"📈 *Звіт активності*\n_(повідомлень: {total})_\n"]
    for rank, (uid, u) in enumerate(active, 1):
        bl = min(int(u["count"] / max(active[0][1]["count"],1) * 10), 10)
        pct = round(u["count"]/total*100) if total else 0
        lines.append(f"{medal(rank)} *{u['name']}* — {u['count']} повід. ({pct}%)\n`{'█'*bl+'░'*(10-bl)}`")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")
    if silent:
        mentions = [f"@{u['username']}" if u.get("username") else f"[{u['name']}](tg://user?id={uid})" for uid, u in silent]
        await update.message.reply_text(
            "👻 *Хто мовчить?*\n\n" + " ".join(mentions) + "\n\nАу, ви живі? 😄",
            parse_mode="Markdown"
        )

async def cmd_reset_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    activity[update.effective_chat.id] = {}
    await update.message.reply_text("🔄 Статистику скинуто!")

async def cmd_gather(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    data = activity.get(chat_id, {})
    if not data:
        await update.message.reply_text("😔 Список порожній. Починається рахунок з /autostart.")
        return
    mentions = [f"@{u['username']}" if u.get("username") else f"[{u['name']}](tg://user?id={uid})" for uid, u in data.items()]
    msg_text = " ".join(context.args) if context.args else "Збір! 👋"
    text = f"📢 *{msg_text}*\n\n" + " ".join(mentions) + "\n\n_Повідомлення видалиться через 1 хвилину_ 🗑"
    sent = await update.message.reply_text(text, parse_mode="Markdown")
    context.job_queue.run_once(
        lambda ctx: ctx.bot.delete_message(chat_id, sent.message_id),
        when=60
    )
    try:
        await update.message.delete()
    except Exception:
        pass

# ─────────────────────────────────────────────
# Питання / теми
# ─────────────────────────────────────────────

async def cmd_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"❓ {random.choice(RANDOM_QUESTIONS)}")

async def cmd_topic(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(random.choice(DISCUSSION_TOPICS), parse_mode="Markdown")

# ─────────────────────────────────────────────
# Автоматичні завдання
# ─────────────────────────────────────────────

async def sched_random(context: ContextTypes.DEFAULT_TYPE):
    now = datetime.now(KYIV_TZ)
    if now.hour < 7 or now.hour >= 22:
        return
    chat_id = context.job.data["chat_id"]
    text = f"❓ {random.choice(RANDOM_QUESTIONS)}" if random.random() < 0.5 else random.choice(DISCUSSION_TOPICS)
    await context.bot.send_message(chat_id, text, parse_mode="Markdown")

async def sched_weather(context: ContextTypes.DEFAULT_TYPE):
    await scheduled_weather(context)

async def sched_howwasday(context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_poll(
        context.job.data["chat_id"], "🌙 Як пройшов ваш день?",
        ["🔥 Відмінно!", "😊 Добре", "😐 Нормально", "😔 Важкувато", "🤦 Краще не питай"],
        is_anonymous=False, allows_multiple_answers=False
    )

async def sched_monday(context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_message(
        context.job.data["chat_id"],
        "📅 *Новий тиждень!* Є плани?\n\nЗапропонуй івент: /event\nПоточні: /events",
        parse_mode="Markdown"
    )

async def sched_friday(context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_message(
        context.job.data["chat_id"],
        "🎉 *П'ятниця!* Що на вихідних?\n\nЗапропонуй: /event  |  Переглянь: /events",
        parse_mode="Markdown"
    )

async def sched_weekly_report(context: ContextTypes.DEFAULT_TYPE):
    chat_id = context.job.data["chat_id"]
    data = activity.get(chat_id, {})
    if not data:
        return
    srt = sorted(data.items(), key=lambda x: x[1]["count"], reverse=True)
    total = sum(u["count"] for _, u in srt)
    active = [(uid, u) for uid, u in srt if u["count"] > 0]
    silent = [(uid, u) for uid, u in srt if u["count"] == 0]
    lines = [f"📈 *Тижневий звіт*\n_(повідомлень: {total})_\n"]
    for rank, (uid, u) in enumerate(active, 1):
        bl = min(int(u["count"] / max(active[0][1]["count"],1) * 10), 10) if active else 0
        lines.append(f"{medal(rank)} *{u['name']}* — {u['count']} повід.\n`{'█'*bl+'░'*(10-bl)}`")
    await context.bot.send_message(chat_id, "\n".join(lines), parse_mode="Markdown")
    if silent:
        mentions = [f"@{u['username']}" if u.get("username") else f"[{u['name']}](tg://user?id={uid})" for uid, u in silent]
        await context.bot.send_message(chat_id,
            "👻 *Мовчуни тижня:*\n\n" + " ".join(mentions) + "\n\nЯк справи? 💙",
            parse_mode="Markdown")
    for uid in activity[chat_id]:
        activity[chat_id][uid]["count"] = 0

async def cmd_autostart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    jq = context.job_queue
    for name in [str(chat_id), f"{chat_id}_weather", f"{chat_id}_friday",
                 f"{chat_id}_evening", f"{chat_id}_monday", f"{chat_id}_report"]:
        for job in jq.get_jobs_by_name(name):
            job.schedule_removal()

    jq.run_repeating(sched_random,        interval=5*3600, first=60,   data={"chat_id":chat_id}, name=str(chat_id))
    jq.run_daily(sched_weather,           time=time(8,0,tzinfo=KYIV_TZ),  days=tuple(range(7)), data={"chat_id":chat_id}, name=f"{chat_id}_weather")
    jq.run_daily(sched_friday,            time=time(10,0,tzinfo=KYIV_TZ), days=(4,),            data={"chat_id":chat_id}, name=f"{chat_id}_friday")
    jq.run_daily(sched_howwasday,         time=time(21,0,tzinfo=KYIV_TZ), days=tuple(range(7)), data={"chat_id":chat_id}, name=f"{chat_id}_evening")
    jq.run_daily(sched_monday,            time=time(10,0,tzinfo=KYIV_TZ), days=(0,),            data={"chat_id":chat_id}, name=f"{chat_id}_monday")
    jq.run_daily(sched_weekly_report,     time=time(20,0,tzinfo=KYIV_TZ), days=(6,),            data={"chat_id":chat_id}, name=f"{chat_id}_report")

    await update.message.reply_text(
        "✅ *Автоматичні повідомлення увімкнено!*\n\n"
        "🌤 08:00 — погода в Братиславі\n"
        "📅 Пн 10:00 — нагадування запропонувати івент\n"
        "🎉 Пт 10:00 — плани на вихідні\n"
        "🌙 Щодня 21:00 — як пройшов день\n"
        "📈 Нд 20:00 — тижневий звіт\n"
        "❓ Кожні ~5 год (7–22) — рандомне питання",
        parse_mode="Markdown"
    )

# ─────────────────────────────────────────────
# Старт / хелп
# ─────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 *Привіт! Я ваш груповий бот-організатор!*\n\n"
        "🎉 /event — запропонувати івент\n"
        "📋 /events — активні івенти\n"
        "🗑 /clearevents — очистити івенти\n"
        "🌤 /weather — погода в Братиславі\n"
        "❓ /question — рандомне (18+) питання\n"
        "💬 /topic — тема для обговорення\n"
        "📈 /report — звіт активності\n"
        "🔄 /resetstats — скинути статистику\n"
        "📢 /gather — зібрати всіх тегами\n"
        "📋 /anketa — заповнити анкету про себе\n"
        "👤 /profile — переглянути анкету\n"
        "📜 /profiles — всі анкети\n"
        "🤖 /autostart — увімкнути авто-повідомлення\n"
        "ℹ️ /help — довідка",
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

    # Трекер + анкета + кастомний івент — все в одному MessageHandler
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, track_message))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_custom_event_title), group=1)

    # Callback-кнопки
    app.add_handler(CallbackQueryHandler(cb_event_type,   pattern=r"^etype_"))
    app.add_handler(CallbackQueryHandler(cb_event_day,    pattern=r"^eday_"))
    app.add_handler(CallbackQueryHandler(cb_event_cancel, pattern=r"^ev_cancel$"))
    app.add_handler(CallbackQueryHandler(cb_event_vote,   pattern=r"^ev_(yes|no|who)_\d+$"))

    # Команди
    app.add_handler(CommandHandler("start",       cmd_start))
    app.add_handler(CommandHandler("help",        cmd_start))
    app.add_handler(CommandHandler("event",       cmd_event))
    app.add_handler(CommandHandler("events",      cmd_events_list))
    app.add_handler(CommandHandler("clearevents", cmd_clear_events))
    app.add_handler(CommandHandler("weather",     cmd_weather))
    app.add_handler(CommandHandler("question",    cmd_question))
    app.add_handler(CommandHandler("topic",       cmd_topic))
    app.add_handler(CommandHandler("report",      cmd_report))
    app.add_handler(CommandHandler("resetstats",  cmd_reset_stats))
    app.add_handler(CommandHandler("gather",      cmd_gather))
    app.add_handler(CommandHandler("profile",     show_profile))
    app.add_handler(CommandHandler("profiles",    cmd_profiles_list))
    app.add_handler(CommandHandler("autostart",   cmd_autostart))
    app.add_handler(CommandHandler("cancel",      anketa_cancel))

    logger.info("Бот запущено!")
    app.run_polling()

if __name__ == "__main__":
    main()
