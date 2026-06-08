import asyncio
import logging
import random
import pytz
import aiohttp
from datetime import datetime, time
from collections import defaultdict
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    ContextTypes, MessageHandler, filters,
)
import storage

logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

KYIV_TZ = pytz.timezone("Europe/Kyiv")
WEATHER_LAT, WEATHER_LON = "48.1486", "17.1077"

_events: dict = storage.load_events()
_event_counter: int = max((e["id"] for evs in _events.values() for e in evs), default=0)

def next_event_id():
    global _event_counter
    _event_counter += 1
    return _event_counter

activity: dict = defaultdict(dict)

RANDOM_QUESTIONS = [
    "🍑 Якби частини тіла могли голосувати на виборах — яка б перемогла і яку б обіцяла програму?",
    "🎪 Ти коли-небудь робив щось настільки кринжове, що досі прокидаєшся о 3 ночі від цього спогаду?",
    "🧠 Якби твій внутрішній монолог транслювався вголос останні 10 хвилин — скільки людей би встали і пішли?",
    "🍷 Що ти робиш коли п'яний і думаєш що виглядаєш круто — але насправді ні?",
    "😈 Яка твоя найбільш морально сумнівна харчова звичка? Їжа з підлоги рахується.",
    "🎭 Якби твоє особисте життя було жанром кіно — що це було б? Трилер? Комедія? Документалка про катастрофу?",
    "🚿 Які монологи ти виголошуєш в душі — і кому вони адресовані?",
    "🤡 Яка найбезглуздіша річ через яку ти реально посварився з людиною?",
    "🐒 Якби еволюція пішла інакше — які соцмережі були б у мавп і що б вони постили?",
    "🎲 Якби за кожен раз коли ти кажеш «я вже йду» і не йдеш — платив штраф, скільки б заборгував?",
    "🍕 Є їжа яку ти їси тільки наодинці бо соромно? Розкажи. Тут всі свої.",
    "💘 Яку найдурнішу річ ти зробив щоб сподобатись комусь?",
    "🧟 О котрій годині ти перетворюєшся з людини на щось страшніше — і що саме?",
    "🎵 Яка пісня — твоя guilty pleasure яку слухаєш тільки в навушниках?",
    "🏆 Яке твоє найбільше досягнення яке не можна вписати в резюме але ти ним гордишся?",
    "👻 Яка ситуація змушує тебе хотіти буквально зникнути крізь землю?",
    "😏 Яка твоя найкраща відмазка якій ти сам вже не віриш але продовжуєш використовувати?",
    "🔥 Якби твоє тіло виставляло рахунки — яка стаття витрат була б найбільшою?",
    "🤫 Є щось що всі роблять і вважають нормальним — а ти таємно думаєш що це дико?",
    "💤 Яка твоя найдивніша звичка перед сном яку б не зізнався нікому тверезому?",
    "🧃 Яка дитяча звичка у тебе досі є — і не треба соромитись?",
    "🦆 Якби тебе можна було описати однією твариною в стані стресу — яка б це була і чому?",
    "🎬 Якби знімали фільм про твій найбільш незручний момент — який рейтинг би він отримав?",
    "📦 Якби ти міг надіслати посилку собі 10-річному — що б туди поклав і що б написав?",
    "🌙 Який момент у житті ти хотів би заморозити і повертатись до нього?",
    "🍻 Яке твоє найгірше рішення під впливом алкоголю яке ти зараз вважаєш кращим спогадом?",
    "😳 Яку фразу ти казав на побаченні і потім ночами згадував з жахом?",
    "🛁 Є щось що ти робиш в душі і впевнений що всі так роблять — а насправді ні?",
    "🤥 Яка твоя найпереконливіша брехня яку ти розповідаєш так часто що сам вже майже вірите?",
    "🎯 Яку річ ти відкладаєш роками і вже придумав 47 причин чому ще не час?",
    "🌶 Яка твоя найгостріша думка про когось з оточення яку ти ніколи не скажеш вголос?",
    "🛌 Якщо чесно — в скільки ти реально лягаєш спати і скільки годин до цього «збираєшся»?",
    "💅 Яка твоя таємна суперсила про яку ніхто не знає — і це не щось корисне?",
    "🤦 Опиши свій найепічніший факап одним реченням. Переможець отримує повагу всієї компанії.",
    "🐛 Яка твоя найогидніша звичка яку ти вважаєш абсолютно нормальною?",
]

DISCUSSION_TOPICS = [
    "🗣 *Тема:* Є місця в Братиславі де час ніби зупиняється. Де у вас таке місце?",
    "🗣 *Тема:* Дорослі стосунки — чому з віком знайти справжніх друзів стає складніше?",
    "🗣 *Тема:* Настільні ігри — це діагностика характеру чи просто гра?",
    "🗣 *Тема:* Ідеальний вечір з компанією — що має бути обов'язково і чого не має бути?",
    "🗣 *Тема:* Похід у гори — у кого вже є травма і хто готовий повторити?",
    "🗣 *Тема:* Red flag або green flag — що одразу говорить вам все про людину?",
    "🗣 *Тема:* Найкращий спосіб відпочити після важкого тижня — у кожного свій.",
    "🗣 *Тема:* Яке місце в Братиславі треба показати гостю що приїхав вперше?",
    "🔞 *Тема:* Перший поцілунок — романтично чи кринжово? Хто готовий розповісти?",
    "😬 *Тема:* Найгірше побачення у вашому житті — деталі, подробиці, без цензури.",
    "🍺 *Тема:* Є корпоратив або вечірка після якої ви соромились наступного дня — що сталось?",
    "💔 *Тема:* Найдурніша причина через яку ви розходились або сварились — зізнайтесь.",
    "🌶 *Тема:* Що у людях вас заводить — і ні, не обов'язково в романтичному сенсі?",
    "🤐 *Тема:* Є думка яку ви ніколи не скажете вголос в цій компанії — що це?",
    "😂 *Тема:* Найкринжовіший момент вашого підліткового віку — хто перший?",
    "🛏 *Тема:* Ваші стосунки з сном — роман, трагедія чи холодна війна?",
    "💸 *Тема:* На що ви витрачаєте гроші і потім соромитесь це визнавати?",
    "🧲 *Тема:* Яка риса характеру притягує вас у людях як магніт — і чому це майже завжди погано закінчується?",
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
DAYS      = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Нд"]
DAY_EMOJI = ["📅","📅","📅","📅","🎉","🎉","😴"]

# ── Погода ────────────────────────────────────

async def fetch_weather():
    url = (
        "https://api.open-meteo.com/v1/forecast"
        f"?latitude={WEATHER_LAT}&longitude={WEATHER_LON}"
        "&current=temperature_2m,apparent_temperature,weathercode,windspeed_10m,relative_humidity_2m"
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
    return {0:"Ясно",1:"Переважно ясно",2:"Мінлива хмарність",3:"Хмарно",
            45:"Туман",51:"Мряка",61:"Дощ",63:"Помірний дощ",65:"Сильний дощ",
            71:"Сніг",80:"Злива",95:"Гроза"}.get(c,"Змінна погода")

def weather_tip(code, temp, wind):
    if 51<=code<=67 or 80<=code<=82: return "Візьми парасолю ☂️"
    if code in (95,96,99): return "Краще залишись вдома, гроза ⛈"
    if 71<=code<=77: return "Є сніг — обережно 🌨"
    if temp < 5: return "Вдягнись тепло 🧣"
    if temp < 12: return "Захопи куртку 🧥"
    if temp > 28: return "Пий більше води 💧"
    if wind > 40: return "Сильний вітер 💨"
    return "Чудовий день для прогулянки 🚶"

def build_weather_text(data):
    c     = data["current"]
    temp  = round(c["temperature_2m"])
    feels = round(c["apparent_temperature"])
    wind  = round(c["windspeed_10m"])
    hum   = round(c["relative_humidity_2m"])
    code  = int(c["weathercode"])
    return (
        f"🌍 *Погода в Братиславі*\n\n"
        f"{wmo_emoji(code)} *{wmo_desc(code)}* · {temp}°C (відчувається {feels}°C)\n"
        f"💨 Вітер: {wind} км/год  💧 Вологість: {hum}%\n\n"
        f"💡 _{weather_tip(code, temp, wind)}_\n\nГарного дня! ☀️"
    )

async def cmd_weather(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("⏳ Отримую погоду...")
    data = await fetch_weather()
    if data:
        await msg.edit_text(build_weather_text(data), parse_mode="Markdown")
    else:
        await msg.edit_text("😔 Не вдалось отримати погоду.")

async def sched_weather(context: ContextTypes.DEFAULT_TYPE):
    data = await fetch_weather()
    if data:
        await context.bot.send_message(context.job.data["chat_id"], build_weather_text(data), parse_mode="Markdown")

# ── Трекер — анкета + теги + активність ───────

async def track_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user    = update.effective_user
    chat_id = update.effective_chat.id
    if not user or user.is_bot:
        return

    text = (update.message.text or "").strip()
    low  = text.lower()

    # Анкета: "про себе ..."
    if low.startswith("про себе"):
        info = text[len("про себе"):].strip(" :—-\n")
        if info:
            profiles = storage.load_profiles()
            profiles[user.id] = {"text": info, "username": user.username or "", "tg_name": user.first_name}
            storage.save_profiles(profiles)
            await update.message.reply_text(
                f"✅ *Збережено, {user.first_name}!*\n\n_{info}_\n\nПереглянути: /profile",
                parse_mode="Markdown"
            )
        else:
            await update.message.reply_text(
                "📋 Напиши текст після «про себе», наприклад:\n_про себе Привіт! Мене звати Іван, 27 років_ 🙂",
                parse_mode="Markdown"
            )

    # Зберігаємо для /gather
    storage.register_user(user)

    # Активність
    if user.id not in activity[chat_id]:
        activity[chat_id][user.id] = {"name": user.first_name, "count": 0}
    activity[chat_id][user.id]["name"]   = user.first_name
    activity[chat_id][user.id]["count"] += 1

# ── Анкети ────────────────────────────────────

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
                await update.message.reply_text(f"😔 Анкету для @{uname} не знайдено.")
                return
        elif entity.type == "text_mention":
            target_id = entity.user.id

    if target_id is None:
        target_id = update.effective_user.id

    p = profiles.get(int(target_id))
    if not p:
        if int(target_id) == update.effective_user.id:
            await update.message.reply_text(
                "📋 У тебе ще немає анкети.\n\n"
                "Напиши повідомлення що починається з *про себе*:\n"
                "_про себе Привіт! Мене звати Іван, 27 років, з Києва_",
                parse_mode="Markdown"
            )
        else:
            await update.message.reply_text("😔 Ця людина ще не заповнила анкету.")
        return

    mention = f"@{p['username']}" if p.get("username") else p["tg_name"]
    await update.message.reply_text(
        f"👤 *{p['tg_name']}* ({mention})\n\n{p['text']}",
        parse_mode="Markdown"
    )

async def cmd_profiles_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    profiles = storage.load_profiles()
    if not profiles:
        await update.message.reply_text(
            "📭 Ще ніхто не заповнив анкету.\n\n"
            "Напиши: _про себе Привіт, мене звати..._",
            parse_mode="Markdown"
        )
        return
    lines = ["📋 *Анкети учасників:*\n"]
    for uid, p in profiles.items():
        mention = f"@{p['username']}" if p.get("username") else p["tg_name"]
        lines.append(f"• {p['tg_name']} ({mention})")
    lines.append("\n/profile @username — переглянути анкету")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

# ── Теги / Збір ───────────────────────────────

async def cmd_tags_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tags = storage.load_tags()
    if not tags:
        await update.message.reply_text("📭 Список порожній. Бот запам'ятовує всіх хто пише у групі.")
        return
    lines = ["👥 *Учасники групи:*\n"]
    for uid, u in tags.items():
        mention = f"@{u['username']}" if u.get("username") else u["name"]
        lines.append(f"• {u['name']} ({mention})")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

async def cmd_gather(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tags = storage.load_tags()
    if not tags:
        await update.message.reply_text("😔 Список порожній. Бот запам'ятовує людей коли вони пишуть у групі.")
        return

    mentions = []
    for uid, u in tags.items():
        if u.get("username"):
            mentions.append(f"@{u['username']}")
        else:
            # text_mention для тих без username
            mentions.append(f"[{u['name']}](tg://user?id={uid})")

    custom_text = " ".join(context.args) if context.args else "Збір! 👋"
    text = f"📢 *{custom_text}*\n\n" + " ".join(mentions) + "\n\n_Повідомлення видалиться через 1 хвилину_ 🗑"
    sent = await update.message.reply_text(text, parse_mode="Markdown")

    async def delete_it(ctx):
        try:
            await ctx.bot.delete_message(update.effective_chat.id, sent.message_id)
        except Exception:
            pass

    context.job_queue.run_once(delete_it, when=60)
    try:
        await update.message.delete()
    except Exception:
        pass

# ── Івенти ────────────────────────────────────

def event_text(ev):
    etype     = EVENT_TYPES.get(ev["type"], ev["type"])
    day_str   = f"{DAY_EMOJI[ev['day']]} {DAYS[ev['day']]}"
    yes_names = [n for n, v in ev["votes_named"].values() if v]
    no_names  = [n for n, v in ev["votes_named"].values() if not v]
    lines = [f"🎉 *Івент від {ev['author']}*\n"]
    if ev.get("custom_title"):
        lines.append(f"📝 *{ev['custom_title']}*\n_{etype}_")
    else:
        lines.append(etype)
    lines.append(f"\n{day_str}\n")
    lines.append(f"✅ Йдуть ({len(yes_names)}): {', '.join(yes_names) if yes_names else 'поки ніхто'}")
    if no_names:
        lines.append(f"❌ Не йдуть: {', '.join(no_names)}")
    return "\n".join(lines)

def event_kb(ev):
    eid   = ev["id"]
    yes_c = sum(1 for n, v in ev["votes_named"].values() if v)
    no_c  = sum(1 for n, v in ev["votes_named"].values() if not v)
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(f"✅ Йду ({yes_c})",    callback_data=f"ev_yes_{eid}"),
        InlineKeyboardButton(f"❌ Не йду ({no_c})", callback_data=f"ev_no_{eid}"),
    ]])

async def cmd_event(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = [[InlineKeyboardButton(label, callback_data=f"etype_{key}")]
            for key, label in EVENT_TYPES.items()]
    await update.message.reply_text(
        "🎉 *Створити івент*\n\nОбери тип події:",
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
            "✏️ Напиши назву своєї події наступним повідомленням:",
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

async def handle_custom_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user    = update.effective_user
    chat_id = update.effective_chat.id
    key     = f"ev_{user.id}_{chat_id}"
    pending = context.bot_data.get(key)
    if not pending or pending.get("type") != "custom":
        return
    pending["custom_title"] = update.message.text
    day_rows = [[InlineKeyboardButton(f"{DAY_EMOJI[i]} {DAYS[i]}", callback_data=f"eday_custom_{i}")] for i in range(7)]
    day_rows.append([InlineKeyboardButton("❌ Скасувати", callback_data="ev_cancel")])
    await update.message.reply_text(
        f"📝 _{update.message.text}_\n\nКоли проводимо?",
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
    pending = context.bot_data.pop(key, {})
    chat_id = q.message.chat_id

    ev = {
        "id":           next_event_id(),
        "type":         etype,
        "custom_title": pending.get("custom_title"),
        "day":          day,
        "author":       q.from_user.first_name,
        "author_id":    q.from_user.id,
        "votes_named":  {},
        "msg_id":       None,
    }
    if chat_id not in _events:
        _events[chat_id] = []
    _events[chat_id].append(ev)

    # Видаляємо меню вибору
    try:
        await q.delete_message()
    except Exception:
        pass

    # Відправляємо картку
    sent = await context.bot.send_message(chat_id, event_text(ev), parse_mode="Markdown", reply_markup=event_kb(ev))
    ev["msg_id"] = sent.message_id
    storage.save_events(_events)

    # Закріплюємо
    try:
        await context.bot.pin_chat_message(chat_id, sent.message_id, disable_notification=True)
    except Exception as e:
        logger.warning(f"Pin failed: {e}")

async def cb_ev_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    context.bot_data.pop(f"ev_{q.from_user.id}_{q.message.chat_id}", None)
    await q.edit_message_text("❌ Скасовано.")

async def cb_ev_vote(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q       = update.callback_query
    parts   = q.data.split("_")
    action  = parts[1]
    eid     = int(parts[2])
    chat_id = q.message.chat_id
    user    = q.from_user

    ev = next((e for e in _events.get(chat_id, []) if e["id"] == eid), None)
    if not ev:
        await q.answer("Івент не знайдено 😔", show_alert=True)
        return

    ev["votes_named"][str(user.id)] = [user.first_name, action == "yes"]
    storage.save_events(_events)

    vote_text = "✅ Відмітився як «Йду»!" if action == "yes" else "❌ Відмітився як «Не йду»"
    await q.answer(vote_text)

    try:
        await q.edit_message_text(event_text(ev), parse_mode="Markdown", reply_markup=event_kb(ev))
    except Exception:
        pass

async def cmd_events_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    ev_list = _events.get(chat_id, [])
    if not ev_list:
        await update.message.reply_text("📭 Немає активних івентів.\n\nЗапропонуй: /event")
        return
    await update.message.reply_text(f"📋 *Активні івенти ({len(ev_list)}):*", parse_mode="Markdown")
    for ev in ev_list:
        await update.message.reply_text(event_text(ev), parse_mode="Markdown", reply_markup=event_kb(ev))

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

    msg = await update.message.reply_text("🗑 Всі івенти видалено і відкріплено.")
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
    if not data:
        await update.message.reply_text("📭 Статистика порожня. Рахується з моменту /autostart.")
        return
    srt    = sorted(data.items(), key=lambda x: x[1]["count"], reverse=True)
    total  = sum(u["count"] for _, u in srt)
    active = [(uid, u) for uid, u in srt if u["count"] > 0]
    lines  = [f"📈 *Звіт активності*\n_(повідомлень: {total})_\n"]
    for rank, (uid, u) in enumerate(active, 1):
        bl  = min(int(u["count"] / max(active[0][1]["count"],1) * 10), 10)
        pct = round(u["count"]/total*100) if total else 0
        lines.append(f"{medal(rank)} *{u['name']}* — {u['count']} повід. ({pct}%)\n`{'█'*bl+'░'*(10-bl)}`")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

async def cmd_reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    activity[update.effective_chat.id] = {}
    await update.message.reply_text("🔄 Статистику скинуто!")

async def cmd_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"❓ {random.choice(RANDOM_QUESTIONS)}")

async def cmd_topic(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(random.choice(DISCUSSION_TOPICS), parse_mode="Markdown")

# ── Автоматичні завдання ──────────────────────

async def sched_random(context: ContextTypes.DEFAULT_TYPE):
    now = datetime.now(KYIV_TZ)
    if now.hour < 7 or now.hour >= 22:
        return
    chat_id = context.job.data["chat_id"]
    text = f"❓ {random.choice(RANDOM_QUESTIONS)}" if random.random() < 0.5 else random.choice(DISCUSSION_TOPICS)
    await context.bot.send_message(chat_id, text, parse_mode="Markdown")

async def sched_howwasday(context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_poll(
        context.job.data["chat_id"], "🌙 Як пройшов ваш день?",
        ["🔥 Відмінно!", "😊 Добре", "😐 Нормально", "😔 Важкувато", "🤦 Краще не питай"],
        is_anonymous=False, allows_multiple_answers=False
    )

async def sched_monday(context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_message(
        context.job.data["chat_id"],
        "📅 *Новий тиждень!* Є плани?\n\nЗапропонуй івент: /event  |  Переглянь: /events",
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
    data    = activity.get(chat_id, {})
    if not data:
        return
    srt    = sorted(data.items(), key=lambda x: x[1]["count"], reverse=True)
    total  = sum(u["count"] for _, u in srt)
    active = [(uid, u) for uid, u in srt if u["count"] > 0]
    lines  = [f"📈 *Тижневий звіт*\n_(повідомлень: {total})_\n"]
    for rank, (uid, u) in enumerate(active, 1):
        bl = min(int(u["count"] / max(active[0][1]["count"],1) * 10), 10) if active else 0
        lines.append(f"{medal(rank)} *{u['name']}* — {u['count']} повід.\n`{'█'*bl+'░'*(10-bl)}`")
    await context.bot.send_message(chat_id, "\n".join(lines), parse_mode="Markdown")
    active_ids = {uid for uid, u in active}
    tags = storage.load_tags()
    silent = [u for uid, u in tags.items() if int(uid) not in active_ids]
    if silent:
        mentions = [f"@{u['username']}" if u.get("username") else u["name"] for u in silent]
        await context.bot.send_message(chat_id,
            "👻 *Мовчуни тижня:*\n\n" + " ".join(mentions) + "\n\nЯк справи? 💙",
            parse_mode="Markdown")
    for uid in activity[chat_id]:
        activity[chat_id][uid]["count"] = 0

async def cmd_autostart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
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

    await update.message.reply_text(
        "✅ *Автоматичні повідомлення увімкнено!*\n\n"
        "🌤 08:00 — погода\n"
        "📅 Пн 10:00 — нагадування про івент\n"
        "🎉 Пт 10:00 — плани на вихідні\n"
        "🌙 Щодня 21:00 — як пройшов день\n"
        "📈 Нд 20:00 — тижневий звіт\n"
        "❓ Кожні ~5 год (7–22) — рандомне питання",
        parse_mode="Markdown"
    )

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖✨ *Петро Інтерактивний до ваших послуг!*\n\n"
        "Я тут щоб ваша компанія не розпадалась від мовчанки 😄\n\n"
        "━━━━━━━━━━━━━━━━\n"
        "👤 *Анкета*\n"
        "Напиши повідомлення що починається з *про себе*:\n"
        "_про себе Привіт! Мене звати Іван, 27 років, люблю настілки_ 🙂\n"
        "/profile — своя анкета\n"
        "/profile @username — анкета учасника\n"
        "/profiles — всі анкети групи\n\n"
        "━━━━━━━━━━━━━━━━\n"
        "🎉 *Івенти*\n"
        "/event — запропонувати захід (закріпиться автоматично!)\n"
        "/events — всі активні івенти\n"
        "/clearevents — видалити всі івенти\n\n"
        "━━━━━━━━━━━━━━━━\n"
        "📢 *Гукнути всіх*\n"
        "/gather — тегнути кожного (зникне за хвилину)\n"
        "/gather Є хто живий? — з власним текстом\n"
        "/tags — хто є в списку\n\n"
        "━━━━━━━━━━━━━━━━\n"
        "🌤 *Щоденне*\n"
        "/weather — погода в Братиславі\n"
        "/question — гостре питання 🔥\n"
        "/topic — тема для обговорення\n\n"
        "━━━━━━━━━━━━━━━━\n"
        "📊 *Статистика*\n"
        "/report — хто балакучий а хто мовчун\n"
        "/resetstats — обнулити рахунок\n\n"
        "⚙️ /autostart — запустити всі авто-повідомлення",
        parse_mode="Markdown"
    )

def main():
    import os
    TOKEN = os.environ.get("BOT_TOKEN")
    if not TOKEN:
        raise ValueError("BOT_TOKEN не встановлено!")

    app = Application.builder().token(TOKEN).build()

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, track_message), group=0)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_custom_name), group=1)

    app.add_handler(CallbackQueryHandler(cb_etype,     pattern=r"^etype_"))
    app.add_handler(CallbackQueryHandler(cb_eday,      pattern=r"^eday_"))
    app.add_handler(CallbackQueryHandler(cb_ev_cancel, pattern=r"^ev_cancel$"))
    app.add_handler(CallbackQueryHandler(cb_ev_vote,   pattern=r"^ev_(yes|no)_\d+$"))

    app.add_handler(CommandHandler("start",       cmd_start))
    app.add_handler(CommandHandler("help",        cmd_start))
    app.add_handler(CommandHandler("event",       cmd_event))
    app.add_handler(CommandHandler("events",      cmd_events_list))
    app.add_handler(CommandHandler("clearevents", cmd_clear_events))
    app.add_handler(CommandHandler("weather",     cmd_weather))
    app.add_handler(CommandHandler("question",    cmd_question))
    app.add_handler(CommandHandler("topic",       cmd_topic))
    app.add_handler(CommandHandler("report",      cmd_report))
    app.add_handler(CommandHandler("resetstats",  cmd_reset))
    app.add_handler(CommandHandler("gather",      cmd_gather))
    app.add_handler(CommandHandler("tags",        cmd_tags_list))
    app.add_handler(CommandHandler("profile",     cmd_profile))
    app.add_handler(CommandHandler("profiles",    cmd_profiles_list))
    app.add_handler(CommandHandler("autostart",   cmd_autostart))

    logger.info("Бот запущено!")
    app.run_polling()

if __name__ == "__main__":
    main()
