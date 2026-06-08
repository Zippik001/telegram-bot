import logging
import random
import pytz
from collections import defaultdict
from datetime import datetime, time
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    ContextTypes, MessageHandler, filters,
)

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

KYIV_TZ = pytz.timezone("Europe/Kyiv")

# ─────────────────────────────────────────────
# Лічильник активності: { chat_id: { user_id: {"name": ..., "count": ...} } }
# ─────────────────────────────────────────────
activity: dict[int, dict[int, dict]] = defaultdict(dict)

# ─────────────────────────────────────────────
# Дані
# ─────────────────────────────────────────────

RANDOM_QUESTIONS = [
    "☕ Кава чи чай? І чому кава, якщо ви все одно вибрали чай?",
    "🌙 Ви «сова» чи «жайворон»? А може ви просто «кажан» і живете вночі?",
    "🏝 Якби вам зараз подарували тиждень відпустки — куди б ви поїхали?",
    "🎮 Яка настільна гра у вас асоціюється з найкращим вечором?",
    "🍕 Ананас на піці: злочин чи смілива кулінарна ідея?",
    "🐾 Якби ви були твариною — якою і чому?",
    "📚 Остання книга/серіал що вас захопив? Рекомендуєте?",
    "🌳 Похід у ліс або вечір у кафе — що обираєте цими вихідними?",
    "🎵 Яку пісню ви слухаєте на repeat прямо зараз?",
    "🔮 Якби могли отримати одну суперздібність — яку б обрали?",
    "🏕 Намет у горах чи хостел у місті — що ваш стиль подорожі?",
    "😂 Розкажіть один факт про себе, який всіх здивує?",
    "🍦 Яка ваша секретна харчова слабкість?",
    "⏰ Якби можна було повернутися в будь-який час — куди б ви пішли?",
    "🎯 Який один скіл хотіли б опанувати цього року?",
    "🌈 Що вас сьогодні порадувало, навіть якщо це дрібниця?",
    "🧩 Ви більше «плануєте все заздалегідь» чи «живете моментом»?",
    "🚀 Якби могли спробувати будь-яку професію на один день — яку?",
    "🎭 Який фільм або серіал ви могли б дивитися нескінченно?",
    "🌙 Що ви робите коли не можете заснути?",
]

DISCUSSION_TOPICS = [
    "🗣 Тема для обговорення: *Ідеальний вихідний день* — як він виглядає у вас?",
    "🗣 Тема: *Найкраще місце для зустрічі компанії* — кафе, парк, чиясь квартира чи ще щось?",
    "🗣 Тема: *Настільні ігри* — ваш топ-3? Або чому ви їх досі не спробували?",
    "🗣 Тема: *Походи та активний відпочинок* — хто за, хто проти, і чому?",
    "🗣 Тема: *Як познайомитися з новими людьми* — що спрацювало особисто у вас?",
    "🗣 Тема: *Кіно/серіал разом* — чи хтось хотів би організувати перегляд?",
    "🗣 Тема: *Місцеві скарби* — яке місце у нашому місті варто відвідати всій компанією?",
    "🗣 Тема: *Що вас заряджає енергією* після важкого тижня?",
]

ACTIVITY_POLL_OPTIONS = {
    "weekend": {
        "question": "🗓 Що плануєте на ці вихідні?",
        "options": ["Настільні ігри 🎲", "Похід/прогулянка 🥾", "Кафе/ресторан ☕", "Кіно/серіали 🎬", "Нічого конкретного 😴", "Щось інше (пишіть в чат!)"],
        "multiple": True,
    },
    "boardgames": {
        "question": "🎲 Хто готовий зіграти в настільні ігри найближчим часом?",
        "options": ["Так, цього тижня! 🙌", "Так, наступного тижня", "Можливо, залежить від часу", "Поки не можу 😔"],
        "multiple": False,
    },
    "hike": {
        "question": "🥾 Хто хотів би сходити в похід?",
        "options": ["Я в! 💪", "Залежить від маршруту", "Залежить від дати", "Не моє, але бажаю удачі 😄"],
        "multiple": False,
    },
    "cafe": {
        "question": "☕ Хто за зустріч у кафе?",
        "options": ["Я! ☕", "Можливо", "Цього разу не зможу"],
        "multiple": False,
    },
    "howwasday": {
        "question": "🌙 Як пройшов ваш день?",
        "options": ["🔥 Відмінно!", "😊 Добре", "😐 Нормально", "😔 Важкувато", "🤦 Краще не питай"],
        "multiple": False,
    },
    "monday": {
        "question": "📅 Куди збираємось компанією цього тижня?",
        "options": ["Настільні ігри 🎲", "Похід/прогулянка 🥾", "Кафе/бар ☕", "Кіно 🎬", "Квест або інша активність 🎯", "Онлайн-вечір 💻", "Поки нікуди 😴"],
        "multiple": True,
    },
}

# ─────────────────────────────────────────────
# Допоміжні функції
# ─────────────────────────────────────────────

async def send_poll(bot, chat_id, key):
    data = ACTIVITY_POLL_OPTIONS[key]
    await bot.send_poll(
        chat_id=chat_id,
        question=data["question"],
        options=data["options"],
        is_anonymous=False,
        allows_multiple_answers=data["multiple"],
    )

def medal(rank: int) -> str:
    return {1: "🥇", 2: "🥈", 3: "🥉"}.get(rank, "▪️")

# ─────────────────────────────────────────────
# Трекінг повідомлень
# ─────────────────────────────────────────────

async def track_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Рахує кожне повідомлення кожного учасника."""
    user = update.effective_user
    chat_id = update.effective_chat.id
    if not user or user.is_bot:
        return

    if user.id not in activity[chat_id]:
        activity[chat_id][user.id] = {"name": user.first_name, "username": user.username, "count": 0}

    # Оновити ім'я на випадок зміни
    activity[chat_id][user.id]["name"] = user.first_name
    activity[chat_id][user.id]["username"] = user.username
    activity[chat_id][user.id]["count"] += 1

# ─────────────────────────────────────────────
# Команди
# ─────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "👋 *Привіт! Я ваш груповий бот-організатор!*\n\n"
        "Ось що я вмію:\n"
        "📊 /poll — опитування про вихідні\n"
        "🎲 /boardgames — настільні ігри\n"
        "🥾 /hike — похід\n"
        "☕ /cafe — зустріч у кафе\n"
        "🌙 /howwasday — як пройшов день\n"
        "📅 /weekplan — куди йдемо цього тижня\n"
        "💡 /organize — оголосити свою ідею заходу\n"
        "❓ /question — рандомне цікаве питання\n"
        "💬 /topic — почати обговорення теми\n"
        "📈 /report — звіт активності учасників\n"
        "🔄 /resetstats — скинути статистику\n"
        "🤖 /autostart — увімкнути автоматичні повідомлення\n"
        "ℹ️ /help — показати цю довідку\n\n"
        "Рандомні питання — тільки з 7:00 до 22:00 🌤"
    )
    await update.message.reply_text(text, parse_mode="Markdown")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start(update, context)

async def poll_weekend(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_poll(context.bot, update.effective_chat.id, "weekend")

async def poll_boardgames(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_poll(context.bot, update.effective_chat.id, "boardgames")

async def poll_hike(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_poll(context.bot, update.effective_chat.id, "hike")

async def poll_cafe(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_poll(context.bot, update.effective_chat.id, "cafe")

async def poll_howwasday(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_poll(context.bot, update.effective_chat.id, "howwasday")

async def poll_weekplan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_poll(context.bot, update.effective_chat.id, "monday")


async def activity_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Звіт активності + тег мовчунів."""
    chat_id = update.effective_chat.id
    chat_data = activity.get(chat_id, {})

    if not chat_data:
        await update.message.reply_text(
            "📭 Статистика поки порожня — ніхто ще нічого не писав з моменту запуску /autostart."
        )
        return

    sorted_users = sorted(chat_data.items(), key=lambda x: x[1]["count"], reverse=True)
    total = sum(u["count"] for _, u in sorted_users)

    # Активні (хоч одне повідомлення) і мовчуни (0)
    active = [(uid, u) for uid, u in sorted_users if u["count"] > 0]
    silent = [(uid, u) for uid, u in sorted_users if u["count"] == 0]

    lines = [f"📈 *Звіт активності групи*\n_(всього повідомлень: {total})_\n"]

    for rank, (uid, u) in enumerate(active, 1):
        bar_len = min(int(u["count"] / max(active[0][1]["count"], 1) * 10), 10)
        bar = "█" * bar_len + "░" * (10 - bar_len)
        pct = round(u["count"] / total * 100) if total else 0
        lines.append(f"{medal(rank)} *{u['name']}* — {u['count']} повід. ({pct}%)\n`{bar}`")

    text = "\n".join(lines)

    # Тегаємо мовчунів окремим повідомленням
    if silent:
        mentions = []
        for uid, u in silent:
            if u.get("username"):
                mentions.append(f"@{u['username']}")
            else:
                mentions.append(f"[{u['name']}](tg://user?id={uid})")

        silent_text = (
            "👻 *Хто там мовчить?*\n\n"
            + " ".join(mentions)
            + "\n\nАу, ви живі? 😄 Як у вас справи? Що нового? Ми по вас скучили! 💙"
        )
        await update.message.reply_text(text, parse_mode="Markdown")
        await update.message.reply_text(silent_text, parse_mode="Markdown")
    else:
        text += "\n\n🎉 Всі активні — молодці!"
        await update.message.reply_text(text, parse_mode="Markdown")


async def reset_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Скинути статистику для цього чату."""
    chat_id = update.effective_chat.id
    activity[chat_id] = {}
    await update.message.reply_text("🔄 Статистика скинута! Рахуємо з нуля.")


async def organize(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if not args:
        await update.message.reply_text(
            "✏️ Напишіть що хочете організувати після команди.\n"
            "Приклад: `/organize Похід на Говерлу 15 червня! Хто з нами?`",
            parse_mode="Markdown"
        )
        return

    idea = " ".join(args)
    organizer = update.effective_user.first_name
    keyboard = [[
        InlineKeyboardButton("✅ Я в!", callback_data="org_yes"),
        InlineKeyboardButton("🤔 Може бути", callback_data="org_maybe"),
        InlineKeyboardButton("❌ Не зможу", callback_data="org_no"),
    ]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    text = f"📣 *{organizer} пропонує:*\n\n_{idea}_\n\nХто йде?"
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=reply_markup)


async def organize_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user.first_name
    responses = {
        "org_yes": f"✅ {user} іде!",
        "org_maybe": f"🤔 {user} може бути",
        "org_no": f"❌ {user} не зможе"
    }
    response = responses.get(query.data, "")
    if response:
        await query.message.reply_text(response)


async def random_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"❓ {random.choice(RANDOM_QUESTIONS)}")

async def discussion_topic(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(random.choice(DISCUSSION_TOPICS), parse_mode="Markdown")


# ─────────────────────────────────────────────
# Автоматичні повідомлення
# ─────────────────────────────────────────────

async def scheduled_random_message(context: ContextTypes.DEFAULT_TYPE):
    now_kyiv = datetime.now(KYIV_TZ)
    if now_kyiv.hour < 7 or now_kyiv.hour >= 22:
        return
    chat_id = context.job.data["chat_id"]
    if random.random() < 0.5:
        text = f"❓ {random.choice(RANDOM_QUESTIONS)}"
    else:
        text = random.choice(DISCUSSION_TOPICS)
    await context.bot.send_message(chat_id=chat_id, text=text, parse_mode="Markdown")

async def scheduled_weekend_poll(context: ContextTypes.DEFAULT_TYPE):
    await send_poll(context.bot, context.job.data["chat_id"], "weekend")

async def scheduled_howwasday_poll(context: ContextTypes.DEFAULT_TYPE):
    await send_poll(context.bot, context.job.data["chat_id"], "howwasday")

async def scheduled_monday_poll(context: ContextTypes.DEFAULT_TYPE):
    await send_poll(context.bot, context.job.data["chat_id"], "monday")

async def scheduled_weekly_report(context: ContextTypes.DEFAULT_TYPE):
    """Неділя 20:00 — автоматичний звіт активності."""
    chat_id = context.job.data["chat_id"]
    chat_data = activity.get(chat_id, {})

    if not chat_data:
        return

    sorted_users = sorted(chat_data.items(), key=lambda x: x[1]["count"], reverse=True)
    total = sum(u["count"] for _, u in sorted_users)
    active = [(uid, u) for uid, u in sorted_users if u["count"] > 0]
    silent = [(uid, u) for uid, u in sorted_users if u["count"] == 0]

    lines = [f"📈 *Тижневий звіт активності*\n_(всього повідомлень: {total})_\n"]
    for rank, (uid, u) in enumerate(active, 1):
        bar_len = min(int(u["count"] / max(active[0][1]["count"], 1) * 10), 10) if active else 0
        bar = "█" * bar_len + "░" * (10 - bar_len)
        pct = round(u["count"] / total * 100) if total else 0
        lines.append(f"{medal(rank)} *{u['name']}* — {u['count']} повід. ({pct}%)\n`{bar}`")

    await context.bot.send_message(chat_id=chat_id, text="\n".join(lines), parse_mode="Markdown")

    if silent:
        mentions = []
        for uid, u in silent:
            if u.get("username"):
                mentions.append(f"@{u['username']}")
            else:
                mentions.append(f"[{u['name']}](tg://user?id={uid})")
        silent_text = (
            "👻 *Хто там мовчить цього тижня?*\n\n"
            + " ".join(mentions)
            + "\n\nАу, ви живі? 😄 Як справи? Ми по вас скучили! 💙"
        )
        await context.bot.send_message(chat_id=chat_id, text=silent_text, parse_mode="Markdown")

    # Скидаємо лічильники після тижневого звіту
    for uid in activity[chat_id]:
        activity[chat_id][uid]["count"] = 0


async def setup_jobs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    job_queue = context.job_queue

    job_names = [str(chat_id), f"{chat_id}_friday", f"{chat_id}_evening",
                 f"{chat_id}_monday", f"{chat_id}_report"]
    for name in job_names:
        for job in job_queue.get_jobs_by_name(name):
            job.schedule_removal()

    job_queue.run_repeating(
        scheduled_random_message,
        interval=5 * 3600,
        first=60,
        data={"chat_id": chat_id},
        name=str(chat_id)
    )
    job_queue.run_daily(
        scheduled_weekend_poll,
        time=time(10, 0, tzinfo=KYIV_TZ),
        days=(4,),
        data={"chat_id": chat_id},
        name=f"{chat_id}_friday"
    )
    job_queue.run_daily(
        scheduled_howwasday_poll,
        time=time(21, 0, tzinfo=KYIV_TZ),
        days=(0, 1, 2, 3, 4, 5, 6),
        data={"chat_id": chat_id},
        name=f"{chat_id}_evening"
    )
    job_queue.run_daily(
        scheduled_monday_poll,
        time=time(10, 0, tzinfo=KYIV_TZ),
        days=(0,),
        data={"chat_id": chat_id},
        name=f"{chat_id}_monday"
    )
    job_queue.run_daily(
        scheduled_weekly_report,
        time=time(20, 0, tzinfo=KYIV_TZ),
        days=(6,),  # неділя
        data={"chat_id": chat_id},
        name=f"{chat_id}_report"
    )

    await update.message.reply_text(
        "✅ *Автоматичні повідомлення увімкнено!*\n\n"
        "🌤 Рандомні питання — кожні ~5 год (7:00–22:00)\n"
        "📅 Понеділок 10:00 — куди йдемо цього тижня?\n"
        "🗓 П'ятниця 10:00 — плани на вихідні\n"
        "🌙 Щодня 21:00 — як пройшов день\n"
        "📈 Неділя 20:00 — тижневий звіт активності\n\n"
        "Статистику повідомлень рахую з цього моменту 📊",
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

    # Трекер повідомлень — має бути першим
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, track_message), group=0)

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("poll", poll_weekend))
    app.add_handler(CommandHandler("boardgames", poll_boardgames))
    app.add_handler(CommandHandler("hike", poll_hike))
    app.add_handler(CommandHandler("cafe", poll_cafe))
    app.add_handler(CommandHandler("howwasday", poll_howwasday))
    app.add_handler(CommandHandler("weekplan", poll_weekplan))
    app.add_handler(CommandHandler("organize", organize))
    app.add_handler(CommandHandler("question", random_question))
    app.add_handler(CommandHandler("topic", discussion_topic))
    app.add_handler(CommandHandler("report", activity_report))
    app.add_handler(CommandHandler("resetstats", reset_stats))
    app.add_handler(CommandHandler("autostart", setup_jobs))
    app.add_handler(CallbackQueryHandler(organize_callback, pattern="^org_"))

    logger.info("Бот запущено!")
    app.run_polling()


if __name__ == "__main__":
    main()
