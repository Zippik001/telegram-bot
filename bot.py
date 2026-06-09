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

KYIV_TZ = pytz.timezone("Europe/Bratislava")  # UTC+1/+2 (Братислава)

def he(text: str) -> str:
    """Екранує HTML спецсимволи."""
    return str(text).replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")


WEATHER_LAT, WEATHER_LON = "48.1486", "17.1077"

_events: dict = storage.load_events()
_event_counter: int = max((e["id"] for evs in _events.values() for e in evs), default=0)

def next_event_id():
    global _event_counter
    _event_counter += 1
    return _event_counter

activity: dict = defaultdict(dict)


RANDOM_QUESTIONS = [
    "🍑 Якби твої органи могли писати скарги на тебе — який орган подав би найтовщу папку і за що саме?",
    "🚿 Що ти робиш в душі з таким серйозним виразом обличчя, що якби хтось побачив — одразу б викликав лікаря?",
    "😏 Яка твоя найкінжальніша фраза яку ти кажеш з посмішкою — а людина розуміє лише через годину?",
    "🍷 Опиши свій тип людини трьома словами. Перше слово має бути «проблемний».",
    "🔥 Яку річ ти робиш в ліжку про яку не розкажеш мамі? (їжа о 2 ночі теж рахується)",
    "🤡 З якою твоєю рисою характеру ти вже змирився і навіть зробив її своєю фішкою?",
    "👅 Яка твоя найбільш неприйнятна кулінарна комбінація яку ти їси і захищаєш як адвокат?",
    "🛁 Якби твій душ транслювався в прямому ефірі — на якому моменті ти б вимкнув камеру?",
    "💀 Яка твоя найтемніша думка о 3 ночі яку ти ніколи не напишеш у групі? (пиши тут, ми не розкажемо)",
    "🐍 З ким з групи ти б точно вижив на безлюдному острові — і кого б перший з'їв?",
    "🍺 Яка у тебе репутація на вечірках — і наскільки вона відповідає реальності?",
    "😳 Якби твій телефон отримав право голосу і розповів компанії про твої пошукові запити — що б сказав?",
    "🌶 Що тебе заводить в людях настільки що ти готовий це визнати тут анонімно?",
    "🧠 Яка думка займає у твоїй голові 80% місця — і ти соромишся що це не щось важливе?",
    "💘 Розкажи про свій найфантастичніший план зваблення який провалився настільки епічно що досі смішно?",
    "🎪 Яка твоя прихована кінка про яку знає максимум одна людина і то випадково?",
    "🍑 Якби твоє тіло могло виставляти оцінки твоїм рішенням — яка середня оцінка і за що найнижча?",
    "🤫 Що ти робиш коли думаєш що за тобою ніхто не стежить? Тут можна зізнатись.",
    "🎭 Яку роль ти граєш на людях — і ким ти є насправді о 2 ночі наодинці з собою?",
    "🔞 Який у тебе найдивніший turn-on якого ти соромишся? Їжа, голоси, запахи — все рахується.",
    "🧟 Якби твої ex могли написати один спільний відгук про тебе — що б там було?",
    "💅 Яка твоя найбільша маніпуляція яку ти виправдовуєш словом «я просто чесний»?",
    "🛌 Що ти робиш в ліжку годину перед сном замість того щоб спати — і не кажи що читаєш?",
    "🍻 Яке речення ти вимовив п'яним і зранку знайшов у чернетках як «повідомлення яке краще не надсилати»?",
    "😈 Яка твоя найпідступніша якість яку ти називаєш «стратегічним мисленням»?",
    "🦷 Яка твоя гігієнічна звичка яку ти вважаєш необов'язковою — а лікарі б жахнулись?",
    "🎯 Опиши своє любовне життя за допомогою назви фільму. Чим трагічніша назва — тим точніше.",
    "🌚 О котрій годині твоя внутрішня дитина бере контроль і що вона тоді робить?",
    "💔 Яка найдовша відмазка яку ти придумав щоб не йти на зустріч — і вона спрацювала?",
    "🤢 Яку їжу ти їв прямо з каструлі стоячи над плитою і навіть не соромишся?",
    "🎲 Якби доля вирішувала твоє особисте життя киданням кубика — що б змінилось?",
    "🏆 Яке твоє найбільше досягнення якого немає в жодному резюме але ти ним гордишся як олімпійським медалем?",
    "🐾 Якби твоя кішка або собака могли говорити — що б вони розповіли цій групі першим ділом?",
    "👀 Яка твоя найбільш неадекватна ревнощева поведінка яку ти виправдовував словом «я просто турбуюсь»?",
    "🌊 Що тебе збуджує так що ти готовий зізнатись? (інтелект, влада, запах борщу — всі варіанти валідні)",
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

async def fetch_weather_full():
    """Погода на весь день — поточна + прогноз по годинах."""
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

# Залишаємо для сумісності
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
    return {0:"Ясно",1:"Переважно ясно",2:"Мінлива хмарність",3:"Хмарно",
            45:"Туман",51:"Мряка",61:"Дощ",63:"Помірний дощ",65:"Сильний дощ",
            71:"Сніг",80:"Злива",95:"Гроза"}.get(c,"Змінна погода")

def weather_tip_full(slots):
    """Загальна порада на день на основі всіх слотів."""
    codes = [s["code"] for s in slots]
    temps = [s["temp"] for s in slots]
    has_rain  = any(51<=c<=82 for c in codes)
    has_storm = any(c in (95,96,99) for c in codes)
    has_snow  = any(71<=c<=77 for c in codes)
    min_t = min(temps)
    max_t = max(temps)

    funny = []
    if has_storm:
        funny.append("Гроза? Залишайся вдома, стань людиною-диваном ⛈🛋")
    elif has_rain:
        funny.append("Дощ іде — хороший привід не виходити і дивитись серіали 🌧🍿")
    elif has_snow:
        funny.append("Сніжок! Чудово, якщо ти пінгвін 🐧❄️")
    elif max_t > 28:
        funny.append("Спека! Одягнися як сонячна батарея і плавь тротуари ☀️🥵")
    elif min_t < 3:
        funny.append("Холодно як у серці того хто не відповідає на повідомлення 🥶")
    elif max_t > 18:
        funny.append("Погода — 10 з 10, навіть монітор соромно відкривати 🌞")
    else:
        funny.append("Звичайна братиславська погода — непередбачувана як настрій в понеділок 😅")
    return funny[0]

def build_weather_full(data):
    """Будує повідомлення з погодою по 5 часових слотах."""
    hours_map = {8: "🌅 Ранок",  11: "☀️ Полудень",
                 14: "🌤 День",  17: "🌇 Вечір", 20: "🌙 Ніч"}

    hourly_times = data["hourly"]["time"]
    hourly_temps = data["hourly"]["temperature_2m"]
    hourly_codes = data["hourly"]["weathercode"]
    hourly_prec  = data["hourly"]["precipitation_probability"]

    slots = []
    for target_h, label in hours_map.items():
        # Знаходимо індекс потрібної години
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
    weekdays = ["Понеділок","Вівторок","Середа","Четвер","П'ятниця","Субота","Неділя"]
    weekday = weekdays[now.weekday()]
    lines = [f"🌍 *Погода в Братиславі*\n📅 {weekday}, {date_str}\n"]
    for s in slots:
        lines.append(f"{s['label']}: {s['emoji']} {s['temp']}°C — {s['desc']}{s['prec_str']}")

    tip = weather_tip_full(slots) if slots else "Гарного дня! ☀️"
    lines.append(f"\n💡 _{tip}_")
    return "\n".join(lines)

# Стара функція для сумісності
def build_weather_text(data):
    return build_weather_full(data)

async def cmd_weather(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("⏳ Отримую погоду...")
    data = await fetch_weather_full()
    if data:
        await msg.edit_text(build_weather_full(data), parse_mode="Markdown")
    else:
        await msg.edit_text("😔 Не вдалось отримати погоду.")

async def sched_weather(context: ContextTypes.DEFAULT_TYPE):
    data = await fetch_weather_full()
    if data:
        await context.bot.send_message(
            context.job.data["chat_id"], build_weather_full(data), parse_mode="Markdown"
        )

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
                f"✅ Збережено, {user.first_name}!\n\n{info}\n\nПереглянути: /profile"
            )
        else:
            await update.message.reply_text(
                "📋 Напиши текст після «про себе», наприклад:\nпро себе Привіт! Мене звати Іван, 27 років 🙂"
            )

    # ChatGPT: якщо повідомлення починається з "пєтя," або "@botname" + текст
    petya_triggers = ("пєтя,", "петя,", "пєтя питання", "петя питання", "питання пєтя", "ai,", "шт,")
    if any(low.startswith(t) for t in petya_triggers) or (low.startswith("пєтя ") and len(low) > 6):
        # Витягуємо питання після тригера
        question = text
        for t in ("пєтя,", "петя,", "пєтя ", "петя ", "ai, ", "шт, "):
            if low.startswith(t):
                question = text[len(t):].strip()
                break
        if question:
            thinking = await update.message.reply_text("🤔 Думаю...")
            answer = await ask_ai(question)
            await thinking.edit_text(f"🤖 {answer}")
            storage.register_user(user)
            if user.id not in activity[chat_id]:
                activity[chat_id][user.id] = {"name": user.first_name, "count": 0}
            activity[chat_id][user.id]["name"] = user.first_name
            activity[chat_id][user.id]["count"] += 1
            return

    # Виклик меню через "Пєтя" (регістр не важливий)
    if low.strip() in ("пєтя", "петя", "petya", "пєтя!", "петя!", "пєтя?", "петя?"):
        petya_texts = [
            f"🤖✨ Петро Інтерактивний матеріалізувався!\n\nМене покликали — а значить комусь стало нудно 😏\n\nЩоб заповнити анкету — напиши про себе і далі свій текст\nЩоб запитати мене щось — почни з Пєтя, і я відповім 🫡",
            f"🤖 О, мене покликали! Або хтось скучив або щось трапилось 😄\n\nАнкета: напиши про себе і далі свій текст\nПитання до мене: Пєтя, [питання] — і я не відмовчусь 🎤",
            f"🫡 Петро тут, слухаю і повністю в темі!\n\nЗаповни анкету: про себе + текст\nПитай мене: Пєтя, + запит — дам відповідь яка тебе здивує 🤌",
        ]
        import random as _r
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("📋 Анкети учасників",    callback_data="menu_profiles")],
            [InlineKeyboardButton("🎉 Запропонувати івент", callback_data="menu_event"),
             InlineKeyboardButton("📅 Активні івенти",      callback_data="menu_events")],
            [InlineKeyboardButton("📢 Тегнути всіх",        callback_data="menu_gather")],
            [InlineKeyboardButton("🌤 Погода",              callback_data="menu_weather")],
            [InlineKeyboardButton("❓ Гостре питання",       callback_data="menu_question"),
             InlineKeyboardButton("💬 Тема",                callback_data="menu_topic")],
            [InlineKeyboardButton("📊 Звіт активності",     callback_data="menu_report")],
        ])
        await update.message.reply_text(_r.choice(petya_texts), parse_mode="Markdown", reply_markup=kb)

    # Анонімне повідомлення: починається з "анонім" (або "anonym")
    if low.startswith("анонім ") or low.startswith("anonym "):
        for prefix in ("анонім ", "anonym "):
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
                "🎭 Анонімне повідомлення:\n\n" + anon_text
            )
        return

    # Зберігаємо для /gather
    storage.register_user(user)

    # Активність
    if user.id not in activity[chat_id]:
        activity[chat_id][user.id] = {"name": user.first_name, "count": 0}
    activity[chat_id][user.id]["name"]   = user.first_name
    activity[chat_id][user.id]["count"] += 1

# ── ChatGPT (OpenAI) ──────────────────────────────────────────────────────────

async def ask_ai(question: str) -> str:
    """Відправляє запит до Groq (безкоштовно, без карти)."""
    import os
    api_key = os.environ.get("GROQ_API_KEY", "")
    if not api_key:
        return (
            "😔 Groq API ключ не налаштовано.\n"
            "Додай GROQ_API_KEY в Railway Variables.\n"
            "Отримай безкоштовно: console.groq.com"
        )
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {
        "model": "llama-3.3-70b-versatile",
        "messages": [
            {"role": "system", "content": (
                "Ти — Петро Інтерактивний, неадекватний але добродушний асистент групи друзів у Братиславі. "
                "Відповідай ВИКЛЮЧНО українською мовою — ніякої іншої. "
                "Твій стиль: кринжовий гумор, пошлі але не вульгарні жарти, несподівані порівняння, "
                "саркастичні поради, абсурдні аналогії. "
                "Ти як той друг який завжди скаже щось недоречне але влучне. "
                "Будь коротким — максимум 4-5 речень. "
                "Якщо просять анекдот — розкажи пошлий але смішний, без мату. "
                "Якщо просять пораду — дай її але з таким кринжовим поворотом що людина засміється. "
                "Якщо просять фільм — порадь з описом типу 'там є сцена де...' і зроби це смішно. "
                "Якщо питання серйозне — відповідай серйозно але додай один кринжовий коментар в кінці. "
                "Ніколи не починай з 'Звичайно!' або 'Я радий допомогти' — це нудно і не в твоєму стилі. "
                "Починай відповідь одразу з суті або з несподіваного коментаря."
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
                    return "😔 Помилка при зверненні до ШІ. Спробуй пізніше."
    except Exception as e:
        logger.error(f"Groq exception: {e}")
        return "😔 Не вдалось отримати відповідь від ШІ."

# ── Вітання нових учасників ──────────────────────────────────────────────────

async def welcome_new_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Вітає нового учасника і пояснює правила."""
    for member in update.message.new_chat_members:
        if member.is_bot:
            continue
        # Одразу зберігаємо в теги щоб /gather бачив нового учасника
        storage.register_user(member)
        name = member.first_name
        await update.message.reply_text(
            f"👋 Вітаємо, {name}!\n\n"
            f"Радий бачити тебе в нашій компанії 🎉\n\n"
            f"📋 *Заповни анкету* — напиши повідомлення:\n"
            f"_про себе_ і далі розкажи хто ти, звідки, що любиш\n\n"
            f"📌 *Правила групи:*\n"
            f"✅ Будь активним — пиши, пропонуй івенти, відповідай\n"
            f"😊 Будь позитивним — токсичність тут не в моді\n"
            f"🤝 Поважай інших — ми всі тут для гарного часу\n"
            f"🎉 Пропонуй ідеї — краща ідея та яку ти запропонував\n\n"
            f"Натисни *Пєтя* або /start щоб побачити що я вмію 🤖",
            parse_mode="Markdown"
        )


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
                "📋 У тебе ще немає анкети.\n\nНапиши повідомлення:\nпро себе Привіт! Мене звати Іван, 27 років, з Києва"
            )
        else:
            await update.message.reply_text("😔 Ця людина ще не заповнила анкету.")
        return

    mention = f"@{he(p['username'])}" if p.get("username") else he(p["tg_name"])
    await update.message.reply_text(
        f"👤 <b>{he(p['tg_name'])}</b> ({mention})\n\n{he(p['text'])}",
        parse_mode="HTML"
    )

async def cmd_profiles_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    profiles = storage.load_profiles()
    if not profiles:
        await update.message.reply_text(
            "📭 Ще ніхто не заповнив анкету.\n\n"
            "Напиши: про себе Привіт, мене звати..."
        )
        return
    # Будуємо кнопки — кожна кнопка це ім'я людини, тисниш — отримуєш анкету
    keyboard = []
    profile_map = {}  # callback_data -> uid
    for uid, p in profiles.items():
        label = p["tg_name"]
        if p.get("username"):
            label += f" (@{p['username']})"
        cb = f"showprofile_{uid}"
        keyboard.append([InlineKeyboardButton(label, callback_data=cb)])
    await update.message.reply_text(
        f"📋 Анкети учасників: {len(profiles)}\n\nНатисни на ім'я щоб переглянути 👇",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def cb_show_profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = int(q.data.replace("showprofile_", ""))
    profiles = storage.load_profiles()
    p = profiles.get(uid)
    if not p:
        await q.answer("Анкету не знайдено 😔", show_alert=True)
        return
    mention = f"@{p['username']}" if p.get("username") else p["tg_name"]
    mention = f"@{he(p['username'])}" if p.get("username") else he(p["tg_name"])
    await q.message.reply_text(f"👤 <b>{he(p['tg_name'])}</b> ({mention})\n\n{he(p['text'])}", parse_mode="HTML")

# ── Теги / Збір ───────────────────────────────

async def cmd_tags_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tags = storage.load_tags()
    if not tags:
        await update.message.reply_text("📭 Список порожній. Бот запам'ятовує всіх хто пише у групі.")
        return
    lines = ["👥 Учасники групи:\n"]
    for uid, u in tags.items():
        mention = f"@{u['username']}" if u.get("username") else u["name"]
        lines.append(f"• {u['name']} ({mention})")
    await update.message.reply_text("\n".join(lines))

async def cmd_gather(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id

    # Отримуємо список учасників з Telegram API напряму
    # get_chat_members доступний тільки для ботів-адмінів
    tags = storage.load_tags()

    with_username = []
    without_username = []

    # Спочатку перевіряємо збережених учасників
    for uid_str, u in tags.items():
        try:
            member = await context.bot.get_chat_member(chat_id, int(uid_str))
            if member.status in ("left", "kicked", "banned"):
                continue
            # Оновлюємо дані на свіжі
            if member.user.username:
                with_username.append(f"@{member.user.username}")
            else:
                without_username.append(member.user.first_name)
        except Exception:
            continue

    if not with_username and not without_username:
        await update.message.reply_text(
            "😔 Немає активних учасників.\n\n"
            "Бот запам'ятовує людей коли вони пишуть у групі — попроси всіх написати хоч одне повідомлення."
        )
        return

    custom_text = " ".join(context.args) if context.args else "Збір! 👋"
    all_mentions = with_username + without_username
    text = f"📢 {custom_text}\n\n" + " ".join(all_mentions) + "\n\nПовідомлення видалиться через 1 хвилину 🗑"
    sent = await update.message.reply_text(text)

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
    lines.append(f"\n{day_str}")
    if ev.get("description"):
        lines.append(f"\n💬 {ev['description']}")
    lines.append(f"\n✅ Йдуть ({len(yes_names)}): {', '.join(yes_names) if yes_names else 'поки ніхто'}")
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
    if not pending:
        return

    # Очікуємо опис івенту
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
            "description":  pending.get("description"),
            "author":       pending.get("author", user.first_name),
            "author_id":    pending.get("author_id", user.id),
            "votes_named":  {},
            "msg_id":       None,
        }
        context.bot_data.pop(key, None)
        await _publish_event(context.bot, chat_id, ev)
        return

    # Очікуємо назву кастомного івенту
    if pending.get("type") != "custom":
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
    old     = context.bot_data.get(key, {})
    chat_id = q.message.chat_id

    # Зберігаємо чернетку і просимо опис
    context.bot_data[key] = {
        "type":         etype,
        "custom_title": old.get("custom_title"),
        "day":          day,
        "author":       q.from_user.first_name,
        "author_id":    q.from_user.id,
        "awaiting":     "description",
    }

    await q.edit_message_text(
        f"✏️ Додай опис до івенту — де зустрічаємось, деталі, що брати тощо.\n\n"
        f"Або натисни кнопку щоб пропустити.",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("➡️ Пропустити", callback_data=f"ev_nodesc_{etype}_{day}"),
            InlineKeyboardButton("❌ Скасувати",  callback_data="ev_cancel"),
        ]])
    )


async def _publish_event(bot, chat_id, ev):
    """Публікує картку івенту і закріплює."""
    if chat_id not in _events:
        _events[chat_id] = []
    _events[chat_id].append(ev)
    sent = await bot.send_message(chat_id, event_text(ev), parse_mode="Markdown", reply_markup=event_kb(ev))
    ev["msg_id"] = sent.message_id
    storage.save_events(_events)
    try:
        await bot.pin_chat_message(chat_id, sent.message_id, disable_notification=True)
    except Exception as e:
        logger.warning(f"Pin failed: {e}")


async def cb_ev_nodesc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Пропустити опис — публікувати без нього."""
    q       = update.callback_query
    await q.answer()
    parts   = q.data.split("_")   # ev_nodesc_boardgames_3
    etype   = parts[2]
    day     = int(parts[3])
    chat_id = q.message.chat_id
    key     = f"ev_{q.from_user.id}_{chat_id}"
    pending = context.bot_data.pop(key, {})

    ev = {
        "id":           next_event_id(),
        "type":         etype,
        "custom_title": pending.get("custom_title"),
        "day":          day,
        "description":  None,
        "author":       pending.get("author") or q.from_user.first_name,
        "author_id":    pending.get("author_id") or q.from_user.id,
        "votes_named":  {},
        "msg_id":       None,
    }
    try:
        await q.edit_message_text("⏳ Публікую івент...")
    except Exception:
        pass
    await _publish_event(q.bot, chat_id, ev)

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
    tags    = storage.load_tags()

    # Якщо немає статистики — показуємо тих хто є в списку але нічого не писав
    if not data:
        if tags:
            names = [u["name"] for u in tags.values()]
            await update.message.reply_text(
                f"📭 Статистика порожня — ніхто не писав з моменту /autostart.\n\n"
                f"👥 Відомі учасники: {', '.join(names)}"
            )
        else:
            await update.message.reply_text("📭 Статистика порожня. Запусти /autostart і почни рахунок.")
        return

    srt    = sorted(data.items(), key=lambda x: x[1]["count"], reverse=True)
    total  = sum(u["count"] for _, u in srt)
    active = [(uid, u) for uid, u in srt if u["count"] > 0]
    silent_in_data = [(uid, u) for uid, u in srt if u["count"] == 0]

    lines = [f"📈 Звіт активності\n(повідомлень: {total})\n"]
    for rank, (uid, u) in enumerate(active, 1):
        bl  = min(int(u["count"] / max(active[0][1]["count"],1) * 10), 10)
        pct = round(u["count"]/total*100) if total else 0
        lines.append(f"{medal(rank)} {u['name']} — {u['count']} повід. ({pct}%)\n{'█'*bl+'░'*(10-bl)}")

    # Мовчуни — ті хто є в tags але нічого не писав з моменту /autostart
    active_ids = {uid for uid, _ in active}
    silent_tags = [u for uid, u in tags.items() if int(uid) not in active_ids]
    if silent_tags:
        lines.append("\n👻 Мовчать з останнього /autostart:")
        for u in silent_tags:
            mention = f"@{u['username']}" if u.get("username") else u["name"]
            lines.append(f"  • {u['name']} ({mention})")

    await update.message.reply_text("\n".join(lines))

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
    lines  = [f"📈 Тижневий звіт\n(повідомлень: {total})\n"]
    for rank, (uid, u) in enumerate(active, 1):
        bl = min(int(u["count"] / max(active[0][1]["count"],1) * 10), 10) if active else 0
        lines.append(f"{medal(rank)} {u['name']} — {u['count']} повід.\n{'█'*bl+'░'*(10-bl)}")
    await context.bot.send_message(chat_id, "\n".join(lines))
    active_ids = {uid for uid, u in active}
    tags = storage.load_tags()
    silent = [u for uid, u in tags.items() if int(uid) not in active_ids]
    if silent:
        mentions = [f"@{u['username']}" if u.get("username") else u["name"] for u in silent]
        await context.bot.send_message(chat_id,
            "👻 Мовчуни тижня:\n\n" + " ".join(mentions) + "\n\nЯк справи? 💙")
    for uid in activity[chat_id]:
        activity[chat_id][uid]["count"] = 0


async def cmd_autostart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    jq      = context.job_queue
    all_names = [str(chat_id), f"{chat_id}_weather", f"{chat_id}_friday",
                 f"{chat_id}_evening", f"{chat_id}_monday", f"{chat_id}_report",
                 f"{chat_id}_news"]
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

    await update.message.reply_text(
        "✅ Автоматичні повідомлення увімкнено!\n\n"
        "🌤 08:00 — погода\n"
        "📰 08:05 — смішна новина дня\n"
        "📅 Пн 10:00 — нагадування + івент\n"
        "🎉 Пт 10:00 — плани на вихідні\n"
        "🌙 Щодня 21:00 — як пройшов день\n"
        "📈 Нд 20:00 — тижневий звіт\n"
        "❓ Кожні ~5 год (7–22) — рандомне питання"
    )

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "🤖✨ Петро Інтерактивний до ваших послуг!\n\n"
        "Я тут щоб ваша компанія не розпадалась від мовчанки 😄\n\n"
        "Щоб заповнити анкету — напиши повідомлення:\n"
        "про себе  і далі розкажи про себе 🙂\n\n"
        "Наприклад: про себе Привіт! Я Петро, 28 років, люблю настілки і каву ☕"
    )
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📋 Анкети учасників",     callback_data="menu_profiles")],
        [InlineKeyboardButton("🎉 Запропонувати івент",  callback_data="menu_event"),
         InlineKeyboardButton("📅 Активні івенти",       callback_data="menu_events")],
        [InlineKeyboardButton("📢 Тегнути всіх",         callback_data="menu_gather")],
        [InlineKeyboardButton("🌤 Погода",               callback_data="menu_weather")],
        [InlineKeyboardButton("❓ Гостре питання",        callback_data="menu_question"),
         InlineKeyboardButton("💬 Тема",                 callback_data="menu_topic")],
        [InlineKeyboardButton("📊 Звіт активності",      callback_data="menu_report")],
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
                for key, label in EVENT_TYPES.items()]
        await q.message.reply_text(
            "🎉 Створити івент\n\nОбери тип події:",
            reply_markup=InlineKeyboardMarkup(rows)
        )

    elif action == "events":
        ev_list = _events.get(chat_id, [])
        if not ev_list:
            await q.message.reply_text("📭 Немає активних івентів.\n\nЗапропонуй через кнопку вище!")
        else:
            await q.message.reply_text(f"📋 Активні івенти ({len(ev_list)}):")
            for ev in ev_list:
                await q.message.reply_text(event_text(ev), parse_mode="Markdown", reply_markup=event_kb(ev))

    elif action == "gather":
        tags = storage.load_tags()
        if not tags:
            await q.message.reply_text("😔 Список порожній. Бот запам'ятовує людей коли вони пишуть у групі.")
            return
        with_username = []
        without_username = []
        for uid, u in tags.items():
            if u.get("username"):
                uname = u["username"]
                with_username.append(f"@{uname}")
            else:
                without_username.append(u["name"])
        all_mentions = with_username + without_username
        text = "📢 Збір! 👋\n\n" + " ".join(all_mentions) + "\n\nПовідомлення видалиться через 1 хвилину 🗑"
        sent = await q.message.reply_text(text)
        async def delete_it(ctx):
            try:
                await ctx.bot.delete_message(chat_id, sent.message_id)
            except Exception:
                pass
        context.job_queue.run_once(delete_it, when=60)

    elif action == "weather":
        msg = await q.message.reply_text("⏳ Отримую погоду...")
        data = await fetch_weather()
        if data:
            await msg.edit_text(build_weather_text(data), parse_mode="Markdown")
        else:
            await msg.edit_text("😔 Не вдалось отримати погоду.")

    elif action == "question":
        await q.message.reply_text(f"❓ {random.choice(RANDOM_QUESTIONS)}")

    elif action == "topic":
        await q.message.reply_text(random.choice(DISCUSSION_TOPICS), parse_mode="Markdown")

    elif action == "challenge":
        chat_id2 = q.message.chat_id
        challenge = random.choice(WEEKLY_CHALLENGES)
        now2 = datetime.now(KYIV_TZ)
        week2 = now2.strftime("%Y-W%U")
        _challenges[chat_id2] = {"text": challenge, "week": week2, "accepted": [], "done": [], "skip": []}
        kb2 = InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ Приймаю виклик!", callback_data="challenge_accept"),
            InlineKeyboardButton("😅 Пропускаю", callback_data="challenge_skip"),
        ]])
        await q.message.reply_text(f"💪 {challenge}\n\nХто в грі?", reply_markup=kb2)

    elif action == "challengestats":
        chat_id2 = q.message.chat_id
        ch2 = _challenges.get(chat_id2)
        if not ch2:
            await q.message.reply_text("📭 Активного виклику немає.\n\nЗапусти новий через кнопку Виклик тижня!")
            return
        now2 = datetime.now(KYIV_TZ)
        week_label2 = f"Тиждень {now2.strftime('%d.%m')}"
        accepted2 = ch2.get("accepted", [])
        done2     = ch2.get("done", [])
        skip2     = ch2.get("skip", [])
        lines2 = [f"💪 Виклик тижня ({week_label2})\n", f"_{ch2['text'].replace('Виклик тижня: ', '')}_\n"]
        if done2:
            lines2.append(f"🏆 Виконали: {', '.join(u['name'] for u in done2)}")
        acc_nd = [u for u in accepted2 if u["id"] not in [d["id"] for d in done2]]
        if acc_nd:
            lines2.append(f"⏳ В процесі: {', '.join(u['name'] for u in acc_nd)}")
        if skip2:
            lines2.append(f"😅 Пропустили: {', '.join(u['name'] for u in skip2)}")
        if not accepted2 and not done2 and not skip2:
            lines2.append("🦗 Ніхто ще не відреагував...")
        kb3 = InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ Приймаю!", callback_data="challenge_accept"),
            InlineKeyboardButton("🏆 Виконав!", callback_data="challenge_done"),
        ]])
        await q.message.reply_text("\n".join(lines2), reply_markup=kb3)

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
        await q.message.reply_text("🗑 Всі івенти видалено!")

async def _menu_profiles(q, context):
    profiles = storage.load_profiles()
    if not profiles:
        await q.message.reply_text("📭 Ще ніхто не заповнив анкету.\n\nНапиши: про себе і розкажи про себе")
        return
    chat_id = q.message.chat_id
    # Перевіряємо через Telegram API хто зараз в групі
    filtered = {}
    for uid, p in profiles.items():
        try:
            member = await context.bot.get_chat_member(chat_id, uid)
            if member.status not in ("left", "kicked", "banned"):
                filtered[uid] = p
        except Exception:
            pass  # Не знайдено — пропускаємо
    if not filtered:
        await q.message.reply_text("📭 Ніхто з поточних учасників ще не заповнив анкету.")
        return
    keyboard = []
    for uid, p in filtered.items():
        label = p["tg_name"]
        if p.get("username"):
            label += f" (@{p['username']})"
        keyboard.append([InlineKeyboardButton(label, callback_data=f"showprofile_{uid}")])
    await q.message.reply_text(
        f"📋 Анкети учасників групи: {len(filtered)}\n\nНатисни на ім'я 👇",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def _menu_report(q, context):
    chat_id = q.message.chat_id
    data    = activity.get(chat_id, {})
    tags    = storage.load_tags()
    if not data:
        names = [u["name"] for u in tags.values()] if tags else []
        await q.message.reply_text(
            f"📭 Статистика порожня — ніхто не писав з /autostart.\n\n"
            + (f"👥 Відомі: {', '.join(names)}" if names else "")
        )
        return
    srt    = sorted(data.items(), key=lambda x: x[1]["count"], reverse=True)
    total  = sum(u["count"] for _, u in srt)
    active = [(uid, u) for uid, u in srt if u["count"] > 0]
    lines  = [f"📈 Звіт активності\n(повідомлень: {total})\n"]
    for rank, (uid, u) in enumerate(active, 1):
        bl  = min(int(u["count"] / max(active[0][1]["count"],1) * 10), 10)
        pct = round(u["count"]/total*100) if total else 0
        lines.append(f"{medal(rank)} {u['name']} — {u['count']} повід. ({pct}%)\n{'█'*bl+'░'*(10-bl)}")
    active_ids = {uid for uid, _ in active}
    silent = [u for uid, u in tags.items() if int(uid) not in active_ids]
    if silent:
        lines.append("\n👻 Мовчать:")
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
        "✅ Авто-повідомлення увімкнено!\n\n"
        "🌤 08:00 — погода\n"
        "📅 Пн 10:00 — нагадування\n"
        "🎉 Пт 10:00 — плани на вихідні\n"
        "🌙 21:00 — як пройшов день\n"
        "📈 Нд 20:00 — тижневий звіт\n"
        "❓ Кожні ~5 год — питання"
    )


async def member_left(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Видаляє анкету і теги коли учасник виходить з групи."""
    if not update.message.left_chat_member:
        return
    user = update.message.left_chat_member
    if user.is_bot:
        return

    # Видалити анкету
    profiles = storage.load_profiles()
    if user.id in profiles:
        del profiles[user.id]
        storage.save_profiles(profiles)

    # Видалити з тегів
    tags = storage.load_tags()
    if str(user.id) in tags:
        del tags[str(user.id)]
        storage.save_tags(tags)

    # Видалити зі статистики активності
    chat_id = update.effective_chat.id
    if user.id in activity.get(chat_id, {}):
        del activity[chat_id][user.id]

    await update.message.reply_text(
        f"👋 {user.first_name} покинув групу. Видалено з анкет, списку учасників і статистики."
    )






def main():
    import os
    TOKEN = os.environ.get("BOT_TOKEN")
    if not TOKEN:
        raise ValueError("BOT_TOKEN не встановлено!")

    app = Application.builder().token(TOKEN).build()

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, track_message), group=0)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_custom_name), group=1)
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome_new_member))
    app.add_handler(MessageHandler(filters.StatusUpdate.LEFT_CHAT_MEMBER, member_left))

    app.add_handler(CallbackQueryHandler(cb_menu,        pattern=r"^menu_"))
    app.add_handler(CallbackQueryHandler(cb_show_profile, pattern=r"^showprofile_\d+$"))
    app.add_handler(CallbackQueryHandler(cb_etype,     pattern=r"^etype_"))
    app.add_handler(CallbackQueryHandler(cb_eday,      pattern=r"^eday_"))
    app.add_handler(CallbackQueryHandler(cb_ev_nodesc, pattern=r"^ev_nodesc_"))
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
